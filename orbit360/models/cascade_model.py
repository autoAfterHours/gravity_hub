"""
cascade_model.py — Orbit360 v4.1

QAbstractListModel backing the QML DropdownCascade component.
Each row is one hierarchy level (e.g. "Environment", "Pillar", …).

Roles exposed to QML:
    label        — level label text (str)
    options      — ["", opt1, opt2, …]  display strings (list[str])
    selectedIndex — currently selected index in that list (int)
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Property, QAbstractListModel, QModelIndex, Qt, Signal


class _Level:
    __slots__ = ("label", "options", "selected")

    def __init__(self, label: str) -> None:
        self.label: str = label
        self.options: list[tuple[str, str]] = []   # (raw_name, display_name)
        self.selected: int = 0                      # index into ["", opt1, …]


class CascadeModel(QAbstractListModel):
    LabelRole    = Qt.ItemDataRole.UserRole + 1
    OptionsRole  = Qt.ItemDataRole.UserRole + 2
    SelectedRole = Qt.ItemDataRole.UserRole + 3

    # Emitted whenever the count of levels that have ≥1 option changes.
    # QML bindings on visibleCount update automatically via this signal.
    visibleCountChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._levels: list[_Level] = []

    def _get_visible_count(self) -> int:
        """Number of levels that currently have at least one option."""
        return sum(1 for lvl in self._levels if lvl.options)

    visibleCount = Property(int, _get_visible_count, notify=visibleCountChanged)

    # ------------------------------------------------------------------ #
    # QAbstractListModel implementation                                    #
    # ------------------------------------------------------------------ #

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._levels)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._levels)):
            return None
        lvl = self._levels[index.row()]
        if role == self.LabelRole:
            return lvl.label
        if role == self.OptionsRole:
            return [""] + [d for _, d in lvl.options]
        if role == self.SelectedRole:
            return lvl.selected
        return None

    def roleNames(self) -> dict[int, bytes]:
        return {
            self.LabelRole:    b"label",
            self.OptionsRole:  b"options",
            self.SelectedRole: b"selectedIndex",
        }

    # ------------------------------------------------------------------ #
    # Write API (called from Python)                                       #
    # ------------------------------------------------------------------ #

    def set_levels(self, labels: list[str]) -> None:
        """Replace the entire cascade with fresh, empty levels."""
        self.beginResetModel()
        self._levels = [_Level(lbl) for lbl in labels]
        self.endResetModel()

    def set_options(self, level: int, options: list[tuple[str, str]]) -> None:
        """Fill one level's option list and reset its selection to 0."""
        if not (0 <= level < len(self._levels)):
            return
        old_vis = self._get_visible_count()
        self._levels[level].options = options
        self._levels[level].selected = 0
        idx = self.index(level, 0)
        self.dataChanged.emit(idx, idx, [self.OptionsRole, self.SelectedRole])
        if self._get_visible_count() != old_vis:
            self.visibleCountChanged.emit()

    def set_selected(self, level: int, selected: int) -> None:
        """Update the selected index for one level."""
        if not (0 <= level < len(self._levels)):
            return
        self._levels[level].selected = selected
        idx = self.index(level, 0)
        self.dataChanged.emit(idx, idx, [self.SelectedRole])

    def clear_from(self, level: int) -> None:
        """Empty options and reset selection for all levels >= level."""
        old_vis = self._get_visible_count()
        changed = False
        for i in range(level, len(self._levels)):
            if self._levels[i].options or self._levels[i].selected:
                self._levels[i].options = []
                self._levels[i].selected = 0
                changed = True
        if changed and level < len(self._levels):
            top = self.index(level, 0)
            bot = self.index(len(self._levels) - 1, 0)
            self.dataChanged.emit(top, bot, [self.OptionsRole, self.SelectedRole])
            if self._get_visible_count() != old_vis:
                self.visibleCountChanged.emit()

    # ------------------------------------------------------------------ #
    # Read API (called from Python)                                        #
    # ------------------------------------------------------------------ #

    def level_count(self) -> int:
        return len(self._levels)

    def get_raw_at(self, level: int) -> str:
        """
        Return the raw (filesystem) name for the currently-selected option
        at *level*, or "" if nothing is selected / level is out of range.
        """
        if not (0 <= level < len(self._levels)):
            return ""
        lvl = self._levels[level]
        opt_idx = lvl.selected - 1       # 0 placeholder maps to -1
        if 0 <= opt_idx < len(lvl.options):
            return lvl.options[opt_idx][0]
        return ""
