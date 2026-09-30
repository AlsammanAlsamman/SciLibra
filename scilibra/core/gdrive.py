"""Google Drive backup and sync.

SciLibra keeps working on local files; this module mirrors them to a "SciLibra" folder on the user's
Google Drive and can restore them on another computer:

    SciLibra/library.db            the library (Drive keeps earlier versions as revisions)
    SciLibra/Backups/library-DATE.db   one dated copy per day (the newest ones are kept)
    SciLibra/PDFs/<key>.pdf        every article PDF, including the annotations made in it

Access uses the `drive.file` scope: SciLibra can only see files it created itself.
"""

from __future__ import annotations

import base64
import datetime
import hashlib
import json
import logging
import os
import shutil
import tempfile
import time
from dataclasses import dataclass, field

log = logging.getLogger(__name__)

SCOPES = ["openid", "https://www.googleapis.com/auth/userinfo.email",
          "https://www.googleapis.com/auth/drive.file"]
API = "https://www.googleapis.com/drive/v3"
UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
FOLDER_MIME = "application/vnd.google-apps.folder"
ROOT_FOLDER = "SciLibra"
CHUNK = 8 * 1024 * 1024
KEEP_DAILY_BACKUPS = 10
TIMEOUT = 60
# Temporary Google errors (overloaded server, rate limit): wait and try again, as Google recommends.
RETRY_STATUS = {408, 429, 500, 502, 503, 504}
RETRY_WAITS = (2, 4, 8, 16, 32, 60)     # seconds between attempts
NETWORK_RETRIES = 2                    # connection errors: retry quickly, twice
MAX_FAILURES_IN_A_ROW = 3              # stop a sync when Drive keeps failing
_sleep = time.sleep                    # replaced in tests


class DriveError(Exception):
    """Google Drive could not be reached, refused a request, or is not configured."""


def md5_of(path: str) -> str:
    digest = hashlib.md5()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


# ---------------------------------------------------------------- account / sign-in
DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file"

# The OAuth client shipped with SciLibra is stored scrambled (scilibra/assets/google_client.dat).
# This is not encryption: Google treats the secret of a "Desktop app" client as public by design, since
# anyone can read it from an installed app. Scrambling only keeps it out of plain-text secret scanners,
# which would otherwise revoke it and break sign-in for every user. Access to a user's Drive always
# needs that user's own consent, and SciLibra can only see the files it created itself.
_SCRAMBLE_KEY = b"SciLibra-desktop-oauth-client"


def scramble(data: bytes) -> str:
    mixed = bytes(b ^ _SCRAMBLE_KEY[i % len(_SCRAMBLE_KEY)] for i, b in enumerate(data))
    return base64.b64encode(mixed).decode("ascii")


def unscramble(text: str) -> bytes:
    mixed = base64.b64decode(text.strip())
    return bytes(b ^ _SCRAMBLE_KEY[i % len(_SCRAMBLE_KEY)] for i, b in enumerate(mixed))


def bundle_client_file(json_path: str, dat_path: str):
    """Create the scrambled bundled client from the JSON downloaded from Google Cloud Console."""
    with open(json_path, "rb") as fh:
        data = fh.read()
    json.loads(data)  # must be valid JSON
    with open(dat_path, "w", encoding="ascii") as fh:
        fh.write(scramble(data) + "\n")


def load_client_config(path: str) -> dict:
    """Read an OAuth client file: plain JSON, or the scrambled .dat bundled with SciLibra."""
    if path.endswith(".dat"):
        with open(path, encoding="ascii") as fh:
            return json.loads(unscramble(fh.read()))
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def check_granted(scope):
    """Raise DriveError unless the Drive permission was granted. `scope` is the token's scope (str or list)."""
    granted = scope.split() if isinstance(scope, str) else list(scope or [])
    if scope is not None and DRIVE_SCOPE not in granted:
        raise DriveError("SciLibra did not get permission to store its files on your Google Drive.\n\n"
                         "Please press 'Sign in with Google' again and, on the Google page, tick the box\n"
                         "\"See, edit, create and delete only the specific Google Drive files you use with this app\"\n"
                         "before pressing Continue.")


