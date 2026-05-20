"""
orbit360/ui/about_panel.py
About screen — version info, runtime environment, and key file paths.
"""
from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel,
    QPushButton, QVBoxLayout, QWidget,
)

from orbit360.utils.paths import BASE_DIR, ENV_FILE, ORBIT_DATA_DIR, SYSTEMS_DIR

_BG      = "#0a0e1a"
_BG_CARD = "#0d1520"
_BORDER  = "#1a2a40"
_ACCENT  = "#89b4fa"
_GREEN   = "#a6e3a1"
_TEXT    = "#cdd6f4"
_DIM     = "#6c7086"
_SUBTEXT = "#a6adc8"


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setStyleSheet(f"""
        QFrame {{
            background: {_BG_CARD};
            border: 1px solid {_BORDER};
            border-radius: 8px;
        }}
    """)
    vl = QVBoxLayout(f)
    vl.setContentsMargins(16, 12, 16, 14)
    vl.setSpacing(8)
    lbl = QLabel(title)
    lbl.setStyleSheet(
        f"color: {_ACCENT}; font-size: 11px; font-weight: bold; "
        f"letter-spacing: 1px; background: transparent; border: none;"
    )
    vl.addWidget(lbl)
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"background: {_BORDER}; max-height: 1px; border: none;")
    vl.addWidget(sep)
    return f, vl


def _info_row(label: str, value: str, clickable_path: str | None = None) -> QHBoxLayout:
    hl = QHBoxLayout()
    hl.setSpacing(10)
    lbl = QLabel(label)
    lbl.setFixedWidth(170)
    lbl.setStyleSheet(f"color: {_DIM}; font-size: 11px; background: transparent; border: none;")
    hl.addWidget(lbl)

    if clickable_path:
        val = QPushButton(value)
        val.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: none;
                color: {_ACCENT}; font-size: 11px;
                text-align: left; padding: 0;
            }}
            QPushButton:hover {{ color: #b9d4fc; text-decoration: underline; }}
        """)
        val.setCursor(Qt.CursorShape.PointingHandCursor)
        val.clicked.connect(
            lambda _, p=clickable_path: QDesktopServices.openUrl(QUrl.fromLocalFile(p))
        )
        hl.addWidget(val, 1)
    else:
        val_lbl = QLabel(value)
        val_lbl.setStyleSheet(
            f"color: {_TEXT}; font-size: 11px; background: transparent; border: none;"
        )
        val_lbl.setWordWrap(True)
        hl.addWidget(val_lbl, 1)

    return hl


class AboutPanel(QWidget):
    """About screen — version, runtime environment, and key paths."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"QWidget {{ background: {_BG}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)
        root.setAlignment(Qt.AlignmentFlag.AlignTop)

        # ── Logo block ────────────────────────────────────────────────────
        logo_lbl = QLabel("ORBIT<span style='color:#ff6600'>360</span>")
        logo_lbl.setTextFormat(Qt.TextFormat.RichText)
        logo_lbl.setStyleSheet(
            "color: #e8eaf6; font-size: 28px; font-weight: bold; "
            "letter-spacing: 3px; background: transparent;"
        )

        tagline = QLabel("Healthcare Automation Orchestration Platform")
        tagline.setStyleSheet(f"color: {_DIM}; font-size: 12px; background: transparent;")

        ver_lbl = QLabel("Version 4.0")
        ver_lbl.setStyleSheet(
            f"color: {_SUBTEXT}; font-size: 11px; "
            f"background: transparent; border: none;"
        )

        logo_col = QVBoxLayout()
        logo_col.setSpacing(4)
        logo_col.addWidget(logo_lbl)
        logo_col.addWidget(tagline)
        logo_col.addWidget(ver_lbl)
        root.addLayout(logo_col)

        # ── Runtime card ──────────────────────────────────────────────────
        rt_card, rt_body = _card("RUNTIME ENVIRONMENT")

        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        try:
            import PySide6
            qt_ver = PySide6.__version__
        except Exception:
            qt_ver = "not installed"

        rt_body.addLayout(_info_row("Python",    py_ver))
        rt_body.addLayout(_info_row("PySide6",   qt_ver))
        rt_body.addLayout(_info_row("Platform",  sys.platform))
        root.addWidget(rt_card)

        # ── Paths card ────────────────────────────────────────────────────
        path_card, path_body = _card("KEY PATHS")

        env_exists = ENV_FILE.is_file()
        env_label  = str(ENV_FILE) + ("" if env_exists else "  (not found)")

        path_body.addLayout(_info_row("Project root",    str(BASE_DIR),        str(BASE_DIR)))
        path_body.addLayout(_info_row("Data directory",  str(ORBIT_DATA_DIR),  str(ORBIT_DATA_DIR)))
        path_body.addLayout(_info_row("Systems library", str(SYSTEMS_DIR),     str(SYSTEMS_DIR)))
        path_body.addLayout(_info_row(".env file",       env_label,            str(ENV_FILE) if env_exists else None))

        root.addWidget(path_card)

        # ── Debug info / copy ─────────────────────────────────────────────
        act_row = QHBoxLayout()
        act_row.addStretch()

        self._copy_btn = QPushButton("Copy Debug Info")
        self._copy_btn.setStyleSheet(f"""
            QPushButton {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_SUBTEXT}; font-size: 11px; padding: 5px 16px;
            }}
            QPushButton:hover {{ color: {_ACCENT}; border-color: {_ACCENT}; }}
        """)
        self._copy_btn.clicked.connect(self._copy_debug)
        act_row.addWidget(self._copy_btn)
        root.addLayout(act_row)

        root.addStretch()

    def _copy_debug(self) -> None:
        try:
            import PySide6
            qt_ver = PySide6.__version__
        except Exception:
            qt_ver = "n/a"

        lines = [
            "Orbit360 Debug Info",
            "===================",
            f"Version:      4.0",
            f"Python:       {sys.version}",
            f"PySide6:      {qt_ver}",
            f"Platform:     {sys.platform}",
            "",
            f"BASE_DIR:     {BASE_DIR}",
            f"ORBIT_DATA:   {ORBIT_DATA_DIR}",
            f"SYSTEMS_DIR:  {SYSTEMS_DIR}",
            f".env:         {ENV_FILE}",
        ]
        cb = QApplication.clipboard()
        if cb:
            cb.setText("\n".join(lines))
        self._copy_btn.setText("✓ Copied")
        QTimer.singleShot(2000, lambda: self._copy_btn.setText("Copy Debug Info"))
