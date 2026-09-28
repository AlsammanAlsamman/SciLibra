import os
import sqlite3

import pytest

from scilibra.core.database import SCHEMA_VERSION
from scilibra.core.library import Library
from scilibra.core.models import Article

from .conftest import make_legacy_db, make_pdf


def test_new_library_is_empty(lib):
    assert lib.count() == 0
    assert lib.groups("keywords") == []
    assert lib.db.get_property("schemaversion") == str(SCHEMA_VERSION)


def test_import_and_reload(lib, sample_bib, tmp_path):
    report = lib.import_bibtex(sample_bib)
    assert sorted(report.added) == ["alsamman2023alignstatplot", "doe2019book", "smith2020deep"]
    assert lib.count() == 3
    a = lib.get("smith2020deep")
    assert a.authors == ["Smith, John", "O'Brien, Mary"]  # quotes are stored safely
    assert a.date_added
    # importing again skips existing articles
    again = lib.import_bibtex(sample_bib)
    assert again.added == [] and len(again.skipped) == 3
    # the data survives closing and reopening
    lib.close()
    reopened = Library(lib.path)
    assert reopened.get("alsamman2023alignstatplot").keywords == ["alignment", "statistics", "visualization"]
    reopened.close()


def test_import_file_links_pdfs_next_to_bib(lib, sample_bib, tmp_path):
    bib = tmp_path / "refs.bib"
    bib.write_text(sample_bib, encoding="utf-8")
    make_pdf(tmp_path / "doe2019book.pdf", "Book")
    lib.import_bibtex_file(str(bib))
    assert lib.get("doe2019book").has_pdf
    assert lib.thumbnail("doe2019book").startswith(b"\x89PNG")
    assert not lib.get("smith2020deep").has_pdf


def test_groups_and_group_members(lib, sample_bib):
    lib.import_bibtex(sample_bib)
    years = dict(lib.groups("year"))
    assert years == {"2023": 1, "2020": 1, "2019": 1}
    keywords = dict(lib.groups("keywords"))
    assert keywords["GWAS"] == 1
    assert lib.keys_in_group("author", "O'Brien, Mary") == ["smith2020deep"]


def test_search(lib, sample_bib):
    lib.import_bibtex(sample_bib)
    assert lib.search("gwas").keys == ["smith2020deep"]
    assert set(lib.search("gwas ||| café").keys) == {"smith2020deep", "doe2019book"}
    assert lib.search("gwas ||| café", match_all=True).keys == []
    assert lib.search("2023", fields=["Year"]).keys == ["alsamman2023alignstatplot"]
    assert lib.search("2023", fields=["Title"]).keys == []
    result = lib.search("o'brien")
    assert result.keys == ["smith2020deep"] and result.hits["o'brien"]["Authors"] == 1
    assert lib.search("100%").keys == []  # LIKE wildcards are escaped


def test_update_and_rename(lib, sample_bib):
    lib.import_bibtex(sample_bib)
    a = lib.get("doe2019book")
    a.title = "New title"
    a.keywords = ["x", "y"]
    a.key = "doe2019new"
    lib.update(a, old_key="doe2019book")
    assert lib.get("doe2019book") is None
    b = lib.get("doe2019new")
    assert b.title == "New title" and b.keywords == ["x", "y"]
    assert lib.keys_in_group("keywords", "x") == ["doe2019new"]
    with pytest.raises(ValueError):
        b.key = "smith2020deep"
        lib.update(b, old_key="doe2019new")


def test_comments(lib, sample_bib):
    lib.import_bibtex(sample_bib)
    assert lib.add_comment("doe2019book", "  Read   this ")
    assert not lib.add_comment("doe2019book", "Read this")  # duplicate
    assert lib.get("doe2019book").comments == ["Read this"]
    assert lib.search("read this", fields=["Comments"]).keys == ["doe2019book"]
    assert lib.remove_comment("doe2019book", "Read this")
    assert lib.get("doe2019book").comments == []


def test_delete(lib, sample_bib):
    lib.import_bibtex(sample_bib)
    lib.delete(["doe2019book"])
    assert lib.count() == 2 and ("Doe, Jane", 1) not in lib.groups("author")
    lib.delete_all()
    assert lib.count() == 0 and lib.groups("keywords") == []


def test_link_pdf_folders_and_missing(lib, sample_bib, tmp_path):
    lib.import_bibtex(sample_bib)
    assert len(lib.missing_pdfs()) == 3
    sub = tmp_path / "pdfs" / "nested"
    sub.mkdir(parents=True)
    make_pdf(sub / "smith2020deep.pdf")
    make_pdf(tmp_path / "pdfs" / "unrelated.pdf")
    linked, unmatched = lib.link_pdf_folders([str(tmp_path / "pdfs")])
    assert linked == ["smith2020deep"]
    assert [os.path.basename(p) for p in unmatched] == ["unrelated.pdf"]
    assert lib.get("smith2020deep").pdf_path == str(sub / "smith2020deep.pdf")
    assert lib.thumbnail("smith2020deep")
    assert len(lib.missing_pdfs()) == 2
    # linking again is a no-op
    assert lib.link_pdf_folders([str(tmp_path / "pdfs")])[0] == []


def test_set_pdf_with_any_file_name(lib, sample_bib, tmp_path):
    lib.import_bibtex(sample_bib)
    path = make_pdf(tmp_path / "My Paper (final).pdf")
    lib.set_pdf("doe2019book", path)
    a = lib.get("doe2019book")
    assert a.has_pdf and a.pdffile == "My Paper (final).pdf"


