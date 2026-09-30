"""Make the README screenshots from a library (a temporary copy; the original is never changed).

    python tools/make_screenshots.py [LIBRARY.db]          # light theme -> docs/screenshots/
    python tools/make_screenshots.py --dark [LIBRARY.db]   # dark theme main window

Without LIBRARY.db your own library (~/.local/share/scilibra/library.db) is used.
"""

import os
import shutil
import sys
import tempfile

DARK = "--dark" in sys.argv
os.environ["KIVY_NO_ARGS"] = "1"
os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")
os.environ.setdefault("KCFG_GRAPHICS_WINDOW_STATE", "hidden")
if DARK:
    os.environ["SCILIBRA_THEME"] = "dark"
    os.environ["SCILIBRA_NO_SPLASH"] = "1"

from kivy.config import Config  # noqa: E402

Config.set("graphics", "width", "1400")
Config.set("graphics", "height", "860")

from kivy.clock import Clock  # noqa: E402
from kivy.core.window import Window  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "docs", "screenshots")
WORK = tempfile.mkdtemp(prefix="scilibra-shots-")

from scilibra.config import default_library_path  # noqa: E402

# resolve the source library first, then give the app its own empty data folder (settings, sign-in)
SOURCE = os.path.abspath(next((a for a in sys.argv[1:] if not a.startswith("--")), "") or default_library_path())
os.environ["SCILIBRA_HOME"] = os.path.join(WORK, "home")

from scilibra.core.library import Library  # noqa: E402
from scilibra.gui.app import SciLibraApp  # noqa: E402

# ---------------------------------------------------------------- library
def pick_featured(lib):
    """An article with a PDF, preferably one with highlights/notes (to show off the reader)."""
    rows = lib.db._conn.execute("SELECT ID, count(*) n FROM pdfannotations GROUP BY ID ORDER BY n DESC").fetchall()
    for key, _n in rows:
        a = lib.get(key)
        if a is not None and a.has_pdf:
            return key
    return next(a.key for a in lib.articles() if a.has_pdf)


# ---------------------------------------------------------------- capture
LIB = os.path.join(WORK, "library.db")
shutil.copy2(SOURCE, LIB)
_lib = Library(LIB)
FEATURED = pick_featured(_lib)
_lib.close()
print("library:", SOURCE, "featured:", FEATURED)
os.makedirs(OUT, exist_ok=True)
app = SciLibraApp(library_path=LIB)


def shot(name):
    Window.screenshot(os.path.join(WORK, name + ".png"))
    produced = os.path.join(WORK, name + "0001.png")
    shutil.move(produced, os.path.join(OUT, name + ".png"))
    print("saved", name)


def steps():
    if not DARK:
        yield 0.55
        shot("splash")
    while app.splash is not None:
        yield 0.1
    app.select_article(FEATURED)
    yield 0.6
    if DARK:
        shot("main-dark")
        return
    shot("main")
    app.group_choice = "Keywords"
    yield 0.5
    shot("groups")
    app.open_viewer(app.library.get(FEATURED))
    yield 1.2
    viewer = Window.children[0]
    if viewer.panel != "annotations":
        viewer.toggle_panel("annotations")
    yield 0.8
    shot("reader")
    viewer.dismiss()
    yield 0.4
    app.show_help("read")
    yield 0.5
    shot("help")
    Window.children[0].show("about")
    yield 0.5
    shot("about")


def run(gen):
    try:
        delay = next(gen)
    except StopIteration:
        app.stop()
        return
    Clock.schedule_once(lambda _dt: run(gen), delay)


Clock.schedule_once(lambda _dt: run(steps()), 0.1)
app.run()
shutil.rmtree(WORK, ignore_errors=True)
