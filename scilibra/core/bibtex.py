"""Reading and writing BibTeX."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field

import bibtexparser
from bibtexparser.bibdatabase import BibDatabase
from bibtexparser.bparser import BibTexParser
from bibtexparser.bwriter import BibTexWriter
from pylatexenc.latex2text import LatexNodes2Text

from .models import Article, split_authors, split_comments, split_terms

log = logging.getLogger(__name__)

# Fields whose values are LaTeX-formatted text that should be converted to plain text.
_LATEX_FIELDS = {"title", "author", "journal", "journaltitle", "booktitle", "abstract",
                 "publisher", "keywords", "taggroups", "series", "institution", "school"}
_NON_ENTRY_TYPES = {"string", "comment", "preamble"}
_ENTRY_START = re.compile(r"@\s*(\w+)\s*[{(]\s*([^,\s]*)\s*,", re.MULTILINE)
_latex = LatexNodes2Text()


@dataclass
class ParseResult:
    articles: list[Article] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)  # keys (or snippets) that could not be parsed


def latex_to_text(value: str) -> str:
    # A bare % starts a LaTeX comment and would swallow the rest of the text ("100% pure").
    value = re.sub(r"(?<!\\)%", r"\\%", value)
    try:
        text = _latex.latex_to_text(value)
    except Exception:  # pylatexenc is strict about malformed input; fall back to stripping braces
        text = value.replace("{", "").replace("}", "")
    return " ".join(text.split())


def _pdf_from_file_field(value: str) -> str:
    """Extract a PDF path from Zotero/Mendeley/JabRef style `file` fields."""
    for part in re.split(r"[;]", value):
        for piece in part.split(":"):
            if piece.lower().endswith(".pdf"):
                # Windows paths ("C\:\\...") are split on ':' - rebuild the drive letter if present
                idx = part.find(piece)
                if idx >= 2 and part[idx - 1] == ":" and len(part[:idx - 1].split(":")[-1]) == 1:
                    piece = part[:idx - 1].split(":")[-1] + ":" + piece
                return piece.replace("\\:", ":").strip()
    return ""


def entry_to_article(entry: dict) -> Article:
    """Convert a bibtexparser entry dict into an Article."""
    e = {k.lower(): (v if isinstance(v, str) else str(v)) for k, v in entry.items()}
    for k in list(e):
        if k in _LATEX_FIELDS:
            e[k] = latex_to_text(e[k])
        elif k not in ("id", "entrytype"):
            e[k] = e[k].strip()

    year = e.get("year", "") or e.get("date", "")
    match = re.search(r"\d{4}", year)
    year = match.group(0) if match else year

    article = Article(
        key=e.get("id", "").strip(),
        entry_type=(e.get("entrytype") or "article").lower(),
        title=e.get("title", ""),
        authors=split_authors(e.get("author", "") or e.get("editor", "")),
        year=year,
        journal=e.get("journal") or e.get("journaltitle") or e.get("booktitle") or "",
        keywords=split_terms(e.get("keywords", "")),
        taggroups=split_terms(e.get("taggroups", "")),
        comments=split_comments(e.get("comment", "")),
        abstract=e.get("abstract", ""),
        url=e.get("url", ""),
        doi=normalize_doi(e.get("doi", "")),
        volume=e.get("volume", ""),
        number=e.get("number", "") or e.get("issue", ""),
        pages=e.get("pages", "").replace("--", "-"),
        publisher=e.get("publisher", ""),
        folderpath=e.get("folderpath", ""),
        pdffile=e.get("pdffile", ""),
    )
    if not article.folderpath and e.get("file"):
        pdf = _pdf_from_file_field(e["file"])
        if pdf:
            article.folderpath, article.pdffile = os.path.split(pdf)
    return article


def normalize_doi(doi: str) -> str:
    doi = (doi or "").strip()
    doi = re.sub(r"^(https?://(dx\.)?doi\.org/|doi:\s*)", "", doi, flags=re.IGNORECASE)
    return doi


def parse_bibtex(text: str) -> ParseResult:
    """Parse BibTeX text containing any number of entries of any type.

    Entries that cannot be parsed are reported in `failed` instead of aborting the whole import.
    """
    result = ParseResult()
    parser = BibTexParser(common_strings=True, ignore_nonstandard_types=False, interpolate_strings=True)
    try:
        db = bibtexparser.loads(text, parser=parser)
        entries = db.entries
    except Exception as exc:  # pyparsing errors on badly broken files
        log.warning("BibTeX parse error: %s", exc)
        entries = []

    parsed_keys = set()
    for entry in entries:
        try:
            article = entry_to_article(entry)
        except Exception as exc:
            log.warning("Could not convert entry %s: %s", entry.get("ID"), exc)
            result.failed.append(entry.get("ID", "?"))
            continue
        if not article.key:
            result.failed.append(article.title[:60] or "(entry without key)")
            continue
        parsed_keys.add(article.key)
        result.articles.append(article)

    # Entries silently dropped by the parser are reported as failures.
    for entry_type, key in _ENTRY_START.findall(text):
        if entry_type.lower() not in _NON_ENTRY_TYPES and key not in parsed_keys:
            result.failed.append(key or "(entry without key)")
    return result


def read_bibtex_file(path: str) -> ParseResult:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return parse_bibtex(fh.read())


def _safe_value(value: str) -> str:
    """BibTeX values are wrapped in braces, so they must be brace-balanced."""
    depth = 0
    for ch in value:
        depth += {"{": 1, "}": -1}.get(ch, 0)
        if depth < 0:
            break
    if depth != 0:
        value = value.replace("{", "(").replace("}", ")")
    return value


def safe_key(key: str) -> str:
    return re.sub(r"[\s,{}()\"'#%~\\]", "_", key.strip()) or "untitled"


def articles_to_bibtex(articles, include_local=True) -> str:
    """Serialise articles to BibTeX text. `include_local` keeps folderpath/pdffile/comment fields."""
    db = BibDatabase()
    for a in articles:
        fields = a.to_bibtex_fields()
        if not include_local:
            for k in ("folderpath", "pdffile", "comment"):
                fields.pop(k, None)
        entry = {k: _safe_value(v) for k, v in fields.items()}
        entry["ID"] = safe_key(a.key)
        entry["ENTRYTYPE"] = a.entry_type or "article"
        db.entries.append(entry)
    writer = BibTexWriter()
    writer.indent = "  "
    writer.order_entries_by = None
    writer.display_order = ["title", "author", "journal", "year", "volume", "number", "pages",
                            "publisher", "doi", "url", "keywords", "taggroups", "abstract"]
    return writer.write(db)


def article_to_bibtex(article: Article, include_local=False) -> str:
    return articles_to_bibtex([article], include_local=include_local)
