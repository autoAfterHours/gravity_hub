"""
cascade_bridge.py — Orbit360 v4.1

QObject bridge between the QML DropdownCascade component and Python.

QML calls selectLevel(levelIndex, optionIndex) via onActivated.
QML calls notifyPopupOpened/notifyPopupClosed so Python can resize the
QQuickWidget to keep the downward-opening popup within widget bounds.
Python connects to the levelSelected signal to react to user selections.
"""

from PySide6.QtCore import QObject, Signal, Slot


class CascadeBridge(QObject):
    """
    Thin relay: QML user activation → Python handler.

    QML usage:
        onActivated: (idx) => cascadeBridge.selectLevel(levelRow.rowIdx, idx)
        popup.onOpened: cascadeBridge.notifyPopupOpened(popup.implicitHeight)
        popup.onClosed:  cascadeBridge.notifyPopupClosed()

    Python usage:
        bridge.levelSelected.connect(self._on_cascade_changed)
        bridge.popupOpened.connect(self._on_cascade_popup_opened)
        bridge.popupClosed.connect(self._on_cascade_popup_closed)
    """

    levelSelected = Signal(int, int)   # (level_index, option_index)
    popupOpened   = Signal(int)        # total popup height (px) — expand widget
    popupClosed   = Signal()           # popup dismissed — shrink widget back

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

    @Slot(int, int)
    def selectLevel(self, level_index: int, option_index: int) -> None:
        self.levelSelected.emit(level_index, option_index)

    @Slot(int)
    def notifyPopupOpened(self, height: int) -> None:
        self.popupOpened.emit(height)

    @Slot()
    def notifyPopupClosed(self) -> None:
        self.popupClosed.emit()
