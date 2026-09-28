"""The Article data model and helpers for splitting multi-valued fields."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field

# Fields that hold several values; stored one value per row in their own table.
LIST_FIELDS = ("authors", "keywords", "taggroups", "comments")

_AUTHOR_SPLIT = re.compile(r"\s+and\s+", re.IGNORECASE)
_HTML_TAG = re.compile(r"</?(scp|i|b|em|strong|sub|sup|u|span|mml:[a-z]+)(\s[^>]*)?>", re.IGNORECASE)
# Placeholder "author" used by Google Scholar for truncated author lists ("... and others")
ET_AL = "others"


def clean_text(value: str) -> str:
    """Collapse whitespace and drop inline HTML tags (Crossref titles contain e.g. <scp>...</scp>)."""
    return " ".join(_HTML_TAG.sub("", value or "").split())


_TERM_SPLIT = re.compile(r"[,;\n]")


def split_authors(value: str) -> list[str]:
    """Split a BibTeX author string ("A and B and C") into names."""
    return _clean_list(_AUTHOR_SPLIT.split(value or ""))


def split_terms(value: str) -> list[str]:
    """Split a keyword/tag string separated by commas, semicolons or newlines."""
    return _clean_list(_TERM_SPLIT.split(value or ""))


def split_comments(value: str) -> list[str]:
    """Comments are exported as "**first**second" (legacy SciLibra format)."""
    return _clean_list((value or "").split("**"))


def _clean_list(values) -> list[str]:
    seen, result = set(), []
    for v in values:
        v = " ".join(str(v).split())
        if v and v.lower() != "none" and v not in seen:
            seen.add(v)
            result.append(v)
    return result


@dataclass
class Article:
    key: str
    title: str = ""
    authors: list[str] = field(default_factory=list)
    year: str = ""
    journal: str = ""
    keywords: list[str] = field(default_factory=list)
    taggroups: list[str] = field(default_factory=list)
    comments: list[str] = field(default_factory=list)
    abstract: str = ""
    url: str = ""
    doi: str = ""
    entry_type: str = "article"
    volume: str = ""
    number: str = ""
    pages: str = ""
    publisher: str = ""
    folderpath: str = ""
    pdffile: str = ""
    date_added: str = ""

    def normalize(self) -> "Article":
        """Tidy all fields in place (whitespace, HTML tags, duplicate list values)."""
        for name in ("key", "title", "year", "journal", "abstract", "url", "doi", "entry_type", "volume",
                     "number", "pages", "publisher", "date_added"):
            setattr(self, name, clean_text(getattr(self, name)))
        self.folderpath = (self.folderpath or "").strip()
        self.pdffile = (self.pdffile or "").strip()
        self.entry_type = self.entry_type.lower() or "article"
        for name in ("authors", "keywords", "taggroups", "comments"):
            setattr(self, name, _clean_list(getattr(self, name)))
        return self

    @property
    def author_string(self) -> str:
        return " and ".join(self.authors)

    @property
    def short_authors(self) -> str:
        if not self.authors:
            return ""
        first = self.authors[0].split(",")[0].strip()
        return first + (" et al." if len(self.authors) > 1 else "")

    @property
    def grouping_authors(self) -> list[str]:
        return [a for a in self.authors if a.lower() != ET_AL]

    @property
    def pdf_path(self) -> str:
        """Full path of the article PDF (may not exist), or "" if no folder is known."""
        if not self.folderpath:
            return ""
        return os.path.join(self.folderpath, self.pdffile or self.key + ".pdf")

    @property
    def has_pdf(self) -> bool:
        path = self.pdf_path
        return bool(path) and os.path.isfile(path)

    def to_bibtex_fields(self) -> dict[str, str]:
        """Flat string fields, as they would appear in a BibTeX entry."""
        fields = {
            "title": self.title,
            "author": self.author_string,
            "year": self.year,
            "journal": self.journal,
            "volume": self.volume,
            "number": self.number,
            "pages": self.pages,
            "publisher": self.publisher,
            "doi": self.doi,
            "url": self.url,
            "keywords": ", ".join(self.keywords),
            "taggroups": ", ".join(self.taggroups),
            "abstract": self.abstract,
            "folderpath": self.folderpath,
            "pdffile": self.pdffile,
            "comment": "".join("**" + c for c in self.comments),
        }
        return {k: v for k, v in fields.items() if v}
