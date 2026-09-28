"""The SciLibra Kivy application."""

from __future__ import annotations

import io
import logging
import os
import subprocess
import sys
import threading
import webbrowser

from kivy.app import App
from kivy.clock import Clock, mainthread
from kivy.core.clipboard import Clipboard
from kivy.core.image import Image as CoreImage
from kivy.core.window import Window
from kivy.factory import Factory
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import BooleanProperty, ListProperty, NumericProperty, ObjectProperty, StringProperty
from kivy.uix.behaviors import ButtonBehavior
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.checkbox import CheckBox
from kivy.uix.dropdown import DropDown
from kivy.uix.label import Label
from kivy.uix.widget import Widget
from kivy.uix.recycleview.views import RecycleDataViewBehavior
from kivy.utils import escape_markup

from .. import __version__
from ..config import Settings, resolve_library_path
from ..core import bibtex, crossref
from ..core.library import GROUP_FIELDS, SEARCH_FIELDS, Library
from ..core.models import Article
from . import theme
from .dialogs import ConfirmDialog, FileDialog, MessageDialog, ProgressDialog, TextDialog, ValuePicker
from .editor import ArticleEditor

log = logging.getLogger(__name__)
HERE = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(os.path.dirname(HERE), "assets")
ALL_ARTICLES = "All articles"
GROUP_CHOICES = [ALL_ARTICLES] + list(GROUP_FIELDS)


class ListRow(RecycleDataViewBehavior, ButtonBehavior, BoxLayout):
    """A row in the library list: either a group ("GWAS  12") or an article."""
    index = None
    kind = StringProperty("article")
    title = StringProperty("")
    subtitle = StringProperty("")
    count = StringProperty("")
    selected = BooleanProperty(False)
    has_pdf = BooleanProperty(True)

    def refresh_view_attrs(self, rv, index, data):
        self.index = index
        return super().refresh_view_attrs(rv, index, data)

    def on_release(self):
        App.get_running_app().on_row(self.index)

    def on_touch_down(self, touch):
        if touch.is_double_tap and self.kind == "article" and self.collide_point(*touch.pos):
            app = App.get_running_app()
            Clock.schedule_once(lambda _dt: app.open_pdf(), 0.05)
        return super().on_touch_down(touch)


class CommentRow(BoxLayout):
    text = StringProperty("")


class View:
    """What the left-hand list currently shows."""

    def __init__(self, mode, title, table=None, keys=None):
        self.mode = mode      # "groups" or "articles"
        self.title = title    # breadcrumb text
        self.table = table    # sub table for "groups"
        self.keys = keys      # article keys for "articles" (None = all)


