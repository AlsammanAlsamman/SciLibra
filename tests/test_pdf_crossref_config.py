import json
import os

import pytest
import requests

from scilibra import config
from scilibra.core import crossref, pdf
from scilibra.core.models import Article

from .conftest import make_pdf

CROSSREF_MESSAGE = {
    "DOI": "10.1371/journal.pone.0291204",
    "type": "journal-article",
    "title": ["AlignStatPlot: An R package &amp; online tool"],
    "author": [{"given": "Alsamman M.", "family": "Alsamman"}, {"given": "Achraf", "family": "El Allali"}],
    "container-title": ["PLOS ONE"],
    "published-print": {"date-parts": [[2023, 9]]},
    "volume": "18", "issue": "9", "page": "e0291204",
    "publisher": "Public Library of Science",
    "URL": "http://dx.doi.org/10.1371/journal.pone.0291204",
    "abstract": "<jats:title>Abstract</jats:title><jats:p>Some <jats:italic>text</jats:italic>.</jats:p>",
    "subject": ["Multidisciplinary"],
}


def test_find_doi():
    assert pdf.find_doi("see doi:10.1016/S0140-6736(20)30183-5.") == "10.1016/S0140-6736(20)30183-5"
    assert pdf.find_doi("https://doi.org/10.1371/journal.pone.0291204, 2023") == "10.1371/journal.pone.0291204"
    assert pdf.find_doi("no identifier here") == ""


def test_thumbnail_and_extract(tmp_path):
    path = make_pdf(tmp_path / "x.pdf", "Hello", doi="10.5555/12345678")
    png = pdf.first_page_thumbnail(path, width=200)
    assert png.startswith(b"\x89PNG")
    assert pdf.extract_info(path)["doi"] == "10.5555/12345678"
    bad = tmp_path / "bad.pdf"
    bad.write_bytes(b"not a pdf")
    assert pdf.first_page_thumbnail(str(bad)) is None
    assert pdf.extract_info(str(bad))["doi"] == ""
    assert pdf.first_page_thumbnail(str(tmp_path / "missing.pdf")) is None


def test_crossref_message_mapping():
    a = crossref.message_to_article(CROSSREF_MESSAGE)
    assert a.title == "AlignStatPlot: An R package & online tool"
    assert a.authors == ["Alsamman, Alsamman M.", "El Allali, Achraf"]
    assert (a.year, a.journal, a.volume, a.number, a.pages) == ("2023", "PLOS ONE", "18", "9", "e0291204")
    assert a.abstract == "Some text ."
    assert crossref.make_key(a) == "alsamman2023alignstatplot"


class FakeResponse:
    def __init__(self, status, payload=None):
        self.status_code = status
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, response=None, exc=None):
        self.response, self.exc, self.urls = response, exc, []

    def get(self, url, **kwargs):
        self.urls.append(url)
        assert kwargs.get("timeout")
        if self.exc:
            raise self.exc
        return self.response


def test_fetch_article_success_and_errors():
    session = FakeSession(FakeResponse(200, {"message": CROSSREF_MESSAGE}))
    a = crossref.fetch_article("https://doi.org/10.1371/journal.pone.0291204", key="k", session=session)
    assert a.key == "k" and a.doi == "10.1371/journal.pone.0291204"
    assert session.urls[0].endswith("/works/10.1371/journal.pone.0291204")
    with pytest.raises(crossref.CrossrefError, match="not found"):
        crossref.fetch_article("10.1/x", session=FakeSession(FakeResponse(404)))
    with pytest.raises(crossref.CrossrefError, match="unreachable"):
        crossref.fetch_article("10.1/x", session=FakeSession(exc=requests.ConnectionError("down")))
    with pytest.raises(crossref.CrossrefError):
        crossref.fetch_article("10.1/x", session=FakeSession(FakeResponse(200, None)))


def test_article_from_pdf_uses_crossref(lib, tmp_path):
    path = make_pdf(tmp_path / "Cotton pedigree genome.pdf", "Body", doi="10.1371/journal.pone.0291204")
    session = FakeSession(FakeResponse(200, {"message": CROSSREF_MESSAGE}))
    article, note = lib.article_from_pdf(path, online=True, session=session)
    assert "Crossref" in note
    assert article.key == "alsamman2023alignstatplot"  # file name is not a usable key
    assert article.pdffile == "Cotton pedigree genome.pdf" and article.folderpath == str(tmp_path)
    key = lib.add_pdf_article(article)
    assert lib.get(key).has_pdf


def test_article_pdf_path():
    assert Article(key="k").pdf_path == ""
    assert Article(key="k", folderpath="/a").pdf_path == os.path.join("/a", "k.pdf")
    assert Article(key="k", folderpath="/a", pdffile="x.pdf").pdf_path == os.path.join("/a", "x.pdf")


def test_settings_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("SCILIBRA_HOME", str(tmp_path / "home"))
    s = config.Settings.load()
    assert s.library_path == ""
    s.remember_library(str(tmp_path / "a.db"))
    s.last_folder = str(tmp_path)
    s.save()
    again = config.Settings.load()
    assert again.library_path == str(tmp_path / "a.db") and again.start_folder() == str(tmp_path)
    with open(config.Settings.file(), "w") as fh:
        fh.write("{broken")
    assert config.Settings.load().library_path == ""
    with open(config.Settings.file(), "w") as fh:
        json.dump({"library_path": "x", "unknown": 1}, fh)
    assert config.Settings.load().library_path == "x"


def test_legacy_library_is_copied_on_first_start(tmp_path, monkeypatch):
    monkeypatch.setenv("SCILIBRA_HOME", str(tmp_path / "home"))
    work = tmp_path / "work"
    work.mkdir()
    (work / config.LEGACY_DB_NAME).write_bytes(b"legacy")
    monkeypatch.chdir(work)
    monkeypatch.setattr(config, "PROJECT_DIR", str(tmp_path / "nowhere"))
    path, message = config.resolve_library_path(config.Settings())
    assert path == config.default_library_path() and "Imported" in message
    assert open(path, "rb").read() == b"legacy"
    assert (work / config.LEGACY_DB_NAME).read_bytes() == b"legacy"
    # second start: nothing is copied again
    assert config.resolve_library_path(config.Settings()) == (path, "")
    assert config.resolve_library_path(config.Settings(), explicit="x.db")[0] == os.path.abspath("x.db")
