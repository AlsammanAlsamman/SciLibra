"""Help center: a sidebar of topics, each shown as a page of cards; the last page is "About"."""

from __future__ import annotations

import os
import webbrowser

from kivy.factory import Factory
from kivy.properties import BooleanProperty, ColorProperty, ListProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.modalview import ModalView

from .. import __version__
from . import theme
from .widgets import HoverBehavior

ASSETS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets")
AUTHOR = "Alsamman M. Alsamman"
EMAILS = ["smahmoud@ageri.sci.eg", "A.Alsamman@cgiar.org", "SammanMohammed@gmail.com"]

# Page content. Blocks: ("steps", title, [(heading, text)]), ("card", title, [text, ...]),
# ("keys", title, [(keys, what)]). Text may use Kivy markup ([b]bold[/b]).
PAGES = [
    ("start", "Getting started", "Bring your articles into SciLibra", (0.357, 0.298, 0.878, 1), [
        ("steps", "Four ways to add articles", [
            ("Import a BibTeX file", "[b]Add › Import BibTeX file[/b]. PDFs named [b]<key>.pdf[/b] next to the "
                                     ".bib file are linked automatically."),
            ("Paste BibTeX", "[b]Add › Paste BibTeX[/b] - paste entries copied from Google Scholar or a journal "
                             "website."),
            ("Add PDF files", "[b]Add › Add PDFs[/b] or [b]Add a folder of PDFs[/b]. The DOI is read from each "
                              "PDF and the details are downloaded from Crossref (without internet the PDF title "
                              "is used)."),
            ("Fill in a form", "[b]Add › New article[/b] - type the details yourself, or just a DOI and press "
                               "[b]Fetch details[/b]."),
        ]),
        ("card", "Tip", ["Already have a folder full of PDFs named after their keys? Use "
                         "[b]Library › Link PDF folder[/b] to connect them all at once."]),
    ]),
    ("find", "Finding articles", "Browse, filter and search your library", (0.063, 0.529, 0.608, 1), [
        ("steps", "Three ways to find what you need", [
            ("Group by", "Pick [b]Keywords[/b], [b]Tag groups[/b], [b]Authors[/b], [b]Year[/b] or [b]Journal[/b] "
                         "on the left. Click a group to open it; [b]Back[/b] or [b]Esc[/b] returns."),
            ("Filter this list", "The box above the list narrows it while you type (Ctrl+L)."),
            ("Search", "The search box at the top looks in titles, authors, abstracts, keywords, comments and "
                       "PDF notes (Ctrl+F). Separate several terms with [b];[/b] - tick [b]All terms must "
                       "match[/b] in [b]Options[/b] to require every term."),
        ]),
        ("card", "Shortcuts in the list", ["[b]↑ / ↓[/b] move through the list  ·  [b]Enter[/b] or "
                                          "double-click opens the PDF  ·  [b]Esc[/b] goes back"]),
    ]),
    ("read", "Reading & notes", "The built-in PDF reader and annotations", (0.804, 0.341, 0.176, 1), [
        ("card", "Reading", [
            "[b]Open PDF[/b] (Enter or double-click) opens the article where you stopped last time.",
            "Zoom with Ctrl+wheel, [b]+ / -[/b] or [b]Fit[/b]; find text with Ctrl+F; use [b]Contents[/b] "
            "to jump to a chapter and [b]Night[/b] for dark pages.",
            "[b]External[/b] opens the PDF in your usual PDF application instead.",
        ]),
        ("keys", "Annotation tools (saved inside the PDF)", [
            ("H", "Highlight - drag over text"), ("U", "Underline"), ("S", "Strike out"),
            ("N", "Sticky note - click on the page"), ("B", "Text box"), ("D", "Draw freehand"),
            ("R / O / A", "Rectangle, circle, arrow"), ("E", "Eraser - click an annotation"),
            ("V", "Select - click an annotation to edit or delete it"), ("Ctrl+Z", "Undo"),
        ]),
        ("card", "Selected text", [
            "With the [b]Text[/b] tool (T) select text, then [b]Copy[/b], [b]Copy + citation[/b] "
            "(“...” (Xu et al., 2024, p. 5)), highlight it, or save it as a comment.",
            "The original PDF is backed up before the first change; annotations are visible in any PDF reader.",
        ]),
        ("card", "Notes & comments", [
            "The [b]Notes[/b] panel lists every highlight and note - click one to jump there, "
            "[b]Export notes[/b] writes them as Markdown.",
            "Under the details, [b]Save as comments[/b] copies the PDF notes to the article's comments; "
            "type your own comments in the box and press [b]Add[/b].",
        ]),
    ]),
    ("tools", "Library tools", "Keep your library tidy", (0.188, 0.573, 0.318, 1), [
        ("card", "Library menu", [
            "[b]Link PDF folder[/b] - connect PDFs named <key>.pdf in a folder (and its sub-folders).",
            "[b]Articles without PDF[/b] and [b]Articles with PDF annotations[/b] - quick lists.",
            "[b]Read annotations of all PDFs[/b] - makes your highlights and notes searchable.",
            "[b]Find duplicates[/b], [b]Statistics[/b], [b]Create missing previews[/b].",
            "[b]Export[/b] all articles or just the current list to BibTeX, or your notes to Markdown.",
            "[b]Switch theme[/b] - light or dark.",
        ]),
        ("card", "Editing", [
            "[b]Edit…[/b] changes an article; [b]Pick…[/b] chooses keywords and tag groups that are "
            "already used in your library.",
        ]),
    ]),
    ("drive", "Google Drive backup", "Your library and PDFs, safe in the cloud", (0.216, 0.435, 0.851, 1), [
        ("steps", "Connect once", [
            ("Press Google Drive", "The button at the top right of the main window."),
            ("Sign in with Google", "Your browser opens. Choose your account, tick the box "
                                    "[b]“See, edit, create and delete only the specific Google Drive files you "
                                    "use with this app”[/b] and press [b]Continue[/b]."),
            ("Done", "The button turns green. SciLibra backs up after changes and when you close it."),
        ]),
        ("card", "Good to know", [
            "Everything goes into a [b]SciLibra[/b] folder on your Drive: the library, the PDFs (with your "
            "notes) and a dated copy per day for the last 10 days.",
            "[b]Restore from Drive[/b] sets up the same library on another computer.",
            "SciLibra can only see the files it created - never your other Drive files.",
        ]),
    ]),
    ("keys", "Keyboard shortcuts", "Work faster with the keyboard", (0.741, 0.231, 0.494, 1), [
        ("keys", "Main window", [
            ("Ctrl+F", "Search the library"), ("Ctrl+L", "Filter the list"), ("Ctrl+I", "Import a BibTeX file"),
            ("Ctrl+N", "New article"), ("Ctrl+E", "Edit the article"), ("Ctrl+O / Enter", "Open the PDF"),
            ("↑ / ↓", "Move in the list"), ("Esc", "Back"),
        ]),
        ("keys", "PDF reader", [
            ("PgUp / PgDn", "Previous / next page"), ("Ctrl+wheel, + / -", "Zoom"), ("Ctrl+F", "Find in the PDF"),
            ("Ctrl+Z", "Undo the last annotation"), ("Esc", "Close the reader"),
        ]),
    ]),
]
ABOUT = ("about", "About", "SciLibra and its author", (0.459, 0.337, 0.643, 1))