class SciLibraApp(App):
    title = "SciLibra"
    library = ObjectProperty(None, allownone=True)
    status = StringProperty("")
    library_info = StringProperty("")
    breadcrumb = StringProperty("")
    can_go_back = BooleanProperty(False)
    group_choice = StringProperty(ALL_ARTICLES)
    group_choices = ListProperty(GROUP_CHOICES)
    selected_key = StringProperty("")
    list_count = NumericProperty(0)
    search_fields = ListProperty([])       # empty = all fields
    search_all_terms = BooleanProperty(False)
    search_labels = ListProperty(list(SEARCH_FIELDS))
    # details panel
    d_title = StringProperty("")
    d_meta = StringProperty("")
    d_body = StringProperty("")
    d_pdf = StringProperty("")
    d_has_pdf = BooleanProperty(False)
    d_comments = ListProperty([])
    d_thumb = ObjectProperty(None, allownone=True)

    def __init__(self, library_path: str = "", **kwargs):
        super().__init__(**kwargs)
        self.explicit_library = library_path
        self.settings = Settings.load()
        self.view: View | None = None
        self.history: list[View] = []
        self.rows: list[dict] = []
        self._busy = False

    # ------------------------------------------------------------------ lifecycle
    def build(self):
        self.icon = os.path.join(ASSETS, "icon.png")
        Window.clearcolor = (0.105, 0.115, 0.135, 1)
        Window.minimum_width, Window.minimum_height = dp(900), dp(560)
        Builder.load_file(os.path.join(HERE, "layout.kv"))
        root = Builder.load_string("SciLibraRoot:")
        Window.bind(on_key_down=self._on_key_down)
        return root

    def on_start(self):
        path, message = resolve_library_path(self.settings, self.explicit_library)
        self.open_library(path, notice=message)

    def on_stop(self):
        if self.library:
            self.library.close()

    def open_library(self, path: str, notice: str = ""):
        try:
            library = Library(path)
        except Exception as exc:  # corrupt / unreadable file
            log.exception("Cannot open library")
            self.message("Cannot open library", f"{path}\n\n{exc}")
            return
        if self.library:
            self.library.close()
        self.library = library
        self.settings.remember_library(path)
        self.settings.save()
        if library.db.backup_path:
            notice = (notice + "\n\n" if notice else "") + (
                "The library was upgraded to the new format. A backup of the previous version was saved as:\n"
                + library.db.backup_path)
        self.history = []
        self.group_choice = ALL_ARTICLES
        self.select_article("")
        self.show_view(View("articles", ALL_ARTICLES), remember=False)
        self.set_status(f"Opened {os.path.basename(path)}")
        if notice:
            self.message("Welcome to SciLibra " + __version__, notice)

    # ------------------------------------------------------------------ helpers
    def set_status(self, text: str):
        self.status = text
        if self.library:
            self.library_info = f"{self.library.count()} articles  ·  {self.library.path}"

    def message(self, title: str, text: str):
        MessageDialog(title=title, message=text).open()

    def confirm(self, title, text, action, confirm_text="OK", danger=False):
        ConfirmDialog(title=title, message=text, action=action, confirm_text=confirm_text, danger=danger).open()

    def choose_file(self, title, callback, filters=None, multiselect=False, start=None):
        FileDialog(title=title, mode="open", filters=filters or [], multiselect=multiselect,
                   path=start or self.settings.start_folder(), confirm_text="Open",
                   callback=self._remember_folder(callback)).open()

    def choose_folder(self, title, callback):
        FileDialog(title=title, mode="folder", path=self.settings.start_folder(), confirm_text="Use this folder",
                   callback=self._remember_folder(callback)).open()

    def choose_save(self, title, callback, filename=""):
        FileDialog(title=title, mode="save", filename=filename, filters=["*.bib"], path=self.settings.start_folder(),
                   confirm_text="Save", callback=self._remember_folder(callback)).open()

    def _remember_folder(self, callback):
        def wrapped(result, folder):
            self.settings.last_folder = folder
            self.settings.save()
            callback(result, folder)
        return wrapped

    def pick_values(self, title, table, current, done):
        ValuePicker(title=title, values=self.library.groups(table), selected=list(current), callback=done).open()

    def run_in_background(self, title, work, done):
        """Run work(progress) in a thread with a progress dialog; done(result) runs on the UI thread."""
        if self._busy:
            self.message("Please wait", "Another task is still running.")
            return
        self._busy = True
        dialog = ProgressDialog(title=title, message="Starting...")
        dialog.open()

        def runner():
            try:
                result, error = work(dialog), None
            except Exception as exc:  # report instead of crashing the UI
                log.exception("Background task failed")
                result, error = None, exc
            finish(result, error)

        @mainthread
        def finish(result, error):
            self._busy = False
            dialog.dismiss()
            if error is not None:
                self.message("Something went wrong", str(error))
            else:
                done(result)
        threading.Thread(target=runner, daemon=True).start()

    # ------------------------------------------------------------------ list / navigation
    def on_group_choice(self, _inst, value):
        if not self.library:
            return
        self.history = []
        if value == ALL_ARTICLES:
            self.show_view(View("articles", ALL_ARTICLES), remember=False)
        else:
            table = GROUP_FIELDS[value]
            self.show_view(View("groups", value, table=table), remember=False)

    def show_view(self, view: View, remember=True):
        if remember and self.view is not None:
            self.history.append(self.view)
        self.view = view
        self.can_go_back = bool(self.history)
        self.breadcrumb = view.title
        if self.root:
            self.root.ids.list_filter.text = ""
        self.refresh_list()

    def go_back(self):
        if self.history:
            self.view = self.history.pop()
            self.can_go_back = bool(self.history)
            self.breadcrumb = self.view.title
            self.root.ids.list_filter.text = ""
            self.refresh_list()

    def refresh_list(self, *_):
        if not self.library or not self.view:
            self.rows = []
        elif self.view.mode == "groups":
            self.rows = [{"kind": "group", "title": value, "subtitle": "", "count": str(count),
                          "value": value, "has_pdf": True, "height": dp(40)}
                         for value, count in self.library.groups(self.view.table)]
        else:
            if self.view.keys is None:
                articles = self.library.articles()
            else:
                existing = self.library.articles(self.view.keys)
                articles = sorted(existing, key=lambda a: a.title.lower()) if self.view.mode == "articles" else existing
                self.view.keys = [a.key for a in existing]
            self.rows = [self._article_row(a) for a in articles]
        self.apply_filter()
        self.set_status(self.status)

    @staticmethod
    def _article_row(a: Article) -> dict:
        bits = [b for b in (a.short_authors, a.year, a.journal) if b]
        return {"kind": "article", "title": a.title or a.key, "subtitle": "  ·  ".join(bits), "count": "",
                "key": a.key, "has_pdf": a.has_pdf, "height": dp(56)}

    def apply_filter(self, *_):
        needle = self.root.ids.list_filter.text.strip().lower() if self.root else ""
        rows = [r for r in self.rows if not needle or needle in (r["title"] + " " + r["subtitle"]).lower()
                or needle in r.get("key", "").lower()]
        for r in rows:
            r["selected"] = r.get("key") == self.selected_key and r["kind"] == "article"
        self.list_count = len(rows)
        if self.root:
            self.root.ids.rv.data = rows
            self.root.ids.rv.refresh_from_data()

    def on_row(self, index):
        rows = self.root.ids.rv.data
        if index is None or index >= len(rows):
            return
        row = rows[index]
        if row["kind"] == "group":
            keys = self.library.keys_in_group(self.view.table, row["value"])
            self.show_view(View("articles", f"{self.view.title}  ›  {row['value']}", keys=keys))
        else:
            self.select_article(row["key"])

    def move_selection(self, step):
        rows = self.root.ids.rv.data
        keys = [r.get("key") for r in rows]
        if not rows or rows[0]["kind"] != "article":
            return
        i = keys.index(self.selected_key) + step if self.selected_key in keys else 0
        i = max(0, min(len(rows) - 1, i))
        self.select_article(keys[i])
        rv = self.root.ids.rv
        if len(rows) > 1:
            rv.scroll_y = 1 - i / (len(rows) - 1)

    # ------------------------------------------------------------------ details panel
    def select_article(self, key: str):
        self.selected_key = key or ""
        article = self.library.get(key) if (key and self.library) else None
        if article is None:
            self.selected_key = ""
            self.d_title = self.d_meta = self.d_body = self.d_pdf = ""
            self.d_has_pdf = False
            self.d_comments = []
            self.d_thumb = None
        else:
            self._show_details(article)
        if self.root:
            for r in self.root.ids.rv.data:
                r["selected"] = r.get("key") == self.selected_key and r["kind"] == "article"
            self.root.ids.rv.refresh_from_data()

    def _show_details(self, a: Article):
        e = escape_markup
        self.d_title = e(a.title or a.key)
        venue = ", ".join(p for p in (a.journal, a.volume and f"vol. {a.volume}",
                                      a.number and f"no. {a.number}", a.pages and f"pp. {a.pages}") if p)
        meta = []
        if a.authors:
            meta.append(e("; ".join(a.authors)))
        if venue:
            meta.append(f"[i]{e(venue)}[/i]" + (f"  ({a.year})" if a.year else ""))
        elif a.year:
            meta.append(a.year)
        self.d_meta = "\n".join(meta)

        body = [f"[b]Key[/b]   {e(a.key)}     [b]Type[/b]   {e(a.entry_type)}"]
        if a.doi:
            body.append(f"[b]DOI[/b]   [ref=doi][color=6fa8ff][u]{e(a.doi)}[/u][/color][/ref]")
        if a.url:
            body.append(f"[b]URL[/b]   [ref=url][color=6fa8ff][u]{e(a.url)}[/u][/color][/ref]")
        if a.publisher:
            body.append(f"[b]Publisher[/b]   {e(a.publisher)}")
        if a.keywords:
            body.append(f"[b]Keywords[/b]   {e(', '.join(a.keywords))}")
        if a.taggroups:
            body.append(f"[b]Tag groups[/b]   {e(', '.join(a.taggroups))}")
        if a.date_added:
            body.append(f"[b]Added[/b]   {e(a.date_added[:16])}")
        if a.abstract:
            body.append(f"\n[b]Abstract[/b]\n{e(a.abstract)}")
        self.d_body = "\n".join(body)
        self.d_has_pdf = a.has_pdf
        if a.has_pdf:
            self.d_pdf = e(a.pdf_path)
        elif a.pdf_path:
            self.d_pdf = "[color=ff8080]PDF not found:[/color] " + e(a.pdf_path)
        else:
            self.d_pdf = "[color=ffb060]No PDF attached[/color]"
        self.d_comments = list(a.comments)
        self.d_thumb = self._texture(self.library.thumbnail(a.key))

    @staticmethod
    def _texture(data):
        if not data:
            return None
        try:
            return CoreImage(io.BytesIO(data), ext="png").texture
        except Exception:
            return None

    def on_ref(self, ref):
        a = self.library.get(self.selected_key)
        if not a:
            return
        if ref == "doi" and a.doi:
            webbrowser.open("https://doi.org/" + a.doi)
        elif ref == "url" and a.url:
            webbrowser.open(a.url)

    def _need_selection(self) -> Article | None:
        a = self.library.get(self.selected_key) if self.selected_key else None
        if a is None:
            self.message("No article selected", "Select an article in the list first.")
        return a

    # ------------------------------------------------------------------ article actions
    def open_pdf(self):
        a = self._need_selection()
        if not a:
            return
        if not a.has_pdf:
            self.confirm("PDF not found", "This article has no PDF file linked (or the file was moved).\n\n"
                         "Do you want to choose the PDF now?", self.attach_pdf, confirm_text="Choose PDF...")
            return
        open_with_system(a.pdf_path)
        self.set_status(f"Opened {os.path.basename(a.pdf_path)}")

    def open_folder(self):
        a = self._need_selection()
        if a and a.folderpath and os.path.isdir(a.folderpath):
            open_with_system(a.folderpath)

    def attach_pdf(self):
        a = self._need_selection()
        if not a:
            return

        def chosen(path, _folder):
            self.library.set_pdf(a.key, path)
            self.refresh_list()
            self.select_article(a.key)
            self.set_status(f"Attached {os.path.basename(path)} to {a.key}")
        self.choose_file(f"Choose the PDF for '{a.key}'", chosen, filters=["*.pdf", "*.PDF"])

    def edit_article(self):
        a = self._need_selection()
        if a:
            ArticleEditor(article=a, app=self, save_callback=self._save_edit).open()

    def new_article(self):
        ArticleEditor(article=None, app=self, save_callback=self._save_new).open()

    def _save_edit(self, article, old_key):
        try:
            self.library.update(article, old_key=old_key)
        except ValueError as exc:
            return str(exc)
        self.refresh_list()
        self.select_article(article.key)
        self.set_status(f"Saved {article.key}")
        return None

    def _save_new(self, article, _old_key):
        if not self.library.add(article):
            return f"An article with key '{article.key}' already exists."
        self.refresh_list()
        self.select_article(article.key)
        self.set_status(f"Added {article.key}")
        return None

    def delete_article(self):
        a = self._need_selection()
        if not a:
            return

        def do_delete():
            self.library.delete([a.key])
            self.select_article("")
            self.refresh_list()
            self.set_status(f"Deleted {a.key}")
        self.confirm("Delete article", f"Delete '{a.title or a.key}' from the library?\n\n"
                     "The PDF file itself is not deleted.", do_delete, confirm_text="Delete", danger=True)

    def copy_bibtex(self):
        a = self._need_selection()
        if a:
            text = bibtex.article_to_bibtex(a)
            try:
                Clipboard.copy(text)
                self.set_status(f"Copied BibTeX for {a.key} to the clipboard")
            except Exception:
                self.message("BibTeX", text)

    def add_comment(self, text):
        if not self.selected_key:
            return
        if self.library.add_comment(self.selected_key, text):
            self.root.ids.comment_input.text = ""
            self.select_article(self.selected_key)
            self.set_status("Comment added")

    def remove_comment(self, text):
        key = self.selected_key

        def do_remove():
            self.library.remove_comment(key, text)
            self.select_article(key)
            self.set_status("Comment removed")
        self.confirm("Remove comment", f"Remove this comment?\n\n{text}", do_remove, confirm_text="Remove", danger=True)

    # ------------------------------------------------------------------ adding articles
    def import_bibtex_file(self):
        def chosen(path, _folder):
            try:
                report = self.library.import_bibtex_file(path)
            except OSError as exc:
                self.message("Cannot read file", str(exc))
                return
            self._after_import("Import BibTeX", report)
        self.choose_file("Import a BibTeX file", chosen, filters=["*.bib", "*.bibtex", "*.txt"])

    def paste_bibtex(self):
        def imported(text):
            if not text.strip():
                return False
            report = self.library.import_bibtex(text)
            self._after_import("Paste BibTeX", report)
            return None
        TextDialog(title="Paste BibTeX", confirm_text="Import",
                   hint="Paste one or more BibTeX entries here, e.g.\n\n@article{smith2020deep,\n"
                        "  title = {Deep learning for GWAS},\n  author = {Smith, John and Doe, Jane},\n"
                        "  journal = {Genome Biology},\n  year = {2020}\n}",
                   info="Tip: after importing, use Library › Link PDF folder, or the Attach PDF button, "
                        "to connect the PDF files.",
                   action=imported).open()

    def _after_import(self, title, report):
        self.refresh_list()
        if len(report.added) == 1:
            self.select_article(report.added[0])
        lines = [report.summary().capitalize() + "."]
        if report.skipped:
            lines.append("\nAlready in the library (not changed):\n  " + "\n  ".join(report.skipped[:30]))
            if len(report.skipped) > 30:
                lines.append(f"  ... and {len(report.skipped) - 30} more")
        if report.failed:
            lines.append("\nCould not be read (check the BibTeX syntax):\n  " + "\n  ".join(report.failed[:30]))
        lines += report.notes
        self.set_status(f"{title}: {report.summary()}")
        self.message(title, "\n".join(lines))

    def add_pdfs(self):
        def chosen(paths, _folder):
            self._import_pdfs(paths if isinstance(paths, list) else [paths])
        self.choose_file("Choose PDF files (select several with Ctrl/Shift-click)", chosen,
                         filters=["*.pdf", "*.PDF"], multiselect=True)

    def add_pdf_folder(self):
        def chosen(folder, _parent):
            pdfs = sorted(os.path.join(root, f) for root, _d, files in os.walk(folder)
                          for f in files if f.lower().endswith(".pdf"))
            if not pdfs:
                self.message("No PDFs", f"No PDF files were found in\n{folder}")
                return
            self._import_pdfs(pdfs)
        self.choose_folder("Choose a folder of PDFs to add (sub-folders included)", chosen)

    def _import_pdfs(self, paths):
        library = self.library

        def work(progress):
            online = crossref.is_online()
            added, skipped, notes = [], [], []
            for i, path in enumerate(paths):
                if progress.cancelled:
                    notes.append("Cancelled.")
                    break
                progress.update(i, len(paths), f"{i + 1}/{len(paths)}: {os.path.basename(path)}")
                article, note = library.article_from_pdf(path, online=online)
                key = library.add_pdf_article(article)
                if key:
                    added.append(key)
                    notes.append(f"{os.path.basename(path)} -> {key}: {note}")
                else:
                    skipped.append(os.path.basename(path))
            progress.update(len(paths), len(paths), "Done")
            return added, skipped, notes, online

        def done(result):
            added, skipped, notes, online = result
            self.refresh_list()
            if len(added) == 1:
                self.select_article(added[0])
            text = f"{len(added)} added, {len(skipped)} already in the library."
            if not online:
                text += "\n\nNo internet connection: titles were taken from the PDF files. " \
                        "Use Edit › Fetch from DOI later to complete them."
            if skipped:
                text += "\n\nAlready in the library:\n  " + "\n  ".join(skipped[:30])
            if notes:
                text += "\n\nDetails:\n" + "\n".join(notes[:200])
            self.set_status(f"Add PDFs: {len(added)} added")
            self.message("Add PDFs", text)
        self.run_in_background("Adding PDFs", work, done)

    # ------------------------------------------------------------------ library actions
    def link_pdf_folder(self):
        library = self.library

        def chosen(folder, _parent):
            def work(progress):
                progress.update(0, 1, "Scanning for PDFs named <key>.pdf ...")
                return library.link_pdf_folders([folder])

            def done(result):
                linked, unmatched = result
                self.refresh_list()
                if self.selected_key:
                    self.select_article(self.selected_key)
                text = f"{len(linked)} articles were linked to PDFs in\n{folder}"
                if unmatched:
                    text += (f"\n\n{len(unmatched)} PDFs did not match any article key "
                             "(use Add › Add PDFs to add them as new articles):\n  "
                             + "\n  ".join(os.path.basename(p) for p in unmatched[:40]))
                self.set_status(f"Linked {len(linked)} PDFs")
                self.message("Link PDF folder", text)
            self.run_in_background("Linking PDFs", work, done)
        self.choose_folder("Choose a folder containing PDFs named <key>.pdf (sub-folders included)", chosen)

    def export_bibtex(self, only_view=False):
        keys = None
        if only_view:
            keys = [r["key"] for r in self.root.ids.rv.data if r["kind"] == "article"]
            if not keys:
                self.message("Nothing to export", "The list does not show any articles.")
                return

        def chosen(path, _folder):
            if not path.lower().endswith(".bib"):
                path += ".bib"

            def write():
                n = self.library.export_bibtex(path, keys=keys)
                self.set_status(f"Exported {n} articles to {path}")
                self.message("Export BibTeX", f"{n} articles were saved to\n{path}")
            if os.path.exists(path):
                self.confirm("Replace file?", f"{path}\nalready exists. Replace it?", write, confirm_text="Replace")
            else:
                write()
        self.choose_save("Export BibTeX", chosen, filename="library.bib")

    def show_statistics(self):
        stats = self.library.statistics()
        width = max(len(k) for k in stats)
        self.message("Library statistics", "\n".join(f"{k:<{width}}   {v}" for k, v in stats.items()))

    def show_missing_pdfs(self):
        missing = self.library.missing_pdfs()
        if not missing:
            self.message("Articles without PDF", "Every article has a PDF file.")
            return
        self.show_view(View("articles", f"Without PDF ({len(missing)})", keys=[a.key for a in missing]))
        self.set_status(f"{len(missing)} articles have no PDF - select one and press Attach PDF, "
                        "or use Link PDF folder")

    def find_duplicates(self):
        groups = self.library.find_duplicates()
        if not groups:
            self.message("Duplicates", "No duplicate articles were found (same DOI or same title).")
            return
        lines = []
        for g in groups:
            lines.append(f"• keep  {g[0].key}" + ("  (has PDF)" if g[0].has_pdf else ""))
            lines += [f"    remove  {o.key}" for o in g[1:]]
        removable = sum(len(g) - 1 for g in groups)
        self.show_view(View("duplicates", f"Duplicates ({len(groups)} groups)",
                            keys=[a.key for g in groups for a in g]))

        def remove():
            removed = self.library.remove_duplicates(groups)
            self.go_back()
            self.select_article("")
            self.set_status(f"Removed {len(removed)} duplicates")
            self.message("Duplicates removed", f"{len(removed)} duplicate articles were removed. Comments, keywords "
                                               "and tag groups were merged into the kept article.")
        self.confirm("Duplicates found",
                     f"{len(groups)} groups of duplicates (same DOI or title). The list now shows them.\n"
                     "Only library entries are removed - PDF files are never deleted.\n\n"
                     f"Remove {removable} duplicates? For each group the best copy is kept (with PDF, "
                     "comments and most details); comments, keywords and tag groups are merged into it.\n\n"
                     + "\n".join(lines[:60]), remove, confirm_text=f"Remove {removable}", danger=True)

    def refresh_thumbnails(self):
        library = self.library

        def work(progress):
            return library.refresh_thumbnails(force=False, progress=lambda i, n: progress.update(
                i, n, f"Creating preview {i}/{n}"))

        def done(made):
            if self.selected_key:
                self.select_article(self.selected_key)
            self.message("Previews", f"{made} first-page previews were created.")
        self.run_in_background("Creating previews", work, done)

    def search(self, text=None):
        query = (text if text is not None else self.root.ids.search.text).strip()
        if not query:
            return
        fields = self.search_fields or None
        result = self.library.search(query, fields=fields, match_all=self.search_all_terms)
        self.show_view(View("search", f"Search: {query}  ({len(result.keys)})", keys=result.keys))
        if result.keys:
            per_term = []
            for term, hits in result.hits.items():
                if hits:
                    per_term.append(f"'{term}': " + ", ".join(f"{k} {v}" for k, v in hits.items()))
            self.set_status(" | ".join(per_term) or f"{len(result.keys)} results")
        else:
            self.set_status(f"No results for '{query}'")

    def search_options(self):
        def left_label(text, color=theme.TEXT, **kwargs):
            label = Label(text=text, color=color, halign="left", valign="middle", **kwargs)
            label.bind(size=lambda w, size: setattr(w, "text_size", size))
            return label

        box = BoxLayout(orientation="vertical", spacing=dp(6))
        box.add_widget(left_label("Search in:", theme.MUTED, size_hint_y=None, height=dp(24)))
        chosen = set(self.search_fields or SEARCH_FIELDS)
        for label in SEARCH_FIELDS:
            row = BoxLayout(size_hint_y=None, height=dp(30))
            check = CheckBox(active=label in chosen, size_hint_x=None, width=dp(36))
            check.bind(active=lambda _c, value, name=label: self.toggle_search_field(name, value))
            row.add_widget(check)
            row.add_widget(left_label(label))
            box.add_widget(row)
        row = BoxLayout(size_hint_y=None, height=dp(36))
        every = CheckBox(active=self.search_all_terms, size_hint_x=None, width=dp(36))
        every.bind(active=lambda _c, value: setattr(self, "search_all_terms", value))
        row.add_widget(every)
        row.add_widget(left_label("All terms must match (terms are separated by ';')"))
        box.add_widget(row)
        close = Factory.AccentButton(text="Done")
        box.add_widget(close)
        popup = Factory.BasePopup(title="Search options", content=box, size_hint=(None, None),
                                  size=(dp(440), dp(560)))
        close.bind(on_release=lambda *_: popup.dismiss())
        popup.open()

    def open_menu(self, button, name):
        menu = DropDown(auto_width=False, width=dp(300))
        for label, action in MENUS[name]:
            if label is None:
                menu.add_widget(Widget(size_hint_y=None, height=dp(6)))
                continue
            item = Factory.FlatButton(text=label, halign="left", bg=theme.INPUT, height=dp(38))
            item.bind(size=lambda w, _s: setattr(w, "text_size", (w.width - dp(24), None)))
            item.bind(on_release=lambda _b, act=action: (menu.dismiss(), Clock.schedule_once(
                lambda _dt: self._run_action(act), 0.05)))
            menu.add_widget(item)
        menu.open(button)

    def _run_action(self, action):
        if action == "export_view":
            self.export_bibtex(only_view=True)
        else:
            getattr(self, action)()

    def on_d_comments(self, _inst, comments):
        if not self.root:
            return
        box = self.root.ids.comments_box
        box.clear_widgets()
        for text in comments:
            box.add_widget(CommentRow(text=text))

    def toggle_search_field(self, label, active):
        fields = set(self.search_fields or SEARCH_FIELDS)
        if active:
            fields.add(label)
        else:
            fields.discard(label)
        self.search_fields = [f for f in SEARCH_FIELDS if f in fields]

    def open_library_file(self):
        def chosen(path, _folder):
            self.open_library(path)
        self.choose_file("Open a SciLibra library (.db)", chosen, filters=["*.db"])

    def new_library_file(self):
        def chosen(path, _folder):
            if not path.lower().endswith(".db"):
                path += ".db"
            if os.path.exists(path):
                self.message("File exists", "Choose a new file name for the new library.")
                return
            self.open_library(path)
        FileDialog(title="Create a new library", mode="save", filename="library.db", filters=["*.db"],
                   path=self.settings.start_folder(), confirm_text="Create",
                   callback=self._remember_folder(chosen)).open()

    def delete_all(self):
        n = self.library.count()

        def really():
            self.library.delete_all()
            self.select_article("")
            self.history = []
            self.show_view(View("articles", ALL_ARTICLES), remember=False)
            self.set_status("All articles deleted")

        def second():
            self.confirm("Are you sure?", f"This permanently removes {n} articles and their comments.\n"
                         "Tip: use Library › Export BibTeX first to keep a copy.", really,
                         confirm_text=f"Delete {n} articles", danger=True)
        self.confirm("Delete all articles", f"Delete all {n} articles from this library?\nPDF files are not deleted.",
                     second, confirm_text="Continue...", danger=True)

    def show_about(self):
        self.message("About SciLibra", f"SciLibra {__version__}\n\n"
                     "Free and open-source manager for scientific articles.\n\n"
                     "Created by Alsamman M. Alsamman\n"
                     "smahmoud [at] ageri.sci.eg  ·  A.Alsamman [at] cgiar.org  ·  SammanMohammed [at] gmail.com\n\n"
                     "License: MIT - https://opensource.org/licenses/MIT\n"
                     "https://github.com/AlsammanAlsamman/SciLibra\n\n"
                     f"Library file: {self.library.path if self.library else '-'}")

    def show_help(self):
        self.message("How to use SciLibra", HELP_TEXT)

    # ------------------------------------------------------------------ keyboard
    def _on_key_down(self, _window, key, _scancode, codepoint, modifiers):
        if self.root is None or Window.children and Window.children[0] is not self.root:
            return False  # a popup is open
        ctrl = "ctrl" in modifiers or "meta" in modifiers
        typing = any(getattr(w, "focus", False) for w in (self.root.ids.search, self.root.ids.list_filter,
                                                          self.root.ids.comment_input))
        if ctrl and codepoint == "f":
            self.root.ids.search.focus = True
            return True
        if ctrl and codepoint == "l":
            self.root.ids.list_filter.focus = True
            return True
        if ctrl and codepoint == "i":
            self.import_bibtex_file()
            return True
        if ctrl and codepoint == "n":
            self.new_article()
            return True
        if ctrl and codepoint == "e":
            self.edit_article()
            return True
        if ctrl and codepoint == "o":
            self.open_pdf()
            return True
        if typing:
            return False
        if key == 27:  # Escape: go back instead of quitting
            self.go_back()
            return True
        if key in (273, 274):  # up / down
            self.move_selection(-1 if key == 273 else 1)
            return True
        if key == 13:  # Enter
            self.open_pdf()
            return True
        return False


