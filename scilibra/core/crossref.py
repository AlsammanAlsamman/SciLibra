"""Fetch article metadata for a DOI from the Crossref REST API."""

from __future__ import annotations

import html
import logging
import re

import requests

from .. import __version__
from .bibtex import normalize_doi
from .models import Article

log = logging.getLogger(__name__)

API = "https://api.crossref.org/works/"
HEADERS = {"User-Agent": f"SciLibra/{__version__} (https://github.com/AlsammanAlsamman/SciLibra)"}
TIMEOUT = 15

_ENTRY_TYPES = {"journal-article": "article", "proceedings-article": "inproceedings",
                "book-chapter": "incollection", "book": "book", "posted-content": "misc",
                "dissertation": "phdthesis", "report": "techreport"}


class CrossrefError(Exception):
    """Raised when Crossref cannot be reached or does not know the DOI."""


def is_online(timeout: float = 5) -> bool:
    try:
        requests.head("https://api.crossref.org", timeout=timeout, headers=HEADERS)
        return True
    except requests.RequestException:
        return False


def _strip_jats(text: str) -> str:
    text = re.sub(r"<jats:title>.*?</jats:title>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    return " ".join(html.unescape(text).split())


def message_to_article(msg: dict, key: str = "") -> Article:
    """Convert a Crossref `message` object into an Article."""
    def first(name):
        value = msg.get(name) or []
        return value[0] if isinstance(value, list) and value else (value if isinstance(value, str) else "")

    authors = []
    for person in msg.get("author", []):
        family, given = person.get("family", ""), person.get("given", "")
        name = f"{family}, {given}" if family and given else (family or given or person.get("name", ""))
        if name:
            authors.append(name)
    year = ""
    for date_field in ("published-print", "published-online", "issued", "created"):
        parts = (msg.get(date_field) or {}).get("date-parts") or [[None]]
        if parts and parts[0] and parts[0][0]:
            year = str(parts[0][0])
            break
    doi = normalize_doi(msg.get("DOI", ""))
    return Article(
        key=key,
        entry_type=_ENTRY_TYPES.get(msg.get("type", ""), "article"),
        title=_strip_jats(first("title")),
        authors=authors,
        year=year,
        journal=_strip_jats(first("container-title")),
        volume=str(msg.get("volume", "")),
        number=str(msg.get("issue", "")),
        pages=str(msg.get("page", "")),
        publisher=msg.get("publisher", ""),
        doi=doi,
        url=msg.get("URL", "") or (f"https://doi.org/{doi}" if doi else ""),
        abstract=_strip_jats(msg.get("abstract", "")),
        keywords=[s for s in msg.get("subject", []) if s],
    )


def fetch_article(doi: str, key: str = "", session: requests.Session | None = None) -> Article:
    """Look up `doi` on Crossref. Raises CrossrefError when it is not found or offline."""
    doi = normalize_doi(doi)
    if not doi:
        raise CrossrefError("Empty DOI")
    getter = session or requests
    try:
        response = getter.get(API + requests.utils.quote(doi, safe="/():;"), headers=HEADERS, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise CrossrefError(f"Crossref unreachable: {exc}") from exc
    if response.status_code == 404:
        raise CrossrefError(f"DOI not found on Crossref: {doi}")
    if response.status_code != 200:
        raise CrossrefError(f"Crossref returned HTTP {response.status_code} for {doi}")
    try:
        msg = response.json()["message"]
    except (ValueError, KeyError) as exc:
        raise CrossrefError(f"Unexpected Crossref response for {doi}") from exc
    return message_to_article(msg, key=key)


def make_key(article: Article) -> str:
    """Google-Scholar style key: firstauthorYEARfirstword (e.g. alsamman2023alignstatplot)."""
    surname = ""
    if article.authors:
        surname = article.authors[0].split(",")[0] if "," in article.authors[0] else article.authors[0].split()[-1]
    stop = {"a", "an", "the", "on", "of", "in", "for", "and", "to", "with", "from", "by", "at"}
    words = [w for w in re.findall(r"[a-z0-9]+", article.title.lower()) if w not in stop]
    key = re.sub(r"[^a-z0-9]", "", surname.lower()) + article.year + (words[0] if words else "")
    return key or "article"
