"""Command line entry point: `python -m scilibra` or `scilibra`."""

from __future__ import annotations

import argparse
import logging
import os
import sys

from . import __version__


def main(argv=None):
    parser = argparse.ArgumentParser(prog="scilibra", description="SciLibra - manage your scientific articles.")
    parser.add_argument("library", nargs="?", default="",
                        help="library file (.db) to open; default: the last used library")
    parser.add_argument("--version", action="version", version=f"SciLibra {__version__}")
    parser.add_argument("--debug", action="store_true", help="show debug messages")
    args = parser.parse_args(argv)

    # SciLibra's own messages; Kivy logs to ~/.kivy/logs (and to the console only with --debug).
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    app_log = logging.getLogger("scilibra")
    app_log.addHandler(handler)
    app_log.setLevel(logging.DEBUG if args.debug else logging.WARNING)
    # Kivy must not parse our command line, and should stay quiet unless debugging.
    os.environ.setdefault("KIVY_NO_ARGS", "1")
    if not args.debug:
        os.environ.setdefault("KIVY_NO_CONSOLELOG", "1")

    from kivy.config import Config
    Config.set("input", "mouse", "mouse,multitouch_on_demand")  # no red dots on right-click
    Config.set("kivy", "exit_on_escape", "0")
    Config.set("graphics", "width", "1280")
    Config.set("graphics", "height", "800")

    from .gui.app import SciLibraApp
    SciLibraApp(library_path=args.library).run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