def test_duplicates(lib):
    lib.add(Article(key="a1", title="Deep Learning in Genomics!", date_added="2024-01-01"))
    lib.add(Article(key="a2", title="deep learning in genomics", comments=["keep me"], keywords=["k2"],
                    date_added="2024-02-01"))
    lib.add(Article(key="b1", title="Other", doi="10.1/x"))
    lib.add(Article(key="b2", title="Other paper", doi="10.1/X"))
    lib.add(Article(key="c1", title="Unique"))
    groups = lib.find_duplicates()
    assert sorted(sorted(a.key for a in g) for g in groups) == [["a1", "a2"], ["b1", "b2"]]
    removed = lib.remove_duplicates()
    assert len(removed) == 2 and lib.count() == 3
    kept = lib.get("a2")  # has comments -> preferred
    assert kept and kept.comments == ["keep me"]


def test_statistics(lib, sample_bib):
    lib.import_bibtex(sample_bib)
    stats = lib.statistics()
    assert stats["Articles"] == 3 and stats["Without PDF"] == 3
    assert stats["Year range"] == "2019 - 2023"


def test_export(lib, sample_bib, tmp_path):
    lib.import_bibtex(sample_bib)
    lib.add_comment("doe2019book", "note")
    out = tmp_path / "out.bib"
    assert lib.export_bibtex(str(out)) == 3
    other = Library(str(tmp_path / "other.db"))
    report = other.import_bibtex_file(str(out))
    assert len(report.added) == 3
    assert other.get("doe2019book").comments == ["note"]
    assert other.export_bibtex(str(tmp_path / "one.bib"), keys=["doe2019book"]) == 1
    other.close()


def test_article_from_pdf_offline(lib, tmp_path):
    path = make_pdf(tmp_path / "Some_Paper-Title.pdf", "Text", doi="10.1234/abc.5678", title="A real title here")
    article, note = lib.article_from_pdf(path, online=False)
    assert article.doi == "10.1234/abc.5678"
    assert article.title == "A real title here"
    assert article.key == "Some_Paper-Title" and article.pdffile == ""
    assert "offline" in note
    key = lib.add_pdf_article(article)
    assert key == "Some_Paper-Title" and lib.get(key).has_pdf
    # the same PDF is not added twice
    again, _ = lib.article_from_pdf(path, online=False)
    assert lib.add_pdf_article(again) == ""


def test_legacy_library_migration(tmp_path):
    path = make_legacy_db(str(tmp_path / "scilibraLibrary.db"))
    lib = Library(path)
    assert lib.db.backup_path and os.path.exists(lib.db.backup_path)
    marand = lib.get("marand2021")
    assert marand.authors == ["Marand AP", "Chen Z"]  # repaired from the original author string
    assert marand.keywords == [] and marand.taggroups == []  # 'None' placeholders removed
    vis = lib.get("visscher2017")
    assert vis.keywords == ["GWAS", "Genetics"] and vis.comments == ["Good"]
    assert vis.date_added.startswith("2023-12-03")
    assert lib.thumbnail("visscher2017") is None  # unreadable legacy image dropped (its PDF is missing)
    assert lib.db.get_property("schemaversion") == str(SCHEMA_VERSION)
    con = sqlite3.connect(path)
    assert con.execute("SELECT COUNT(*) FROM comment WHERE ID='ghost'").fetchone()[0] == 0
    assert con.execute("SELECT keywords FROM articles WHERE ID='visscher2017'").fetchone()[0] == "GWAS, Genetics"
    con.close()
    # new articles can be added to a migrated library, and it is not migrated twice
    lib.add(Article(key="new1", title="New"))
    lib.close()
    lib2 = Library(path)
    assert lib2.db.backup_path is None and lib2.count() == 3
    lib2.close()


def test_legacy_gif_previews(tmp_path):
    import pymupdf
    path = make_legacy_db(str(tmp_path / "old.db"))
    old_png = pymupdf.Pixmap(pymupdf.csRGB, pymupdf.IRect(0, 0, 20, 30), False).tobytes("png")
    pdf_path = make_pdf(tmp_path / "marand2021.pdf")
    con = sqlite3.connect(path)
    con.execute("UPDATE articles SET folderpath=? WHERE ID='marand2021'", (str(tmp_path),))
    con.execute("INSERT INTO firstpageimages VALUES ('marand2021', ?)", (b"GIF89a-old-low-res",))
    con.execute("UPDATE firstpageimages SET articleData=? WHERE ID='visscher2017'", (old_png,))
    con.commit()
    con.close()
    lib = Library(path)
    # PDF available: the old preview is dropped and a new PNG is created on demand
    assert lib.db.get_thumbnail("marand2021") is None
    assert lib.thumbnail("marand2021").startswith(b"\x89PNG")
    assert lib.db.get_thumbnail("marand2021").startswith(b"\x89PNG")
    # PDF missing: an existing PNG preview is kept
    assert lib.thumbnail("visscher2017") == old_png
    assert os.path.basename(pdf_path) == "marand2021.pdf"
    lib.close()


def test_text_is_normalised_and_others_not_grouped(lib):
    lib.add(Article(key=" k1 ", title="  <scp>eQTLs</scp>  play\n roles ", year=" 2022 ",
                    authors=["Smith, J", "others"]))
    a = lib.get("k1")
    assert (a.title, a.year) == ("eQTLs play roles", "2022")
    assert a.authors == ["Smith, J", "others"] and a.author_string == "Smith, J and others"
    assert lib.groups("author") == [("Smith, J", 1)]


def test_pdf_without_metadata_uses_file_name_as_key(lib, tmp_path):
    path = make_pdf(tmp_path / "Offline Paper.pdf", "Body", title="An offline paper about maize")
    article, _ = lib.article_from_pdf(path, online=False)
    assert article.key == "Offline_Paper" and article.pdffile == "Offline Paper.pdf"
