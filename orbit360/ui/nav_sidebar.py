"""
orbit360/ui/nav_sidebar.py
Collapsible left-side navigation sidebar for the Orbit360 app shell.
"""
from __future__ import annotations

from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QEasingCurve, QSettings
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QPushButton,
    QSizePolicy, QVBoxLayout, QWidget,
)

_EXPANDED_W  = 200
_COLLAPSED_W = 52

_NAV_ITEMS: list[tuple[int, str, str]] = [
    (0, "⌂",  "Command Deck"),
    (1, "⚡", "Launcher"),
    (2, "▲",  "Pulse"),
    (3, "◈",  "Genesis"),
    (4, "▣",  "Vault"),
    (5, "⚙",  "Settings"),
    (6, "ℹ",  "About Orbit360"),
    (7, "⏱",  "Scheduler"),
]

_SIDEBAR_BG = "#0a0e1a"
_ACCENT     = "#89b4fa"

_SHEET_BASE = f"""
QWidget#navSidebar {{
    background-color: {_SIDEBAR_BG};
    border-right: 1px solid #1a2233;
}}
QPushButton.navBtn {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    color: #5a6a88;
    text-align: left;
    padding: 8px 0 8px 14px;
    font-size: 13px;
    font-family: "Segoe UI";
}}
QPushButton.navBtn:hover {{
    background: #111c30;
    color: #cdd6f4;
    border-left: 3px solid #2a4a6a;
}}
QPushButton.navBtn[active="true"] {{
    background: #132240;
    color: {_ACCENT};
    border-left: 3px solid {_ACCENT};
}}
"""


class NavSidebar(QWidget):
    """Collapsible navigation sidebar.  Emits navigate(int) on item click."""

    navigate = Signal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setObjectName("navSidebar")
        self._expanded = True
        self._current  = 0
        self._buttons: list[QPushButton] = []

        self.setFixedWidth(_EXPANDED_W)
        self.setStyleSheet(_SHEET_BASE)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Logo strip ────────────────────────────────────────────────────
        logo_strip = QWidget()
        logo_strip.setFixedHeight(60)
        logo_strip.setStyleSheet(f"background: {_SIDEBAR_BG};")
        ll = QHBoxLayout(logo_strip)
        ll.setContentsMargins(16, 0, 10, 0)

        self._logo_lbl = QLabel("ORBIT<span style='color:#ff6600'>360</span>")
        self._logo_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._logo_lbl.setStyleSheet(
            "color: #e8eaf6; font-size: 17px; font-weight: bold; letter-spacing: 2px;"
        )
        ll.addWidget(self._logo_lbl)
        ll.addStretch()
        root.addWidget(logo_strip)

        _hline(root)

        # ── Nav buttons ───────────────────────────────────────────────────
        nav_area = QWidget()
        nav_area.setStyleSheet(f"background: {_SIDEBAR_BG};")
        nav_layout = QVBoxLayout(nav_area)
        nav_layout.setContentsMargins(0, 10, 0, 10)
        nav_layout.setSpacing(2)

        for idx, icon, label in _NAV_ITEMS:
            btn = QPushButton(f"  {icon}   {label}")
            btn.setObjectName(f"navBtn_{idx}")
            btn.setProperty("class", "navBtn")
            btn.setFixedHeight(40)
            btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn.setProperty("active", idx == 0)
            btn.clicked.connect(lambda _=False, i=idx: self._click(i))
            nav_layout.addWidget(btn)
            self._buttons.append(btn)

        root.addWidget(nav_area)
        root.addStretch()

        _hline(root)

        # ── Bottom strip ──────────────────────────────────────────────────
        bottom = QWidget()
        bottom.setStyleSheet(f"background: {_SIDEBAR_BG};")
        bl = QVBoxLayout(bottom)
        bl.setContentsMargins(16, 10, 16, 10)
        bl.setSpacing(4)

        status_row = QHBoxLayout()
        dot = QLabel("●")
        dot.setStyleSheet("color: #a6e3a1; font-size: 9px;")
        self._status_lbl = QLabel("Operational")
        self._status_lbl.setStyleSheet("color: #a6e3a1; font-size: 11px;")
        status_row.addWidget(dot)
        status_row.addSpacing(4)
        status_row.addWidget(self._status_lbl)
        status_row.addStretch()
        bl.addLayout(status_row)

        self._ver_lbl = QLabel("Version 2.0.0")
        self._ver_lbl.setStyleSheet("color: #2a3a55; font-size: 10px;")
        bl.addWidget(self._ver_lbl)

        # Collapse button
        crow = QHBoxLayout()
        crow.addStretch()
        self._collapse_btn = QPushButton("‹")
        self._collapse_btn.setFixedSize(26, 26)
        self._collapse_btn.setStyleSheet("""
            QPushButton {
                background: #111c30;
                border: 1px solid #1e3a5f;
                border-radius: 13px;
                color: #5a6a88;
                font-size: 14px;
            }
            QPushButton:hover { color: #89b4fa; background: #162440; }
        """)
        self._collapse_btn.setToolTip("Collapse sidebar")
        self._collapse_btn.clicked.connect(self._toggle)
        crow.addWidget(self._collapse_btn)
        bl.addLayout(crow)

        root.addWidget(bottom)

        # Restore collapsed state
        settings = QSettings("Orbit360", "NavSidebar")
        if settings.value("collapsed", False, type=bool):
            self._expanded = False
            self.setFixedWidth(_COLLAPSED_W)
            self._apply_collapsed_text()

    # ── Public ─────────────────────────────────────────────────────────────

    def set_active(self, index: int) -> None:
        self._current = index
        for i, btn in enumerate(self._buttons):
            btn.setProperty("active", i == index)
            btn.setStyle(btn.style())   # force stylesheet re-evaluation

    def set_version(self, version: str) -> None:
        self._ver_lbl.setText(f"Version {version}")

    # ── Private ────────────────────────────────────────────────────────────

    def _click(self, index: int) -> None:
        self.set_active(index)
        self.navigate.emit(index)

    def _toggle(self) -> None:
        self._expanded = not self._expanded
        target = _EXPANDED_W if self._expanded else _COLLAPSED_W

        for prop in (b"minimumWidth", b"maximumWidth"):
            anim = QPropertyAnimation(self, prop, self)
            anim.setDuration(160)
            anim.setStartValue(self.width())
            anim.setEndValue(target)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.start()

        self._logo_lbl.setVisible(self._expanded)
        self._status_lbl.setVisible(self._expanded)
        self._ver_lbl.setVisible(self._expanded)
        self._collapse_btn.setText("›" if not self._expanded else "‹")
        self._collapse_btn.setToolTip(
            "Expand sidebar" if not self._expanded else "Collapse sidebar"
        )
        self._apply_collapsed_text()

        QSettings("Orbit360", "NavSidebar").setValue("collapsed", not self._expanded)

    def _apply_collapsed_text(self) -> None:
        for i, btn in enumerate(self._buttons):
            _, icon, label = _NAV_ITEMS[i]
            btn.setText(f"  {icon}   {label}" if self._expanded else f"  {icon}")


# ── Helpers ─────────────────────────────────────────────────────────────────

def _hline(layout: QVBoxLayout) -> None:
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet("background: #141e30; max-height: 1px; border: none;")
    layout.addWidget(sep)
