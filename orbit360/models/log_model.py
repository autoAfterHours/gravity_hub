"""
log_model.py — Orbit360 v4.0
QAbstractListModel for structured log entries consumed by qml/LogConsole.qml.
No UI logic. No Qt widget imports.
"""

from __future__ import annotations

import datetime
from typing import Any

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class LogEntryModel(QAbstractListModel):
    """
    Append-only list model that holds colored log entries.

    Roles:
        TextRole      — the log line text (str)
        ColorRole     — Catppuccin Mocha hex color string for this line (str)
        TimestampRole — HH:MM:SS string captured at append time (str)
        HighlightRole — True when this row matches the active search term (bool)

    QML usage:
        Text { text: model.entryText;      color: model.entryColor }
        Text { text: model.entryTimestamp; color: "#45475a" }
    """

    TextRole      = Qt.ItemDataRole.UserRole + 1
    ColorRole     = Qt.ItemDataRole.UserRole + 2
    TimestampRole = Qt.ItemDataRole.UserRole + 3
    HighlightRole = Qt.ItemDataRole.UserRole + 4

    _MAX_ENTRIES = 8_000  # hard cap — prune oldest _DROP_COUNT rows when hit
    _DROP_COUNT  = 2_000  # rows removed per prune to amortise the cost

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._entries:     list[dict] = []   # [{"text": str, "color": str, "timestamp": str}]
        self._search_text: str        = ""

    # ------------------------------------------------------------------ #
    # QAbstractListModel implementation                                    #
    # ------------------------------------------------------------------ #

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._entries)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._entries)):
            return None
        entry = self._entries[index.row()]
        if role == self.TextRole:
            return entry["text"]
        if role == self.ColorRole:
            return entry["color"]
        if role == self.TimestampRole:
            return entry["timestamp"]
        if role == self.HighlightRole:
            if not self._search_text:
                return False
            return self._search_text.lower() in entry["text"].lower()
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.TextRole:      b"entryText",
            self.ColorRole:     b"entryColor",
            self.TimestampRole: b"entryTimestamp",
            self.HighlightRole: b"entryHighlighted",
        }

    # ------------------------------------------------------------------ #
    # Mutation API                                                         #
    # ------------------------------------------------------------------ #

    def append(self, text: str, color: str) -> None:
        """
        Append a single log line.
        When _MAX_ENTRIES is reached, the oldest _DROP_COUNT rows are pruned
        so memory stays bounded across arbitrarily long runs.
        """
        if len(self._entries) >= self._MAX_ENTRIES:
            self.beginRemoveRows(QModelIndex(), 0, self._DROP_COUNT - 1)
            del self._entries[: self._DROP_COUNT]
            self.endRemoveRows()
        _dt   = datetime.datetime.now()
        _hr   = str(int(_dt.strftime("%I")))
        _ampm = "AM" if _dt.hour < 12 else "PM"
        ts    = f"{_hr}:{_dt.strftime('%M:%S')} {_ampm}"
        row   = len(self._entries)
        self.beginInsertRows(QModelIndex(), row, row)
        self._entries.append({"text": text, "color": color, "timestamp": ts})
        self.endInsertRows()

    def update_last(self, text: str, color: str) -> None:
        """Replace the text+color of the most-recently appended entry in-place."""
        if not self._entries:
            return
        idx = len(self._entries) - 1
        self._entries[idx]["text"]  = text
        self._entries[idx]["color"] = color
        qi = self.index(idx)
        self.dataChanged.emit(qi, qi, [self.TextRole, self.ColorRole])

    def clear(self) -> None:
        """Remove all entries and emit a model reset."""
        if not self._entries:
            return
        self.beginResetModel()
        self._entries.clear()
        self._search_text = ""
        self.endResetModel()

    # ------------------------------------------------------------------ #
    # Search API                                                           #
    # ------------------------------------------------------------------ #

    def set_search_text(self, text: str) -> None:
        """
        Set the active search term.  Emits dataChanged for all rows so the
        QML ListView refreshes entryHighlighted on every delegate.
        """
        self._search_text = text
        if self._entries:
            top    = self.index(0, 0)
            bottom = self.index(len(self._entries) - 1, 0)
            self.dataChanged.emit(top, bottom, [self.HighlightRole])

    @property
    def match_count(self) -> int:
        """Number of entries whose text contains the current search term."""
        if not self._search_text or not self._entries:
            return 0
        needle = self._search_text.lower()
        return sum(1 for e in self._entries if needle in e["text"].lower())
