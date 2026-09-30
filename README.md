<p align="center">
  <img src="https://raw.githubusercontent.com/AlsammanAlsamman/SciLibra/master/SciLibra_icon.png" alt="SciLibra logo" width="170">
</p>

<h1 align="center">SciLibra</h1>

<p align="center">
  <b>Your scientific articles, PDFs and notes - organised, searchable and safely backed up.</b><br>
  A free, open-source desktop app for researchers: BibTeX + PDF library, built-in PDF reader &amp; annotator,
  and one-click Google Drive backup.
</p>

<p align="center">
  <a href="https://pypi.org/project/scilibra/"><img alt="PyPI" src="https://img.shields.io/pypi/v/scilibra?color=5B4CE0"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-3.9%2B-3776AB?logo=python&logoColor=white">
  <img alt="Kivy" src="https://img.shields.io/badge/UI-Kivy-5B4CE0">
  <img alt="Platforms" src="https://img.shields.io/badge/platform-Linux%20%7C%20Windows%20%7C%20macOS-8E58F3">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-2E8E4E">
</p>

<p align="center">
  <a href="#-features">Features</a> ·
  <a href="#-screenshots">Screenshots</a> ·
  <a href="#-installation">Installation</a> ·
  <a href="#-quick-start">Quick start</a> ·
  <a href="#%EF%B8%8F-google-drive-backup">Google Drive backup</a> ·
  <a href="#-the-author">Author</a>
</p>

<p align="center">
  <img src="https://raw.githubusercontent.com/AlsammanAlsamman/SciLibra/master/docs/screenshots/main.png" alt="SciLibra main window" width="900">
</p>

---

## ✨ Features

<table>
<tr>
<td width="50%" valign="top">

### 📥 Add articles your way
- **Import a `.bib` file** - every entry type; PDFs named `<key>.pdf` next to it are linked automatically
- **Paste BibTeX** from Google Scholar or a journal website
- **Drop in PDFs** (files or a whole folder) - the DOI is read from each PDF and the details are
  downloaded from Crossref
- **Fill in a form** - or just type a DOI and press *Fetch details*

</td>
<td width="50%" valign="top">

### 🔎 Find anything in seconds
- **Group by** keywords, tag groups, authors, year or journal - with counts
- **Filter** any list as you type
- **Search** titles, authors, abstracts, keywords, comments, DOI… and the notes inside your PDFs
- Several terms with `;` - any term, or all of them

</td>
</tr>
<tr>
<td valign="top">

### 📖 Read & annotate
- Built-in reader that **reopens each paper where you stopped**
- **Highlight, underline, strike out, sticky notes, text boxes, pen, shapes**, eraser, 6 colours, undo
- Select text to **copy it with a citation** - “…” (Xu et al., 2024, p. 5)
- Annotations are **saved inside the PDF**, so Acrobat, Zotero or Okular show them too

</td>
<td valign="top">

### 📝 Your notes, everywhere
- Every highlight and note is listed with the article and is **searchable**
- Save them as comments, or **export them to Markdown** for your literature review
- Add your own comments and **tag groups** (*to-read*, *thesis chapter 2*…)

</td>
</tr>
<tr>
<td valign="top">

### ☁️ One-click Google Drive backup
- Library, PDFs and annotations backed up automatically
- A dated copy every day for the last 10 days
- **Restore everything** on a new computer
- SciLibra only sees the files it created - never your other Drive files

</td>
<td valign="top">

### 🎨 Modern and friendly
- Material-style design, **light and dark themes**
- Animated start screen, hover effects, rounded cards
- A **Help center** with step-by-step guides and keyboard shortcuts
- Safe by design: confirmations before deleting, PDFs are never deleted, automatic backups

</td>
</tr>
</table>

## 📸 Screenshots

