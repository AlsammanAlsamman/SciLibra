"""End-to-end GUI scenario: drives the real app (dialogs included) and checks the library after each step.

Run directly:   python tests/gui_scenario.py OUTPUT_DIR [LIBRARY.db]
It is also run by tests/test_gui.py when a display is available.
Exit code 0 = every step passed. Screenshots of each step are written to OUTPUT_DIR.
"""

import os
import shutil
import sys
import tempfile
import time
import traceback

os.environ["KIVY_NO_ARGS"] = "1"
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")
from kivy.config import Config  # noqa: E402

Config.set("graphics", "width", "1280")
Config.set("graphics", "height", "800")
Config.set("kivy", "exit_on_escape", "0")

from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402
from kivy.uix.modalview import ModalView  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.conftest import SAMPLE_BIB, make_pdf  # noqa: E402
from tests.test_pdf_crossref_config import make_annotated_pdf  # noqa: E402

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "gui-shots")
EXISTING = sys.argv[2] if len(sys.argv) > 2 else ""
os.makedirs(OUT, exist_ok=True)
WORK = tempfile.mkdtemp(prefix="scilibra-gui-")
os.environ["SCILIBRA_HOME"] = os.path.join(WORK, "home")

from scilibra.gui.app import SciLibraApp  # noqa: E402
from scilibra.gui.dialogs import (ConfirmDialog, FileDialog, MessageDialog, ProgressDialog,  # noqa: E402
                                  TextDialog, ValuePicker)
from scilibra.gui.editor import ArticleEditor  # noqa: E402
from scilibra.gui.viewer import PdfViewer  # noqa: E402

LIB = os.path.join(WORK, "library.db")
if EXISTING:
    shutil.copy2(EXISTING, LIB)
app = SciLibraApp(library_path=LIB)
failures = []
counter = [0]


# ---------------------------------------------------------------- helpers
def popups():
    return [w for w in Window.children if isinstance(w, ModalView)]


def top(cls=None):
    items = popups()
    assert items, "expected an open popup"
    if cls is not None:
        assert isinstance(items[0], cls), f"expected {cls.__name__}, got {type(items[0]).__name__}"
    return items[0]


def close_all():
    for p in popups():
        p.dismiss(animation=False)


def shot(name):
    """Save a screenshot. Steps `yield FRAME` first so Kivy has laid out and drawn the current state."""
    counter[0] += 1
    Window.screenshot(os.path.join(OUT, f"{counter[0]:02d}_{name}.png"))


FRAME = 0.35  # seconds to let Kivy render before a screenshot
BUSY = "busy"  # yield BUSY to wait until the app's background task has finished


def ids():
    return app.root.ids


def rows():
    return ids().rv.data


def click_row(title_part):
    for i, r in enumerate(rows()):
        if title_part.lower() in r["title"].lower():
            app.on_row(i)
            return r
    raise AssertionError(f"no row containing {title_part!r}: {[r['title'] for r in rows()][:10]}")


def click(widget):
    """A real mouse click at the widget's centre, dispatched through the window like a user's click."""
    from kivy.tests.common import UnitTestTouch
    x, y = widget.to_window(*widget.center)
    touch = UnitTestTouch(x, y)
    touch.touch_down()
    touch.touch_up()


def real_drag(page, p0, p1, steps=5):
    """A real mouse drag between two PDF points of a page."""
    from kivy.tests.common import UnitTestTouch
    points = [page.to_window(*page.to_widget(p0[0] + (p1[0] - p0[0]) * i / steps, p0[1] + (p1[1] - p0[1]) * i / steps))
              for i in range(steps + 1)]
    touch = UnitTestTouch(*points[0])
    touch.touch_down()
    for x, y in points[1:]:
        touch.touch_move(x, y)
    touch.touch_up()


def button(root, text):
    found = [w for w in root.walk() if getattr(w, "text", None) == text and hasattr(w, "trigger_action")]
    assert found, f"no button {text!r}"
    return found[0]


def choose_in_file_dialog(path=None, folder=None, filename=None):
    dialog = top(FileDialog)
    chooser = dialog.ids.chooser
    if folder:
        chooser.path = folder
    if path:
        files = [path] if isinstance(path, str) else list(path)
        chooser.path = os.path.dirname(files[0])
        chooser.selection = files
    if filename is not None:
        dialog.ids.filename.text = filename
    dialog.confirm()
    assert dialog not in popups(), f"file dialog stayed open: {dialog.error!r}"


# ---------------------------------------------------------------- data for the scenario
DATA = os.path.join(WORK, "data")
os.makedirs(os.path.join(DATA, "pdfs", "sub"))
BIB = os.path.join(DATA, "refs.bib")
with open(BIB, "w", encoding="utf-8") as fh:
    fh.write(SAMPLE_BIB)
