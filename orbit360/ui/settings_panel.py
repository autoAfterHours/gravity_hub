"""
orbit360/ui/settings_panel.py
Settings screen — read/write .env vars that drive orbit360 behaviour.

Changes take effect on the next run start (env vars are read fresh each time);
no app restart is required.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import NamedTuple

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QScrollArea, QSpinBox, QDoubleSpinBox,
    QVBoxLayout, QWidget,
)

from orbit360.utils.paths import ENV_FILE as _ENV_PATH

_BG      = "#0a0e1a"
_BG_CARD = "#0d1520"
_BORDER  = "#1a2a40"
_ACCENT  = "#89b4fa"
_GREEN   = "#a6e3a1"
_AMBER   = "#f9e2af"
_TEXT    = "#cdd6f4"
_DIM     = "#6c7086"
_SUBTEXT = "#a6adc8"

_FIELD_SHEET = f"""
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
        background: #111c30;
        border: 1px solid {_BORDER};
        border-radius: 4px;
        color: {_TEXT};
        font-size: 12px;
        padding: 3px 8px;
        min-height: 24px;
    }}
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
        border-color: {_ACCENT};
    }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{
        background: #111c30;
        border: 1px solid {_BORDER};
        color: {_TEXT};
        selection-background-color: #132240;
    }}
    QSpinBox::up-button, QSpinBox::down-button,
    QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
        background: #1a2a40; border: none; width: 16px;
    }}
    QCheckBox {{ color: {_TEXT}; font-size: 12px; spacing: 6px; }}
    QCheckBox::indicator {{
        width: 14px; height: 14px;
        border: 1px solid {_BORDER}; border-radius: 3px;
        background: #111c30;
    }}
    QCheckBox::indicator:checked {{
        background: {_ACCENT}; border-color: {_ACCENT};
    }}