<table>
<tr>
<td width="50%"><img src="https://raw.githubusercontent.com/AlsammanAlsamman/SciLibra/master/docs/screenshots/groups.png" alt="Browse by keywords"><p align="center"><b>Browse by keywords, tag groups, authors, year or journal</b></p></td>
<td width="50%"><img src="https://raw.githubusercontent.com/AlsammanAlsamman/SciLibra/master/docs/screenshots/reader.png" alt="PDF reader with highlights"><p align="center"><b>Built-in reader with highlights and notes</b></p></td>
</tr>
<tr>
<td><img src="https://raw.githubusercontent.com/AlsammanAlsamman/SciLibra/master/docs/screenshots/main-dark.png" alt="Dark theme"><p align="center"><b>Dark theme</b></p></td>
<td><img src="https://raw.githubusercontent.com/AlsammanAlsamman/SciLibra/master/docs/screenshots/help.png" alt="Help center"><p align="center"><b>Help center</b></p></td>
</tr>
<tr>
<td><img src="https://raw.githubusercontent.com/AlsammanAlsamman/SciLibra/master/docs/screenshots/splash.png" alt="Start screen"><p align="center"><b>Start screen</b></p></td>
<td><img src="https://raw.githubusercontent.com/AlsammanAlsamman/SciLibra/master/docs/screenshots/about.png" alt="About page"><p align="center"><b>About</b></p></td>
</tr>
</table>

## 🚀 Installation

