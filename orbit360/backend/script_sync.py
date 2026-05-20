"""
script_sync.py — Orbit360
Background git-pull worker for the sidecar systems/ directory.

When orbit360.exe finds a systems/ directory next to itself it uses that
instead of the read-only bundled copy.  This module runs `git pull` there in
a background thread so scripts stay current without a rebuild.

One-time setup for each machine that receives the exe:
    1. Copy (or git-clone) the orbit_hub systems/ folder next to orbit360.exe
    2. From then on, Orbit360 will auto-pull on every launch and on demand
       via the "Sync Scripts" button.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from PySide6.QtCore import QThread, Signal


def is_git_repo(path: Path) -> bool:
    """Return True if *path* is inside a git working tree and git is on PATH."""
    try:
        r = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--is-inside-work-tree"],
            capture_output=True, text=True, timeout=5,
        )
        return r.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


class ScriptSyncWorker(QThread):
    """
    Runs ``git pull --ff-only`` on *systems_dir* in a background thread.

    Signals:
        sync_finished(success: bool, message: str)
            Always emitted once the attempt completes or is skipped.
            *success* is False when git is unavailable, the directory is not a
            repo, or the pull fails — the app continues with whatever scripts
            are already present.
    """

    sync_finished = Signal(bool, str)  # success, human-readable message

    def __init__(self, systems_dir: Path, parent=None) -> None:
        super().__init__(parent)
        self._systems_dir = systems_dir

    def run(self) -> None:
        path = self._systems_dir

        if not path.exists():
            self.sync_finished.emit(False, "Sidecar systems/ not found — using bundled scripts")
            return

        if not is_git_repo(path):
            self.sync_finished.emit(False, "Sidecar systems/ is not a git repo — sync skipped")
            return

        try:
            result = subprocess.run(
                ["git", "-C", str(path), "pull", "--ff-only"],
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode == 0:
                msg = result.stdout.strip() or "Scripts already up to date."
                self.sync_finished.emit(True, msg)
            else:
                err = result.stderr.strip() or result.stdout.strip() or "git pull failed"
                self.sync_finished.emit(False, f"Sync failed: {err}")
        except FileNotFoundError:
            self.sync_finished.emit(
                False, "git not found on PATH — install git to enable auto-sync"
            )
        except subprocess.TimeoutExpired:
            self.sync_finished.emit(False, "git pull timed out after 30 s")
