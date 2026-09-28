"""Creating, editing and saving PDF annotations (standard PDF annotations, readable by any PDF reader)."""

from __future__ import annotations

import hashlib
import logging
import os
import re
import shutil
import tempfile

import pymupdf

from .pdf import Annotation, annotation_from_pymupdf

log = logging.getLogger(__name__)

# name -> RGB (0..1)
COLORS = {
    "Yellow": (1.0, 0.89, 0.2),
    "Green": (0.45, 0.85, 0.35),
    "Blue": (0.35, 0.65, 1.0),
    "Pink": (1.0, 0.45, 0.72),
    "Red": (0.95, 0.25, 0.25),
    "Orange": (1.0, 0.6, 0.15),
}
AUTHOR = "SciLibra"


# ---------------------------------------------------------------- reading text
def page_words(page) -> list:
    """Words of a page in reading order: (x0, y0, x1, y1, word, block, line, word_no)."""
    words = page.get_text("words", sort=False)
    words.sort(key=lambda w: (w[5], w[6], w[7]))
    return words


def _nearest_word(words, x, y) -> int:
    best, best_d = -1, None
    for i, w in enumerate(words):
        dx = 0 if w[0] <= x <= w[2] else min(abs(x - w[0]), abs(x - w[2]))
        dy = 0 if w[1] <= y <= w[3] else min(abs(y - w[1]), abs(y - w[3]))
        d = dy * 3 + dx  # prefer the same line
        if best_d is None or d < best_d:
            best, best_d = i, d
    return best


def words_between(words, p0, p1) -> list:
    """Words from the one nearest to point p0 to the one nearest to p1 (in reading order)."""
    if not words:
        return []
    a, b = _nearest_word(words, *p0), _nearest_word(words, *p1)
    if a > b:
        a, b = b, a
    return words[a:b + 1]


def words_text(words) -> str:
    lines, current, key = [], [], None
    for w in words:
        if key is not None and (w[5], w[6]) != key:
            lines.append(" ".join(current))
            current = []
        current.append(w[4])
        key = (w[5], w[6])
    if current:
        lines.append(" ".join(current))
    text = " ".join(lines)
    return re.sub(r"(\w)- (?=[a-z])", r"\1", text)


def line_rects(words) -> list:
    """One rectangle per text line covered by `words` (used as highlight quads)."""
    rects, key = [], None
    for w in words:
        r = pymupdf.Rect(w[:4])
        if key == (w[5], w[6]) and rects:
            rects[-1] |= r
        else:
            rects.append(r)
            key = (w[5], w[6])
    return rects


# ---------------------------------------------------------------- creating annotations
def _finish(annot, color=None, note="", fill=None, width=None, opacity=None):
    info = {"title": AUTHOR}
    if note:
        info["content"] = note
    annot.set_info(**info)
    if color is not None:
        colors = {"stroke": color}
        if fill is not None:
            colors["fill"] = fill
        annot.set_colors(**colors)
    if width is not None:
        annot.set_border(width=width)
    if opacity is not None:
        annot.set_opacity(opacity)
    annot.update()
    return annot.xref


def add_markup(page, kind: str, words, color=COLORS["Yellow"], note="") -> int:
    """Highlight / Underline / StrikeOut / Squiggly the given words. Returns the annotation xref (0 if none)."""
    rects = line_rects(words)
    if not rects:
        return 0
    make = {"Highlight": page.add_highlight_annot, "Underline": page.add_underline_annot,
            "StrikeOut": page.add_strikeout_annot, "Squiggly": page.add_squiggly_annot}[kind]
    annot = make(quads=[r.quad for r in rects])
    return _finish(annot, color, note)


def add_note(page, point, text, color=COLORS["Yellow"]) -> int:
    annot = page.add_text_annot(pymupdf.Point(point), text, icon="Note")
    return _finish(annot, color, text)


def add_textbox(page, rect, text, color=COLORS["Red"], fontsize=11) -> int:
    annot = page.add_freetext_annot(pymupdf.Rect(rect), text, fontsize=fontsize, fontname="helv",
                                    text_color=color, fill_color=(1, 1, 0.9))
    annot.set_info(title=AUTHOR, content=text)
    annot.set_border(width=1)
    annot.update(text_color=color, fill_color=(1, 1, 0.9))
    return annot.xref


