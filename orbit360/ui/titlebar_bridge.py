"""
titlebar_bridge.py — Orbit360 v4.1

QObject bridge that exposes run-state to the QML TitleBar component.

QML binds to the `runActive` property via Connections; Python calls
`set_run_active()` to match the old TitleBar widget API exactly so
main_window.py needs only a minimal change.

PySide6 note: Property getter/setter must be declared at class level using
Property(type, fget, fset, notify=signal) rather than the @prop.setter
chaining used by PyQt6, which is not guaranteed across PySide6 versions.
"""

from PySide6.QtCore import Property, QObject, Signal


class TitleBarBridge(QObject):
    runActiveChanged = Signal(bool)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._run_active = False

    def _get_run_active(self) -> bool:
        return self._run_active

    def _set_run_active(self, value: bool) -> None:
        if self._run_active != value:
            self._run_active = value
            self.runActiveChanged.emit(value)

    runActive = Property(bool, _get_run_active, _set_run_active, notify=runActiveChanged)

    def set_run_active(self, active: bool) -> None:
        """Matches the TitleBar widget API called from main_window.py."""
        self._set_run_active(active)
