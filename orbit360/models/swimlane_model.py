"""
swimlane_model.py — Per-lane model for parallel execution view.

Each SwimlaneLane represents one concurrently-running script.
AppBackend holds a list of these and exposes it to QML as a QVariantList.

QML delegates connect to lineAdded to append colored lines without
rebuilding the entire text content on every update.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Signal, Slot, Property


class SwimlaneLane(QObject):
    dotColorChanged = Signal()
    lineAdded       = Signal(str, str)   # text, hex color

    def __init__(self, name: str, parent=None) -> None:
        super().__init__(parent)
        self._name      = name
        self._dot_color = "#45475a"      # Catppuccin Surface — gray = pending

    # ── Properties ──────────────────────────────────────────────────────── #

    def _get_name(self) -> str:
        return self._name

    def _get_dot_color(self) -> str:
        return self._dot_color

    name     = Property(str, _get_name, constant=True)
    dotColor = Property(str, _get_dot_color, notify=dotColorChanged)

    # ── Mutators (called from AppBackend on main thread) ─────────────────── #

    def set_dot_color(self, color: str) -> None:
        if self._dot_color != color:
            self._dot_color = color
            self.dotColorChanged.emit()

    @Slot(str, str)
    def appendLine(self, text: str, color: str) -> None:
        """Emit lineAdded so the QML delegate can append without a full re-render."""
        self.lineAdded.emit(text, color)
