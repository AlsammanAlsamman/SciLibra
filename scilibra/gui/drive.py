"""Google Drive: sign-in dialog, manual and automatic backup/sync, and restore."""

from __future__ import annotations

import datetime
import logging
import os
import threading
import webbrowser

from kivy.clock import Clock, mainthread
from kivy.properties import BooleanProperty, ObjectProperty, StringProperty

from ..config import data_dir
from ..core import gdrive
from .dialogs import BasePopup, ProgressDialog

log = logging.getLogger(__name__)

CONSOLE_URL = "https://console.cloud.google.com/apis/credentials"
SETUP_STEPS = """Google requires every app to have its own "OAuth client". Create it once (about 5 minutes):

1. Open Google Cloud Console (button below) and sign in with your Google account.
2. Create a project (any name, e.g. "SciLibra").
3. APIs & Services > Library: search "Google Drive API" and press Enable.
4. APIs & Services > OAuth consent screen: choose "External", fill in the app name and your
   e-mail, and add yourself under "Test users".
5. APIs & Services > Credentials > Create credentials > OAuth client ID,
   Application type: "Desktop app". Press Create, then "Download JSON".
6. Press "Load client file..." below and choose the downloaded file.

SciLibra only gets access to the files it creates itself (a "SciLibra" folder),
never to your other Drive files."""

AUTO_SYNC_INTERVAL = 90      # seconds between checks for changes
AFTER_CHANGE_DELAY = 8       # seconds after an edit before syncing


class DriveDialog(BasePopup):
    controller = ObjectProperty(None)
    state = StringProperty("setup")      # setup / signin / connected
    account = StringProperty("")
    last_sync = StringProperty("")
    auto_sync = BooleanProperty(True)
    setup_steps = StringProperty(SETUP_STEPS)

    def refresh(self, *_):
        c = self.controller
        self.state = "connected" if c.account.signed_in else ("signin" if c.account.has_client else "setup")
        self.account = c.account.email or "your Google account"
        stamp = c.app.library.db.get_property("drive_last_sync") if c.app.library else ""
        self.last_sync = stamp[:16] if stamp else "never"
        self.auto_sync = c.app.settings.drive_auto_sync

    def on_open(self):
        self.refresh()


