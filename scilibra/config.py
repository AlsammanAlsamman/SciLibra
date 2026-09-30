"""User settings and data locations."""

from __future__ import annotations

import json
import logging
import os
import shutil
import sys
from dataclasses import asdict, dataclass, field

log = logging.getLogger(__name__)

LEGACY_DB_NAME = "scilibraLibrary.db"
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def data_dir() -> str:
    """Per-user folder for the library and settings (override with $SCILIBRA_HOME)."""
    if os.environ.get("SCILIBRA_HOME"):
        return os.path.abspath(os.path.expanduser(os.environ["SCILIBRA_HOME"]))
    if sys.platform.startswith("win"):
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        return os.path.join(base, "SciLibra")
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/SciLibra")
    base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
    return os.path.join(base, "scilibra")


@dataclass
class Settings:
    library_path: str = ""
    last_folder: str = ""
    recent_libraries: list[str] = field(default_factory=list)
    drive_auto_sync: bool = True
    theme: str = "light"

    @staticmethod
    def file() -> str:
        return os.path.join(data_dir(), "settings.json")

    @classmethod
    def load(cls) -> "Settings":
        try:
            with open(cls.file(), encoding="utf-8") as fh:
                data = json.load(fh)
            known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
            return cls(**known)
        except FileNotFoundError:
            return cls()
        except (OSError, ValueError, TypeError) as exc:
            log.warning("Ignoring unreadable settings file: %s", exc)
            return cls()

    def save(self):
        os.makedirs(data_dir(), exist_ok=True)
        tmp = self.file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(asdict(self), fh, indent=2)
        os.replace(tmp, self.file())

    def start_folder(self) -> str:
        for folder in (self.last_folder, os.path.expanduser("~/Documents"), os.path.expanduser("~")):
            if folder and os.path.isdir(folder):
                return folder
        return os.getcwd()

    def remember_library(self, path: str):
        path = os.path.abspath(path)
        self.library_path = path
        self.recent_libraries = [path] + [p for p in self.recent_libraries if p != path][:7]


def default_library_path() -> str:
    return os.path.join(data_dir(), "library.db")


def resolve_library_path(settings: Settings, explicit: str = "") -> tuple[str, str]:
    """Pick the library file to open. Returns (path, message) - message describes a legacy import.

    On first start, a SciLibra 1.x library (scilibraLibrary.db in the current or project folder)
    is copied to the data folder; the original file is left untouched.
    """
    if explicit:
        return os.path.abspath(explicit), ""
    if settings.library_path and os.path.exists(settings.library_path):
        return settings.library_path, ""
    target = default_library_path()
    if os.path.exists(target):
        return target, ""
    for folder in (os.getcwd(), PROJECT_DIR):
        legacy = os.path.join(folder, LEGACY_DB_NAME)
        if os.path.isfile(legacy):
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(legacy, target)
            return target, f"Imported your existing library from {legacy} (the original file was not changed)."
    return target, ""