make_pdf(os.path.join(DATA, "alsamman2023alignstatplot.pdf"), "AlignStatPlot first page")
make_pdf(os.path.join(DATA, "pdfs", "sub", "smith2020deep.pdf"), "Deep learning paper")
NEW_PDF = make_pdf(os.path.join(DATA, "pdfs", "Offline Paper.pdf"), "Body", doi="10.9999/scilibra.test.404",
                   title="An offline paper about maize genomes")


# ---------------------------------------------------------------- steps
def s_start():
    close_all()  # welcome / upgrade message
    yield FRAME
    shot("start")
    if not EXISTING:
        assert app.library.count() == 0 and rows() == []


def s_import_bibtex():
    before = app.library.count()
    app.import_bibtex_file()
    yield FRAME
    shot("file_dialog")
    choose_in_file_dialog(path=BIB)
    msg = top(MessageDialog)
    assert "3 added" in msg.message or "already" in msg.message, msg.message
    yield FRAME
    shot("import_report")
    msg.dismiss(animation=False)
    assert app.library.count() == before + 3
    a = app.library.get("alsamman2023alignstatplot")
    assert a.has_pdf and app.library.thumbnail(a.key), "PDF next to the .bib must be linked with a preview"


def s_select_article():
    ids().list_filter.text = "alignstat"
    assert len(rows()) == 1
    click_row("AlignStatPlot")
    assert app.selected_key == "alsamman2023alignstatplot" and app.d_thumb is not None
    yield FRAME
    shot("details_with_preview")
    ids().list_filter.text = ""


def s_group_by_keywords():
    app.group_choice = "Keywords"
    assert rows() and rows()[0]["kind"] == "group"
    yield FRAME
    shot("groups_keywords")
    click_row("GWAS")
    assert app.can_go_back and all(r["kind"] == "article" for r in rows())
    click_row("Deep learning")
    assert app.selected_key == "smith2020deep"
    yield FRAME
    shot("group_members")
    app.go_back()
    assert rows()[0]["kind"] == "group" and not app.can_go_back


def s_group_by_other_fields():
    for choice in ("Tag groups", "Authors", "Year", "Journal"):
        app.group_choice = choice
        assert rows(), f"no groups for {choice}"
    app.group_choice = "Year"
    assert {r["title"] for r in rows()} >= {"2019", "2020", "2023"}
    app.group_choice = "All articles"


def s_keyboard():
    app.select_article("")
    app.move_selection(1)
    first = app.selected_key
    app.move_selection(1)
    assert app.selected_key and app.selected_key != first
    app.move_selection(-1)
    assert app.selected_key == first


def key(code, char=None, modifiers=()):
    Window.dispatch("on_key_down", code, 0, char, list(modifiers))


def s_keyboard_events():
    app.group_choice = "All articles"
    app.select_article("")
    key(274)  # down
    assert app.selected_key == rows()[0]["key"]
    key(274)
    assert app.selected_key == rows()[1]["key"]
    key(273)  # up
    assert app.selected_key == rows()[0]["key"]
    key(102, "f", ["ctrl"])
    assert ids().search.focus
    ids().search.focus = False
    app.group_choice = "Year"
    click_row("2020")
    assert app.can_go_back
    key(27)  # Esc goes back instead of quitting
    assert not app.can_go_back and app.root is not None
    app.group_choice = "All articles"


def s_edit_article():
    app.select_article("doe2019book")
    app.edit_article()
    editor = top(ArticleEditor)
    yield FRAME
    assert editor.ids.title.text == "A Book about Café Science"
    editor.ids.title.text = "A Book about Café Science (2nd edition)"
    editor.ids.keywords.text = "coffee, science"
    editor.ids.year.text = ""
    yield FRAME
    shot("editor")
    editor.save()
    a = app.library.get("doe2019book")
    assert a.title.endswith("(2nd edition)") and a.keywords == ["coffee", "science"] and a.year == ""


def s_editor_validation_and_picker():
    app.select_article("doe2019book")
    app.edit_article()
    editor = top(ArticleEditor)
    yield FRAME
    editor.ids.key.text = "smith2020deep"  # already used
    editor.save()
    assert "already exists" in editor.error
    editor.ids.key.text = ""
    editor.save()
    assert "key is required" in editor.error
    editor.ids.key.text = "doe2019book"
    editor.ids.pdf.text = "/does/not/exist.pdf"
    editor.save()
    assert "does not exist" in editor.error
    editor.ids.pdf.text = ""
    editor.pick("keywords")
    picker = top(ValuePicker)
    yield FRAME
    assert any(d["text"] == "GWAS" for d in picker.ids.rv.data)
    picker.ids.filter.text = "gw"
    assert [d["text"] for d in picker.ids.rv.data] == ["GWAS"]
    picker.toggle("GWAS")
    picker.add_new("brand new; another")
    yield FRAME
    shot("value_picker")
    picker.done()
    assert editor.ids.keywords.text == "coffee, science, GWAS, brand new, another"
    editor.ids.key.text = "doe2019renamed"
    editor.save()
    assert app.library.get("doe2019book") is None
    assert app.library.get("doe2019renamed").keywords == ["coffee", "science", "GWAS", "brand new", "another"]
    assert app.selected_key == "doe2019renamed"


