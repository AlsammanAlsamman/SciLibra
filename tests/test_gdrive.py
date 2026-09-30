import json
import os
import sqlite3
import time

import pytest

from scilibra.core import gdrive
from scilibra.core.gdrive import DriveAccount, DriveClient, DriveError, DriveSync, restore_from_drive
from scilibra.core.library import Library
from scilibra.core.models import Article

from .conftest import make_pdf
from .fake_drive import FakeDrive, fake_token


@pytest.fixture
def drive():
    return FakeDrive()


@pytest.fixture
def synced(tmp_path, drive):
    pdfs = tmp_path / "pdfs"
    pdfs.mkdir()
    lib = Library(str(tmp_path / "lib.db"))
    for key in ("a1", "a2"):
        make_pdf(pdfs / f"{key}.pdf", f"text of {key}")
        lib.add(Article(key=key, title=f"Title {key}", folderpath=str(pdfs), keywords=["k"]))
    lib.add(Article(key="nopdf", title="No PDF"))
    yield lib, DriveSync(lib, DriveClient(drive)), pdfs
    lib.close()


def test_first_sync_uploads_library_and_pdfs(synced, drive):
    lib, sync, _pdfs = synced
    assert sync.pending()
    report = sync.sync()
    assert report.library_saved and sorted(report.uploaded) == ["a1", "a2"] and report.unchanged == 0
    root = drive.by_name("SciLibra")[0]
    assert root["mimeType"] == gdrive.FOLDER_MIME
    assert {f["name"] for f in drive.children(root["id"])} == {"library.db", "PDFs", "Backups"}
    pdf_folder = drive.by_name("PDFs")[0]["id"]
    assert sorted(f["name"] for f in drive.children(pdf_folder)) == ["a1.pdf", "a2.pdf"]
    assert drive.content("a1.pdf").startswith(b"%PDF")
    # the uploaded library is a valid SQLite database containing the articles
    path = str(os.path.join(os.path.dirname(lib.path), "check.db"))
    open(path, "wb").write(drive.content("library.db"))
    con = sqlite3.connect(path)
    assert con.execute("SELECT COUNT(*) FROM articles").fetchone()[0] == 3
    con.close()
    backups = drive.children(drive.by_name("Backups")[0]["id"])
    assert len(backups) == 1 and backups[0]["name"].startswith("library-")
    assert not sync.pending()
    assert lib.db.get_property("drive_last_sync")


def test_second_sync_only_uploads_changes(synced, drive):
    lib, sync, pdfs = synced
    sync.sync()
    uploads = drive.upload_count
    report = sync.sync()
    assert report.uploaded == [] and report.unchanged == 2
    assert drive.upload_count == uploads + 2  # library.db + today's backup only
    # an annotated (changed) PDF is uploaded again into the same Drive file (new revision)
    file_id = drive.by_name("a1.pdf")[0]["id"]
    time.sleep(0.01)
    make_pdf(pdfs / "a1.pdf", "annotated version")
    assert sync.pending()
    report = sync.sync()
    assert report.uploaded == ["a1"]
    assert drive.by_name("a1.pdf")[0]["id"] == file_id and drive.files[file_id]["_revisions"] == 2
    # touching a file without changing it does not upload it again
    os.utime(pdfs / "a2.pdf", (time.time() + 10, time.time() + 10))
    report = sync.sync()
    assert report.uploaded == [] and report.unchanged == 2
    # library edits make the library pending again
    lib.add_comment("a2", "note")
    assert sync.pending()


def test_recovers_when_files_or_folders_were_deleted_on_drive(synced, drive):
    lib, sync, _pdfs = synced
    sync.sync()
    drive.trash("PDFs")
    for f in list(drive.files.values()):
        if f["name"] in ("a1.pdf", "a2.pdf"):
            f["trashed"] = True
    drive.trash("library.db")
    report = sync.sync()
    assert sorted(report.uploaded) == ["a1", "a2"]
    assert len(drive.by_name("PDFs")) == 1 and len(drive.by_name("library.db")) == 1


def test_existing_identical_remote_pdf_is_reused(synced, drive, tmp_path):
    lib, sync, pdfs = synced
    sync.sync()
    # same library on a second computer without sync state: nothing is uploaded twice
    other = Library(str(tmp_path / "copy.db"))
    for a in lib.articles():
        other.add(a)
    other_sync = DriveSync(other, DriveClient(drive))
    report = other_sync.sync()
    assert report.uploaded == [] and report.unchanged == 2
    assert len(drive.by_name("a1.pdf")) == 1
    other.close()


def test_daily_backups_are_pruned(synced, drive, monkeypatch):
    lib, sync, _pdfs = synced
    import datetime as real_datetime

    class FakeDate(real_datetime.date):
        current = real_datetime.date(2026, 1, 1)

        @classmethod
        def today(cls):
            return cls.current

    monkeypatch.setattr(gdrive.datetime, "date", FakeDate)
    for day in range(1, 15):
        FakeDate.current = real_datetime.date(2026, 1, day)
        sync.backup_library()
    backups = sorted(f["name"] for f in drive.children(drive.by_name("Backups")[0]["id"]))
    assert len(backups) == gdrive.KEEP_DAILY_BACKUPS
    assert backups[0] == "library-2026-01-05.db" and backups[-1] == "library-2026-01-14.db"