def add_ink(page, strokes, color=COLORS["Red"], width=1.5) -> int:
    strokes = [[tuple(p) for p in s] for s in strokes if len(s) >= 2]
    if not strokes:
        return 0
    annot = page.add_ink_annot(strokes)
    return _finish(annot, color, width=width)


def add_shape(page, kind, p0, p1, color=COLORS["Red"], width=1.5, note="") -> int:
    rect = pymupdf.Rect(p0, p1)
    rect.normalize()
    if kind in ("Arrow", "Line"):
        if abs(p1[0] - p0[0]) < 2 and abs(p1[1] - p0[1]) < 2:
            return 0
        annot = page.add_line_annot(pymupdf.Point(p0), pymupdf.Point(p1))
        if kind == "Arrow":
            annot.set_line_ends(pymupdf.PDF_ANNOT_LE_NONE, pymupdf.PDF_ANNOT_LE_OPEN_ARROW)
    elif rect.width < 2 or rect.height < 2:
        return 0
    elif kind == "Ellipse":
        annot = page.add_circle_annot(rect)
    else:
        annot = page.add_rect_annot(rect)
    return _finish(annot, color, note, width=width)


# ---------------------------------------------------------------- editing
def find_annot(page, xref):
    for annot in page.annots():
        if annot.xref == xref:
            return annot
    return None


def annot_at(page, point, tolerance=3.0):
    """The (smallest) annotation under a point, or None."""
    p = pymupdf.Point(point)
    hits = []
    for annot in page.annots():
        if annot.type[1] in ("Popup", "Link", "Widget"):
            continue
        r = pymupdf.Rect(annot.rect)
        r.x0 -= tolerance
        r.y0 -= tolerance
        r.x1 += tolerance
        r.y1 += tolerance
        if p in r:
            hits.append((r.get_area(), annot.xref))
    if not hits:
        return None
    return find_annot(page, min(hits)[1])


def update_annot(page, xref, note=None, color=None) -> bool:
    annot = find_annot(page, xref)
    if annot is None:
        return False
    if note is not None:
        if annot.type[1] == "FreeText":
            annot.set_info(content=note)
            annot.update()
        else:
            annot.set_info(content=note)
    if color is not None:
        if annot.type[1] == "FreeText":
            annot.update(text_color=color)
        else:
            annot.set_colors(stroke=color)
    annot.update()
    return True


def delete_annot(page, xref) -> bool:
    annot = find_annot(page, xref)
    if annot is None:
        return False
    page.delete_annot(annot)
    return True


def document_annotations(doc) -> list[Annotation]:
    """Annotations of an open document (with their xref, for editing)."""
    result = []
    for page in doc:
        annots = list(page.annots())
        if not annots:
            continue
        words = page.get_text("words")
        for annot in annots:
            found = annotation_from_pymupdf(page, annot, words)
            if found is not None:
                result.append(found)
    return result


# ---------------------------------------------------------------- saving
def backup_once(pdf_path: str, backup_dir: str) -> str:
    """Copy the original PDF to `backup_dir` the first time SciLibra modifies it. Returns the backup path."""
    os.makedirs(backup_dir, exist_ok=True)
    digest = hashlib.sha1(os.path.abspath(pdf_path).encode()).hexdigest()[:10]
    target = os.path.join(backup_dir, f"{digest}-{os.path.basename(pdf_path)}")
    if not os.path.exists(target):
        shutil.copy2(pdf_path, target)
    return target


def save_document(doc, path: str) -> bool:
    """Save changes into the PDF file: incrementally when possible, otherwise via a safe full rewrite.

    Returns True when the file was rewritten - the caller must then re-open the document.
    """
    try:
        if doc.can_save_incrementally():
            doc.saveIncr()
            return False
    except Exception as exc:
        log.info("Incremental save failed for %s: %s", path, exc)
    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(suffix=".pdf", dir=folder)
    os.close(fd)
    try:
        doc.save(tmp, garbage=1, deflate=True)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return True