class DriveController:
    def __init__(self, app):
        self.app = app
        bundled = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets",
                               "google_client.json")
        self.account = gdrive.DriveAccount(data_dir(), bundled_client=bundled)
        self.syncing = False
        self.dialog = None
        self._after_change = None
        Clock.schedule_interval(self._tick, AUTO_SYNC_INTERVAL)
        self.update_state()

    # ------------------------------------------------------------------ state shown in the UI
    def update_state(self):
        app = self.app
        app.drive_connected = self.account.signed_in
        app.drive_syncing = self.syncing
        if self.dialog is not None:
            self.dialog.refresh()

    def open_dialog(self):
        self.dialog = DriveDialog(controller=self, title="Google Drive backup")
        self.dialog.bind(on_dismiss=lambda *_: setattr(self, "dialog", None))
        self.dialog.open()

    def set_auto_sync(self, value):
        self.app.settings.drive_auto_sync = bool(value)
        self.app.settings.save()
        if value:
            self.changed()

    # ------------------------------------------------------------------ setup / sign-in
    def open_console(self):
        webbrowser.open(CONSOLE_URL)

    def load_client_file(self):
        def chosen(path, _folder):
            try:
                self.account.install_client_file(path)
            except gdrive.DriveError as exc:
                self.app.message("Google Drive", str(exc))
                return
            self.update_state()
            self.app.set_status("Google OAuth client loaded - now press 'Sign in with Google'")
        self.app.choose_file("Choose the OAuth client JSON file downloaded from Google Cloud Console", chosen,
                             filters=["*.json"])

    def sign_in(self):
        progress = ProgressDialog(title="Sign in with Google",
                                  message="Your browser opened the Google sign-in page. Choose your account and "
                                          "press Allow, then come back here.")
        progress.open()

        def work():
            try:
                self.account.sign_in()
                error = None
            except Exception as exc:  # browser closed, access denied, network...
                log.exception("Google sign-in failed")
                error = str(exc) or exc.__class__.__name__
            finish(error)

        @mainthread
        def finish(error):
            progress.dismiss()
            self.update_state()
            if error:
                self.app.message("Google sign-in failed", error)
                return
            self.app.set_status(f"Connected to Google Drive as {self.account.email or 'your account'}")
            self.sync(manual=True)
        threading.Thread(target=work, daemon=True).start()

    def sign_out(self):
        def really():
            self.account.sign_out()
            self.update_state()
            self.app.set_status("Signed out of Google Drive (your files on Drive were kept)")
        self.app.confirm("Sign out of Google Drive", "SciLibra will stop backing up to Google Drive.\n"
                         "The files already on your Drive are kept.", really, confirm_text="Sign out")

    def open_in_browser(self):
        library = self.app.library
        if library:
            webbrowser.open(gdrive.DriveSync(library, None).folder_link())

    # ------------------------------------------------------------------ sync
    def _client(self):
        return gdrive.DriveClient(self.account.session())

    def changed(self):
        """Something changed locally: sync soon (if automatic sync is on)."""
        if not (self.account.signed_in and self.app.settings.drive_auto_sync):
            return
        if self._after_change is not None:
            self._after_change.cancel()
        self._after_change = Clock.schedule_once(lambda _dt: self.sync(manual=False), AFTER_CHANGE_DELAY)

    def _tick(self, _dt):
        if self.syncing or not self.account.signed_in or not self.app.settings.drive_auto_sync or not self.app.library:
            return
        try:
            pending = gdrive.DriveSync(self.app.library, None).pending()
        except Exception:
            pending = False
        if pending:
            self.sync(manual=False)

    def sync(self, manual=True):
        """Back up the library and upload new/changed PDFs. Manual syncs show progress and a report."""
        library = self.app.library
        if library is None or not self.account.signed_in:
            return
        if self.syncing:
            if manual:
                self.app.message("Google Drive", "A backup is already running.")
            return
        self.syncing = True
        self.update_state()
        progress = ProgressDialog(title="Backing up to Google Drive", message="Connecting...") if manual else None
        if progress:
            progress.open()
        else:
            self.app.set_status("Google Drive: backing up...")

        def report(i, n, key):
            if progress:
                progress.update(i, n, f"Uploading {i + 1}/{n}: {key}" if key and key != "library"
                                else "Backing up the library...")

        def work():
            try:
                if not manual and not gdrive.DriveSync(library, None).pending():
                    finish(None, None)
                    return
                result = gdrive.DriveSync(library, self._client()).sync(
                    progress=report, cancelled=lambda: bool(progress and progress.cancelled))
                finish(result, None)
            except Exception as exc:
                log.warning("Drive sync failed: %s", exc)
                finish(None, exc)

        @mainthread
        def finish(result, error):
            self.syncing = False
            if progress:
                progress.dismiss()
            self.update_state()
            if result is None and error is None:  # nothing changed
                self.app.set_status("Google Drive: everything is backed up")
                return
            if error is not None:
                if manual:
                    self.app.message("Google Drive backup failed", str(error))
                else:
                    self.app.set_status(f"Google Drive: backup failed ({error}) - will retry")
                return
            now = datetime.datetime.now().strftime("%H:%M")
            self.app.set_status(f"Google Drive: {result.summary()} ({now})")
            if manual:
                text = f"Backup finished: {result.summary()}."
                if result.failed:
                    text += "\n\nCould not upload: " + ", ".join(result.failed[:20])
                self.app.message("Google Drive", text)
        threading.Thread(target=work, daemon=True).start()

    def sync_before_exit(self, timeout=45):
        """On closing the app: finish a backup of pending changes (waits at most `timeout` seconds)."""
        if not (self.account.signed_in and self.app.settings.drive_auto_sync and self.app.library) or self.syncing:
            return
        try:
            sync = gdrive.DriveSync(self.app.library, None)
            if not sync.pending():
                return
            worker = threading.Thread(target=lambda: gdrive.DriveSync(self.app.library, self._client()).sync(),
                                      daemon=True)
            worker.start()
            worker.join(timeout)
        except Exception as exc:
            log.warning("Backup on exit failed: %s", exc)

    # ------------------------------------------------------------------ restore
    def restore(self):
        def chosen(folder, _parent):
            pdf_folder = os.path.join(folder, "SciLibra PDFs")
            stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            dest = os.path.join(data_dir(), f"library-from-drive-{stamp}.db")

            def work(progress):
                return gdrive.restore_from_drive(
                    self._client(), dest, pdf_folder,
                    progress=lambda i, n, key: progress.update(i, n, f"Downloading {i + 1}/{n}: {key}"),
                    cancelled=lambda: progress.cancelled)

            def done(result):
                self.app.open_library(dest)
                text = f"Restored the library from Google Drive: {result.summary()}.\n\nPDFs are in:\n{pdf_folder}"
                if result.missing:
                    text += f"\n\n{len(result.missing)} articles had a PDF that is not on Drive yet."
                self.app.message("Restore from Google Drive", text)
            self.app.run_in_background("Restoring from Google Drive", work, done)

        def ask_folder():
            self.app.choose_folder("Where should the PDFs be saved? (a 'SciLibra PDFs' folder is created there)",
                                   chosen)
        self.app.confirm("Restore from Google Drive",
                         "This downloads your library and all PDFs from Google Drive - use it on a new computer "
                         "or to recover your library.\n\nThe restored library is opened as a separate file; "
                         "your current library is not changed.", ask_folder, confirm_text="Choose folder...")
