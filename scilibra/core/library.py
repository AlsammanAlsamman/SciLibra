"""High-level library operations used by the GUI (and usable from scripts)."""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field

from . import bibtex, crossref, pdf
from .database import Database
from .models import Article

log = logging.getLogger(__name__)

# Fields the library can be grouped by: label -> sub table
GROUP_FIELDS = {
    "Keywords": "keywords",
    "Tag groups": "taggroups",
    "Authors": "author",
    "Year": "year",
    "Journal": "journal",
}
# Fields that can be searched: label -> column / sub table
SEARCH_FIELDS = {
    "Title": "title",
    "Authors": "author",
    "Abstract": "abstract",
    "Keywords": "keywords",
    "Tag groups": "taggroups",
    "Journal": "journal",
    "Year": "year",
    "Comments": "comment",
    "Key": "ID",
    "DOI": "doi",
}


@dataclass
class ImportReport:
    added: list[str] = field(default_factory=list)
    updated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # already in the library
    failed: list[str] = field(default_factory=list)   # could not be parsed / fetched
    notes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = [f"{len(self.added)} added"]
        if self.updated:
            parts.append(f"{len(self.updated)} updated")
        if self.skipped:
            parts.append(f"{len(self.skipped)} already in library")
        if self.failed:
            parts.append(f"{len(self.failed)} failed")
        return ", ".join(parts)


@dataclass
class SearchResult:
    keys: list[str]
    hits: dict[str, dict[str, int]]  # term -> field label -> number of articles


def normalize_title(title: str) -> str:
    text = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def _looks_like_key(stem: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_:\-.]{3,60}", stem))