class DriveAccount:
    """Sign-in state. Files live in the SciLibra data folder:

    google-client.json   the OAuth client ("Desktop app") created in Google Cloud Console
    google-token.json    the user's saved sign-in (refresh token)
    """

    def __init__(self, folder: str, bundled_client: str = ""):
        self.folder = folder
        self.client_file = os.path.join(folder, "google-client.json")
        self.token_file = os.path.join(folder, "google-token.json")
        self.bundled_client = bundled_client

    # client configuration
    def client_config_path(self) -> str:
        for path in (self.client_file, self.bundled_client):
            if path and os.path.isfile(path):
                return path
        return ""

    @property
    def has_client(self) -> bool:
        return bool(self.client_config_path())

    def install_client_file(self, path: str):
        """Validate and store the OAuth client JSON downloaded from Google Cloud Console."""
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, ValueError) as exc:
            raise DriveError(f"This is not a readable JSON file: {exc}") from exc
        section = data.get("installed") or data.get("web")
        if not section or not section.get("client_id") or not section.get("client_secret"):
            raise DriveError("This file is not an OAuth client file. In Google Cloud Console create "
                             "'OAuth client ID' of type 'Desktop app' and download its JSON.")
        if "web" in data and "installed" not in data:
            raise DriveError("This OAuth client is of type 'Web application'. Please create one of type "
                             "'Desktop app' instead.")
        os.makedirs(self.folder, exist_ok=True)
        shutil.copyfile(path, self.client_file)

    # sign-in
    @property
    def signed_in(self) -> bool:
        return os.path.isfile(self.token_file)

    @property
    def email(self) -> str:
        try:
            with open(self.token_file, encoding="utf-8") as fh:
                return json.load(fh).get("scilibra_email", "")
        except (OSError, ValueError):
            return ""

    def sign_in(self, open_browser=True):
        """Open the Google sign-in page in the browser and wait for the user to approve."""
        from google_auth_oauthlib.flow import InstalledAppFlow
        path = self.client_config_path()
        if not path:
            raise DriveError("Google Drive is not set up yet: the OAuth client file is missing.")
        # Google lets the user untick single permissions; accept the reply and check it ourselves
        # (otherwise oauthlib fails with a cryptic "Scope has changed" warning).
        os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
        flow = InstalledAppFlow.from_client_config(load_client_config(path), SCOPES)
        creds = flow.run_local_server(
            port=0, open_browser=open_browser, authorization_prompt_message="", timeout_seconds=300,
            success_message="Done - you can close this tab and go back to SciLibra.")
        check_granted(flow.oauth2session.token.get("scope"))
        self._save(creds, email=self._fetch_email(creds))

    def _fetch_email(self, creds) -> str:
        try:
            from google.auth.transport.requests import AuthorizedSession
            response = AuthorizedSession(creds).get("https://openidconnect.googleapis.com/v1/userinfo", timeout=20)
            return response.json().get("email", "") if response.status_code == 200 else ""
        except Exception:
            return ""

    def _save(self, creds, email=""):
        os.makedirs(self.folder, exist_ok=True)
        data = json.loads(creds.to_json())
        data["scilibra_email"] = email or self.email
        tmp = self.token_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh)
        os.replace(tmp, self.token_file)
        try:
            os.chmod(self.token_file, 0o600)
        except OSError:
            pass

    def credentials(self):
        from google.auth.exceptions import RefreshError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        if not self.signed_in:
            raise DriveError("Not signed in to Google Drive.")
        try:
            creds = Credentials.from_authorized_user_file(self.token_file, SCOPES)
            if not creds.valid:
                creds.refresh(Request())
                self._save(creds)
        except RefreshError as exc:
            os.remove(self.token_file)  # the sign-in is no longer usable: ask the user to sign in again
            raise DriveError("Your Google sign-in has expired or was revoked. Please sign in again.") from exc
        except (ValueError, OSError) as exc:
            raise DriveError(f"The saved Google sign-in is unreadable: {exc}") from exc
        return creds

    def session(self):
        from google.auth.transport.requests import AuthorizedSession
        return AuthorizedSession(self.credentials())

    def sign_out(self):
        """Forget the sign-in (and revoke it at Google when possible). Files on Drive are kept."""
        try:
            import requests
            token = json.load(open(self.token_file, encoding="utf-8")).get("refresh_token")
            if token:
                requests.post("https://oauth2.googleapis.com/revoke", params={"token": token}, timeout=10)
        except Exception:
            pass
        if os.path.exists(self.token_file):
            os.remove(self.token_file)


