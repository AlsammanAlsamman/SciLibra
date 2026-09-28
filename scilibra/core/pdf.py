"""PDF helpers: first-page thumbnails, DOI detection and basic metadata (PyMuPDF)."""

from __future__ import annotations

import logging
import os
import re

import pymupdf

log = logging.getLogger(__name__)
pymupdf.TOOLS.mupdf_display_errors(False)

DOI_PATTERN = re.compile(r"\b(10\.\d{4,9}/[^\s\"'<>]+)", re.IGNORECASE)
_TRAILING = ".,;:)]}>"


def first_page_thumbnail(pdf_path: str, width: int = 300) -> bytes | None:
    """Render the first page of a PDF as PNG bytes `width` pixels wide. Returns None on failure."""
    try:
        with pymupdf.open(pdf_path) as doc:
            if doc.page_count == 0:
                return None
            page = doc[0]
            zoom = width / max(page.rect.width, 1)
            pix = page.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
            return pix.tobytes("png")
    except Exception as exc:
        log.info("No thumbnail for %s: %s", pdf_path, exc)
        return None


def image_to_png(data: bytes) -> bytes | None:
    """Convert image bytes (e.g. the GIF previews of SciLibra 1.x) to PNG."""
    try:
        return pymupdf.Pixmap(data).tobytes("png")
    except Exception:
        return None


def clean_doi(doi: str) -> str:
    doi = doi.strip()
    while doi and doi[-1] in _TRAILING:
        # keep balanced parentheses that are part of the DOI, e.g. 10.1016/S0140-6736(20)30183-5
        if doi[-1] == ")" and doi.count("(") >= doi.count(")"):
            break
        doi = doi[:-1]
    return doi


def find_doi(text: str) -> str:
    """Return the first DOI found in `text`, or ""."""
    text = re.sub(r"doi\.org/\s+", "doi.org/", text)
    match = DOI_PATTERN.search(text)
    return clean_doi(match.group(1)) if match else ""


def extract_info(pdf_path: str, pages: int = 2) -> dict:
    """Extract DOI, title and author hints from a PDF's metadata and first pages."""
    info = {"doi": "", "title": "", "author": "", "year": ""}
    try:
        with pymupdf.open(pdf_path) as doc:
            meta = doc.metadata or {}
            text = "\n".join(doc[i].get_text() for i in range(min(pages, doc.page_count)))
    except Exception as exc:
        log.info("Cannot read %s: %s", pdf_path, exc)
        return info
    candidates = [meta.get("subject", ""), meta.get("keywords", ""), meta.get("title", ""), text]
    for candidate in candidates:
        doi = find_doi(candidate or "")
        if doi:
            info["doi"] = doi
            break
    title = (meta.get("title") or "").strip()
    # Many PDFs carry junk titles such as "untitled" or the file name.
    if title and len(title) > 8 and not title.lower().endswith((".pdf", ".doc", ".docx")) \
            and "untitled" not in title.lower() and not title.lower().startswith("microsoft word"):
        info["title"] = title
    info["author"] = (meta.get("author") or "").strip()
    date = meta.get("creationDate") or ""
    match = re.search(r"(19|20)\d{2}", date)
    info["year"] = match.group(0) if match else ""
    return info


def title_from_filename(pdf_path: str) -> str:
    stem = os.path.splitext(os.path.basename(pdf_path))[0]
    return " ".join(re.sub(r"[_\-]+", " ", stem).split())
