"""
screenshot_watcher.py — Orbit360 v4.0

QFileSystemWatcher wrapper that monitors a run's output tree for new PNG files
and emits new_screenshot(path) for each one discovered.

Usage:
    watcher = ScreenshotWatcher(parent)
    watcher.new_screenshot.connect(strip.add_screenshot)
    watcher.watch(str(run_root))   # call at run start
    watcher.clear()                # call before the next run
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QFileSystemWatcher, QObject, Signal


class ScreenshotWatcher(QObject):
    """
    Monitors a run root directory tree for new .png files.

    QFileSystemWatcher only fires on direct directory changes, so this class
    adds new subdirectories to the watcher as they appear (Orbit creates a
    subdirectory per script).  Within each directory it emits new_screenshot
    for every PNG it hasn't seen before.
    """

    new_screenshot = Signal(str)   # absolute path to a newly-found PNG

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._fs_watcher = QFileSystemWatcher(self)
        self._known: set[str] = set()
        self._fs_watcher.directoryChanged.connect(self._on_dir_changed)

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def watch(self, run_root: str) -> None:
        """
        Start watching `run_root` (and its descendants) for new PNG files.
        Any previously watched paths are removed first.
        """
        self._remove_all_watched()
        self._known.clear()
        root = Path(run_root)
        if root.exists():
            self._fs_watcher.addPath(str(root))
            for sub in root.rglob("*"):
                if sub.is_dir():
                    self._fs_watcher.addPath(str(sub))

    def clear(self) -> None:
        """Stop watching and forget all known screenshots."""
        self._remove_all_watched()
        self._known.clear()

    # ------------------------------------------------------------------ #
    # Internal                                                             #
    # ------------------------------------------------------------------ #

    def _remove_all_watched(self) -> None:
        dirs = self._fs_watcher.directories()
        if dirs:
            self._fs_watcher.removePaths(dirs)

    def _watch_dir(self, path: Path) -> None:
        """Add `path` to the watcher and recurse into any existing subdirs."""
        p_str = str(path)
        if p_str not in self._fs_watcher.directories():
            self._fs_watcher.addPath(p_str)
        try:
            for child in path.iterdir():
                if child.is_dir():
                    self._watch_dir(child)
        except OSError:
            pass

    def _on_dir_changed(self, path: str) -> None:
        """Called by QFileSystemWatcher whenever a watched directory changes."""
        p = Path(path)
        try:
            # Add any new subdirectories (and their children) that appeared
            for child in p.iterdir():
                if child.is_dir():
                    self._watch_dir(child)

            # Emit newly-discovered PNGs in this directory
            for png in sorted(p.glob("*.png"), key=lambda f: f.stat().st_mtime):
                key = str(png)
                if key not in self._known:
                    self._known.add(key)
                    self.new_screenshot.emit(key)
        except OSError:
            pass  # directory may have been deleted mid-run