"""

_SAVE_SHEET = f"""
    QPushButton {{
        background: #132240;
        border: 1px solid {_ACCENT};
        border-radius: 4px;
        color: {_ACCENT};
        font-size: 12px;
        font-weight: bold;
        padding: 5px 24px;
    }}
    QPushButton:hover {{ background: #1a3a5f; }}
    QPushButton:pressed {{ background: #0d1a30; }}
"""

_BROWSE_SHEET = f"""
    QPushButton {{
        background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
        color: {_SUBTEXT}; font-size: 11px; padding: 3px 10px; min-height: 24px;
    }}
    QPushButton:hover {{ color: {_ACCENT}; border-color: {_ACCENT}; }}
"""


# ── .env I/O ─────────────────────────────────────────────────────────────────

def _read_env_file() -> dict[str, str]:
    """Return {KEY: value} for every non-comment, non-blank line in .env."""
    if not _ENV_PATH.is_file():
        return {}
    result: dict[str, str] = {}
    for raw in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        result[key.strip()] = value.strip().strip('"').strip("'")
    return result


def _write_env_file(values: dict[str, str]) -> None:
    """Write key=value pairs to .env, preserving blank lines and comments."""
    existing_lines: list[str] = []
    if _ENV_PATH.is_file():
        existing_lines = _ENV_PATH.read_text(encoding="utf-8").splitlines()

    written: set[str] = set()
    output: list[str] = []

    for raw in existing_lines:
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            output.append(raw)
            continue
        key, _, _ = line.partition("=")
        key = key.strip()
        if key in values:
            output.append(f'{key}={values[key]}')
            written.add(key)
        else:
            output.append(raw)

    # Append keys not already in the file
    new_keys = [k for k in values if k not in written]
    if new_keys:
        if output and output[-1].strip():
            output.append("")
        for k in new_keys:
            output.append(f"{k}={values[k]}")

    _ENV_PATH.write_text("\n".join(output) + "\n", encoding="utf-8")


# ── UI helpers ────────────────────────────────────────────────────────────────

def _section_card(title: str, subtitle: str = "") -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setStyleSheet(f"""
        QFrame {{
            background: {_BG_CARD};
            border: 1px solid {_BORDER};
            border-radius: 8px;
        }}
    """)
    vl = QVBoxLayout(card)
    vl.setContentsMargins(16, 12, 16, 14)
    vl.setSpacing(10)

    hdr = QHBoxLayout()
    title_lbl = QLabel(title)
    title_lbl.setStyleSheet(
        f"color: {_ACCENT}; font-size: 12px; font-weight: bold; "
        f"letter-spacing: 1px; background: transparent; border: none;"
    )
    hdr.addWidget(title_lbl)
    if subtitle:
        sub_lbl = QLabel(subtitle)
        sub_lbl.setStyleSheet(f"color: {_DIM}; font-size: 10px; background: transparent; border: none;")
        hdr.addWidget(sub_lbl)
    hdr.addStretch()
    vl.addLayout(hdr)

    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.HLine)
    sep.setStyleSheet(f"background: {_BORDER}; max-height: 1px; border: none;")
    vl.addWidget(sep)

    return card, vl


def _row(label: str, hint: str = "") -> tuple[QHBoxLayout, QLabel]:
    hl = QHBoxLayout()
    hl.setSpacing(10)
    lbl = QLabel(label)
    lbl.setFixedWidth(220)
    lbl.setStyleSheet(f"color: {_TEXT}; font-size: 12px; background: transparent; border: none;")
    lbl.setWordWrap(True)
    hl.addWidget(lbl)
    if hint:
        lbl.setToolTip(hint)
    return hl, lbl


def _hint_lbl(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"color: {_DIM}; font-size: 10px; background: transparent; border: none;")
    lbl.setWordWrap(True)
    return lbl


# ── Main panel ────────────────────────────────────────────────────────────────

class SettingsPanel(QWidget):
    """Settings screen — edit .env vars that drive orbit360 behaviour."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"QWidget {{ background: {_BG}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Fixed header ──────────────────────────────────────────────────
        hdr_bar = QWidget()
        hdr_bar.setFixedHeight(52)
        hdr_bar.setStyleSheet(f"background: {_BG};")
        hdr_layout = QHBoxLayout(hdr_bar)
        hdr_layout.setContentsMargins(20, 0, 20, 0)

        title = QLabel("⚙  SETTINGS")
        title.setStyleSheet(
            f"color: {_ACCENT}; font-size: 18px; font-weight: bold; letter-spacing: 2px;"
        )
        sub = QLabel("Configure orbit360 via .env")
        sub.setStyleSheet(f"color: {_DIM}; font-size: 11px;")
        hdr_layout.addWidget(title)
        hdr_layout.addSpacing(12)
        hdr_layout.addWidget(sub)
        hdr_layout.addStretch()
        outer.addWidget(hdr_bar)

        # ── Scroll area ───────────────────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: {_BG}; border: none; }}
            QScrollBar:vertical {{
                background: {_BG}; width: 8px; border: none; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: #2a3a50; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)
        outer.addWidget(scroll, 1)

        body = QWidget()
        body.setStyleSheet(f"background: {_BG};")
        self._body_layout = QVBoxLayout(body)
        self._body_layout.setContentsMargins(20, 4, 20, 20)
        self._body_layout.setSpacing(12)

        body.setStyleSheet(_FIELD_SHEET + f"QWidget {{ background: {_BG}; }}")

        # ── Section: General ──────────────────────────────────────────────
        gen_card, gen_body = _section_card("GENERAL")

        row, _ = _row("Parallel workers", "Number of scripts that run concurrently. 1 = sequential mode.")
        self._parallel = QSpinBox()
        self._parallel.setRange(1, 32)
        self._parallel.setFixedWidth(80)
        row.addWidget(self._parallel)
        row.addWidget(_hint_lbl("ORBIT_PARALLEL — 1 runs scripts sequentially (default)"))
        row.addStretch()
        gen_body.addLayout(row)

        row2, _ = _row("Dry run mode", "If checked, scripts are loaded but not executed.")
        self._dry_run = QCheckBox("Skip subprocess execution (for testing)")
        row2.addWidget(self._dry_run)
        row2.addStretch()
        gen_body.addLayout(row2)

        self._body_layout.addWidget(gen_card)

        # ── Section: Script execution ─────────────────────────────────────
        exec_card, exec_body = _section_card("SCRIPT EXECUTION")

        row, _ = _row("Timeout (minutes)", "Seconds before a running script is killed. 0 = no timeout.")
        self._timeout = QSpinBox()
        self._timeout.setRange(0, 1440)
        self._timeout.setFixedWidth(80)
        self._timeout.setSpecialValueText("None")
        row.addWidget(self._timeout)
        row.addWidget(_hint_lbl("ORBIT_TIMEOUT_MINUTES"))
        row.addStretch()
        exec_body.addLayout(row)

        row2, _ = _row("Retry count", "Times to retry a failed script before marking it failed.")
        self._retry = QSpinBox()
        self._retry.setRange(0, 10)
        self._retry.setFixedWidth(80)
        row2.addWidget(self._retry)
        row2.addWidget(_hint_lbl("ORBIT_RETRY_COUNT"))
        row2.addStretch()
        exec_body.addLayout(row2)

        self._body_layout.addWidget(exec_card)

        # ── Section: Storage ──────────────────────────────────────────────
        stor_card, stor_body = _section_card("STORAGE")

        row, _ = _row("Storage limit (GB)", "Warn before a run when orbit_data/ approaches this size.")
        self._storage_limit = QDoubleSpinBox()
        self._storage_limit.setRange(1, 9999)
        self._storage_limit.setDecimals(1)
        self._storage_limit.setFixedWidth(100)
        row.addWidget(self._storage_limit)
        row.addWidget(_hint_lbl("ORBIT_STORAGE_LIMIT_GB (default: 20)"))
        row.addStretch()
        stor_body.addLayout(row)

        row2, _ = _row("Warn threshold (%)", "Percentage of the limit at which a warning is shown.")
        self._storage_warn = QSpinBox()
        self._storage_warn.setRange(10, 100)
        self._storage_warn.setFixedWidth(80)
        row2.addWidget(self._storage_warn)
        row2.addWidget(_hint_lbl("ORBIT_STORAGE_WARN_PCT (default: 80)"))
        row2.addStretch()
        stor_body.addLayout(row2)

        self._body_layout.addWidget(stor_card)

        # ── Section: UiPath ───────────────────────────────────────────────
        uip_card, uip_body = _section_card("UIPATH", "leave blank to auto-discover UiRobot.exe")

        row, _ = _row("UiRobot.exe path", "Explicit path to UiRobot.exe. Leave blank for auto-discovery.")
        self._uirobot = QLineEdit()
        self._uirobot.setPlaceholderText("e.g. C:\\UiPath\\Robot\\UiRobot.exe")
        row.addWidget(self._uirobot, 1)
        browse_ui = QPushButton("Browse…")
        browse_ui.setStyleSheet(_BROWSE_SHEET)
        browse_ui.clicked.connect(self._browse_uirobot)
        row.addWidget(browse_ui)
        uip_body.addLayout(row)
        uip_body.addWidget(_hint_lbl("ORBIT_UIROBOT_PATH"))

        self._body_layout.addWidget(uip_card)

        # ── Section: SQL Executor ─────────────────────────────────────────
        sql_card, sql_body = _section_card("SQL EXECUTOR", "leave blank to disable SQL scripts")

        row, _ = _row("Dialect")
        self._sql_dialect = QComboBox()
        self._sql_dialect.addItems(["", "sqlite", "mssql", "oracle"])
        self._sql_dialect.setFixedWidth(120)
        self._sql_dialect.currentTextChanged.connect(self._on_dialect_changed)
        row.addWidget(self._sql_dialect)
        row.addWidget(_hint_lbl("ORBIT_SQL_DIALECT"))
        row.addStretch()
        sql_body.addLayout(row)

        row2, _ = _row("SQLite DB path", "Absolute path to .db file (sqlite dialect only).")
        self._sql_db_path = QLineEdit()
        self._sql_db_path.setPlaceholderText("e.g. C:\\data\\mydb.db")
        row2.addWidget(self._sql_db_path, 1)
        browse_db = QPushButton("Browse…")
        browse_db.setStyleSheet(_BROWSE_SHEET)
        browse_db.clicked.connect(self._browse_db)
        row2.addWidget(browse_db)
        self._sql_db_row_widget = QWidget()
        self._sql_db_row_widget.setStyleSheet("background: transparent;")
        QHBoxLayout(self._sql_db_row_widget).setContentsMargins(0,0,0,0)
        # embed row2 inside a container so we can hide the whole row
        self._sql_db_container = QWidget()
        self._sql_db_container.setStyleSheet("background: transparent;")
        dc = QVBoxLayout(self._sql_db_container)
        dc.setContentsMargins(0, 0, 0, 0)
        dc.setSpacing(2)
        dc.addLayout(row2)
        dc.addWidget(_hint_lbl("ORBIT_SQL_DB_PATH"))
        sql_body.addWidget(self._sql_db_container)

        row3, _ = _row("Connection string (DSN)", "pyodbc connection string for mssql / oracle.")
        self._sql_dsn = QLineEdit()
        self._sql_dsn.setPlaceholderText("e.g. DSN=MyServer;UID=sa;PWD=...")
        row3.addWidget(self._sql_dsn, 1)
        self._sql_dsn_container = QWidget()
        self._sql_dsn_container.setStyleSheet("background: transparent;")
        nc = QVBoxLayout(self._sql_dsn_container)
        nc.setContentsMargins(0, 0, 0, 0)
        nc.setSpacing(2)
        nc.addLayout(row3)
        nc.addWidget(_hint_lbl("ORBIT_SQL_DSN"))
        sql_body.addWidget(self._sql_dsn_container)

        row4, _ = _row("Query timeout (s)")
        self._sql_timeout = QSpinBox()
        self._sql_timeout.setRange(0, 3600)
        self._sql_timeout.setFixedWidth(80)
        row4.addWidget(self._sql_timeout)
        row4.addWidget(_hint_lbl("ORBIT_SQL_TIMEOUT (default: 30)"))
        row4.addStretch()
        sql_body.addLayout(row4)

        row5, _ = _row("Output format")
        self._sql_fmt = QComboBox()
        self._sql_fmt.addItems(["log", "csv", "json"])
        self._sql_fmt.setFixedWidth(100)
        row5.addWidget(self._sql_fmt)
        row5.addWidget(_hint_lbl("ORBIT_SQL_OUTPUT_FORMAT"))
        row5.addStretch()
        sql_body.addLayout(row5)

        self._body_layout.addWidget(sql_card)

        # ── Save bar ──────────────────────────────────────────────────────
        save_bar = QWidget()
        save_bar.setStyleSheet("background: transparent;")
        save_layout = QHBoxLayout(save_bar)
        save_layout.setContentsMargins(0, 4, 0, 0)

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color: {_GREEN}; font-size: 11px; background: transparent;")
        save_layout.addWidget(self._status_lbl)
        save_layout.addStretch()

        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {_BORDER};
                border-radius: 4px; color: {_DIM}; font-size: 11px; padding: 4px 14px;
            }}
            QPushButton:hover {{ color: {_AMBER}; border-color: {_AMBER}; }}
        """)
        reset_btn.clicked.connect(self._reset_to_defaults)
        save_layout.addWidget(reset_btn)

        save_btn = QPushButton("Save Changes")
        save_btn.setStyleSheet(_SAVE_SHEET)
        save_btn.clicked.connect(self._save)
        save_layout.addWidget(save_btn)

        self._body_layout.addWidget(save_bar)
        self._body_layout.addStretch()

        scroll.setWidget(body)

        self._load()
        self._on_dialect_changed(self._sql_dialect.currentText())

    # ── Public ───────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._load()

    # ── Private ──────────────────────────────────────────────────────────────

    def _load(self) -> None:
        env = _read_env_file()

        def _e(key: str, default: str = "") -> str:
            return env.get(key, os.environ.get(key, default))

        self._parallel.setValue(int(_e("ORBIT_PARALLEL", "1") or 1))
        self._dry_run.setChecked(_e("ORBIT_DRY_RUN", "0") == "1")
        self._timeout.setValue(int(_e("ORBIT_TIMEOUT_MINUTES", "0") or 0))
        self._retry.setValue(int(_e("ORBIT_RETRY_COUNT", "0") or 0))
        self._storage_limit.setValue(float(_e("ORBIT_STORAGE_LIMIT_GB", "20") or 20))
        self._storage_warn.setValue(int(_e("ORBIT_STORAGE_WARN_PCT", "80") or 80))
        self._uirobot.setText(_e("ORBIT_UIROBOT_PATH", ""))

        self._status_lbl.setText("")

        dialect = _e("ORBIT_SQL_DIALECT", "")
        idx = self._sql_dialect.findText(dialect)
        if idx < 0 and dialect:
            self._status_lbl.setStyleSheet(
                f"color: {_AMBER}; font-size: 11px; background: transparent;"
            )
            self._status_lbl.setText(
                f"Warning: ORBIT_SQL_DIALECT '{dialect}' not recognised — select a dialect below"
            )
        else:
            self._status_lbl.setStyleSheet(
                f"color: {_GREEN}; font-size: 11px; background: transparent;"
            )
        self._sql_dialect.setCurrentIndex(max(0, idx))
        self._sql_db_path.setText(_e("ORBIT_SQL_DB_PATH", ""))
        self._sql_dsn.setText(_e("ORBIT_SQL_DSN", ""))
        self._sql_timeout.setValue(int(_e("ORBIT_SQL_TIMEOUT", "30") or 30))
        fmt = _e("ORBIT_SQL_OUTPUT_FORMAT", "log")
        self._sql_fmt.setCurrentText(fmt if fmt in ("log", "csv", "json") else "log")

    def _save(self) -> None:
        self._status_lbl.setStyleSheet(
            f"color: {_AMBER}; font-size: 11px; background: transparent;"
        )
        self._status_lbl.setText("Saving…")
        QApplication.processEvents()

        values: dict[str, str] = {}

        parallel = self._parallel.value()
        if parallel != 1:
            values["ORBIT_PARALLEL"] = str(parallel)

        if self._dry_run.isChecked():
            values["ORBIT_DRY_RUN"] = "1"

        timeout = self._timeout.value()
        if timeout:
            values["ORBIT_TIMEOUT_MINUTES"] = str(timeout)

        retry = self._retry.value()
        if retry:
            values["ORBIT_RETRY_COUNT"] = str(retry)

        limit = self._storage_limit.value()
        if limit != 20.0:
            values["ORBIT_STORAGE_LIMIT_GB"] = f"{limit:.1f}"

        warn = self._storage_warn.value()
        if warn != 80:
            values["ORBIT_STORAGE_WARN_PCT"] = str(warn)

        uirobot = self._uirobot.text().strip()
        if uirobot:
            values["ORBIT_UIROBOT_PATH"] = uirobot

        dialect = self._sql_dialect.currentText()
        if dialect:
            values["ORBIT_SQL_DIALECT"] = dialect
            if dialect == "sqlite":
                db = self._sql_db_path.text().strip()
                if db:
                    values["ORBIT_SQL_DB_PATH"] = db
            else:
                dsn = self._sql_dsn.text().strip()
                if dsn:
                    values["ORBIT_SQL_DSN"] = dsn
            t = self._sql_timeout.value()
            if t != 30:
                values["ORBIT_SQL_TIMEOUT"] = str(t)
            fmt = self._sql_fmt.currentText()
            if fmt != "log":
                values["ORBIT_SQL_OUTPUT_FORMAT"] = fmt

        try:
            _write_env_file(values)
        except Exception as exc:
            QMessageBox.warning(self, "Save Failed", str(exc))
            return

        # Apply to live process so next run picks them up immediately
        for key, val in values.items():
            os.environ[key] = val

        self._status_lbl.setStyleSheet(
            f"color: {_GREEN}; font-size: 11px; background: transparent;"
        )
        self._status_lbl.setText("✓  Saved")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(3000, lambda: self._status_lbl.setText(""))

    def _reset_to_defaults(self) -> None:
        self._parallel.setValue(1)
        self._dry_run.setChecked(False)
        self._timeout.setValue(0)
        self._retry.setValue(0)
        self._storage_limit.setValue(20.0)
        self._storage_warn.setValue(80)
        self._uirobot.setText("")
        self._sql_dialect.setCurrentIndex(0)
        self._sql_db_path.setText("")
        self._sql_dsn.setText("")
        self._sql_timeout.setValue(30)
        self._sql_fmt.setCurrentText("log")

    def _on_dialect_changed(self, dialect: str) -> None:
        self._sql_db_container.setVisible(dialect == "sqlite")
        self._sql_dsn_container.setVisible(dialect in ("mssql", "oracle"))

    def _browse_uirobot(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select UiRobot.exe", "", "Executables (*.exe);;All files (*)"
        )
        if path:
            self._uirobot.setText(path)

    def _browse_db(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select SQLite database", "", "SQLite (*.db *.sqlite *.sqlite3);;All files (*)"
        )
        if path:
            self._sql_db_path.setText(path)