def s_comments():
    app.select_article("smith2020deep")
    ids().comment_input.text = "Important for chapter 2"
    app.add_comment(ids().comment_input.text)
    assert app.library.get("smith2020deep").comments == ["Important for chapter 2"]
    assert len(ids().comments_box.children) == 1 and ids().comment_input.text == ""
    yield FRAME
    shot("comment_added")
    app.remove_comment("Important for chapter 2")
    top(ConfirmDialog).confirm()
    assert app.library.get("smith2020deep").comments == []


def s_search():
    ids().search.text = "gwas"
    app.search("gwas")
    found = {r.get("key") for r in rows()}
    assert {"smith2020deep", "doe2019renamed"} <= found, found  # title/keyword GWAS (keyword added earlier)
    assert app.breadcrumb.startswith("Search: gwas")
    yield FRAME
    shot("search_results")
    app.search("zzzz-not-there")
    assert rows() == []
    app.search_options()
    yield FRAME
    shot("search_options")
    top().dismiss(animation=False)
    app.search("café")
    assert [r["key"] for r in rows()] == ["doe2019renamed"]
    app.toggle_search_field("Title", False)
    app.search("café")  # the word only appears in a title
    assert rows() == []
    app.toggle_search_field("Title", True)
    app.go_back()
    app.go_back()
    app.go_back()
    app.go_back()
    assert not app.can_go_back


def s_paste_bibtex():
    before = app.library.count()
    app.paste_bibtex()
    dialog = top(TextDialog)
    dialog.ids.input.text = "@misc{pasted2024, title={Pasted entry with 100% {braces}}, author={Doe, J}, year={2024}}"
    yield FRAME
    shot("paste_bibtex")
    dialog.confirm()
    msg = top(MessageDialog)
    assert "1 added" in msg.message, msg.message
    msg.dismiss(animation=False)
    assert app.library.count() == before + 1 and app.selected_key == "pasted2024"
    assert app.library.get("pasted2024").title == "Pasted entry with 100% braces"


def s_attach_pdf():
    app.select_article("pasted2024")
    app.open_pdf()  # no PDF -> offers to choose one
    top(ConfirmDialog).confirm()
    choose_in_file_dialog(path=NEW_PDF)
    a = app.library.get("pasted2024")
    assert a.has_pdf and a.pdffile == "Offline Paper.pdf"
    assert app.d_has_pdf
    # detach again for the next steps
    a.folderpath = a.pdffile = ""
    app.library.update(a)
    app.select_article("pasted2024")


def s_annotations_in_details():
    annotated = make_annotated_pdf(os.path.join(DATA, "annotated.pdf"))
    app.library.set_pdf("alsamman2023alignstatplot", annotated)
    app.select_article("alsamman2023alignstatplot")
    for _ in range(20):  # read in the background
        if app.d_annotations:
            break
        yield 0.2
    assert [a.kind for a in app.d_annotations] == ["Highlight", "Text", "FreeText", "Underline"]
    assert len(ids().annotations_box.children) == 4
    yield FRAME
    shot("annotations_in_details")
    app.annotations_to_comments()
    assert len(app.library.get("alsamman2023alignstatplot").comments) == 4
    assert len(ids().comments_box.children) == 4
    app.search("methods section")  # sticky note text is searchable
    assert [r["key"] for r in rows()] == ["alsamman2023alignstatplot"]
    app.go_back()


def s_pdf_viewer():
    app.select_article("alsamman2023alignstatplot")
    app.open_pdf()
    viewer = top(PdfViewer)
    yield 0.6
    assert viewer.page_count == 2 and viewer.page == 1
    assert viewer.pages[0].texture is not None, "first page must be rendered"
    corner = viewer.pages[0].texture.pixels[:4]
    assert corner == b"\xff\xff\xff\xff", f"page background must be opaque white, got {corner!r}"
    assert len(viewer.ids.annotation_list.children) == 4 and viewer.panel == "annotations"
    shot("viewer")
    viewer.next_page()
    yield 0.4
    assert viewer.page == 2 and viewer.pages[1].texture is not None
    before = viewer.zoom
    viewer.zoom_in()
    yield 0.3
    assert viewer.zoom > before and not viewer.fit_width
    viewer.fit()
    yield 0.3
    assert viewer.fit_width
    viewer.ids.search.text = "wheat"
    viewer.search("wheat")
    assert viewer.hit_count == 1 and viewer.page == 2
    viewer.search("zzz-nothing")
    assert viewer.hit_count == 0 and "not found" in viewer.status
    viewer.ids.search.text = "association"
    viewer.search("association")
    yield FRAME
    shot("viewer_search")
    viewer.show_annotation(1)  # sticky note on page 1
    yield 0.3
    assert viewer.page == 1
    key(281)  # PageDown inside the viewer
    yield 0.2
    assert viewer.page == 2
    key(278)  # Home
    yield 0.2
    assert viewer.page == 1
    viewer.save_all_as_comments()
    assert "already saved" in viewer.status
    key(27)  # Esc closes the viewer, not the app
    yield 0.2
    assert viewer not in popups() and app.root is not None


