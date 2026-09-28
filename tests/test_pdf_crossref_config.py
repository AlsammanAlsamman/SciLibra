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


def make_annotated_pdf(path):
    import pymupdf
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 100), "Genome wide association studies are powerful.")
    page.insert_text((72, 130), "Nothing to see on this line.")
    hl = page.add_highlight_annot(page.search_for("association studies")[0])
    hl.set_info(content="key idea", title="Samman")
    hl.update()
    page.add_text_annot((300, 300), "Check the methods section").update()
    page.add_freetext_annot(pymupdf.Rect(72, 200, 300, 230), "My summary box").update()
    page2 = doc.new_page()
    page2.insert_text((72, 100), "Second page text about heat toler-")
    page2.insert_text((72, 115), "ance in wheat.")
    page2.add_underline_annot(page2.search_for("toler-")[0] | page2.search_for("ance in")[0]).update()
    doc.save(path)
    doc.close()
    return str(path)


def test_extract_annotations(tmp_path):
    path = make_annotated_pdf(tmp_path / "a.pdf")
    found = pdf.extract_annotations(path)
    kinds = [(a.page, a.kind) for a in found]
    assert kinds == [(1, "Highlight"), (1, "Text"), (1, "FreeText"), (2, "Underline")]
    hl, note, box, under = found
    assert (hl.text, hl.note, hl.author) == ("association studies", "key idea", "Samman")
    assert note.note == "Check the methods section" and note.label == "Sticky note"
    assert box.text == "My summary box" and box.label == "Text box"
    assert "tolerance" in under.text  # hyphenated line break re-joined
    assert hl.as_comment() == '[p. 1] Highlight: "association studies" - key idea'
    assert pdf.extract_annotations(str(tmp_path / "missing.pdf")) == []


def test_library_annotations_cache_search_and_comments(lib, tmp_path):
    import os
    import time
    path = make_annotated_pdf(tmp_path / "k1.pdf")
    lib.add(Article(key="k1", title="T", folderpath=str(tmp_path)))
    lib.add(Article(key="k2", title="No PDF"))
    assert len(lib.annotations("k1")) == 4 and lib.annotations("k2") == []
    # cached: served from the database while the PDF is unchanged
    assert lib.db.cached_annotations("k1", os.path.abspath(path), os.path.getmtime(path)) is not None
    assert [a.text for a in lib.annotations("k1")][0] == "association studies"
    assert lib.search("methods section", fields=["PDF annotations"]).keys == ["k1"]
    assert lib.search("methods section", fields=["Title"]).keys == []
    assert lib.annotated_keys() == ["k1"]
    # saving as comments is idempotent
    assert lib.annotations_to_comments("k1") == 4
    assert lib.annotations_to_comments("k1") == 0
    assert lib.get("k1").comments[0].startswith('[p. 1] Highlight: "association studies"')
    # a changed PDF is read again
    time.sleep(0.01)
    make_pdf(tmp_path / "k1.pdf", "no annotations any more")
    os.utime(path, (time.time() + 5, time.time() + 5))
    assert lib.annotations("k1") == []
    # index + rename + delete keep the cache consistent
    make_annotated_pdf(tmp_path / "k1.pdf")
    assert lib.index_annotations() == {"k1": 4}
    a = lib.get("k1")
    a.key = "k1new"
    a.pdffile = "k1.pdf"
    lib.update(a, old_key="k1")
    assert lib.search("summary box", fields=["PDF annotations"]).keys == ["k1new"]
    lib.delete(["k1new"])
    assert lib.annotated_keys() == []


def test_markdown_citation_and_last_page(lib, tmp_path):
    make_annotated_pdf(tmp_path / "k1.pdf")
    lib.add(Article(key="k1", title="Heat tolerance in wheat", authors=["Xu, Li", "Wang, J"], year="2024",
                    journal="Nature", doi="10.1/x", folderpath=str(tmp_path), comments=["great methods"]))
    lib.add(Article(key="k2", title="Nothing here"))
    assert lib.citation("k1") == "Xu et al., 2024"
    md = lib.annotations_markdown(["k1", "k2"])
    assert md.startswith("# Reading notes") and "## Heat tolerance in wheat" in md
    assert '- **p. 1, Highlight**: “association studies” — key idea' in md
    assert "- **p. 1, Sticky note**: Check the methods section" in md
    assert "- great methods" in md and "Nothing here" not in md
    assert lib.annotations_markdown(["k2"]) == ""
    assert lib.last_page("k1") == 1
    lib.set_last_page("k1", 7)
    assert lib.last_page("k1") == 7