MENUS = {
    "add": [
        ("Import BibTeX file...   Ctrl+I", "import_bibtex_file"),
        ("Paste BibTeX...", "paste_bibtex"),
        (None, None),
        ("Add PDF files (details from DOI)...", "add_pdfs"),
        ("Add a folder of PDFs...", "add_pdf_folder"),
        (None, None),
        ("New article (form)...   Ctrl+N", "new_article"),
    ],
    "library": [
        ("Link PDF folder...", "link_pdf_folder"),
        ("Articles without PDF", "show_missing_pdfs"),
        ("Find duplicates...", "find_duplicates"),
        ("Create missing previews", "refresh_thumbnails"),
        ("Statistics", "show_statistics"),
        (None, None),
        ("Export all to BibTeX...", "export_bibtex"),
        ("Export this list to BibTeX...", "export_view"),
        (None, None),
        ("Open another library...", "open_library_file"),
        ("New empty library...", "new_library_file"),
        ("Delete all articles...", "delete_all"),
    ],
    "help": [
        ("How to use SciLibra", "show_help"),
        ("About SciLibra", "show_about"),
    ],
}

HELP_TEXT = """Getting articles into SciLibra
  • Add › Import BibTeX file - PDFs named <key>.pdf next to the .bib file are linked automatically.
  • Add › Paste BibTeX - paste entries copied from Google Scholar, a journal site, etc.
  • Add › Add PDFs / Add folder of PDFs - the DOI is read from each PDF and the details are
    downloaded from Crossref (needs internet). Without internet the PDF title is used.
  • Add › New article - fill in the form yourself (or type a DOI and press Fetch).

Finding articles
  • Group by (left) - browse by keywords, tag groups, authors, year or journal. Click a group to
    open it and "Back" (or Esc) to return.
  • Filter box - narrows the list as you type.
  • Search box (top) - searches titles, authors, abstracts, keywords, comments... Separate several
    terms with ';' (any term matches, or tick "All terms" in Search options).

Working with an article
  • Open PDF (or Enter / double-click), Attach PDF, Edit, Copy BibTeX, Delete.
  • Comments - type in the box under the details and press Add.
  • Edit › Pick... - choose keywords / tag groups from the ones already used in the library.

Library menu
  • Link PDF folder - connects PDFs named <key>.pdf in a folder (and sub-folders) to articles.
  • Articles without PDF, Find duplicates, Statistics, Export BibTeX, Create previews.

Keyboard
  Ctrl+F search · Ctrl+L filter list · Ctrl+I import BibTeX · Ctrl+N new article
  Ctrl+E edit · Ctrl+O / Enter open PDF · ↑/↓ move in the list · Esc back"""


def open_with_system(path: str):
    """Open a file or folder with the default application."""
    try:
        if sys.platform.startswith("win"):
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        webbrowser.open("file://" + os.path.abspath(path))