def _make(name, **props):
    """Create a widget of a KV-defined class; its properties exist only after creation, so set them then."""
    widget = getattr(Factory, name)()
    for key, value in props.items():
        setattr(widget, key, value)
    return widget


class HelpNavItem(HoverBehavior, ButtonBehavior, BoxLayout):
    text = StringProperty("")
    tint = ColorProperty((0, 0, 0, 1))
    selected = BooleanProperty(False)
    page = StringProperty("")


class HelpCenter(ModalView):
    """Help and About in one window (layout: `<HelpCenter>` and the Help* rules in layout.kv)."""
    page = StringProperty("start")
    page_title = StringProperty("")
    page_subtitle = StringProperty("")
    page_tint = ColorProperty(theme.ACCENT)
    library_path = StringProperty("")
    version = StringProperty(__version__)
    nav = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        for pid, title, _sub, tint, *_ in PAGES + [ABOUT]:
            item = HelpNavItem(text=title, tint=tint, page=pid)
            item.bind(on_release=lambda w: self.show(w.page))
            self.ids.nav_box.add_widget(item)
            self.nav.append(item)
        self.show(self.page)

    # open and close instantly, like the other dialogs
    def open(self, *args, **kwargs):
        kwargs.setdefault("animation", False)
        return super().open(*args, **kwargs)

    def dismiss(self, *args, **kwargs):
        kwargs.setdefault("animation", False)
        return super().dismiss(*args, **kwargs)

    def show(self, page):
        self.page = page
        pid, title, subtitle, tint, *rest = next((p for p in PAGES + [ABOUT] if p[0] == page), PAGES[0])
        self.page_title, self.page_subtitle, self.page_tint = title, subtitle, tint
        for item in self.nav:
            item.selected = item.page == pid
        body = self.ids.body
        body.clear_widgets()
        if pid == "about":
            body.add_widget(self._about())
        else:
            for block in rest[0]:
                body.add_widget(self._block(block, tint))
        self.ids.scroll.scroll_y = 1

    def _block(self, block, tint):
        kind, title = block[0], block[1]
        card = _make("HelpCard", title=title)
        if kind == "steps":
            for number, (heading, text) in enumerate(block[2], 1):
                card.ids.content.add_widget(_make("HelpStep", number=str(number), heading=heading, text=text,
                                                             tint=tint))
        elif kind == "keys":
            for keys, what in block[2]:
                card.ids.content.add_widget(_make("HelpKey", keys=keys, text=what))
        else:
            for line in block[2]:
                card.ids.content.add_widget(_make("HelpLine", text=line, tint=tint))
        return card

    def _about(self):
        page = _make("HelpAbout", photo=os.path.join(ASSETS, "author.png"), icon=os.path.join(ASSETS, "icon.png"),
                                 author=AUTHOR, version=__version__, library_path=self.library_path)
        for email in EMAILS:
            chip = _make("HelpChip", text=email)
            chip.bind(on_release=lambda w: webbrowser.open("mailto:" + w.text))
            page.ids.emails.add_widget(chip)
        return page