class FakeTouch:
    """Minimal stand-in for a mouse touch, used to drive the annotation tools."""

    def __init__(self, x, y):
        self.x, self.y, self.ox, self.oy = x, y, x, y
        self.pos = (x, y)
        self.button = "left"
        self.is_mouse_scrolling = False

    def move(self, x, y):
        self.x, self.y, self.pos = x, y, (x, y)
        return self


def drag(viewer, page, p0, p1, steps=4):
    """Drag on `page` from PDF point p0 to p1 with the active tool."""
    touch = FakeTouch(*page.to_widget(*p0))
    assert viewer.tool_down(page, touch)
    for i in range(1, steps + 1):
        t = i / steps
        viewer.tool_move(page, touch.move(*page.to_widget(p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t)))
    viewer.tool_up(page, touch)


def s_annotate_in_viewer():
    import pymupdf
    from scilibra.core import annotate as ann
    from scilibra.core.pdf import extract_annotations
    path = os.path.join(DATA, "toannotate.pdf")
    doc = pymupdf.open()
    for n in range(3):
        page = doc.new_page()
        page.insert_text((72, 100), f"Section {n + 1}: Deep learning improves genomic prediction accuracy.")
        page.insert_text((72, 115), "Results were validated in three independent wheat panels.")
    doc.set_toc([[1, "Introduction", 1], [1, "Methods", 2], [2, "Statistics", 2], [1, "Results", 3]])
    doc.save(path)
    doc.close()
    app.library.set_pdf("pasted2024", path)
    app.select_article("pasted2024")
    app.open_pdf()
    viewer = top(PdfViewer)
    yield 0.6
    assert viewer.panel == "contents" and len(viewer.ids.toc_list.children) == 4
    icons = [getattr(w, "icon", "|") for w in reversed(viewer.ids.tool_row.children)]
    assert icons == ["select", "text", "|", "Highlight", "Underline", "StrikeOut", "|", "note", "textbox", "|",
                     "draw", "shapes", "eraser", "|", "color", "undo"], icons
    viewer.ids.toc_list.children[-2].dispatch("on_release")  # "Methods" (children are reversed)
    yield 0.2
    assert viewer.page == 2
    viewer.go_to(1)
    yield 0.4
    page = viewer.pages[0]
    words = ann.page_words(viewer.doc[0])
    w = {x[4]: x for x in words}
    mid = lambda word: ((w[word][0] + w[word][2]) / 2, (w[word][1] + w[word][3]) / 2)  # noqa: E731

    viewer.tool = "Highlight"
    drag(viewer, page, mid("learning"), mid("prediction"))
    viewer.color_name = "Green"
    viewer.tool = "Underline"
    drag(viewer, page, mid("Results"), mid("validated"))
    viewer.tool = "note"
    drag(viewer, page, (400, 300), (400, 300), steps=1)
    note_dialog = top(TextDialog)
    note_dialog.ids.input.text = "Compare with Table 2"
    note_dialog.confirm()
    viewer.tool = "textbox"
    drag(viewer, page, (72, 400), (300, 440))
    box_dialog = top(TextDialog)
    box_dialog.ids.input.text = "Key result"
    box_dialog.confirm()
    viewer.tool = "draw"
    drag(viewer, page, (100, 500), (200, 540), steps=8)
    viewer.tool = "Rectangle"
    drag(viewer, page, (72, 600), (200, 680))
    viewer.tool = "Arrow"
    drag(viewer, page, (250, 700), (320, 640))
    viewer.set_zoom(0.62)
    viewer.panel = "annotations"
    yield 0.8
    shot("annotating")
    viewer.fit()
    yield 0.3
    kinds = [a.kind for a in viewer.annotations]
    assert kinds == ["Highlight", "Underline", "Text", "FreeText", "Ink", "Square", "Line"], kinds
    assert viewer.annotations[0].text == "learning improves genomic prediction"
    assert viewer.annotations[2].note == "Compare with Table 2"
    # saved inside the PDF file (read back independently) and the original was backed up
    on_disk = extract_annotations(path)
    assert [a.kind for a in on_disk] == kinds
    backups = os.listdir(os.path.join(os.environ["SCILIBRA_HOME"], "pdf-backups"))
    assert any(b.endswith("toannotate.pdf") for b in backups)

    viewer.undo()  # removes the arrow
    assert [a.kind for a in viewer.annotations][-1] == "Square" and len(extract_annotations(path)) == 6
    viewer.tool = "eraser"
    rect = viewer.annotations[-1].rect
    drag(viewer, page, ((rect[0] + rect[2]) / 2, rect[1] + 1), ((rect[0] + rect[2]) / 2, rect[1] + 1), steps=1)
    assert "Square" not in [a.kind for a in viewer.annotations]

    # toolbar menus (shapes, colours), hover hints and the Line tool
    from kivy.uix.dropdown import DropDown
    buttons = viewer._icon_buttons
    menu = viewer._open_shapes(buttons["shapes"])
    yield FRAME
    shot("shapes_menu")
    line_item = [w for w in menu.walk() if getattr(w, "text", "").startswith("Line")][0]
    line_item.dispatch("on_release")
    assert viewer.tool == "Line" and buttons["shapes"].icon == "Line" and buttons["shapes"].active
    menu = viewer._open_colors(buttons["color"])
    [w for w in menu.walk() if getattr(w, "text", "") == "Blue"][0].dispatch("on_release")
    assert viewer.color_name == "Blue" and tuple(buttons["Highlight"].accent) == ann.COLORS["Blue"]
    yield 0.2
    assert not [w for w in Window.children if isinstance(w, DropDown)]
    before = len(viewer.annotations)
    drag(viewer, page, (300, 700), (500, 720))
    assert viewer.annotations[-1].kind == "Line" and len(viewer.annotations) == before + 1
    viewer.undo()
    assert len(viewer.annotations) == before
    viewer._on_mouse(None, buttons["StrikeOut"].to_window(*buttons["StrikeOut"].center))
    assert viewer.status == "Strikethrough (S)" and buttons["StrikeOut"].hovered
    viewer._on_mouse(None, (1, 1))
    assert not buttons["StrikeOut"].hovered

    # real mouse input: click a tool icon, drag over text, click an annotation, and the red Close button
    viewer.go_to(1)
    yield 0.3
    click(buttons["StrikeOut"])
    assert viewer.tool == "StrikeOut"
    count = len(viewer.annotations)
    real_drag(page, mid("independent"), mid("panels."))
    assert len(viewer.annotations) == count + 1 and viewer.annotations[-1].kind == "StrikeOut", \
        [a.kind for a in viewer.annotations]
    assert viewer.annotations[-1].text == "independent wheat panels."
    viewer.undo()
    click(buttons["select"])
    assert viewer.tool == "select"

    # select tool: click the highlight, change its note and colour
    viewer.tool = "select"
    hl = viewer.annotations[0]
    touch = FakeTouch(*page.to_widget((hl.rect[0] + hl.rect[2]) / 2, (hl.rect[1] + hl.rect[3]) / 2))
    viewer.click_select(page, touch)
    editor = top()
    yield FRAME
    shot("annotation_editor")
    editor.ids.note.text = "Main claim"
    editor.choose("Blue", ann.COLORS["Blue"])
    editor.finish("save")
    first = extract_annotations(path)[0]
    assert first.note == "Main claim" and tuple(round(c, 2) for c in first.color) == ann.COLORS["Blue"]

    # text selection: quote with citation, save as comment, highlight
    viewer.tool = "text"
    drag(viewer, page, mid("three"), mid("wheat"))
    assert viewer.selection_text == "three independent wheat"
    yield FRAME
    shot("text_selection")
    viewer.copy_selection(with_citation=True)
    viewer.selection_to_comment()
    assert app.library.get("pasted2024").comments[-1] == '[p. 1] \u201cthree independent wheat\u201d'
    drag(viewer, page, mid("Deep"), mid("learning"))
    viewer.markup_selection("Highlight")
    assert viewer.selection_text == "" and len(viewer.annotations) == 6
    # keyboard: tool shortcuts, Ctrl+Z, Esc drops the tool first
    key(104, "h")
    assert viewer.tool == "Highlight"
    key(122, "z", ["ctrl"])
    assert len(viewer.annotations) == 5
    key(27)
    assert viewer.tool == "select" and viewer in popups()
    viewer.night = True
    yield 0.4
    shot("night_mode")
    assert viewer.pages[0].texture.pixels[:4] == b"\x00\x00\x00\xff"
    viewer.night = False
    viewer.go_to(3)
    yield 0.3
    click(button(viewer, "\u00d7   Close"))
    yield 0.3
    assert viewer not in popups()
    # closing refreshes the details panel and remembers the page
    for _ in range(20):
        if len(app.d_annotations) == 5:
            break
        yield 0.2
    assert len(app.d_annotations) == 5
    assert app.library.last_page("pasted2024") == 3
    app.open_pdf()
    reopened = top(PdfViewer)
    yield 0.5
    assert reopened.page == 3
    reopened.dismiss()