class Library:
    def __init__(self, path: str):
        self.db = Database(path)
        self.path = self.db.path

    def close(self):
        self.db.close()

    # ------------------------------------------------------------------ settings stored in the library
    @property
    def thumbnails_enabled(self) -> bool:
        return (self.db.get_property("firstpageimage") or "yes") == "yes"

    @thumbnails_enabled.setter
    def thumbnails_enabled(self, value: bool):
        self.db.set_property("firstpageimage", "yes" if value else "no")

    @property
    def default_group(self) -> str:
        table = self.db.get_property("clusteringcategory") or "keywords"
        return table if table in GROUP_FIELDS.values() else "keywords"

    @default_group.setter
    def default_group(self, table: str):
        self.db.set_property("clusteringcategory", table)

    # ------------------------------------------------------------------ reading
    def count(self) -> int:
        return self.db.count()

    def get(self, key: str) -> Article | None:
        return self.db.get(key)

    def articles(self, keys=None, sort=True) -> list[Article]:
        items = self.db.load(keys)
        if sort and keys is None:
            items.sort(key=lambda a: a.title.lower())
        return items

    def thumbnail(self, key: str, create: bool = True) -> bytes | None:
        """PNG preview of the first page. Created (and stored) on demand when the PDF is available."""
        data = self.db.get_thumbnail(key)
        if data and bytes(data[:4]) != b"\x89PNG":
            data = pdf.image_to_png(bytes(data))
            self.db.set_thumbnail(key, data)
        if data is None and create and self.thumbnails_enabled:
            article = self.db.get(key)
            if article is not None and article.has_pdf:
                data = pdf.first_page_thumbnail(article.pdf_path)
                if data:
                    self.db.set_thumbnail(key, data)
        return data

    def unique_key(self, base: str) -> str:
        base = bibtex.safe_key(base)
        if not self.db.exists(base):
            return base
        for suffix in "abcdefghijklmnopqrstuvwxyz":
            if not self.db.exists(base + suffix):
                return base + suffix
        n = 2
        while self.db.exists(f"{base}_{n}"):
            n += 1
        return f"{base}_{n}"

    # ------------------------------------------------------------------ writing
    def _refresh_thumbnail(self, article: Article):
        if not self.thumbnails_enabled:
            return
        data = pdf.first_page_thumbnail(article.pdf_path) if article.has_pdf else None
        if data:
            self.db.set_thumbnail(article.key, data)

    def add(self, article: Article, overwrite: bool = False) -> bool:
        """Add an article. Returns False if the key exists and overwrite is False."""
        article.key = bibtex.safe_key(article.key)
        if self.db.exists(article.key):
            if not overwrite:
                return False
            old = self.db.get(article.key)
            article.date_added = old.date_added
            if not article.comments:
                article.comments = old.comments
        self.db.save(article)
        self._refresh_thumbnail(article)
        return True

    def update(self, article: Article, old_key: str | None = None):
        """Save edits to an article, renaming it if its key changed."""
        article.key = bibtex.safe_key(article.key)
        old_key = old_key or article.key
        previous = self.db.get(old_key)
        if old_key != article.key:
            if self.db.exists(article.key):
                raise ValueError(f"An article with key '{article.key}' already exists")
            self.db.rename(old_key, article.key)
        if previous and not article.date_added:
            article.date_added = previous.date_added
        self.db.save(article)
        if previous is None or previous.pdf_path != article.pdf_path or self.db.get_thumbnail(article.key) is None:
            if article.has_pdf:
                self._refresh_thumbnail(article)
            elif previous is not None and previous.pdf_path != article.pdf_path:
                self.db.set_thumbnail(article.key, None)

    def delete(self, keys):
        self.db.delete(keys)

    def delete_all(self):
        self.db.delete(self.db.keys())

    def add_comment(self, key: str, text: str) -> bool:
        text = " ".join(text.split())
        article = self.db.get(key)
        if article is None or not text or text in article.comments:
            return False
        article.comments.append(text)
        self.db.save(article)
        return True

    def remove_comment(self, key: str, text: str) -> bool:
        article = self.db.get(key)
        if article is None or text not in article.comments:
            return False
        article.comments.remove(text)
        self.db.save(article)
        return True

    # ------------------------------------------------------------------ import
    def import_bibtex(self, text: str, pdf_folder: str = "", overwrite: bool = False) -> ImportReport:
        """Import BibTeX text. PDFs named <key>.pdf in `pdf_folder` are linked automatically."""
        parsed = bibtex.parse_bibtex(text)
        report = ImportReport(failed=list(parsed.failed))
        for article in parsed.articles:
            if not article.folderpath and pdf_folder and os.path.isfile(os.path.join(pdf_folder, article.key + ".pdf")):
                article.folderpath = pdf_folder
            existed = self.db.exists(bibtex.safe_key(article.key))
            if self.add(article, overwrite=overwrite):
                (report.updated if existed else report.added).append(article.key)
            else:
                report.skipped.append(article.key)
        if not parsed.articles and not parsed.failed:
            report.notes.append("No BibTeX entries were found.")
        return report

    def import_bibtex_file(self, path: str, overwrite: bool = False) -> ImportReport:
        with open(path, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
        return self.import_bibtex(text, pdf_folder=os.path.dirname(os.path.abspath(path)), overwrite=overwrite)

    def article_from_pdf(self, pdf_path: str, online: bool = True, session=None) -> tuple[Article, str]:
        """Build an Article for a PDF (via its DOI on Crossref when possible). Does not save it.

        Returns (article, note) where note explains how the metadata was obtained.
        """
        pdf_path = os.path.abspath(pdf_path)
        info = pdf.extract_info(pdf_path)
        stem = os.path.splitext(os.path.basename(pdf_path))[0]
        article, note = None, ""
        if info["doi"] and online:
            try:
                article = crossref.fetch_article(info["doi"], session=session)
                note = f"metadata from Crossref (DOI {info['doi']})"
            except crossref.CrossrefError as exc:
                note = str(exc)
        elif not info["doi"]:
            note = "no DOI found in the PDF"
        else:
            note = "offline - DOI lookup skipped"
        if article is None:
            article = Article(key="", title=info["title"] or pdf.title_from_filename(pdf_path),
                              authors=[a.strip() for a in re.split(r"[;,]| and ", info["author"]) if a.strip()],
                              year=info["year"], doi=info["doi"],
                              url=f"https://doi.org/{info['doi']}" if info["doi"] else "")
            note = "basic metadata from the PDF file (" + note + ")"
        if _looks_like_key(stem):
            article.key = stem
        elif article.authors and article.year:
            article.key = crossref.make_key(article)
        else:
            article.key = bibtex.safe_key(stem)
        article.folderpath, article.pdffile = os.path.split(pdf_path)
        if article.pdffile == article.key + ".pdf":
            article.pdffile = ""
        return article, note

    def add_pdf_article(self, article: Article) -> str:
        """Save an Article built by `article_from_pdf`, choosing a free key. Returns the key used."""
        for existing in self.db.load():
            if existing.pdf_path and os.path.abspath(existing.pdf_path) == os.path.abspath(article.pdf_path):
                return ""  # this PDF is already in the library
            if article.doi and existing.doi.lower() == article.doi.lower():
                return ""
        article.key = self.unique_key(article.key)
        self.add(article)
        return article.key

    # ------------------------------------------------------------------ PDFs
    def set_pdf(self, key: str, pdf_path: str):
        article = self.db.get(key)
        if article is None:
            raise KeyError(key)
        folder, name = os.path.split(os.path.abspath(pdf_path))
        article.folderpath = folder
        article.pdffile = "" if name == key + ".pdf" else name
        self.db.save(article)
        self.db.set_thumbnail(key, None)
        self._refresh_thumbnail(article)

    def link_pdf_folders(self, folders, recursive: bool = True) -> tuple[list[str], list[str]]:
        """Link PDFs named <key>.pdf found in `folders` to their articles.

        Returns (linked keys, PDF paths that matched no article).
        """
        pdfs = {}
        for folder in folders:
            if not folder or not os.path.isdir(folder):
                continue
            walker = os.walk(folder) if recursive else [(folder, [], os.listdir(folder))]
            for root, _dirs, files in walker:
                for name in files:
                    if name.lower().endswith(".pdf"):
                        pdfs.setdefault(os.path.splitext(name)[0], os.path.join(root, name))
        linked = []
        by_key = {a.key: a for a in self.db.load()}
        for stem, path in sorted(pdfs.items()):
            article = by_key.get(stem)
            if article is None:
                continue
            if article.has_pdf and os.path.abspath(article.pdf_path) == os.path.abspath(path):
                if self.db.get_thumbnail(article.key) is None:
                    self._refresh_thumbnail(article)
                continue
            self.set_pdf(article.key, path)
            linked.append(article.key)
        unmatched = [p for s, p in sorted(pdfs.items()) if s not in by_key]
        return linked, unmatched

    def missing_pdfs(self) -> list[Article]:
        return [a for a in self.articles() if not a.has_pdf]

    def refresh_thumbnails(self, force: bool = False, progress=None) -> int:
        have = self.db.thumbnail_keys()
        todo = [a for a in self.articles() if a.has_pdf and (force or a.key not in have)]
        made = 0
        for i, article in enumerate(todo):
            data = pdf.first_page_thumbnail(article.pdf_path)
            if data:
                self.db.set_thumbnail(article.key, data)
                made += 1
            if progress:
                progress(i + 1, len(todo))
        return made

    # ------------------------------------------------------------------ browse & search
    def groups(self, table: str) -> list[tuple[str, int]]:
        return self.db.group_counts(table)

    def keys_in_group(self, table: str, value: str) -> list[str]:
        return self.db.keys_for_value(table, value)

    def distinct_values(self, table: str) -> list[str]:
        return self.db.distinct_values(table)

    def search(self, query: str, fields=None, match_all: bool = False) -> SearchResult:
        """Search `fields` (labels from SEARCH_FIELDS; default all) for each term in `query`.

        Terms are separated by `|||` or `;`. With match_all, an article must match every term.
        """
        labels = list(fields or SEARCH_FIELDS)
        terms = [t.strip() for t in re.split(r"\|\|\||;", query) if t.strip()]
        hits, per_term = {}, []
        for term in terms:
            found = set()
            hits[term] = {}
            for label in labels:
                keys = self.db.search_column(SEARCH_FIELDS[label], term)
                if keys:
                    hits[term][label] = len(keys)
                    found.update(keys)
            per_term.append(found)
        if not per_term:
            keys = set()
        elif match_all:
            keys = set.intersection(*per_term)
        else:
            keys = set.union(*per_term)
        ordered = [a.key for a in sorted(self.db.load(keys), key=lambda a: a.title.lower())]
        return SearchResult(keys=ordered, hits=hits)

    # ------------------------------------------------------------------ maintenance
    def find_duplicates(self) -> list[list[Article]]:
        """Groups of articles that share a DOI or a (normalised) title."""
        articles = self.articles()
        parent = {a.key: a.key for a in articles}

        def find(k):
            while parent[k] != k:
                parent[k] = parent[parent[k]]
                k = parent[k]
            return k

        for attr in ("doi", "title"):
            seen = {}
            for a in articles:
                value = a.doi.lower() if attr == "doi" else normalize_title(a.title)
                if not value or (attr == "title" and len(value) < 10):
                    continue
                if value in seen:
                    parent[find(a.key)] = find(seen[value])
                else:
                    seen[value] = a.key
        groups = {}
        for a in articles:
            groups.setdefault(find(a.key), []).append(a)
        result = [g for g in groups.values() if len(g) > 1]
        for g in result:
            g.sort(key=lambda a: a.date_added or "9999")  # oldest first among equals (stable sort)
            g.sort(key=self._keep_score, reverse=True)
        return result

    @staticmethod
    def _keep_score(a: Article):
        """Prefer keeping the copy with a PDF, more comments and more metadata."""
        filled = sum(bool(getattr(a, f)) for f in ("abstract", "doi", "journal", "keywords", "taggroups", "year"))
        return (a.has_pdf, len(a.comments), filled)

    def remove_duplicates(self, groups=None) -> list[str]:
        """Delete all but the best article of each duplicate group; merges comments/tags into it."""
        groups = self.find_duplicates() if groups is None else groups
        removed = []
        for group in groups:
            keep, *others = group
            for other in others:
                for attr in ("comments", "keywords", "taggroups"):
                    merged = getattr(keep, attr) + [v for v in getattr(other, attr) if v not in getattr(keep, attr)]
                    setattr(keep, attr, merged)
                removed.append(other.key)
            self.db.save(keep)
            self.db.delete([o.key for o in others])
        return removed

    def statistics(self) -> dict:
        articles = self.articles()
        years = Counter(a.year for a in articles if a.year)
        return {
            "Articles": len(articles),
            "With PDF": sum(a.has_pdf for a in articles),
            "Without PDF": sum(not a.has_pdf for a in articles),
            "With thumbnail": len(self.db.thumbnail_keys()),
            "With abstract": sum(bool(a.abstract) for a in articles),
            "With comments": sum(bool(a.comments) for a in articles),
            "Distinct authors": len(self.groups("author")),
            "Distinct journals": len(self.groups("journal")),
            "Distinct keywords": len(self.groups("keywords")),
            "Distinct tag groups": len(self.groups("taggroups")),
            "Year range": f"{min(years)} - {max(years)}" if years else "-",
            "Most common year": f"{years.most_common(1)[0][0]} ({years.most_common(1)[0][1]})" if years else "-",
            "Created": (self.db.get_property("creationdate") or "")[:19],
            "Last modified": (self.db.get_property("lastmodificationdate") or "")[:19],
        }

    def export_bibtex(self, path: str, keys=None, include_local: bool = True) -> int:
        articles = self.articles(keys) if keys is not None else self.articles()
        text = bibtex.articles_to_bibtex(articles, include_local=include_local)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        return len(articles)
