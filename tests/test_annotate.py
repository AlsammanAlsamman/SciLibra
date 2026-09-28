import os

import pymupdf

from scilibra.core import annotate
from scilibra.core.pdf import extract_annotations

from .conftest import make_pdf


def two_line_pdf(path):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Deep learning improves genomic prediction accuracy.")
    page.insert_text((72, 115), "Results were validated in three wheat panels.")
    page.insert_text((72, 200), "Unrelated closing sentence.")
    doc.save(path)
    doc.close()
    return str(path)


def test_word_selection_across_lines(tmp_path):
    doc = pymupdf.open(two_line_pdf(tmp_path / "p.pdf"))
    words = annotate.page_words(doc[0])
    start = [w for w in words if w[4] == "genomic"][0]
    end = [w for w in words if w[4] == "three"][0]
    picked = annotate.words_between(words, (start[0] + 1, start[1] + 2), (end[2] - 1, end[1] + 2))
    assert annotate.words_text(picked) == "genomic prediction accuracy. Results were validated in three"
    assert len(annotate.line_rects(picked)) == 2
    # dragging backwards selects the same words
    back = annotate.words_between(words, (end[2] - 1, end[1] + 2), (start[0] + 1, start[1] + 2))
    assert back == picked
    assert annotate.words_between([], (0, 0), (1, 1)) == []


def test_create_every_kind_save_and_reread(tmp_path):
    path = two_line_pdf(tmp_path / "p.pdf")
    doc = pymupdf.open(path)
    page = doc[0]
    words = annotate.page_words(page)
    first_line = [w for w in words if w[6] == words[0][6] and w[5] == words[0][5]]
    xrefs = [
        annotate.add_markup(page, "Highlight", first_line[:2], annotate.COLORS["Green"], note="important"),
        annotate.add_markup(page, "Underline", first_line[2:4]),
        annotate.add_markup(page, "StrikeOut", first_line[4:5]),
        annotate.add_note(page, (400, 300), "Check reference 12"),
        annotate.add_textbox(page, (72, 400, 300, 440), "Summary: works well"),
        annotate.add_ink(page, [[(100, 500), (150, 520), (200, 510)]]),
        annotate.add_shape(page, "Rectangle", (72, 600), (200, 650)),
        annotate.add_shape(page, "Ellipse", (250, 600), (350, 650)),
        annotate.add_shape(page, "Arrow", (400, 600), (500, 650)),
    ]
    assert all(xrefs)
    assert annotate.add_markup(page, "Highlight", []) == 0
    assert annotate.add_ink(page, [[(1, 1)]]) == 0
    backup = annotate.backup_once(path, str(tmp_path / "backups"))
    original = open(backup, "rb").read()
    rewritten = annotate.save_document(doc, path)
    doc.close()
    assert isinstance(rewritten, bool)
    assert b"/Annot" not in original  # the backup is the untouched file
    found = extract_annotations(path)
    kinds = [a.kind for a in found]
    assert kinds == ["Highlight", "Underline", "StrikeOut", "Text", "FreeText", "Ink", "Square", "Circle", "Line"]
    hl = found[0]
    assert hl.text == "Deep learning" and hl.note == "important" and hl.author == "SciLibra"
    assert tuple(round(c, 2) for c in hl.color) == (0.45, 0.85, 0.35)
    assert found[3].note == "Check reference 12" and found[4].text == "Summary: works well"
    # a second backup call keeps the first (original) copy
    assert annotate.backup_once(path, str(tmp_path / "backups")) == backup
    assert open(backup, "rb").read() == original


def test_find_update_delete(tmp_path):
    path = two_line_pdf(tmp_path / "p.pdf")
    doc = pymupdf.open(path)
    page = doc[0]
    words = annotate.page_words(page)
    xref = annotate.add_markup(page, "Highlight", words[:3])
    note = annotate.add_note(page, (400, 300), "old")
    hit = annotate.annot_at(page, ((words[0][0] + words[0][2]) / 2, (words[0][1] + words[0][3]) / 2))
    assert hit is not None and hit.xref == xref
    assert annotate.annot_at(page, (10, 780)) is None
    assert annotate.update_annot(page, note, note="new text", color=annotate.COLORS["Blue"])
    assert annotate.update_annot(page, xref, note="why?")
    assert annotate.delete_annot(page, xref)
    assert not annotate.delete_annot(page, xref)
    listed = annotate.document_annotations(doc)
    assert [(a.kind, a.note) for a in listed] == [("Text", "new text")]
    assert listed[0].xref == note
    annotate.save_document(doc, path)
    doc.close()
    assert [(a.kind, a.note) for a in extract_annotations(path)] == [("Text", "new text")]


def test_save_falls_back_to_full_rewrite(tmp_path):
    path = make_pdf(tmp_path / "x.pdf", "Hello")
    doc = pymupdf.open(path)
    doc.insert_page(-1, text="new page")  # structural change: incremental save may not be possible
    annotate.add_note(doc[0], (100, 100), "n")
    annotate.save_document(doc, path)
    doc.close()
    with pymupdf.open(path) as check:
        assert check.page_count == 2
    assert [a.note for a in extract_annotations(path)] == ["n"]
    assert not [f for f in os.listdir(tmp_path) if f.startswith("tmp")]