Requires **Python 3.9 or newer**. Install from [PyPI](https://pypi.org/project/scilibra/):

```bash
pip install scilibra
scilibra                            # start it (or: python -m scilibra)
scilibra path/to/other-library.db   # open another library
```

Tip: install it in its own environment, e.g. `pipx install scilibra` or a virtual environment.

<details>
<summary><b>Install from source</b></summary>

```bash
git clone https://github.com/AlsammanAlsamman/SciLibra.git
cd SciLibra
python3 -m venv .venv
.venv/bin/pip install -e .          # Windows: .venv\Scripts\pip install -e .
.venv/bin/scilibra
```
</details>

Your library lives in `~/.local/share/scilibra/library.db` (Windows: `%APPDATA%\SciLibra`,
macOS: `~/Library/Application Support/SciLibra`). Set `SCILIBRA_HOME` to use another folder.

<details>
<summary><b>Desktop shortcut (Linux)</b></summary>

Edit the paths in `SciLibra.desktop`, then:

```bash
cp SciLibra.desktop ~/.local/share/applications/
```
</details>

<details>
<summary><b>Coming from SciLibra 1.x?</b></summary>

On the first start, an existing `scilibraLibrary.db` in the current folder or the project folder is copied
to the location above and upgraded. The original file is not changed, and a backup of the pre-upgrade copy
is kept next to it.
</details>

## 🧭 Quick start

1. **Add › Import BibTeX file** (or **Add › Add PDF files**).
2. PDFs somewhere else? **Library › Link PDF folder** connects PDFs named `<key>.pdf` in that folder and its
   sub-folders. For other file names use **Attach PDF…**
3. Choose **Group by › Keywords** (or Tag groups, Authors…) and click a group to open it.
4. Select an article to see its details - double-click it to read and annotate the PDF.
5. Press **Google Drive** (top right) to switch on the backup.

Everything is also explained inside the app: **Help › How to use SciLibra**.

### ⌨️ Keyboard shortcuts

| Main window | | PDF reader | |
|---|---|---|---|
| `Ctrl+F` | Search the library | `H` `U` `S` | Highlight · underline · strike |
| `Ctrl+L` | Filter the list | `N` `B` | Sticky note · text box |
| `Ctrl+I` | Import BibTeX | `D` `R` `O` `A` `L` | Pen · rectangle · ellipse · arrow · line |
| `Ctrl+N` | New article | `E` `V` `T` | Eraser · select · select text |
| `Ctrl+E` | Edit | `Ctrl+Z` | Undo |
| `Ctrl+O` / `Enter` | Open the PDF | `Ctrl+F` | Find in the PDF |
| `↑` `↓` | Move in the list | `PgUp` `PgDn` | Previous / next page |
| `Esc` | Back | `Esc` | Close the reader |

## ☁️ Google Drive backup

Press **Google Drive** › **Sign in with Google**. Your browser opens: choose your account, tick
*"See, edit, create and delete only the specific Google Drive files you use with this app"* and press
**Continue**. The button turns green and the backup starts.

What is stored in the **SciLibra** folder on your Drive:

```
SciLibra/
├── library.db                      the whole library: details, keywords, tag groups, comments, previews
├── Backups/library-YYYY-MM-DD.db   one copy per day, last 10 days
└── PDFs/<key>.pdf                  every PDF, including your highlights and notes
```

After the first backup only what changed is uploaded - a few seconds after each change and when you close
SciLibra. Temporary Google errors are retried automatically. **Restore from Drive…** sets up the same
library, with all PDFs, on another computer.

**Privacy:** SciLibra only gets access to the files it creates itself (`drive.file`) - never to your other
files. Your sign-in is stored only on your computer, and you can remove it at any time with *Sign out* or at
[myaccount.google.com/permissions](https://myaccount.google.com/permissions).

<details>
<summary><b>For maintainers: the OAuth client</b></summary>

The OAuth client (type **Desktop app**) ships as `scilibra/assets/google_client.dat`. To replace it, download
the client JSON from Google Cloud Console and run

```bash
python -c "from scilibra.core.gdrive import bundle_client_file as b; b('client_secret.json', 'scilibra/assets/google_client.dat')"
```

Never commit the JSON itself (it is git-ignored). Users can also use their own client with
**Load client file…** in the Google Drive dialog.
</details>

## 🛠️ Development

```bash
.venv/bin/pip install -e ".[test]"
.venv/bin/python -m pytest                        # core tests + end-to-end GUI scenario
.venv/bin/python tests/gui_scenario.py shots/     # run the GUI scenario and keep its screenshots
.venv/bin/python tools/make_screenshots.py        # refresh the README screenshots (add --dark for dark)
```

<details>
<summary><b>Project layout</b></summary>

```
scilibra/
  core/            GUI-independent logic (usable from scripts)
    models.py      Article data model
    database.py    SQLite storage, schema upgrades (compatible with 1.x libraries)
    bibtex.py      BibTeX import/export
    pdf.py         first-page previews, DOI detection, reading annotations (PyMuPDF)
    annotate.py    creating/editing annotations and saving them into the PDF
    crossref.py    DOI -> metadata (Crossref REST API)
    gdrive.py      Google Drive sign-in, backup and restore
    library.py     high-level operations: import, link PDFs, search, duplicates, statistics
  gui/             Kivy user interface
    app.py         main window           viewer.py      PDF reader / annotator
    theme.py       colours (light/dark)  widgets.py     hover, rounded fields
    splash.py      start screen          helpcenter.py  Help center and About
    layout.kv      the look of everything
  config.py        settings and data locations
tests/             pytest suite and GUI scenario
tools/             screenshot generator
```
</details>

Using the core from Python:

```python
from scilibra.core import Library
lib = Library("my.db")
lib.import_bibtex_file("refs.bib")
print(lib.search("GWAS").keys)
lib.export_bibtex("out.bib")
```

## 👤 The author

<table>
<tr>
<td width="150" align="center"><img src="https://raw.githubusercontent.com/AlsammanAlsamman/SciLibra/master/scilibra/assets/author.png" alt="Alsamman M. Alsamman" width="130"></td>
<td>

**Alsamman M. Alsamman** - creator of SciLibra

📧 smahmoud [at] ageri.sci.eg · A.Alsamman [at] cgiar.org · SammanMohammed [at] gmail.com<br>
🐙 [github.com/AlsammanAlsamman](https://github.com/AlsammanAlsamman)

Found a bug or have an idea? [Open an issue](https://github.com/AlsammanAlsamman/SciLibra/issues).

</td>
</tr>
</table>

## 📄 License

[MIT License](https://opensource.org/licenses/MIT). The software comes with no warranty - use at your own
risk. This software is not intended for commercial use.
