from scilibra.core import bibtex
from scilibra.core.models import Article, split_authors, split_terms


def test_parse_all_entry_types(sample_bib):
    result = bibtex.parse_bibtex(sample_bib)
    assert [a.key for a in result.articles] == ["alsamman2023alignstatplot", "smith2020deep", "doe2019book"]
    assert result.failed == []
    types = {a.key: a.entry_type for a in result.articles}
    assert types == {"alsamman2023alignstatplot": "article", "smith2020deep": "inproceedings", "doe2019book": "book"}


def test_fields_are_converted_to_plain_text(sample_bib):
    a, b, c = bibtex.parse_bibtex(sample_bib).articles
    assert a.title.startswith("AlignStatPlot: An R package")
    assert a.authors == ["Alsamman, Alsamman M", "El Allali, Achraf", "Marand, Alexandre P"]
    assert a.keywords == ["alignment", "statistics", "visualization"]
    assert a.taggroups == ["Bioinformatics", "Tools"]
    assert a.doi == "10.1371/journal.pone.0291204"
    assert b.journal == "Proceedings of Genomics 2020"  # booktitle used as venue
    assert "O'Brien" in b.title and '"method"' in b.title
    assert c.title == "A Book about Café Science"


def test_broken_entry_does_not_abort_import():
    text = """
@article{good1, title={Good one}, year={2020}}
@article{broken, title={Missing brace, year={2020}
@article{good2, title={Good two}, year={2021}}
"""
    result = bibtex.parse_bibtex(text)
    keys = [a.key for a in result.articles]
    assert "good1" in keys
    assert result.failed, "the broken entry must be reported"


def test_roundtrip_keeps_everything(sample_bib):
    articles = bibtex.parse_bibtex(sample_bib).articles
    articles[0].comments = ["first note", "second note"]
    articles[0].folderpath = "/tmp/pdfs"
    text = bibtex.articles_to_bibtex(articles)
    again = bibtex.parse_bibtex(text).articles
    assert [x.key for x in again] == [x.key for x in articles]
    for before, after in zip(articles, again):
        assert after.title == before.title
        assert after.authors == before.authors
        assert after.keywords == before.keywords
        assert after.entry_type == before.entry_type
    assert again[0].comments == ["first note", "second note"]
    assert again[0].folderpath == "/tmp/pdfs"


def test_export_without_local_fields():
    a = Article(key="k", title="T", folderpath="/x", comments=["c"])
    text = bibtex.article_to_bibtex(a, include_local=False)
    assert "folderpath" not in text and "comment" not in text and "@article{k," in text


def test_unbalanced_braces_are_made_safe():
    a = Article(key="bad key,{}", title="weird } title {")
    text = bibtex.article_to_bibtex(a)
    parsed = bibtex.parse_bibtex(text).articles
    assert len(parsed) == 1 and parsed[0].key == "bad_key___"


def test_zotero_file_field():
    text = "@article{z1, title={T}, file={Full Text PDF:/home/u/papers/z1 paper.pdf:application/pdf}}"
    a = bibtex.parse_bibtex(text).articles[0]
    assert a.folderpath == "/home/u/papers" and a.pdffile == "z1 paper.pdf"


def test_split_helpers():
    assert split_authors("Rolland, Ann and Brand, Bob AND Candy, C") == ["Rolland, Ann", "Brand, Bob", "Candy, C"]
    assert split_terms("a, b;c\n a ,None,") == ["a", "b", "c"]


def test_doi_normalisation():
    assert bibtex.normalize_doi("https://doi.org/10.1/abc") == "10.1/abc"
    assert bibtex.normalize_doi("doi: 10.1/abc") == "10.1/abc"


def test_percent_sign_is_not_a_comment():
    a = bibtex.parse_bibtex(r"@misc{p, title={A 100% {pure} method and 5\% more}}").articles[0]
    assert a.title == "A 100% pure method and 5% more"