def s_export_notes():
    app.select_article("pasted2024")
    app.export_notes(["pasted2024"])
    yield BUSY
    choose_in_file_dialog(folder=DATA, filename="notes")
    close_all()
    with open(os.path.join(DATA, "notes.md"), encoding="utf-8") as fh:
        text = fh.read()
    assert "Main claim" in text and "**p. 1, Highlight**" in text and "Compare with Table 2" in text


def s_google_drive():
    import json as _json
    from scilibra.core.gdrive import DriveClient
    from scilibra.gui import drive as drive_mod
    from scilibra.gui.drive import DriveDialog
    from tests.fake_drive import FakeDrive, fake_token
    fake = FakeDrive()
    controller = app.drive
    controller._client = lambda: DriveClient(fake)
    controller.account.sign_in = lambda open_browser=True: fake_token(controller.account.token_file)
    drive_mod.AFTER_CHANGE_DELAY = 0.3
    assert not app.drive_connected
    opened = []
    drive_mod.webbrowser.open = lambda url: opened.append(url)
    drive_button = [w for w in app.root.walk() if w.__class__.__name__ == "DriveButton"][0]
    assert "Google Drive" in [c.text for c in drive_button.children if hasattr(c, "text")]
    # 0) with the OAuth client shipped in the app, users go straight to "Sign in with Google"
    bundled = controller.account.bundled_client
    if os.path.isfile(bundled):
        click(drive_button)
        yield FRAME
        assert top(DriveDialog).state == "signin"
        click(button(top(DriveDialog), "Close"))
        yield FRAME
    # 1) no client shipped (e.g. a fork): every button must react to a real click
    controller.account.bundled_client = ""
    click(drive_button)
    dialog = top(DriveDialog)
    yield FRAME
    assert dialog.state == "setup"
    shot("drive_setup")
    click(button(dialog, "Open Google Cloud Console"))
    assert opened == [drive_mod.CONSOLE_URL], opened
    client_json = os.path.join(DATA, "client_secret_test.json")
    with open(client_json, "w") as fh:
        _json.dump({"installed": {"client_id": "x.apps.googleusercontent.com", "client_secret": "y",
                                  "auth_uri": "a", "token_uri": "t"}}, fh)
    click(button(dialog, "Load client file..."))
    yield FRAME
    file_dialog = top(FileDialog)
    file_dialog.ids.chooser.path = DATA
    file_dialog.ids.chooser.selection = [client_json]
    yield FRAME
    click(button(file_dialog, "Open"))
    yield FRAME
    assert dialog.state == "signin" and top() is dialog
    shot("drive_signin")
    # 2) sign in -> first backup runs
    click(button(dialog, "Sign in with Google"))
    for _ in range(50):
        if app.drive_connected and not controller.syncing and isinstance(popups()[0], MessageDialog):
            break
        yield 0.2
    msg = top(MessageDialog)
    assert "library backed up" in msg.message and "PDFs uploaded" in msg.message, msg.message
    click(button(msg, "Close"))
    yield FRAME
    assert app.drive_connected and dialog.state == "connected" and "scientist@example.com" in dialog.account
    shot("drive_connected")
    click(button(dialog, "Back up now"))
    for _ in range(50):
        if not controller.syncing and isinstance(popups()[0], MessageDialog):
            break
        yield 0.2
    assert "already up to date" in top(MessageDialog).message
    click(button(top(MessageDialog), "Close"))
    yield FRAME
    click(button(dialog, "Open in Google Drive"))
    assert opened[-1].startswith("https://drive.google.com/drive/folders/")
    click(button(dialog, "Close"))
    yield FRAME
    assert dialog not in popups()
    shot("drive_button_green")
    uploaded = {f["name"] for f in fake.files.values()}
    assert {"SciLibra", "PDFs", "Backups", "library.db"} <= uploaded and "smith2020deep.pdf" in uploaded
    # 3) automatic backup after a change
    before = fake.upload_count
    app.select_article("smith2020deep")
    app.add_comment("sync me")
    for _ in range(40):
        if fake.upload_count > before and not controller.syncing:
            break
        yield 0.2
    assert fake.upload_count > before, "automatic backup did not run"
    lib_copy = os.path.join(DATA, "drive_check.db")
    open(lib_copy, "wb").write(fake.content("library.db"))
    import sqlite3
    con = sqlite3.connect(lib_copy)
    assert con.execute("SELECT COUNT(*) FROM comment WHERE articleData='sync me'").fetchone()[0] == 1
    con.close()
    # nothing changed -> the periodic check does not upload again
    before = fake.upload_count
    controller._tick(0)
    yield 0.5
    assert fake.upload_count == before
    # 4) restore on a "new computer"
    current = app.library.path
    controller.restore()
    top(ConfirmDialog).confirm()
    newpc = os.path.join(WORK, "newpc")
    os.makedirs(newpc)
    choose_in_file_dialog(folder=newpc)
    yield BUSY
    msg = top(MessageDialog)
    assert "Restored the library" in msg.message, msg.message
    msg.dismiss()
    assert app.library.path != current and "library-from-drive" in app.library.path
    restored = app.library.get("smith2020deep")
    assert restored.comments[-1] == "sync me" and restored.has_pdf
    assert restored.folderpath == os.path.join(newpc, "SciLibra PDFs")
    app.open_library(current)
    close_all()
    # 5) sign out -> grey again
    click(drive_button)
    yield FRAME
    click(button(top(DriveDialog), "Sign out"))
    yield FRAME
    click(button(top(ConfirmDialog), "Sign out"))
    yield FRAME
    assert not app.drive_connected and top(DriveDialog).state == "signin"
    click(button(top(DriveDialog), "Close"))


