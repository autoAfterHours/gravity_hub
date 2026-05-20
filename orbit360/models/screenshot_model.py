"""
screenshot_model.py — QAbstractListModel for the screenshot thumbnail strip.

Exposes a list of PNG file paths to QML via the imagePath role.
AppBackend owns one instance and populates it as ScreenshotWatcher fires.
"""
from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt


class ScreenshotModel(QAbstractListModel):
    PathRole = Qt.ItemDataRole.UserRole + 1

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._paths: list[str] = []

    def roleNames(self) -> dict:
        return {self.PathRole: b"imagePath"}

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(self._paths)

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() >= len(self._paths):
            return None
        if role == self.PathRole:
            return self._paths[index.row()]
        return None

    def append(self, path: str) -> None:
        n = len(self._paths)
        self.beginInsertRows(QModelIndex(), n, n)
        self._paths.append(path)
        self.endInsertRows()

    def clear(self) -> None:
        if not self._paths:
            return
        self.beginRemoveRows(QModelIndex(), 0, len(self._paths) - 1)
        self._paths.clear()
        self.endRemoveRows()

    def count(self) -> int:
        return len(self._paths)
