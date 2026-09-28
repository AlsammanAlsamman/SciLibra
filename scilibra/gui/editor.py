"""Form for creating and editing an article."""

from __future__ import annotations

import os
import threading

from kivy.clock import Clock
from kivy.properties import ObjectProperty, StringProperty

from ..core import crossref
from ..core.models import Article, split_authors, split_terms
from .dialogs import BasePopup

ENTRY_TYPES = ["article", "inproceedings", "book", "incollection", "inbook", "phdthesis",
               "mastersthesis", "techreport", "misc", "unpublished", "online"]

# Article attribute -> TextInput id
SIMPLE_FIELDS = ["key", "title", "year", "journal", "volume", "number", "pages", "publisher",
                 "doi", "url", "abstract"]


class ArticleEditor(BasePopup):
    """Edit an Article. `save_callback(article, old_key)` returns an error string or None."""
    article = ObjectProperty(None)
    old_key = StringProperty("")
    error = StringProperty("")
    status = StringProperty("")
    save_callback = ObjectProperty(None, allownone=True)
    app = ObjectProperty(None)

    def __init__(self, article: Article | None = None, **kwargs):
        kwargs.setdefault("auto_dismiss", False)
        super().__init__(**kwargs)
        self.article = article or Article(key="")
        self.old_key = self.article.key
        self.title = "Edit article" if self.old_key else "New article"
        Clock.schedule_once(lambda _dt: self._fill(self.article))

    def _fill(self, a: Article):
        ids = self.ids
        for name in SIMPLE_FIELDS:
            ids[name].text = getattr(a, name) or ""
        ids.entry_type.text = a.entry_type or "article"
        ids.authors.text = "\n".join(a.authors)
        ids.keywords.text = ", ".join(a.keywords)
        ids.taggroups.text = ", ".join(a.taggroups)
        ids.pdf.text = a.pdf_path

    def collect(self) -> Article:
        ids = self.ids
        a = Article(key=ids.key.text.strip())
        for name in SIMPLE_FIELDS:
            setattr(a, name, ids[name].text.strip())
        a.entry_type = ids.entry_type.text
        a.authors = split_authors(ids.authors.text.replace("\n", " and "))
        a.keywords = split_terms(ids.keywords.text)
        a.taggroups = split_terms(ids.taggroups.text)
        pdf = os.path.expanduser(ids.pdf.text.strip())
        if pdf:
            a.folderpath, name = os.path.split(os.path.abspath(pdf))
            a.pdffile = "" if name == a.key + ".pdf" else name
        a.comments = list(self.article.comments)
        a.date_added = self.article.date_added
        return a

    def save(self):
        a = self.collect()
        if not a.key:
            self.error = "The key is required (e.g. smith2020deep)."
            return
        if not a.title:
            self.error = "The title is required."
            return
        if a.year and not a.year.isdigit():
            self.error = "The year should be a number (e.g. 2021)."
            return
        pdf = self.ids.pdf.text.strip()
        if pdf and not os.path.isfile(os.path.expanduser(pdf)):
            self.error = "The PDF file does not exist. Fix the path or leave it empty."
            return
        error = self.save_callback(a, self.old_key) if self.save_callback else None
        if error:
            self.error = error
            return
        self.dismiss()

    def browse_pdf(self):
        self.error = ""
        start = os.path.dirname(self.ids.pdf.text.strip()) or None

        def chosen(path, _folder):
            self.ids.pdf.text = path
        self.app.choose_file("Choose the article PDF", chosen, filters=["*.pdf", "*.PDF"], start=start)

    def pick(self, field):
        self.error = ""
        table = {"keywords": "keywords", "taggroups": "taggroups"}[field]
        current = split_terms(self.ids[field].text)

        def done(values):
            self.ids[field].text = ", ".join(values)
        self.app.pick_values("Choose " + ("keywords" if field == "keywords" else "tag groups"),
                             table, current, done)

    def fetch_doi(self):
        doi = self.ids.doi.text.strip()
        if not doi:
            self.error = "Enter a DOI first."
            return
        self.error = ""
        self.status = "Looking up the DOI on Crossref..."

        def work():
            try:
                found = crossref.fetch_article(doi)
                Clock.schedule_once(lambda _dt: self._apply_fetched(found))
            except crossref.CrossrefError as exc:
                message = str(exc)
                Clock.schedule_once(lambda _dt: self._fetch_failed(message))
        threading.Thread(target=work, daemon=True).start()

    def _fetch_failed(self, message):
        self.status = ""
        self.error = message

    def _apply_fetched(self, found: Article):
        current = self.collect()
        found.key = current.key or crossref.make_key(found)
        found.keywords = current.keywords or found.keywords
        found.taggroups = current.taggroups
        found.folderpath, found.pdffile = current.folderpath, current.pdffile
        found.comments = current.comments
        self._fill(found)
        self.status = "Filled in from Crossref - review and press Save."
