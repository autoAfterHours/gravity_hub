"""
log_bridge.py — Orbit360 v4.1

QObject bridge between the QML LogConsole and Python.

Exposes:
  copyText(str)       — push a log line to the system clipboard
  setSearchText(str)  — update the search term (highlights matching rows)
  matchCount  (int)   — live count of matching rows (notifies QML on change)
  searchOpened ()     — signal emitted by openSearch(); QML opens the bar
"""

from PySide6.QtCore import Property, QObject, Signal, Slot
from PySide6.QtWidgets import QApplication


class LogBridge(QObject):
    # Emitted when Ctrl+F is pressed; QML listens and slides the bar open
    searchOpened = Signal()
    # Emitted after each setSearchText so QML's matchCount binding refreshes
    matchCountChanged = Signal()

    def __init__(self, model, parent=None) -> None:
        super().__init__(parent)
        self._model = model

    # ── Clipboard ─────────────────────────────────────────────────────────

    @Slot(str)
    def copyText(self, text: str) -> None:
        QApplication.clipboard().setText(text)

    # ── Search ────────────────────────────────────────────────────────────

    @Slot()
    def openSearch(self) -> None:
        """Tell QML to show the search bar (triggered by Ctrl+F)."""
        self.searchOpened.emit()

    @Slot(str)
    def setSearchText(self, text: str) -> None:
        """Called by the QML search TextField on every keystroke."""
        self._model.set_search_text(text)
        self.matchCountChanged.emit()

    def _get_match_count(self) -> int:
        return self._model.match_count

    matchCount = Property(int, _get_match_count, notify=matchCountChanged)
