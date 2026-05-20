"""
models.py — Orbit360 v4.0
QAbstractListModel subclasses for Qt Model/View and QML binding.
No UI logic. No subprocess calls. No Qt widget imports.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class TestScriptModel(QAbstractListModel):
    """
    List model that holds the script entries loaded from a tests.yaml file.

    Roles:
        DisplayRole / NameRole  — script display name (str)
        PathRole                — relative path to script file (str)
        StatusRole              — run state: "" | "running" | "passed" | "failed" | "error"

    QML usage (hybrid mode):
        engine.rootContext().setContextProperty("scriptModel", window.script_model)

        ListView {
            model: scriptModel
            delegate: Text { text: model.name; color: model.scriptStatus === "passed" ? "green" : "white" }
        }
    """

    NameRole     = Qt.ItemDataRole.UserRole + 1
    PathRole     = Qt.ItemDataRole.UserRole + 2
    StatusRole   = Qt.ItemDataRole.UserRole + 3
    DurationRole = Qt.ItemDataRole.UserRole + 4
    TagsRole     = Qt.ItemDataRole.UserRole + 5
    HistoryRole  = Qt.ItemDataRole.UserRole + 6  # last-7 statuses for sparkline

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scripts:   list[dict]       = []
        self._statuses:  dict[str, str]   = {}   # script name → run status
        self._durations: dict[str, str]   = {}   # script name → formatted duration
        self._histories: dict[str, list]  = {}   # script name → last-N status strings

    # ------------------------------------------------------------------ #
    # QAbstractListModel implementation                                    #
    # ------------------------------------------------------------------ #

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._scripts)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._scripts)):
            return None
        entry = self._scripts[index.row()]
        if role in (Qt.ItemDataRole.DisplayRole, self.NameRole):
            return entry.get("name", "")
        if role == self.PathRole:
            return entry.get("path", "")
        if role == self.StatusRole:
            return self._statuses.get(entry.get("name", ""), "")
        if role == self.DurationRole:
            return self._durations.get(entry.get("name", ""), "")
        if role == self.TagsRole:
            raw = entry.get("tags") or []
            return [str(t) for t in raw] if isinstance(raw, list) else ([str(raw)] if raw else [])
        if role == self.HistoryRole:
            return self._histories.get(entry.get("name", ""), [])
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            Qt.ItemDataRole.DisplayRole: b"display",
            self.NameRole:               b"name",
            self.PathRole:               b"path",
            self.StatusRole:             b"scriptStatus",
            self.DurationRole:           b"scriptDuration",
            self.TagsRole:               b"scriptTags",
            self.HistoryRole:            b"scriptHistory",
        }

    # ------------------------------------------------------------------ #
    # Mutation API                                                         #
    # ------------------------------------------------------------------ #

    def set_scripts(self, scripts: list[dict]) -> None:
        """Replace the entire script list and clear all statuses, durations, and histories."""
        self.beginResetModel()
        self._scripts   = list(scripts)
        self._statuses  = {}
        self._durations = {}
        self._histories = {}
        self.endResetModel()

    def clear(self) -> None:
        """Remove all scripts from the model."""
        self.set_scripts([])

    def script_at(self, row: int) -> dict:
        """Return the raw entry dict for the script at `row`, or {} if out of range."""
        if 0 <= row < len(self._scripts):
            return self._scripts[row]
        return {}

    def set_script_status(self, name: str, status: str) -> None:
        """
        Update the run status for a single script and notify QML delegates.
        status should be one of: "running" | "passed" | "failed" | "error"
        """
        for row, entry in enumerate(self._scripts):
            if entry.get("name") == name:
                self._statuses[name] = status
                idx = self.index(row, 0)
                self.dataChanged.emit(idx, idx, [self.StatusRole])
                return

    def set_script_duration(self, name: str, seconds: float) -> None:
        """
        Store a human-readable duration string for a script after it finishes.
        Displayed as "42s" for sub-minute runs or "1:23" for longer ones.
        """
        s = int(round(seconds))
        label = f"{s}s" if s < 60 else f"{s // 60}:{s % 60:02d}"
        for row, entry in enumerate(self._scripts):
            if entry.get("name") == name:
                self._durations[name] = label
                idx = self.index(row, 0)
                self.dataChanged.emit(idx, idx, [self.DurationRole])
                return

    def set_script_history(self, name: str, statuses: list) -> None:
        """
        Store the last-N run statuses for a script so QML can draw a sparkline.
        `statuses` is a list of strings like ["passed", "failed", "passed", ...],
        most-recent last.  Called once after scripts are loaded from the DB.
        """
        for row, entry in enumerate(self._scripts):
            if entry.get("name") == name:
                self._histories[name] = list(statuses)
                idx = self.index(row, 0)
                self.dataChanged.emit(idx, idx, [self.HistoryRole])
                return

    def reset_statuses(self) -> None:
        """
        Clear all script statuses and durations (call at the start of each run
        so previous results don't carry over when re-running the same test set).
        Histories are NOT cleared — they persist across runs to keep sparklines visible.
        """
        if not self._statuses and not self._durations:
            return
        self._statuses.clear()
        self._durations.clear()
        if self._scripts:
            top    = self.index(0, 0)
            bottom = self.index(len(self._scripts) - 1, 0)
            self.dataChanged.emit(top, bottom, [self.StatusRole, self.DurationRole])