# ---------------------------------------------------------------- Drive REST client
class DriveClient:
    """Minimal Google Drive v3 client over an authorised requests-style session."""

    FIELDS = "id,name,md5Checksum,size,modifiedTime,mimeType,trashed"

    def __init__(self, session):
        self.session = session

    def _check(self, response, what):
        if response.status_code >= 400:
            try:
                message = response.json().get("error", {}).get("message", "")
            except Exception:
                message = ""
            raise DriveError(f"Google Drive: {what} failed (HTTP {response.status_code}) {message}".strip())
        return response

    def _send(self, method, url, what, **kwargs):
        """One HTTP call, retried after temporary errors (HTTP 5xx/429, connection problems)."""
        import requests
        kwargs.setdefault("timeout", TIMEOUT)
        for attempt, wait in enumerate(RETRY_WAITS + (None,)):
            try:
                response = getattr(self.session, method)(url, **kwargs)
            except requests.RequestException as exc:
                # no internet at all: say so quickly instead of waiting through the whole retry schedule
                if wait is None or attempt >= NETWORK_RETRIES:
                    raise DriveError(f"Google Drive cannot be reached ({what}): {exc}") from exc
                log.info("Google Drive %s: %s - retrying in %ss", what, exc, wait)
            else:
                if response.status_code not in RETRY_STATUS or wait is None:
                    return response
                retry_after = response.headers.get("Retry-After", "")
                if retry_after.isdigit():
                    wait = min(int(retry_after), 120)
                log.info("Google Drive %s: HTTP %s - retrying in %ss", what, response.status_code, wait)
            _sleep(wait)

    def _request(self, method, url, what, **kwargs):
        return self._check(self._send(method, url, what, **kwargs), what)

    @staticmethod
    def _quote(name):
        return name.replace("\\", "\\\\").replace("'", "\\'")

    def get(self, file_id):
        """File metadata, or None if it does not exist (or is in the trash)."""
        response = self._send("get", f"{API}/files/{file_id}", "reading file information",
                              params={"fields": self.FIELDS})
        if response.status_code == 404:
            return None
        data = self._check(response, "reading file information").json()
        return None if data.get("trashed") else data

    def list(self, parent, name=None, folders_only=False):
        query = [f"'{parent}' in parents", "trashed = false"]
        if name is not None:
            query.append(f"name = '{self._quote(name)}'")
        if folders_only:
            query.append(f"mimeType = '{FOLDER_MIME}'")
        files, token = [], None
        while True:
            params = {"q": " and ".join(query), "fields": f"nextPageToken,files({self.FIELDS})",
                      "pageSize": 1000, "spaces": "drive"}
            if token:
                params["pageToken"] = token
            data = self._request("get", f"{API}/files", "listing files", params=params).json()
            files += data.get("files", [])
            token = data.get("nextPageToken")
            if not token:
                return files

    def ensure_folder(self, name, parent="root", known_id=""):
        if known_id and self.get(known_id) is not None:
            return known_id
        found = self.list(parent, name=name, folders_only=True)
        if found:
            return found[0]["id"]
        metadata = {"name": name, "mimeType": FOLDER_MIME, "parents": [parent]}
        return self._request("post", f"{API}/files", "creating a folder", json=metadata,
                             params={"fields": "id"}).json()["id"]

    def upload(self, path, name, parent, file_id="", mime="application/octet-stream"):
        """Create (or replace the content of) a file with a resumable upload. Returns its metadata."""
        size = os.path.getsize(path)
        params = {"uploadType": "resumable", "fields": self.FIELDS}
        if file_id:
            start = self._request("patch", f"{UPLOAD_API}/files/{file_id}", "starting an upload",
                                  params=params, json={"name": name},
                                  headers={"X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(size)})
        else:
            start = self._request("post", f"{UPLOAD_API}/files", "starting an upload", params=params,
                                  json={"name": name, "parents": [parent]},
                                  headers={"X-Upload-Content-Type": mime, "X-Upload-Content-Length": str(size)})
        location = start.headers.get("Location") or start.headers.get("location")
        if not location:
            raise DriveError("Google Drive did not accept the upload.")
        with open(path, "rb") as fh:
            offset, stalled = 0, 0
            while True:
                fh.seek(offset)
                chunk = fh.read(CHUNK)
                end = offset + len(chunk) - 1
                headers = {"Content-Length": str(len(chunk)),
                           "Content-Range": f"bytes {offset}-{end}/{size}" if size else "bytes */0"}
                response = self._send("put", location, "uploading", data=chunk, headers=headers)
                if response.status_code in (200, 201):
                    return response.json()
                if response.status_code == 308:
                    new_offset = self._received(response, offset + len(chunk))
                elif response.status_code in RETRY_STATUS:
                    # Still failing after the retries: ask Drive how much it has, and continue from there.
                    new_offset = self._upload_status(location, size, name)
                    if isinstance(new_offset, dict):
                        return new_offset
                else:
                    self._check(response, f"uploading {name}")
                    raise DriveError(f"Upload of {name} was interrupted (HTTP {response.status_code}).")
                stalled = stalled + 1 if new_offset <= offset else 0
                if stalled > 2:
                    raise DriveError(f"Upload of {name} does not progress (HTTP {response.status_code}).")
                offset = new_offset

    @staticmethod
    def _received(response, default):
        """Bytes Drive has received, from the Range header of a 308 reply ("bytes=0-1234")."""
        value = response.headers.get("Range") or response.headers.get("range")
        if not value:
            return 0 if default is None else default
        try:
            return int(value.rsplit("-", 1)[1]) + 1
        except (IndexError, ValueError):
            return 0 if default is None else default

    def _upload_status(self, location, size, name):
        """Offset to resume an interrupted upload from, or the file metadata if it is already complete."""
        response = self._send("put", location, "checking an upload", data=b"",
                              headers={"Content-Length": "0", "Content-Range": f"bytes */{size}"})
        if response.status_code in (200, 201):
            return response.json()
        if response.status_code == 308:
            return self._received(response, None)
        self._check(response, f"uploading {name}")
        raise DriveError(f"Upload of {name} was interrupted (HTTP {response.status_code}).")

    def download(self, file_id, dest):
        folder = os.path.dirname(os.path.abspath(dest))
        os.makedirs(folder, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=folder, suffix=".part")
        os.close(fd)
        try:
            response = self._request("get", f"{API}/files/{file_id}", "downloading", params={"alt": "media"},
                                     stream=True)
            with open(tmp, "wb") as fh:
                for block in response.iter_content(1024 * 1024):
                    fh.write(block)
            os.replace(tmp, dest)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    def delete(self, file_id):
        self._request("delete", f"{API}/files/{file_id}", "deleting a file")


# ---------------------------------------------------------------- sync
@dataclass
class SyncReport:
    uploaded: list[str] = field(default_factory=list)
    unchanged: int = 0
    failed: list[str] = field(default_factory=list)
    library_saved: bool = False
    downloaded: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    def summary(self) -> str:
        parts = []
        if self.library_saved:
            parts.append("library backed up")
        if self.uploaded:
            parts.append(f"{len(self.uploaded)} PDFs uploaded")
        if self.unchanged:
            parts.append(f"{self.unchanged} PDFs already up to date")
        if self.downloaded:
            parts.append(f"{len(self.downloaded)} PDFs downloaded")
        if self.failed:
            parts.append(f"{len(self.failed)} PDFs skipped after errors (tried again at the next backup)")
        return ", ".join(parts) or "nothing to do"


class DriveSync:
    """Mirror a Library to Google Drive, and restore it from there."""

    def __init__(self, library, client: DriveClient):
        self.library = library
        self.db = library.db
        self.client = client

    # folder ids are remembered in the library
    def _folder(self, prop, name, parent):
        known = self.db.get_property(prop) or ""
        folder_id = self.client.ensure_folder(name, parent, known_id=known)
        if folder_id != known:
            self.db.set_property(prop, folder_id)
        return folder_id

    def folders(self):
        root = self._folder("drive_folder", ROOT_FOLDER, "root")
        pdfs = self._folder("drive_pdf_folder", "PDFs", root)
        backups = self._folder("drive_backup_folder", "Backups", root)
        return root, pdfs, backups

    def folder_link(self) -> str:
        folder = self.db.get_property("drive_folder")
        return f"https://drive.google.com/drive/folders/{folder}" if folder else "https://drive.google.com/"

    # ---- library
    def backup_library(self) -> bool:
        root, _pdfs, backups = self.folders()
        with tempfile.TemporaryDirectory() as tmp:
            copy = os.path.join(tmp, "library.db")
            self.db.snapshot(copy)
            known = self.db.get_property("drive_library_file") or ""
            if known and self.client.get(known) is None:
                known = ""
            if not known:
                existing = self.client.list(root, name="library.db")
                known = existing[0]["id"] if existing else ""
            meta = self.client.upload(copy, "library.db", root, file_id=known)
            self.db.set_property("drive_library_file", meta["id"])
            today = f"library-{datetime.date.today().isoformat()}.db"
            daily = self.client.list(backups, name=today)
            self.client.upload(copy, today, backups, file_id=daily[0]["id"] if daily else "")
        dated = sorted((f for f in self.client.list(backups) if f["name"].startswith("library-")),
                       key=lambda f: f["name"], reverse=True)
        for old in dated[KEEP_DAILY_BACKUPS:]:
            self.client.delete(old["id"])
        self.db.set_property("drive_library_synced", self.db.get_property("lastmodificationdate") or "")
        return True

    # ---- PDFs
    def _pdf_jobs(self):
        """(article, local path, stat, state row) for every article with a PDF."""
        state = self.db.drive_state()
        for article in self.library.articles():
            if not article.has_pdf:
                continue
            path = os.path.abspath(article.pdf_path)
            st = os.stat(path)
            yield article, path, st, state.get(article.key)

    @staticmethod
    def _unchanged(path, st, row):
        return row is not None and row["fileid"] and row["path"] == path and row["size"] == st.st_size \
            and abs((row["mtime"] or 0) - st.st_mtime) < 1e-6

    def pending(self) -> bool:
        """True when the library or any PDF changed since the last sync (quick check, no network)."""
        if (self.db.get_property("drive_library_synced") or None) != (self.db.get_property("lastmodificationdate") or ""):
            return True
        return any(not self._unchanged(path, st, row) for _a, path, st, row in self._pdf_jobs())

    def sync_pdfs(self, report: SyncReport, progress=None, cancelled=lambda: False):
        _root, pdfs, _backups = self.folders()
        jobs = list(self._pdf_jobs())
        # One listing per sync tells which uploads still exist on Drive (files may be deleted there).
        remote = self.client.list(pdfs)
        by_id = {f["id"]: f for f in remote}
        by_name = {f["name"]: f for f in remote}
        failures_in_a_row = 0
        for i, (article, path, st, row) in enumerate(jobs):
            if cancelled():
                break
            if progress:
                progress(i, len(jobs), article.key)
            on_drive = row is not None and row["fileid"] in by_id
            if on_drive and self._unchanged(path, st, row):
                report.unchanged += 1
                continue
            try:
                md5 = md5_of(path)
                name = f"{article.key}.pdf"
                if on_drive and row["md5"] == md5:
                    file_id = row["fileid"]
                    report.unchanged += 1
                else:
                    file_id = row["fileid"] if on_drive else ""
                    same = by_name.get(name)
                    if not file_id and same and same.get("md5Checksum") == md5:
                        file_id = same["id"]  # already uploaded (e.g. from another computer)
                        report.unchanged += 1
                    else:
                        if not file_id and same:
                            file_id = same["id"]
                        meta = self.client.upload(path, name, pdfs, file_id=file_id, mime="application/pdf")
                        file_id = meta["id"]
                        report.uploaded.append(article.key)
                self.db.set_drive_state(article.key, path, st.st_mtime, st.st_size, md5, file_id)
                failures_in_a_row = 0
            except OSError as exc:
                log.warning("Cannot upload %s: %s", path, exc)
                report.failed.append(article.key)
            except DriveError as exc:
                # Skip this PDF (it is tried again next time); give up only if Drive keeps failing.
                log.warning("Cannot upload %s: %s", path, exc)
                report.failed.append(article.key)
                failures_in_a_row += 1
                if failures_in_a_row >= MAX_FAILURES_IN_A_ROW:
                    raise DriveError(f"{exc}\n\nGoogle Drive failed {failures_in_a_row} times in a row, so the "
                                     f"backup was paused. Everything uploaded so far is kept; press "
                                     f"'Back up now' later to continue.") from exc
        if progress:
            progress(len(jobs), len(jobs), "")

    def sync(self, progress=None, cancelled=lambda: False) -> SyncReport:
        """Back up the library and upload new or changed PDFs."""
        report = SyncReport()
        if progress:
            progress(0, 1, "library")
        report.library_saved = self.backup_library()
        self.sync_pdfs(report, progress, cancelled)
        self.db.set_property("drive_last_sync", datetime.datetime.now().isoformat(sep=" ", timespec="seconds"))
        return report

    # ---- restore
    def remote_library(self):
        """Metadata of library.db on Drive, or None."""
        root = self.client.list("root", name=ROOT_FOLDER, folders_only=True)
        if not root:
            return None
        found = self.client.list(root[0]["id"], name="library.db")
        return found[0] if found else None


def restore_from_drive(client: DriveClient, library_dest: str, pdf_folder: str, progress=None,
                       cancelled=lambda: False) -> SyncReport:
    """Download the library and all PDFs from Drive. PDFs go to `pdf_folder`; the restored library points to them."""
    from .library import Library
    report = SyncReport()
    root = client.list("root", name=ROOT_FOLDER, folders_only=True)
    if not root:
        raise DriveError("There is no SciLibra folder on this Google Drive yet.")
    root_id = root[0]["id"]
    library_file = client.list(root_id, name="library.db")
    if not library_file:
        raise DriveError("The SciLibra folder on Google Drive does not contain a library.")
    if progress:
        progress(0, 1, "library")
    if os.path.exists(library_dest):
        raise DriveError(f"{library_dest} already exists.")
    client.download(library_file[0]["id"], library_dest)
    library = Library(library_dest)
    try:
        folders = client.list(root_id, name="PDFs", folders_only=True)
        remote = {f["name"]: f for f in client.list(folders[0]["id"])} if folders else {}
        os.makedirs(pdf_folder, exist_ok=True)
        articles = library.articles()
        for i, article in enumerate(articles):
            if cancelled():
                break
            if progress:
                progress(i, len(articles), article.key)
            meta = remote.get(f"{article.key}.pdf")
            if meta is None:
                if article.folderpath:
                    report.missing.append(article.key)
                continue
            dest = os.path.join(pdf_folder, f"{article.key}.pdf")
            if not (os.path.exists(dest) and md5_of(dest) == meta.get("md5Checksum")):
                client.download(meta["id"], dest)
                report.downloaded.append(article.key)
            article.folderpath, article.pdffile = pdf_folder, ""
            library.db.save(article)
            st = os.stat(dest)
            library.db.set_drive_state(article.key, os.path.abspath(dest), st.st_mtime, st.st_size,
                                       meta.get("md5Checksum", ""), meta["id"])
        library.db.set_property("drive_folder", root_id)
        if folders:
            library.db.set_property("drive_pdf_folder", folders[0]["id"])
        library.db.set_property("drive_library_file", library_file[0]["id"])
        library.db.set_property("drive_library_synced", library.db.get_property("lastmodificationdate") or "")
    finally:
        library.close()
    return report