def s_viewer_from_annotation_and_bad_pdf():
    app.select_article("alsamman2023alignstatplot")
    yield 0.5
    app.show_annotation(3)  # underline on page 2
    viewer = top(PdfViewer)
    yield 0.8
    assert viewer.page == 2
    viewer.dismiss()
    broken = os.path.join(DATA, "broken.pdf")
    with open(broken, "wb") as fh:
        fh.write(b"%PDF-1.4 this is not really a pdf")
    app.library.set_pdf("doe2019renamed", broken)
    app.select_article("doe2019renamed")
    app.open_pdf()
    viewer = top(PdfViewer)
    yield 0.3
    assert viewer.error and viewer.page_count == 0
    viewer.dismiss()
    app.library.update(app.library.get("doe2019renamed").__class__(**{
        **app.library.get("doe2019renamed").__dict__, "folderpath": "", "pdffile": ""}))


def s_add_pdfs():
    before = app.library.count()
    app.add_pdfs()
    choose_in_file_dialog(path=[NEW_PDF])
    assert isinstance(popups()[0], ProgressDialog)
    yield 0.05
    shot("progress")
    yield BUSY
    msg = top(MessageDialog)
    assert "1 added" in msg.message, msg.message
    yield FRAME
    shot("add_pdfs_report")
    msg.dismiss(animation=False)
    assert app.library.count() == before + 1
    added = [a for a in app.library.articles() if a.key == "Offline_Paper"]
    assert added and added[0].doi == "10.9999/scilibra.test.404", [(a.key, a.doi) for a in added]
    # adding the same PDF again is detected
    app.add_pdfs()
    choose_in_file_dialog(path=[NEW_PDF])
    yield BUSY
    msg = top(MessageDialog)
    assert "0 added, 1 already" in msg.message, msg.message
    msg.dismiss(animation=False)


