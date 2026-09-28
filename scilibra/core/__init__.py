"""GUI-independent core of SciLibra: data model, storage, BibTeX, PDF and Crossref."""

from .models import Article
from .library import Library

__all__ = ["Article", "Library"]
