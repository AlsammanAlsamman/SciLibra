import sqlite3

import pymupdf
import pytest

from scilibra.core.library import Library

SAMPLE_BIB = r"""
@article{alsamman2023alignstatplot,
  title={AlignStatPlot: An {R} package and online tool for robust sequence alignment statistics},
  author={Alsamman, Alsamman M and El Allali, Achraf and Marand, Alexandre P},
  journal={PloS one},
  volume={18},
  number={9},
  pages={e0291204},
  year={2023},
  publisher={Public Library of Science},
  doi={10.1371/journal.pone.0291204},
  keywords={alignment; statistics, visualization},
  taggroups = {Bioinformatics,Tools},
}

@inproceedings{smith2020deep,
  title = {Deep learning for {GWAS}: O'Brien's "method"},
  author = {Smith, John and O'Brien, Mary},
  booktitle = {Proceedings of Genomics 2020},
  year = {2020},
  keywords = {deep learning, GWAS},
}

@book{doe2019book,
  title = {A Book about Caf\'e Science},
  author = {Doe, Jane},
  publisher = {Science Press},
  year = {2019}
}
"""


def make_pdf(path, text="Hello", doi=None, title=None):
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_text((72, 72), text)
    if doi:
        page.insert_text((72, 100), f"https://doi.org/{doi}")
    if title:
        doc.set_metadata({"title": title})
    doc.save(path)
    doc.close()
    return str(path)


@pytest.fixture
def lib(tmp_path):
    library = Library(str(tmp_path / "lib.db"))
    yield library
    library.close()


@pytest.fixture
def sample_bib():
    return SAMPLE_BIB


def make_legacy_db(path):
    """Build a library exactly as SciLibra 1.x created it (including its data quirks)."""
    con = sqlite3.connect(path)
    c = con.cursor()
    c.execute("CREATE TABLE articles\n (ID text, title text, author text, year text, journal text, taggroups text, "
              "url text, folderpath text, keywords text, abstract text, ENTRYTYPE text, pages text, volume text, "
              "number text, publisher text)")
    c.execute("CREATE TABLE libraryproperties\n (property text, value text)")
    for prop, value in [("creationdate", "2023-12-03 05:51:19.855642"), ("lastmodificationdate", "2023-12-03"),
                        ("clusteringcategory", "keywords"), ("firstpageimage", "yes"),
                        ("firstpageimageresolution", "30")]:
        c.execute("INSERT INTO libraryproperties VALUES (?,?)", (prop, value))
    for t in ["taggroups", "author", "title", "keywords", "year", "comment", "journal"]:
        c.execute(f"CREATE TABLE {t} (ID text, articleData text)")
    c.execute("CREATE TABLE firstpageimages (ID text, articleData blob)")
    rows = [
        ("marand2021", "Chromatin in maize", "Marand AP and Chen Z", "2021", "Nature Plants", "",
         "", "/nonexistent", "", "", "article", "", "", "", ""),
        ("visscher2017", "10 years of GWAS discovery", "Visscher, Peter M and Wray, Naomi R", "2017",
         "AJHG", "", "", "/nonexistent", "", "abstract text", "article", "", "", "", ""),
    ]
    c.executemany("INSERT INTO articles VALUES (%s)" % ",".join("?" * 15), rows)
    # 1.x author split on "and " -> "Marand" became "Mar"
    c.executemany("INSERT INTO author VALUES (?,?)", [("marand2021", "Mar"), ("marand2021", "AP"),
                                                      ("marand2021", "Chen Z"), ("visscher2017", "Visscher, Peter M"),
                                                      ("visscher2017", "Wray, Naomi R")])
    # empty keywords were stored as 'None'; keywords were edited in the sub table only
    c.executemany("INSERT INTO keywords VALUES (?,?)", [("marand2021", "None"), ("visscher2017", "GWAS"),
                                                        ("visscher2017", "Genetics\n")])
    c.executemany("INSERT INTO taggroups VALUES (?,?)", [("marand2021", "None"), ("visscher2017", "None")])
    c.executemany("INSERT INTO comment VALUES (?,?)", [("visscher2017", "Good"), ("ghost", "orphan comment")])
    for t in ["title", "year", "journal"]:
        c.execute(f"INSERT INTO {t} SELECT ID, {t} FROM articles")
    c.execute("INSERT INTO firstpageimages VALUES (?,?)", ("visscher2017", b"GIF89a..."))
    con.commit()
    con.close()
    return path
