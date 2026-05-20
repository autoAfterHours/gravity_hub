"""
app_backend.py — AppBackend: central QObject for QML-facing run models.

Owns:
    ScreenshotModel     : list of PNG paths exposed to ScreenshotStrip.qml
    ScreenshotWatcher   : filesystem watcher that feeds ScreenshotModel
    SwimlaneLane list   : one per concurrently-running script (parallel mode)

Subscribes to the event bus directly so callers need no proxy layer.
Call setup_lanes(names) before a parallel run to pre-create lane objects.
"""
from __future__ import annotations

from PySide6.QtCore import Property, QObject, Qt, Signal

from orbit360.backend.event_bus import bus
from orbit360.models.screenshot_model import ScreenshotModel
from orbit360.models.screenshot_watcher import ScreenshotWatcher
from orbit360.models.swimlane_model import SwimlaneLane

# Catppuccin Mocha palette — matches main_window and LogConsole.qml
_CLR_DIM     = "#6c7086"
_CLR_SUBTEXT = "#a6adc8"
_CLR_BLUE    = "#89b4fa"
_CLR_GREEN   = "#a6e3a1"
_CLR_RED     = "#f38ba8"
_CLR_AMBER   = "#f9e2af"
_CLR_ORANGE  = "#fab387"


def _line_color(raw: str) -> str:
    parts    = raw.split("|", 1)
    level    = parts[0].strip().upper()
    msg_part = parts[1].strip() if len(parts) > 1 else ""
    if msg_part.startswith("─"):
        return _CLR_BLUE
    if "Total Run Duration" in msg_part or msg_part == "Run Started":
        return _CLR_BLUE
    if level in ("ERROR", "CRITICAL") or "SCRIPT FAILED" in raw:
        return _CLR_RED
    if level == "WARNING" or "MANUAL STEP" in raw:
        return _CLR_ORANGE
    if level == "INFO":
        return _CLR_GREEN
    if level == "DEBUG":
        return _CLR_DIM
    return _CLR_SUBTEXT


class AppBackend(QObject):
    """Central QObject that owns the QML-facing data models for the run view."""

    lanesChanged           = Signal()
    screenshotCountChanged = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._screenshot_model = ScreenshotModel(self)
        self._watcher          = ScreenshotWatcher(self)
        self._lanes: list[SwimlaneLane] = []

        self._watcher.new_screenshot.connect(self._on_new_screenshot)

        _ct = Qt.ConnectionType.UniqueConnection
        bus.run_started.connect(self._on_run_started, _ct)
        bus.script_started.connect(self._on_script_started, _ct)
        bus.progress_updated.connect(self._on_progress_updated, _ct)
        bus.script_finished.connect(self._on_script_finished, _ct)
        bus.worker_finished.connect(self._on_worker_finished, _ct)

    # ── Public API ────────────────────────────────────────────────────────── #

    def setup_lanes(self, script_names: list[str]) -> None:
        """Pre-create lanes for all named scripts before a parallel run starts."""
        self._lanes = [SwimlaneLane(name, self) for name in script_names]
        self.lanesChanged.emit()

    def clear_screenshots(self) -> None:
        """Clear the screenshot model (called when the user clears the console)."""
        self._screenshot_model.clear()
        self.screenshotCountChanged.emit()

    # ── Properties ────────────────────────────────────────────────────────── #

    def _get_screenshot_model(self) -> ScreenshotModel:
        return self._screenshot_model

    def _get_lanes(self) -> list:
        return self._lanes

    def _get_screenshot_count(self) -> int:
        return self._screenshot_model.count()

    screenshotModel = Property(QObject, _get_screenshot_model, constant=True)
    lanes           = Property(list,    _get_lanes,            notify=lanesChanged)
    screenshotCount = Property(int,     _get_screenshot_count, notify=screenshotCountChanged)

    # ── Bus / watcher handlers ────────────────────────────────────────────── #

    def _on_run_started(self, run_root: str) -> None:
        self._screenshot_model.clear()
        self.screenshotCountChanged.emit()
        self._watcher.watch(run_root)

    def _on_new_screenshot(self, path: str) -> None:
        self._screenshot_model.append(path)
        self.screenshotCountChanged.emit()
        bus.new_screenshot.emit(path)

    def _on_script_started(self, name: str, index: int, total: int) -> None:
        if not any(ln.name == name for ln in self._lanes):
            lane = SwimlaneLane(name, self)
            self._lanes.append(lane)
            self.lanesChanged.emit()

    def _on_progress_updated(self, script_name: str, message: str) -> None:
        if not script_name:
            return
        lane = next((ln for ln in self._lanes if ln.name == script_name), None)
        if lane is None:
            return
        parts = message.split("|", 1)
        if len(parts) == 2:
            if parts[0].strip().upper() == "DEBUG":
                return
            msg_body = parts[1].strip()
            display  = msg_body if msg_body.startswith("─") else f"  | {msg_body}"
        else:
            display = f"  | {message}"
        lane.appendLine(display, _line_color(message))

    def _on_script_finished(self, result: object) -> None:
        from orbit360.orbit_logger import ScriptResult
        if not isinstance(result, ScriptResult):
            return
        lane = next((ln for ln in self._lanes if ln.name == result.script_name), None)
        if lane is None:
            return
        if result.status == "passed":
            lane.set_dot_color(_CLR_GREEN)
        elif result.status == "manual_complete":
            lane.set_dot_color(_CLR_AMBER)
        else:
            lane.set_dot_color(_CLR_RED)

    def _on_worker_finished(self) -> None:
        self._watcher.clear()
