"""Runs the end-to-end GUI scenario (tests/gui_scenario.py) in a separate process.

Skipped when no display is available. Set SCILIBRA_GUI_SHOTS=<folder> to keep the screenshots.
"""

import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))


@pytest.mark.skipif(not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY") or sys.platform in ("win32", "darwin")),
                    reason="needs a display")
def test_gui_scenario(tmp_path):
    shots = os.environ.get("SCILIBRA_GUI_SHOTS") or str(tmp_path / "shots")
    proc = subprocess.run([sys.executable, os.path.join(HERE, "gui_scenario.py"), shots],
                          capture_output=True, text=True, timeout=300)
    summary = [line for line in proc.stdout.splitlines() if line.startswith(("PASS", "FAIL")) or "steps passed" in line]
    assert proc.returncode == 0, "\n".join(summary) + "\n" + proc.stdout[-4000:] + proc.stderr[-2000:]