def test_restore_on_another_computer(synced, drive, tmp_path):
    lib, sync, _pdfs = synced
    lib.add_comment("a1", "restored comment")
    sync.sync()
    dest = str(tmp_path / "newpc" / "library.db")
    pdf_dir = str(tmp_path / "newpc" / "PDFs")
    report = restore_from_drive(DriveClient(drive), dest, pdf_dir)
    assert sorted(report.downloaded) == ["a1", "a2"]
    restored = Library(dest)
    a1 = restored.get("a1")
    assert a1.comments == ["restored comment"] and a1.has_pdf and a1.folderpath == pdf_dir
    assert not restored.get("nopdf").has_pdf
    # the restored library knows it is in sync (nothing to upload again)
    assert not DriveSync(restored, DriveClient(drive)).pending()
    restored.close()
    with pytest.raises(DriveError, match="already exists"):
        restore_from_drive(DriveClient(drive), dest, pdf_dir)


def test_restore_errors(tmp_path, drive):
    with pytest.raises(DriveError, match="no SciLibra folder"):
        restore_from_drive(DriveClient(drive), str(tmp_path / "x.db"), str(tmp_path))


def test_network_errors_are_reported(synced, drive):
    _lib, sync, _pdfs = synced
    drive.offline = True
    with pytest.raises(DriveError, match="cannot be reached"):
        sync.sync()


def test_names_with_quotes_are_escaped(drive):
    client = DriveClient(drive)
    folder = client.ensure_folder("O'Brien's papers")
    assert client.ensure_folder("O'Brien's papers") == folder
    assert client.list("root", name="O'Brien's papers")[0]["id"] == folder


def test_large_file_is_uploaded_in_chunks(tmp_path, drive, monkeypatch):
    monkeypatch.setattr(gdrive, "CHUNK", 1000)
    path = tmp_path / "big.bin"
    path.write_bytes(os.urandom(4500))
    meta = DriveClient(drive).upload(str(path), "big.bin", "root")
    assert drive.files[meta["id"]]["_content"] == path.read_bytes()
    out = tmp_path / "back.bin"
    DriveClient(drive).download(meta["id"], str(out))
    assert out.read_bytes() == path.read_bytes()


def test_account_client_file_and_sign_out(tmp_path):
    account = DriveAccount(str(tmp_path / "home"))
    assert not account.has_client and not account.signed_in and account.email == ""
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    with pytest.raises(DriveError, match="not an OAuth client"):
        account.install_client_file(str(bad))
    web = tmp_path / "web.json"
    web.write_text(json.dumps({"web": {"client_id": "x", "client_secret": "y"}}))
    with pytest.raises(DriveError, match="Desktop app"):
        account.install_client_file(str(web))
    good = tmp_path / "client_secret_123.json"
    good.write_text(json.dumps({"installed": {"client_id": "x.apps.googleusercontent.com", "client_secret": "y",
                                              "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                                              "token_uri": "https://oauth2.googleapis.com/token"}}))
    account.install_client_file(str(good))
    assert account.has_client
    with pytest.raises(DriveError, match="Not signed in"):
        account.credentials()
    fake_token(account.token_file)
    assert account.signed_in and account.email == "scientist@example.com"
    account.sign_out()
    assert not account.signed_in


def test_bundled_client_is_used(tmp_path):
    bundled = tmp_path / "bundled.json"
    bundled.write_text("{}")
    assert DriveAccount(str(tmp_path / "home"), bundled_client=str(bundled)).client_config_path() == str(bundled)


def test_rename_and_delete_keep_drive_state_consistent(synced, drive):
    lib, sync, _pdfs = synced
    sync.sync()
    a = lib.get("a1")
    a.key = "a1new"
    a.pdffile = "a1.pdf"
    lib.update(a, old_key="a1")
    assert "a1new" in lib.db.drive_state() and "a1" not in lib.db.drive_state()
    report = sync.sync()
    assert report.uploaded == [] or report.uploaded == ["a1new"]
    lib.delete(["a1new"])
    assert "a1new" not in lib.db.drive_state()


def test_sign_in_requires_drive_permission():
    """Google lets users untick the Drive permission; that must give a clear error, not a crash."""
    from scilibra.core.gdrive import DRIVE_SCOPE, DriveError, check_granted
    check_granted(f"openid https://www.googleapis.com/auth/userinfo.email {DRIVE_SCOPE}")
    check_granted(["openid", DRIVE_SCOPE])
    check_granted(None)  # Google omits the scope when everything asked for was granted
    with pytest.raises(DriveError, match="tick the box"):
        check_granted("https://www.googleapis.com/auth/userinfo.email openid")


def test_bundled_client_is_scrambled(tmp_path):
    """The shipped client file must not contain the secret in plain text, but must load back unchanged."""
    from scilibra.core.gdrive import bundle_client_file, load_client_config
    config = {"installed": {"client_id": "123.apps.googleusercontent.com", "client_secret": "not-a-real-secret"}}
    src, dat = tmp_path / "client.json", tmp_path / "google_client.dat"
    src.write_text(json.dumps(config))
    bundle_client_file(str(src), str(dat))
    assert "not-a-real-secret" not in dat.read_text() and "client_secret" not in dat.read_text()
    assert load_client_config(str(dat)) == config
    assert load_client_config(str(src)) == config
    account = DriveAccount(str(tmp_path / "home"), bundled_client=str(dat))
    assert account.client_config_path() == str(dat)


def test_shipped_client_file_is_valid():
    from scilibra.core.gdrive import load_client_config
    path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "scilibra", "assets", "google_client.dat")
    if os.path.exists(path):
        section = load_client_config(path)["installed"]
        assert section["client_id"].endswith(".apps.googleusercontent.com") and section["client_secret"]
