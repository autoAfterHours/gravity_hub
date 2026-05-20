"""
qml_bridge.py — Orbit360 v4.1
Thin QObject bridge for QML ↔ Python communication.
QML calls into Python slots; Python connects to signals or reads properties.
No UI logic. No Qt widget imports.
"""

from __future__ import annotations

from PySide6.QtCore import Property, QObject, Signal, Slot


class TagsBridge(QObject):
    """
    Exposes the unique sorted set of tag strings present in the loaded scripts
    to QML so the chip-filter row can render without knowing model internals.

    Python side: call set_tags([...]) after set_scripts().
    QML side:    bind to tagsBridge.tags (a QVariantList / JS array).

    The tagsChanged signal is emitted on every change so QML bindings
    re-evaluate automatically.
    """

    tagsChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._tags: list[str] = []

    def _get_tags(self) -> list:
        return self._tags

    tags = Property(list, _get_tags, notify=tagsChanged)

    def set_tags(self, raw_tags: list[str]) -> None:
        """Deduplicate, sort, and publish the tag set."""
        sorted_tags = sorted(set(raw_tags))
        if sorted_tags != self._tags:
            self._tags = sorted_tags
            self.tagsChanged.emit()


class SelectionBridge(QObject):
    """
    Relays list-selection events from the QML ListView to the Python widget layer.

    QML usage:
        selectionBridge.notifyRow(index)   // call on item click
        selectionBridge.notifyRow(-1)      // call on deselect / model reset

    Python usage:
        bridge.rowChanged.connect(self._on_test_selection_changed)
        current = bridge.currentRow
        bridge.reset()   # clear selection programmatically
    """

    rowChanged = Signal(int)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._current_row: int = -1

    @Slot(int)
    def notifyRow(self, row: int) -> None:
        """Called by QML when the user clicks an item or the model resets."""
        self._current_row = row
        self.rowChanged.emit(row)

    def _get_current_row(self) -> int:
        return self._current_row

    currentRow = Property(int, _get_current_row)

    def reset(self) -> None:
        """
        Clear selection from Python (e.g. when repopulating the model).
        Only emits rowChanged if the selection actually changes.
        """
        if self._current_row != -1:
            self._current_row = -1
            self.rowChanged.emit(-1)


class DeckNavBridge(QObject):
    """
    Lets CommandDeck.qml trigger Python-side navigation without relying on
    rootObject().signal.connect(), which can miss the statusChanged(Ready)
    window.  Uses the same context-property @Slot pattern as every other bridge.

    QML usage:
        deckNavBridge.navigate(cardData.screenIndex)

    Python usage:
        bridge.navigated.connect(main_window._on_nav_changed)
    """

    navigated = Signal(int)

    @Slot(int)
    def navigate(self, screen_index: int) -> None:
        self.navigated.emit(screen_index)