def s_link_folder():
    assert not app.library.get("smith2020deep").has_pdf
    app.link_pdf_folder()
    choose_in_file_dialog(folder=os.path.join(DATA, "pdfs"))
    yield BUSY
    msg = top(MessageDialog)
    assert "1 articles were linked" in msg.message, msg.message
    msg.dismiss(animation=False)
    assert app.library.get("smith2020deep").has_pdf


def s_missing_pdfs():
    app.show_missing_pdfs()
    keys = {r["key"] for r in rows()}
    assert "doe2019renamed" in keys and "smith2020deep" not in keys and "pasted2024" not in keys
    yield FRAME
    shot("missing_pdfs")
    app.go_back()


def s_duplicates():
    app.library.import_bibtex("@article{dup_copy, title={Deep learning for GWAS: O'Brien's \"method\"}, year={2020}}")
    before = app.library.count()
    app.find_duplicates()
    confirm = top(ConfirmDialog)
    assert "dup_copy" in confirm.message and "smith2020deep" in confirm.message
    yield FRAME
    shot("duplicates")
    confirm.confirm()
    msg = top(MessageDialog)
    msg.dismiss(animation=False)
    assert app.library.count() == before - 1 and app.library.get("smith2020deep") is not None
    app.find_duplicates()
    assert "No duplicate" in top(MessageDialog).message
    close_all()


def s_statistics_help_about():
    app.show_statistics()
    assert "Articles" in top(MessageDialog).message
    yield FRAME
    shot("statistics")
    close_all()
    app.show_help()
    yield FRAME
    shot("help")
    close_all()
    app.show_about()
    close_all()


def s_menus():
    buttons = [w for w in app.root.walk() if getattr(w, "text", "") == "Library"]
    # moving the mouse over a button highlights it (and must not crash)
    Window.mouse_pos = buttons[0].to_window(*buttons[0].center)
    assert buttons[0].hovered
    Window.mouse_pos = (1, 1)
    assert not buttons[0].hovered
    app.open_menu(buttons[0], "library")
    yield FRAME
    from kivy.uix.dropdown import DropDown
    menu = [w for w in Window.children if isinstance(w, DropDown)][0]
    item = [w for w in menu.walk() if getattr(w, "text", "") == "Statistics"][0]
    Window.mouse_pos = item.to_window(*item.center)
    assert item.hovered and not buttons[0].hovered  # only the open menu reacts
    yield FRAME
    shot("library_menu")
    for w in list(Window.children):
        if isinstance(w, DropDown):
            w.dismiss()


