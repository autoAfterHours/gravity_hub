"""
orbit360/ui/tray_manager.py
System-tray icon and OS-level toast notifications for Orbit360.

Attaches to the event_bus so any screen can receive run events without
holding a direct reference to the main window.
"""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from orbit360.backend.event_bus import bus

_ACCENT  = "#89b4fa"
_ORANGE  = "#fab387"
_RED     = "#f38ba8"
_DARK    = "#0d1520"
_BORDER  = "#1a2a40"
_TEXT    = "#cdd6f4"


def _make_icon(color: str = _ACCENT) -> QIcon:
    pix = QPixmap(32, 32)
    pix.fill(Qt.GlobalColor.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.PenStyle.NoPen)
    p.drawEllipse(2, 2, 28, 28)
    p.setPen(QColor("white"))
    f = QFont("Segoe UI", 12, QFont.Weight.Bold)
    p.setFont(f)
    p.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "O")
    p.end()
    return QIcon(pix)


class TrayManager(QObject):
    """
    Wraps QSystemTrayIcon for Orbit360.

    Call ``attach(window)`` once after the main window is shown.
    Closing the window minimizes to tray; double-clicking the icon
    or choosing "Show" from the context menu restores it.
    """

    # QObject base is required so bus.connect(..., UniqueConnection) sees the
    # handlers as bound methods on a QObject subclass — otherwise Qt logs
    # "unique connections require a pointer to member function of a QObject
    # subclass" at startup and the unique-connection guarantee is lost.

    def __init__(self, window) -> None:
        super().__init__(window)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            self._tray = None
            return

        # Icons are built here (not at module level) so QApplication already exists.
        self._icon_idle = _make_icon(_ACCENT)
        self._icon_run  = _make_icon("#a6e3a1")
        self._icon_fail = _make_icon(_RED)

        self._window = window
        self._tray   = QSystemTrayIcon(self._icon_idle)
        self._tray.setToolTip("Orbit360")

        menu = QMenu()
        menu.setStyleSheet(f"""
            QMenu {{
                background: {_DARK};
                border: 1px solid {_BORDER};
                color: {_TEXT};
                font-size: 12px;
                padding: 4px 0;
            }}
            QMenu::item {{ padding: 6px 18px 6px 14px; }}
            QMenu::item:selected {{ background: #132240; color: {_ACCENT}; }}
            QMenu::separator {{ height: 1px; background: {_BORDER}; margin: 4px 0; }}
        """)
        show_act = menu.addAction("Show Orbit360")
        show_act.triggered.connect(self._show_window)
        menu.addSeparator()
        quit_act = menu.addAction("Quit")
        quit_act.triggered.connect(QApplication.quit)
        self._tray.setContextMenu(menu)
        self._tray.activated.connect(self._on_activated)

        bus.run_started.connect(self._on_run_started,
                                Qt.ConnectionType.UniqueConnection)
        bus.run_completed.connect(self._on_run_completed,
                                  Qt.ConnectionType.UniqueConnection)
        bus.run_aborted.connect(self._on_run_aborted,
                                Qt.ConnectionType.UniqueConnection)
        bus.run_failed.connect(self._on_run_failed,
                               Qt.ConnectionType.UniqueConnection)

        self._tray.show()

    # ── Public ──────────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._tray is not None

    def notify(self, title: str, message: str,
               icon: QSystemTrayIcon.MessageIcon = QSystemTrayIcon.MessageIcon.Information,
               ms: int = 4000) -> None:
        if self._tray:
            self._tray.showMessage(title, message, icon, ms)

    # ── Private ─────────────────────────────────────────────────────────────

    def _show_window(self) -> None:
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()

    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._show_window()

    def _on_run_started(self, _run_root: str) -> None:
        if self._tray:
            self._tray.setIcon(self._icon_run)
        self.notify("Orbit360 — Run Started",
                    "Automation run is in progress…",
                    ms=3000)

    def _on_run_completed(self, _path: str,
                          passed: int, failed: int, errored: int) -> None:
        total = passed + failed + errored
        if failed == 0 and errored == 0:
            if self._tray:
                self._tray.setIcon(self._icon_idle)
            self.notify("Orbit360 — Run Passed",
                        f"All {total} scripts passed.",
                        QSystemTrayIcon.MessageIcon.Information,
                        ms=5000)
        else:
            if self._tray:
                self._tray.setIcon(self._icon_fail)
            self.notify("Orbit360 — Run Finished",
                        f"{passed}/{total} passed  ·  {failed + errored} failed",
                        QSystemTrayIcon.MessageIcon.Warning,
                        ms=6000)

    def _on_run_aborted(self, _path: str,
                        passed: int, _f: int, _e: int) -> None:
        if self._tray:
            self._tray.setIcon(self._icon_idle)
        self.notify("Orbit360 — Run Aborted",
                    f"{passed} script(s) completed before abort.",
                    QSystemTrayIcon.MessageIcon.Warning,
                    ms=5000)

    def _on_run_failed(self, error: str) -> None:
        if self._tray:
            self._tray.setIcon(self._icon_fail)
        self.notify("Orbit360 — Run Error",
                    error[:120],
                    QSystemTrayIcon.MessageIcon.Critical,
                    ms=6000)
