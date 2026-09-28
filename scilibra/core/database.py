"""SQLite storage for the library.

The schema is compatible with libraries created by SciLibra 1.x:

* ``articles`` - one row per article (flat text columns)
* ``author``, ``keywords``, ``taggroups``, ``comment``, ``title``, ``year``, ``journal`` -
  ``(ID, articleData)`` tables used for grouping; multi-valued fields have one row per value
* ``firstpageimages`` - ``(ID, articleData blob)`` first-page thumbnails
* ``libraryproperties`` - ``(property, value)`` settings stored with the library
"""

from __future__ import annotations

import datetime
import logging
import os
import shutil
import sqlite3
import threading
from contextlib import contextmanager

from .models import Article, clean_text, split_authors, split_terms

log = logging.getLogger(__name__)

SCHEMA_VERSION = 2

# articles table columns (1.x columns first, then columns added in schema 2)
ARTICLE_COLUMNS = ["ID", "title", "author", "year", "journal", "taggroups", "url", "folderpath",
                   "keywords", "abstract", "ENTRYTYPE", "pages", "volume", "number", "publisher",
                   "doi", "pdffile", "dateadded"]

# Article attribute -> articles column
_ATTR_TO_COLUMN = {
    "key": "ID", "title": "title", "year": "year", "journal": "journal", "url": "url",
    "folderpath": "folderpath", "abstract": "abstract", "entry_type": "ENTRYTYPE", "pages": "pages",
    "volume": "volume", "number": "number", "publisher": "publisher", "doi": "doi",
    "pdffile": "pdffile", "date_added": "dateadded",
}
# Multi-valued attribute -> sub table
LIST_TABLES = {"authors": "author", "keywords": "keywords", "taggroups": "taggroups", "comments": "comment"}
# Single-valued attribute -> sub table (kept for grouping and 1.x compatibility)
SINGLE_TABLES = {"title": "title", "year": "year", "journal": "journal"}
SUB_TABLES = list(LIST_TABLES.values()) + list(SINGLE_TABLES.values())

DEFAULT_PROPERTIES = {
    "clusteringcategory": "keywords",
    "firstpageimage": "yes",
    "firstpageimageresolution": "30",
}


def now() -> str:
    return datetime.datetime.now().isoformat(sep=" ", timespec="seconds")