def s_export():
    out = os.path.join(DATA, "export.bib")
    app.export_bibtex()
    yield FRAME
    shot("save_dialog")
    choose_in_file_dialog(folder=DATA, filename="export")
    msg = top(MessageDialog)
    assert os.path.exists(out) and "were saved" in msg.message
    msg.dismiss(animation=False)
    # exporting again asks before replacing
    app.export_bibtex()
    choose_in_file_dialog(folder=DATA, filename="export.bib")
    top(ConfirmDialog).confirm()
    close_all()
    # export only the current list
    app.group_choice = "Year"
    click_row("2020")
    app.export_bibtex(only_view=True)
    choose_in_file_dialog(folder=DATA, filename="year2020.bib")
    close_all()
    with open(os.path.join(DATA, "year2020.bib"), encoding="utf-8") as fh:
        text = fh.read()
    assert text.count("@") == 1 and "smith2020deep" in text
    app.group_choice = "All articles"


def s_new_article():
    before = app.library.count()
    app.new_article()
    editor = top(ArticleEditor)
    yield FRAME
    editor.save()
    assert "key is required" in editor.error
    editor.ids.key.text = "manual2025"
    editor.save()
    assert "title is required" in editor.error
    editor.ids.title.text = "Manually added article"
    editor.ids.authors.text = "Last, First\nSecond, Author"
    editor.ids.year.text = "2025"
    editor.save()
    assert app.library.count() == before + 1
    a = app.library.get("manual2025")
    assert a.authors == ["Last, First", "Second, Author"] and app.selected_key == "manual2025"


def s_delete_article():
    app.select_article("manual2025")
    app.delete_article()
    top(ConfirmDialog).dismiss(animation=False)  # cancel keeps it
    assert app.library.get("manual2025") is not None
    app.delete_article()
    yield FRAME
    shot("confirm_delete")
    top(ConfirmDialog).confirm()
    assert app.library.get("manual2025") is None and app.selected_key == ""


def s_no_selection_messages():
    app.select_article("")
    app.edit_article()
    assert "No article selected" in top(MessageDialog).title
    close_all()


def s_delete_all():
    if EXISTING:
        return  # keep the copy of a real library intact
    app.delete_all()
    top(ConfirmDialog).confirm()
    top(ConfirmDialog).confirm()
    assert app.library.count() == 0 and rows() == []
    yield FRAME
    shot("empty_library")


def s_finish():
    yield FRAME
    shot("final")
    app.stop()


STEPS = [s_start, s_import_bibtex, s_select_article, s_group_by_keywords, s_group_by_other_fields, s_keyboard, s_keyboard_events,
         s_edit_article, s_editor_validation_and_picker, s_comments, s_search, s_paste_bibtex, s_attach_pdf,
         s_annotations_in_details, s_pdf_viewer, s_annotate_in_viewer, s_export_notes, s_viewer_from_annotation_and_bad_pdf, s_add_pdfs, s_link_folder, s_missing_pdfs, s_duplicates, s_statistics_help_about, s_google_drive, s_menus, s_export,
         s_new_article, s_delete_article, s_no_selection_messages, s_delete_all, s_finish]
queue = list(STEPS)


def run_step(step):
    """Run a step; generator steps yield FRAME/seconds (let Kivy render) or BUSY (wait for a background task)."""
    name = step.__name__
    started = time.time()

    def fail():
        failures.append(name)
        print(f"FAIL {name}\n{traceback.format_exc()}", flush=True)
        close_all()
        Clock.schedule_once(lambda _dt: next_step(), 0.1)

    def drive(gen):
        try:
            command = next(gen)
        except StopIteration:
            print(f"PASS {name}", flush=True)
            Clock.schedule_once(lambda _dt: next_step(), 0.1)
            return
        except Exception:
            fail()
            return
        if command == BUSY:
            def poll(_dt):
                if app._busy and time.time() - started < 120:
                    Clock.schedule_once(poll, 0.2)
                else:
                    drive(gen)
            Clock.schedule_once(poll, 0.2)
        else:
            Clock.schedule_once(lambda _dt: drive(gen), command)

    try:
        result = step()
    except Exception:
        fail()
        return
    if hasattr(result, "__next__"):
        drive(result)
    else:
        print(f"PASS {name}", flush=True)
        Clock.schedule_once(lambda _dt: next_step(), 0.1)


def next_step():
    if queue:
        run_step(queue.pop(0))


Clock.schedule_once(lambda _dt: next_step(), 1.0)
app.run()
shutil.rmtree(WORK, ignore_errors=True)
print(f"\n{len(STEPS) - len(failures)}/{len(STEPS)} steps passed" + (f"; failed: {failures}" if failures else ""))
sys.exit(1 if failures else 0)
