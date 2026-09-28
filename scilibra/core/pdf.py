"""PDF helpers: first-page thumbnails, DOI detection, metadata and annotations (PyMuPDF)."""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass

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


# Annotation types that mark up existing text; the marked text is extracted for them.
TEXT_MARKUP = {"Highlight", "Underline", "StrikeOut", "Squiggly"}
# Types without useful content for the user.
_SKIP_TYPES = {"Popup", "Link", "Widget", "Sound", "Movie", "Screen", "PrinterMark", "TrapNet",
               "Watermark", "3D", "RichMedia", "Projection"}


@dataclass
class Annotation:
    page: int            # 1-based page number
    kind: str            # Highlight, Text (sticky note), FreeText, Underline, Ink, ...
    text: str = ""       # the marked text (highlights etc.) or the text of a text box
    note: str = ""       # the comment typed by the reader
    author: str = ""
    color: tuple = ()    # RGB 0..1 of the annotation, if any
    rect: tuple = ()     # (x0, y0, x1, y1) in PDF points, top-left origin
    xref: int = 0        # PDF object number (identifies the annotation while editing)

    @property
    def label(self) -> str:
        return {"Text": "Sticky note", "FreeText": "Text box", "StrikeOut": "Strike-out", "Ink": "Drawing",
                "Square": "Rectangle", "Circle": "Ellipse", "Line": "Arrow / line", "Caret": "Insert mark",
                "PolyLine": "Polyline", "FileAttachment": "Attached file"}.get(self.kind, self.kind)

    def as_comment(self) -> str:
        parts = [f"[p. {self.page}] {self.label}:"]
        if self.text:
            parts.append(f'"{self.text}"')
        if self.note:
            parts.append(("- " if self.text else "") + self.note)
        return " ".join(parts)


def _marked_text(page, annot, words) -> str:
    """Text covered by a highlight/underline, using the annotation's quad points."""
    vertices = annot.vertices or []
    quads = [pymupdf.Quad(vertices[i:i + 4]).rect for i in range(0, len(vertices) - 3, 4)] or [annot.rect]
    picked = []
    for w in words:
        r = pymupdf.Rect(w[:4])
        if r.is_empty:
            continue
        for q in quads:
            inter = pymupdf.Rect(r) & q
            if not inter.is_empty and inter.get_area() >= 0.5 * r.get_area():
                picked.append(w)
                break
    picked.sort(key=lambda w: (w[5], w[6], w[7]))  # block, line, word order
    text = " ".join(w[4] for w in picked)
    return re.sub(r"(\w)- (?=[a-z])", r"\1", text)  # re-join words hyphenated across lines


def annotation_from_pymupdf(page, annot, words=None) -> Annotation | None:
    kind = annot.type[1]
    if kind in _SKIP_TYPES:
        return None
    info = annot.info or {}
    if kind in TEXT_MARKUP:
        text = _marked_text(page, annot, page.get_text("words") if words is None else words)
    else:
        text = ""
    note = (info.get("content") or "").strip()
    if kind == "FreeText" and note and not text:
        text, note = note, ""
    colors = annot.colors or {}
    color = tuple(colors.get("stroke") or colors.get("fill") or ())
    r = annot.rect
    return Annotation(page=page.number + 1, kind=kind, text=" ".join(text.split()), note=" ".join(note.split()),
                      author=(info.get("title") or "").strip(), color=color, rect=(r.x0, r.y0, r.x1, r.y1),
                      xref=annot.xref)


def extract_annotations(pdf_path: str) -> list[Annotation]:
    """All reader annotations of a PDF (sticky notes, highlights, text boxes, drawings...)."""
    result = []
    try:
        with pymupdf.open(pdf_path) as doc:
            for page in doc:
                annots = list(page.annots())
                if not annots:
                    continue
                words = page.get_text("words")
                for annot in annots:
                    found = annotation_from_pymupdf(page, annot, words)
                    if found is not None:
                        result.append(found)
    except Exception as exc:
        log.info("Cannot read annotations of %s: %s", pdf_path, exc)
    return result