class Database:
    """Thread-safe access to one library file."""

    def __init__(self, path: str):
        self.path = os.path.abspath(path)
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute("PRAGMA foreign_keys = OFF")
        self.backup_path: str | None = None
        self._init_schema()

    def close(self):
        with self._lock:
            self._conn.close()

    @contextmanager
    def transaction(self):
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def _query(self, sql, params=()):
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    # ------------------------------------------------------------------ schema
    def _tables(self) -> set[str]:
        return {r[0] for r in self._query("SELECT name FROM sqlite_master WHERE type='table'")}

    def _init_schema(self):
        tables = self._tables()
        if "articles" not in tables:
            self._create_schema()
            return
        version = int(self.get_property("schemaversion") or 1)
        if version < SCHEMA_VERSION:
            self._migrate(version)

    def _create_schema(self):
        with self.transaction() as c:
            c.execute("CREATE TABLE articles (%s)" % ", ".join(f"{col} text" for col in ARTICLE_COLUMNS))
            c.execute("CREATE TABLE libraryproperties (property text, value text)")
            for table in SUB_TABLES:
                c.execute(f"CREATE TABLE {table} (ID text, articleData text)")
            c.execute("CREATE TABLE firstpageimages (ID text, articleData blob)")
            self._create_indexes(c)
            props = dict(DEFAULT_PROPERTIES, creationdate=now(), lastmodificationdate=now(),
                         schemaversion=str(SCHEMA_VERSION))
            c.executemany("INSERT INTO libraryproperties VALUES (?, ?)", props.items())

    @staticmethod
    def _create_indexes(c):
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_articles_id ON articles(ID)")
        for table in SUB_TABLES + ["firstpageimages"]:
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_id ON {table}(ID)")
        for table in SUB_TABLES:
            c.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_data ON {table}(articleData)")

    def _migrate(self, version: int):
        """Upgrade a SciLibra 1.x library. A backup copy is written first."""
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        self.backup_path = f"{self.path}.v{version}-backup-{stamp}"
        with self._lock:
            self._conn.commit()
            shutil.copy2(self.path, self.backup_path)
        log.info("Migrating library %s from schema %s (backup: %s)", self.path, version, self.backup_path)

        with self.transaction() as c:
            existing = {r[1] for r in c.execute("PRAGMA table_info(articles)")}
            for col in ARTICLE_COLUMNS:
                if col not in existing:
                    c.execute(f"ALTER TABLE articles ADD COLUMN {col} text")
            for table in SUB_TABLES:
                c.execute(f"CREATE TABLE IF NOT EXISTS {table} (ID text, articleData text)")
            c.execute("CREATE TABLE IF NOT EXISTS firstpageimages (ID text, articleData blob)")
            c.execute("CREATE TABLE IF NOT EXISTS libraryproperties (property text, value text)")

            # Remove duplicated article rows (keep the first) so the unique index can be created.
            c.execute("DELETE FROM articles WHERE rowid NOT IN (SELECT MIN(rowid) FROM articles GROUP BY ID)")
            c.execute("DELETE FROM firstpageimages WHERE rowid NOT IN "
                      "(SELECT MIN(rowid) FROM firstpageimages GROUP BY ID)")
            c.execute("UPDATE articles SET dateadded = ? WHERE dateadded IS NULL OR dateadded = ''",
                      (self.get_property("creationdate", c) or now(),))

            # Keywords/tag groups/comments were edited in their sub tables in 1.x, so those are the
            # source of truth; tidy them, then re-save every article so the flat columns and all
            # sub tables are rebuilt consistently (this also re-splits authors, which 1.x split
            # on "and " - breaking names such as "Marand").
            for table in ("keywords", "taggroups", "comment"):
                c.execute(f"DELETE FROM {table} WHERE articleData IS NULL OR TRIM(articleData) IN ('', 'None')")
            with self._lock:
                articles = self.load()
            for a in articles:
                if not (a.keywords or a.taggroups):
                    flat = c.execute("SELECT keywords, taggroups FROM articles WHERE ID=?", (a.key,)).fetchone()
                    a.keywords, a.taggroups = split_terms(flat[0] or ""), split_terms(flat[1] or "")
                new_key = clean_text(a.key)
                if new_key != a.key:  # key with stray whitespace
                    for table in ["articles", "firstpageimages"] + SUB_TABLES:
                        c.execute(f"UPDATE {table} SET ID=? WHERE ID=?", (new_key, a.key))
                    a.key = new_key
                self._write_article(c, a)
            # 1.x stored low-resolution GIF previews. Drop them when the PDF is available (a sharper
            # PNG is created on demand) and convert the others to PNG.
            from .pdf import image_to_png
            for a in articles:
                row = c.execute("SELECT articleData FROM firstpageimages WHERE ID=?", (a.key,)).fetchone()
                if not row or not row[0] or bytes(row[0][:4]) == b"\x89PNG":
                    continue
                png = None if a.has_pdf else image_to_png(bytes(row[0]))
                c.execute("DELETE FROM firstpageimages WHERE ID=?", (a.key,))
                if png:
                    c.execute("INSERT INTO firstpageimages VALUES (?, ?)", (a.key, sqlite3.Binary(png)))
            # Rows belonging to articles that no longer exist.
            for table in SUB_TABLES + ["firstpageimages"]:
                c.execute(f"DELETE FROM {table} WHERE ID NOT IN (SELECT ID FROM articles)")

            self._create_indexes(c)
            for prop, value in DEFAULT_PROPERTIES.items():
                if self.get_property(prop, c) is None:
                    self.set_property(prop, value, c)
            self.set_property("schemaversion", str(SCHEMA_VERSION), c)

    # ------------------------------------------------------------------ properties
    def get_property(self, name, conn=None):
        conn = conn or self._conn
        with self._lock:
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if "libraryproperties" not in tables:
                return None
            row = conn.execute("SELECT value FROM libraryproperties WHERE property=?", (name,)).fetchone()
        return row[0] if row else None

    def set_property(self, name, value, conn=None):
        def write(c):
            c.execute("DELETE FROM libraryproperties WHERE property=?", (name,))
            c.execute("INSERT INTO libraryproperties VALUES (?, ?)", (name, str(value)))
        if conn is not None:
            write(conn)
        else:
            with self.transaction() as c:
                write(c)

    def properties(self) -> dict:
        return dict(self._query("SELECT property, value FROM libraryproperties"))

    # ------------------------------------------------------------------ articles
    @staticmethod
    def _write_list(c, table, key, values):
        c.execute(f"DELETE FROM {table} WHERE ID=?", (key,))
        c.executemany(f"INSERT INTO {table} VALUES (?, ?)", [(key, v) for v in values])

    def _write_article(self, c, a: Article):
        a.normalize()
        row = {col: getattr(a, attr) or "" for attr, col in _ATTR_TO_COLUMN.items()}
        row.update(author=a.author_string, keywords=", ".join(a.keywords), taggroups=", ".join(a.taggroups))
        cols = list(row)
        c.execute("DELETE FROM articles WHERE ID=?", (a.key,))
        c.execute("INSERT INTO articles (%s) VALUES (%s)" % (", ".join(cols), ", ".join("?" * len(cols))),
                  [row[k] for k in cols])
        for attr, table in LIST_TABLES.items():
            self._write_list(c, table, a.key, a.grouping_authors if attr == "authors" else getattr(a, attr))
        for attr, table in SINGLE_TABLES.items():
            value = getattr(a, attr)
            self._write_list(c, table, a.key, [value] if value else [])

    def save(self, article: Article):
        """Insert or replace an article."""
        if not article.date_added:
            article.date_added = now()
        with self.transaction() as c:
            self._write_article(c, article)
            self.set_property("lastmodificationdate", now(), c)

    def save_many(self, articles):
        with self.transaction() as c:
            for a in articles:
                if not a.date_added:
                    a.date_added = now()
                self._write_article(c, a)
            self.set_property("lastmodificationdate", now(), c)

    def rename(self, old_key: str, new_key: str):
        with self.transaction() as c:
            for table in ["articles", "firstpageimages"] + SUB_TABLES:
                c.execute(f"UPDATE {table} SET ID=? WHERE ID=?", (new_key, old_key))

    def delete(self, keys):
        keys = list(keys)
        with self.transaction() as c:
            for table in ["articles", "firstpageimages"] + SUB_TABLES:
                c.executemany(f"DELETE FROM {table} WHERE ID=?", [(k,) for k in keys])
            self.set_property("lastmodificationdate", now(), c)

    def exists(self, key: str) -> bool:
        return bool(self._query("SELECT 1 FROM articles WHERE ID=?", (key,)))

    def keys(self) -> list[str]:
        return [r[0] for r in self._query("SELECT ID FROM articles")]

    def count(self) -> int:
        return self._query("SELECT COUNT(*) FROM articles")[0][0]

    def get(self, key: str) -> Article | None:
        found = self.load([key])
        return found[0] if found else None

    def load(self, keys=None) -> list[Article]:
        """Load articles (all, or the given keys) with their multi-valued fields."""
        with self._lock:
            c = self._conn.cursor()
            if keys is None:
                rows = c.execute("SELECT * FROM articles").fetchall()
            else:
                keys = list(dict.fromkeys(keys))
                rows = []
                for i in range(0, len(keys), 500):
                    chunk = keys[i:i + 500]
                    rows += c.execute("SELECT * FROM articles WHERE ID IN (%s)" % ",".join("?" * len(chunk)),
                                      chunk).fetchall()
            cols = [d[0] for d in c.description] if c.description else ARTICLE_COLUMNS
            wanted = {r[cols.index("ID")] for r in rows}
            lists = {attr: {} for attr in LIST_TABLES}
            for attr, table in LIST_TABLES.items():
                if attr == "authors":
                    continue
                for key, value in c.execute(f"SELECT ID, articleData FROM {table} ORDER BY rowid"):
                    if key in wanted and value not in (None, ""):
                        lists[attr].setdefault(key, []).append(value)

        articles = []
        for r in rows:
            data = dict(zip(cols, r))
            a = Article(key=data["ID"])
            for attr, col in _ATTR_TO_COLUMN.items():
                if attr != "key":
                    setattr(a, attr, data.get(col) or "")
            for attr in LIST_TABLES:
                setattr(a, attr, lists[attr].get(a.key, []))
            # The author sub table is only an index for grouping (it omits "others");
            # the full, ordered author list lives in the articles table.
            a.authors = split_authors(data.get("author") or "")
            articles.append(a)
        if keys is not None:
            order = {k: i for i, k in enumerate(keys)}
            articles.sort(key=lambda a: order[a.key])
        return articles

    # ------------------------------------------------------------------ thumbnails
    def get_thumbnail(self, key: str) -> bytes | None:
        row = self._query("SELECT articleData FROM firstpageimages WHERE ID=?", (key,))
        return row[0][0] if row else None

    def set_thumbnail(self, key: str, data: bytes | None):
        with self.transaction() as c:
            c.execute("DELETE FROM firstpageimages WHERE ID=?", (key,))
            if data:
                c.execute("INSERT INTO firstpageimages VALUES (?, ?)", (key, sqlite3.Binary(data)))

    def thumbnail_keys(self) -> set[str]:
        return {r[0] for r in self._query("SELECT ID FROM firstpageimages")}

    # ------------------------------------------------------------------ grouping / search
    def group_counts(self, table: str) -> list[tuple[str, int]]:
        if table not in SUB_TABLES:
            raise ValueError(f"Unknown group field: {table}")
        return self._query(f"SELECT articleData, COUNT(DISTINCT ID) FROM {table} "
                           f"WHERE articleData IS NOT NULL AND articleData != '' "
                           f"GROUP BY articleData ORDER BY COUNT(DISTINCT ID) DESC, articleData COLLATE NOCASE")

    def keys_for_value(self, table: str, value: str) -> list[str]:
        if table not in SUB_TABLES:
            raise ValueError(f"Unknown group field: {table}")
        return [r[0] for r in self._query(f"SELECT DISTINCT ID FROM {table} WHERE articleData=?", (value,))]

    def distinct_values(self, table: str) -> list[str]:
        return [v for v, _ in self.group_counts(table)]

    def search_column(self, column: str, text: str) -> list[str]:
        if column in SUB_TABLES:
            sql = f"SELECT DISTINCT ID FROM {column} WHERE articleData LIKE ? ESCAPE '\\'"
        elif column in ARTICLE_COLUMNS:
            sql = f"SELECT ID FROM articles WHERE {column} LIKE ? ESCAPE '\\'"
        else:
            raise ValueError(f"Unknown search field: {column}")
        escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        return [r[0] for r in self._query(sql, (f"%{escaped}%",))]
