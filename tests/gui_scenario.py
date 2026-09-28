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

OUT = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "gui-shots")
EXISTING = sys.argv[2] if len(sys.argv) > 2 else ""
os.makedirs(OUT, exist_ok=True)
WORK = tempfile.mkdtemp(prefix="scilibra-gui-")
os.environ["SCILIBRA_HOME"] = os.path.join(WORK, "home")

from scilibra.gui.app import SciLibraApp  # noqa: E402
from scilibra.gui.dialogs import (ConfirmDialog, FileDialog, MessageDialog, ProgressDialog,  # noqa: E402
                                  TextDialog, ValuePicker)
from scilibra.gui.editor import ArticleEditor  # noqa: E402

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
    assert "pasted2024" in keys and "smith2020deep" not in keys
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
    app.open_menu(buttons[0], "library")
    yield FRAME
    shot("library_menu")
    from kivy.uix.dropdown import DropDown
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
         s_add_pdfs, s_link_folder, s_missing_pdfs, s_duplicates, s_statistics_help_about, s_menus, s_export,
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
