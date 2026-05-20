"""
orbit360/ui/reports_panel.py
Vault — archived run history with filtering, script drill-down, and CSV export.
"""
from __future__ import annotations

import csv
import shutil
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont
from PySide6.QtWidgets import (
    QApplication, QButtonGroup, QComboBox, QDialog, QFrame, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMenu, QMessageBox, QPushButton,
    QRadioButton, QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem,
    QTextEdit, QVBoxLayout, QWidget,
)

from orbit360.backend import history_db
from orbit360.ui._ui_utils import fmt_dur as _fmt_dur
from orbit360.utils.paths import RUNS_DIR

_BG      = "#0a0e1a"
_BG_CARD = "#0d1520"
_BORDER  = "#1a2a40"
_ACCENT  = "#89b4fa"
_GREEN   = "#a6e3a1"
_RED     = "#f38ba8"
_AMBER   = "#f9e2af"
_TEXT    = "#cdd6f4"
_DIM     = "#6c7086"
_SUBTEXT = "#a6adc8"

_PERIOD_OPTIONS: list[tuple[str, int | None]] = [
    ("All Time",     None),
    ("Last 30 Days", 30),
    ("Last 7 Days",   7),
    ("Today",         1),
]

_TABLE_SHEET = f"""
    QTableWidget {{
        background: transparent; color: {_TEXT}; font-size: 11px; border: none;
    }}
    QTableWidget::item:selected {{ background: #132240; color: {_ACCENT}; }}
    QTableWidget::item:alternate {{ background: #0a1525; }}
    QHeaderView::section {{
        background: #0a0e1a; color: {_DIM}; font-size: 10px; font-weight: bold;
        border: none; border-bottom: 1px solid {_BORDER}; padding: 4px 8px;
    }}
    QHeaderView::section:hover {{ color: {_ACCENT}; }}
"""

_COMBO_SHEET = f"""
    QComboBox {{
        background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
        color: {_SUBTEXT}; font-size: 11px; padding: 2px 8px;
    }}
    QComboBox:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
    QComboBox::drop-down {{ border: none; }}
    QComboBox QAbstractItemView {{
        background: #111c30; border: 1px solid {_BORDER};
        color: {_TEXT}; selection-background-color: #132240;
    }}
"""


# ── Log viewer dialog ────────────────────────────────────────────────────────

def _colorize_log_line(line: str) -> str:
    """Return an HTML-colored version of a log line."""
    esc = (
        line.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
    )
    parts = line.split("|", 1)
    level = parts[0].strip().upper() if parts else ""
    if level in ("ERROR", "CRITICAL") or "SCRIPT FAILED" in line:
        return f"<span style='color:#f38ba8'>{esc}</span>"
    if level == "WARNING" or "MANUAL STEP" in line:
        return f"<span style='color:#fab387'>{esc}</span>"
    if level == "INFO":
        if line.startswith("─") or "─" in (parts[1] if len(parts) > 1 else ""):
            return f"<span style='color:#89b4fa'>{esc}</span>"
        return f"<span style='color:#a6e3a1'>{esc}</span>"
    if level == "DEBUG":
        return f"<span style='color:#6c7086'>{esc}</span>"
    if line.startswith("ORBIT_"):
        return f"<span style='color:#cba6f7'>{esc}</span>"
    return f"<span style='color:#a6adc8'>{esc}</span>"


class LogViewerDialog(QDialog):
    """Read-only log viewer for a single script's output.log."""

    def __init__(self, script_name: str, log_path: Path,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Log — {script_name}")
        self.resize(820, 560)
        self.setStyleSheet(f"QDialog {{ background: #080d18; color: #cdd6f4; }}")

        vl = QVBoxLayout(self)
        vl.setContentsMargins(12, 10, 12, 10)
        vl.setSpacing(8)

        # Header
        hdr = QLabel(f"<b style='color:#89b4fa'>{script_name}</b>"
                     f"  <span style='color:#6c7086; font-size:10px'>{log_path}</span>")
        hdr.setTextFormat(Qt.TextFormat.RichText)
        hdr.setWordWrap(True)
        vl.addWidget(hdr)

        # Text area
        self._text = QTextEdit()
        self._text.setReadOnly(True)
        self._text.setStyleSheet("""
            QTextEdit {
                background: #080d18;
                border: 1px solid #1a2a40;
                border-radius: 6px;
                color: #a6adc8;
                font-family: "Consolas", "Courier New", monospace;
                font-size: 11px;
            }
        """)
        f = QFont("Consolas", 10)
        f.setFixedPitch(True)
        self._text.setFont(f)
        vl.addWidget(self._text, 1)

        # Button row
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self._copy_all_btn = QPushButton("Copy All")
        self._copy_all_btn.setFixedWidth(80)
        self._copy_all_btn.setToolTip("Copy all log lines to clipboard")
        self._copy_all_btn.setStyleSheet(f"""
            QPushButton {{
                background: #111c30; border: 1px solid #1a2a40; border-radius: 4px;
                color: #a6adc8; font-size: 11px; padding: 4px 12px;
            }}
            QPushButton:hover {{ border-color: #89b4fa; color: #89b4fa; }}
        """)
        self._copy_all_btn.clicked.connect(self._copy_all)
        btn_row.addWidget(self._copy_all_btn)

        close_btn = QPushButton("Close")
        close_btn.setFixedWidth(80)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: #111c30; border: 1px solid #1a2a40; border-radius: 4px;
                color: #a6adc8; font-size: 11px; padding: 4px 12px;
            }}
            QPushButton:hover {{ border-color: #89b4fa; color: #89b4fa; }}
        """)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        vl.addLayout(btn_row)

        self._load(log_path)

    def _copy_all(self) -> None:
        cb = QApplication.clipboard()
        if cb:
            cb.setText(self._text.toPlainText())
        self._copy_all_btn.setText("✓ Copied")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, lambda: self._copy_all_btn.setText("Copy All"))

    def _load(self, path: Path) -> None:
        if not path.is_file():
            self._text.setPlainText(f"Log file not found:\n{path}")
            return
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except Exception as exc:
            self._text.setPlainText(f"Could not read log: {exc}")
            return
        html_lines = [_colorize_log_line(l) for l in lines]
        self._text.setHtml(
            "<div style='font-family:Consolas,monospace; font-size:11px; "
            "line-height:1.45; white-space:pre'>"
            + "<br>".join(html_lines)
            + "</div>"
        )
        # Scroll to bottom
        sb = self._text.verticalScrollBar()
        sb.setValue(sb.maximum())


# ── Purge dialog ─────────────────────────────────────────────────────────────

def _folder_size_bytes(path: Path) -> int:
    total = 0
    try:
        for f in path.rglob("*"):
            try:
                if f.is_file():
                    total += f.stat().st_size
            except OSError:
                continue
    except OSError:
        pass
    return total


def _fmt_bytes(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.1f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


class PurgeDialog(QDialog):
    """Manual purge of old run folders under RUNS_DIR.

    Two modes:
      - Keep the most recent N runs (default 25)
      - Delete runs older than N days (default 30)

    The dialog previews how many folders match and the total disk space that
    will be reclaimed before any deletion happens. OneDrive-locked files are
    skipped silently and reported back at the end.
    """

    _MODE_KEEP = "keep"
    _MODE_DAYS = "days"

    def __init__(self, runs_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Purge Old Runs")
        self.setMinimumWidth(440)
        self.setStyleSheet(f"QDialog {{ background: #080d18; color: {_TEXT}; }}")

        self._runs_dir = runs_dir
        self._all_folders: list[Path] = []
        self._target_folders: list[Path] = []

        vl = QVBoxLayout(self)
        vl.setContentsMargins(16, 14, 16, 14)
        vl.setSpacing(10)

        title = QLabel("🗑  PURGE RUN FOLDERS")
        title.setStyleSheet(
            f"color: {_ACCENT}; font-size: 13px; font-weight: bold; letter-spacing: 1px;"
        )
        vl.addWidget(title)

        self._summary_lbl = QLabel("Scanning…")
        self._summary_lbl.setStyleSheet(f"color: {_DIM}; font-size: 11px;")
        vl.addWidget(self._summary_lbl)

        # ── Mode: keep most recent N ────────────────────────────────────
        self._group = QButtonGroup(self)
        keep_row = QHBoxLayout()
        keep_row.setSpacing(8)
        self._keep_radio = QRadioButton("Keep the most recent")
        self._keep_radio.setStyleSheet(self._radio_style())
        self._keep_radio.setChecked(True)
        self._group.addButton(self._keep_radio)
        keep_row.addWidget(self._keep_radio)

        self._keep_spin = QSpinBox()
        self._keep_spin.setRange(0, 9999)
        self._keep_spin.setValue(25)
        self._keep_spin.setFixedWidth(80)
        self._keep_spin.setStyleSheet(self._spin_style())
        keep_row.addWidget(self._keep_spin)
        keep_row.addWidget(QLabel("runs"))
        keep_row.addStretch()
        vl.addLayout(keep_row)

        # ── Mode: older than N days ─────────────────────────────────────
        days_row = QHBoxLayout()
        days_row.setSpacing(8)
        self._days_radio = QRadioButton("Delete runs older than")
        self._days_radio.setStyleSheet(self._radio_style())
        self._group.addButton(self._days_radio)
        days_row.addWidget(self._days_radio)

        self._days_spin = QSpinBox()
        self._days_spin.setRange(1, 3650)
        self._days_spin.setValue(30)
        self._days_spin.setFixedWidth(80)
        self._days_spin.setStyleSheet(self._spin_style())
        days_row.addWidget(self._days_spin)
        days_row.addWidget(QLabel("days"))
        days_row.addStretch()
        vl.addLayout(days_row)

        # Style all child labels uniformly
        for lbl in self.findChildren(QLabel):
            if lbl is not title and lbl is not self._summary_lbl:
                lbl.setStyleSheet(f"color: {_SUBTEXT}; font-size: 11px;")

        # ── Preview ─────────────────────────────────────────────────────
        self._preview_lbl = QLabel(" ")
        self._preview_lbl.setWordWrap(True)
        self._preview_lbl.setStyleSheet(
            f"color: {_AMBER}; font-size: 11px; "
            f"background: #110b00; border: 1px solid #3a2c0d; "
            f"border-radius: 6px; padding: 8px 10px;"
        )
        vl.addWidget(self._preview_lbl)

        # ── Buttons ─────────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedWidth(90)
        cancel_btn.setStyleSheet(self._cancel_style())
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._purge_btn = QPushButton("Purge")
        self._purge_btn.setFixedWidth(100)
        self._purge_btn.setStyleSheet(self._purge_style())
        self._purge_btn.clicked.connect(self._on_purge)
        btn_row.addWidget(self._purge_btn)
        vl.addLayout(btn_row)

        # Wire previews to inputs
        self._keep_radio.toggled.connect(self._update_preview)
        self._days_radio.toggled.connect(self._update_preview)
        self._keep_spin.valueChanged.connect(self._update_preview)
        self._days_spin.valueChanged.connect(self._update_preview)

        self._scan()
        self._update_preview()

    # ── Public ──────────────────────────────────────────────────────────────
    @property
    def deleted_count(self) -> int:
        return getattr(self, "_deleted", 0)

    @property
    def freed_bytes(self) -> int:
        return getattr(self, "_freed", 0)

    # ── Internals ───────────────────────────────────────────────────────────
    def _scan(self) -> None:
        if not self._runs_dir.is_dir():
            self._summary_lbl.setText("Run folder does not exist yet — nothing to purge.")
            self._purge_btn.setEnabled(False)
            return
        try:
            self._all_folders = sorted(
                (d for d in self._runs_dir.iterdir() if d.is_dir()),
                key=lambda d: d.stat().st_mtime,
                reverse=True,  # newest first
            )
        except OSError:
            self._all_folders = []
        self._summary_lbl.setText(
            f"Found {len(self._all_folders)} run folder(s) under "
            f"<code style='color:{_SUBTEXT}'>{self._runs_dir}</code>."
        )
        self._summary_lbl.setTextFormat(Qt.TextFormat.RichText)

    def _selected_targets(self) -> list[Path]:
        if not self._all_folders:
            return []
        if self._keep_radio.isChecked():
            keep = max(0, self._keep_spin.value())
            return self._all_folders[keep:]  # everything past the newest `keep`
        cutoff = time.time() - self._days_spin.value() * 86400
        result: list[Path] = []
        for d in self._all_folders:
            try:
                if d.stat().st_mtime < cutoff:
                    result.append(d)
            except OSError:
                continue
        return result

    def _update_preview(self) -> None:
        targets = self._selected_targets()
        self._target_folders = targets
        if not targets:
            self._preview_lbl.setText("Nothing matches — no folders will be deleted.")
            self._purge_btn.setEnabled(False)
            return
        # Cap size scan to first ~50 folders to stay snappy on huge histories
        sample = targets[:50]
        sampled_bytes = sum(_folder_size_bytes(p) for p in sample)
        if len(targets) > len(sample):
            est = sampled_bytes * len(targets) / len(sample)
            size_str = f"~{_fmt_bytes(int(est))}"
        else:
            size_str = _fmt_bytes(sampled_bytes)
        self._preview_lbl.setText(
            f"<b>{len(targets)}</b> run folder(s) will be deleted "
            f"(<b>{size_str}</b>). This cannot be undone."
        )
        self._preview_lbl.setTextFormat(Qt.TextFormat.RichText)
        self._purge_btn.setEnabled(True)

    def _on_purge(self) -> None:
        targets = self._target_folders
        if not targets:
            self.reject()
            return
        confirm = QMessageBox(self)
        confirm.setWindowTitle("Confirm Purge")
        confirm.setIcon(QMessageBox.Icon.Warning)
        confirm.setText(
            f"Permanently delete <b>{len(targets)}</b> run folder(s)?<br><br>"
            f"<span style='color:{_DIM}'>OneDrive-locked files will be skipped.</span>"
        )
        confirm.setTextFormat(Qt.TextFormat.RichText)
        confirm.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        confirm.setDefaultButton(QMessageBox.StandardButton.No)
        if confirm.exec() != QMessageBox.StandardButton.Yes:
            return

        deleted, freed, skipped = 0, 0, 0
        for d in targets:
            size = _folder_size_bytes(d)
            try:
                shutil.rmtree(d)
                deleted += 1
                freed += size
            except OSError:
                # OneDrive lock, permission, or in-use — skip silently
                skipped += 1

        self._deleted = deleted
        self._freed = freed
        self._skipped = skipped
        self.accept()

    # ── Styling helpers ─────────────────────────────────────────────────────
    @staticmethod
    def _radio_style() -> str:
        return f"""
            QRadioButton {{ color: {_TEXT}; font-size: 12px; spacing: 6px; }}
            QRadioButton::indicator {{ width: 12px; height: 12px; }}
            QRadioButton::indicator:unchecked {{
                border: 1px solid {_BORDER}; border-radius: 6px; background: #0a1525;
            }}
            QRadioButton::indicator:checked {{
                border: 1px solid {_ACCENT}; border-radius: 6px; background: {_ACCENT};
            }}
        """

    @staticmethod
    def _spin_style() -> str:
        return f"""
            QSpinBox {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_TEXT}; font-size: 11px; padding: 2px 6px;
            }}
            QSpinBox::up-button, QSpinBox::down-button {{ width: 14px; }}
        """

    @staticmethod
    def _cancel_style() -> str:
        return f"""
            QPushButton {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_SUBTEXT}; font-size: 11px; padding: 5px 12px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
        """

    @staticmethod
    def _purge_style() -> str:
        return f"""
            QPushButton {{
                background: #2a1020; border: 1px solid {_RED}; border-radius: 4px;
                color: {_RED}; font-size: 11px; font-weight: bold; padding: 5px 12px;
            }}
            QPushButton:hover {{ background: #3a1428; }}
            QPushButton:disabled {{
                background: #0a1525; border-color: #1a2233; color: #2a3a50;
            }}
        """


# ── Table helper ─────────────────────────────────────────────────────────────

def _cell(text: str, color: str = _TEXT,
          align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
          ) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setTextAlignment(align)
    item.setForeground(QColor(color))
    return item


class ReportsPanel(QWidget):
    """Vault — archived run history with filtering, script drill-down, and CSV export."""

    _COLS = ["Timestamp", "System", "Scripts", "Passed", "Failed", "Duration", "Actions"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"QWidget {{ background: {_BG}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(8)

        # ── Title row ─────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title = QLabel("▣  VAULT")
        title.setStyleSheet(
            f"color: {_ACCENT}; font-size: 18px; font-weight: bold; letter-spacing: 2px;"
        )
        sub = QLabel("Archived run history, execution logs, and result exports")
        sub.setStyleSheet(f"color: {_DIM}; font-size: 11px;")
        title_row.addWidget(title)
        title_row.addSpacing(12)
        title_row.addWidget(sub)
        title_row.addStretch()
        root.addLayout(title_row)

        # ── Filter / action row ───────────────────────────────────────────
        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        self._period_combo = QComboBox()
        for label, _ in _PERIOD_OPTIONS:
            self._period_combo.addItem(label)
        self._period_combo.setFixedHeight(26)
        self._period_combo.setMinimumWidth(110)
        self._period_combo.setStyleSheet(_COMBO_SHEET)
        self._period_combo.setToolTip("Filter run history by time window")
        self._period_combo.currentIndexChanged.connect(self.refresh)
        filter_row.addWidget(self._period_combo)

        self._system_combo = QComboBox()
        self._system_combo.addItem("All Systems")
        self._system_combo.setFixedHeight(26)
        self._system_combo.setMinimumWidth(130)
        self._system_combo.setStyleSheet(_COMBO_SHEET)
        self._system_combo.currentIndexChanged.connect(self._apply_filters)
        filter_row.addWidget(self._system_combo)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Filter by system, timestamp, or run ID...")
        self._search.setFixedHeight(26)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_TEXT}; font-size: 11px; padding: 2px 8px;
            }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
        """)
        self._search.textChanged.connect(self._apply_filters)
        filter_row.addWidget(self._search, 1)

        export_btn = QPushButton("⬇  Export CSV")
        export_btn.setFixedHeight(26)
        export_btn.setStyleSheet(f"""
            QPushButton {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_SUBTEXT}; font-size: 11px; padding: 2px 12px;
            }}
            QPushButton:hover {{ color: {_GREEN}; border-color: {_GREEN}; }}
        """)
        export_btn.clicked.connect(self._export_csv)
        filter_row.addWidget(export_btn)

        purge_btn = QPushButton("🗑  Purge…")
        purge_btn.setFixedHeight(26)
        purge_btn.setToolTip("Manually delete old run folders from disk")
        purge_btn.setStyleSheet(f"""
            QPushButton {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_SUBTEXT}; font-size: 11px; padding: 2px 12px;
            }}
            QPushButton:hover {{ color: {_RED}; border-color: {_RED}; }}
        """)
        purge_btn.clicked.connect(self._open_purge_dialog)
        filter_row.addWidget(purge_btn)

        self._refresh_btn = QPushButton("↺  Refresh")
        self._refresh_btn.setFixedHeight(26)
        self._refresh_btn.setToolTip("Reload run history from database")
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_SUBTEXT}; font-size: 11px; padding: 2px 12px;
            }}
            QPushButton:hover {{ color: {_ACCENT}; border-color: {_ACCENT}; }}
        """)
        self._refresh_btn.clicked.connect(self.refresh)
        filter_row.addWidget(self._refresh_btn)
        root.addLayout(filter_row)

        # ── Summary strip ─────────────────────────────────────────────────
        self._summary_lbl = QLabel("")
        self._summary_lbl.setStyleSheet(f"color: {_DIM}; font-size: 11px;")
        root.addWidget(self._summary_lbl)

        # ── Main table card ───────────────────────────────────────────────
        card = QFrame()
        card.setStyleSheet(f"""
            QFrame {{
                background: {_BG_CARD}; border: 1px solid {_BORDER}; border-radius: 8px;
            }}
        """)
        card_vl = QVBoxLayout(card)
        card_vl.setContentsMargins(0, 0, 0, 0)
        card_vl.setSpacing(0)

        self._table = QTableWidget(0, len(self._COLS))
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(30)
        self._table.horizontalHeader().setHighlightSections(False)
        self._table.horizontalHeader().setStretchLastSection(False)
        self._table.setShowGrid(False)
        self._table.setStyleSheet(_TABLE_SHEET)

        hv = self._table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)    # Timestamp
        hv.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)  # System
        hv.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)    # Scripts
        hv.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)    # Passed
        hv.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)    # Failed
        hv.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)    # Duration
        hv.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)    # Actions
        self._table.setColumnWidth(0, 148)
        self._table.setColumnWidth(2, 66)
        self._table.setColumnWidth(3, 66)
        self._table.setColumnWidth(4, 66)
        self._table.setColumnWidth(5, 88)
        self._table.setColumnWidth(6, 140)
        self._table.currentCellChanged.connect(
            lambda row, col, prow, pcol: self._on_row_selected(row)
        )

        card_vl.addWidget(self._table)
        root.addWidget(card, 1)

        # ── Script detail panel (populated on row click) ──────────────────
        self._detail_card = QFrame()
        self._detail_card.setStyleSheet(f"""
            QFrame {{
                background: {_BG_CARD}; border: 1px solid {_BORDER}; border-radius: 8px;
            }}
        """)
        detail_vl = QVBoxLayout(self._detail_card)
        detail_vl.setContentsMargins(14, 10, 14, 12)
        detail_vl.setSpacing(6)

        self._detail_title = QLabel("Click any run to see per-script results")
        self._detail_title.setStyleSheet(
            f"color: {_ACCENT}; font-size: 11px; font-weight: bold; "
            f"letter-spacing: 1px; background: transparent; border: none;"
        )
        detail_vl.addWidget(self._detail_title)

        self._detail_table = QTableWidget(0, 3)
        self._detail_table.setHorizontalHeaderLabels(["Script", "Status", "Duration"])
        self._detail_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._detail_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._detail_table.setAlternatingRowColors(True)
        self._detail_table.verticalHeader().setVisible(False)
        self._detail_table.verticalHeader().setDefaultSectionSize(24)
        self._detail_table.horizontalHeader().setHighlightSections(False)
        self._detail_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self._detail_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._detail_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._detail_table.setShowGrid(False)
        self._detail_table.setMaximumHeight(160)
        self._detail_table.setStyleSheet(_TABLE_SHEET)
        self._detail_table.itemDoubleClicked.connect(self._on_script_double_clicked)
        self._detail_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._detail_table.customContextMenuRequested.connect(self._on_detail_context_menu)
        detail_vl.addWidget(self._detail_table)

        self._hint_lbl = QLabel("Double-click a script row to view its log")
        self._hint_lbl.setStyleSheet(
            f"color: {_DIM}; font-size: 10px; background: transparent; border: none;"
        )
        detail_vl.addWidget(self._hint_lbl)

        root.addWidget(self._detail_card)

        # State
        self._all_runs:      list[dict]      = []
        self._visible_runs:  list[dict]      = []
        self._run_dir_cache: dict[str, Path] = {}
        self._current_run_dir: Path | None   = None
        self._current_scripts: list[dict]    = []

        self.refresh()

    # ── Public ───────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._run_dir_cache = self._build_run_dir_cache()

        idx        = self._period_combo.currentIndex()
        since_days = _PERIOD_OPTIONS[idx][1] if 0 <= idx < len(_PERIOD_OPTIONS) else None
        self._all_runs = history_db.get_recent_runs(limit=500, since_days=since_days)

        # Rebuild system combo preserving selection
        systems     = sorted({r.get("system", "") for r in self._all_runs if r.get("system")})
        prev_system = self._system_combo.currentText()
        self._system_combo.blockSignals(True)
        self._system_combo.clear()
        self._system_combo.addItem("All Systems")
        for s in systems:
            self._system_combo.addItem(s)
        restore = self._system_combo.findText(prev_system)
        if restore >= 0:
            self._system_combo.setCurrentIndex(restore)
        self._system_combo.blockSignals(False)

        self._apply_filters()

    # ── Private ──────────────────────────────────────────────────────────────

    def _apply_filters(self) -> None:
        sys_filter  = self._system_combo.currentText()
        search_text = self._search.text().strip().lower()

        runs = self._all_runs
        if sys_filter and sys_filter != "All Systems":
            runs = [r for r in runs if r.get("system", "") == sys_filter]
        if search_text:
            runs = [
                r for r in runs
                if search_text in r.get("system",    "").lower()
                or search_text in r.get("timestamp", "").lower()
                or search_text in r.get("run_id",    "").lower()
            ]

        self._visible_runs = runs
        self._populate_table(runs)

        total_pass = sum(r.get("passed", 0) for r in runs)
        total_fail = sum(r.get("failed", 0) + r.get("errored", 0) for r in runs)
        if runs:
            filtered = "  (filtered)" if len(runs) < len(self._all_runs) else ""
            self._summary_lbl.setText(
                f"{len(runs)} runs{filtered}  •  "
                f"{total_pass} scripts passed  •  "
                f"{total_fail} scripts failed"
            )
        else:
            self._summary_lbl.setText("No runs match the current filters.")

    def _populate_table(self, runs: list[dict]) -> None:
        _C = Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        self._table.setRowCount(0)   # clear stale cell widgets before resizing
        if not runs:
            self._table.setRowCount(1)
            empty = QTableWidgetItem("No runs match the current filters")
            empty.setForeground(QColor(_DIM))
            empty.setTextAlignment(_C)
            empty.setFlags(empty.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            self._table.setItem(0, 0, empty)
            self._table.setSpan(0, 0, 1, self._table.columnCount())
            return
        self._table.setRowCount(len(runs))
        for i, r in enumerate(runs):
            ts     = r.get("timestamp", "")
            ts_s   = ts[:19].replace("T", "  ") if len(ts) >= 16 else ts
            total  = r.get("total",  0)
            passed = r.get("passed", 0)
            failed = r.get("failed", 0) + r.get("errored", 0)
            dur    = _fmt_dur(r.get("duration_secs", 0))
            run_id = r.get("run_id", "")

            self._table.setItem(i, 0, _cell(ts_s,        _SUBTEXT))
            self._table.setItem(i, 1, _cell(r.get("system", "—")))
            self._table.setItem(i, 2, _cell(str(total),  _SUBTEXT, _C))
            self._table.setItem(i, 3, _cell(str(passed), _GREEN,   _C))
            self._table.setItem(i, 4, _cell(str(failed), _RED if failed else _GREEN, _C))
            self._table.setItem(i, 5, _cell(dur,         _SUBTEXT))
            self._table.setCellWidget(i, 6, self._build_action_buttons(run_id))

    def _on_row_selected(self, row: int) -> None:
        if row < 0 or row >= len(self._visible_runs):
            return
        r      = self._visible_runs[row]
        run_id = r.get("run_id", "")
        ts     = r.get("timestamp", "")
        ts_s   = ts[:19].replace("T", "  ") if len(ts) >= 16 else ts
        sys_   = r.get("system", "—")

        scripts = history_db.get_run_scripts(run_id)
        self._current_run_dir  = self._find_run_dir(run_id)
        self._current_scripts  = scripts
        count = len(scripts)
        title_text = (
            f"RUN DETAIL  —  {sys_}  —  {ts_s}"
            + (f"  •  {count} scripts" if count else "")
        )
        self._detail_title.setText(title_text)
        self._detail_title.setToolTip(f"{sys_}  |  {ts_s}  |  Run ID: {run_id}")
        self._hint_lbl.setVisible(bool(scripts) and self._current_run_dir is not None)

        _C = Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        if not scripts:
            self._detail_table.setRowCount(1)
            item = QTableWidgetItem("No per-script data recorded for this run")
            item.setForeground(QColor(_DIM))
            item.setTextAlignment(_C)
            self._detail_table.setItem(0, 0, item)
            self._detail_table.setSpan(0, 0, 1, 3)
            return

        self._detail_table.setRowCount(count)
        for i, s in enumerate(scripts):
            status = s.get("status", "")
            color  = _GREEN if status == "passed" else (_RED if status in ("failed", "error") else _AMBER)
            self._detail_table.setItem(i, 0, _cell(s.get("script_name", ""), _TEXT))
            self._detail_table.setItem(i, 1, _cell(status.upper(), color, _C))
            self._detail_table.setItem(i, 2, _cell(_fmt_dur(s.get("duration_secs", 0.0)), _SUBTEXT, _C))

    def _on_script_double_clicked(self, item: QTableWidgetItem) -> None:
        row = item.row()
        if row < 0 or not self._current_run_dir or row >= len(self._current_scripts):
            return
        script_name = self._current_scripts[row].get("script_name", "")
        log_path = self._current_run_dir / script_name / "output.log"
        dlg = LogViewerDialog(script_name, log_path, self)
        dlg.exec()

    def _on_detail_context_menu(self, pos) -> None:
        item = self._detail_table.itemAt(pos)
        if item is None:
            return
        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: #111c30; border: 1px solid {_BORDER};
                color: {_TEXT}; font-size: 11px;
            }}
            QMenu::item:selected {{ background: #132240; color: {_ACCENT}; }}
        """)
        copy_cell = menu.addAction("Copy Cell")
        copy_row  = menu.addAction("Copy Row")
        action = menu.exec(self._detail_table.viewport().mapToGlobal(pos))
        cb = QApplication.clipboard()
        if not cb:
            return
        if action == copy_cell:
            cb.setText(item.text())
        elif action == copy_row:
            row = item.row()
            parts = [
                self._detail_table.item(row, c).text()
                for c in range(self._detail_table.columnCount())
                if self._detail_table.item(row, c)
            ]
            cb.setText("\t".join(parts))

    def _build_action_buttons(self, run_id: str) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(w)
        hl.setContentsMargins(4, 2, 4, 2)
        hl.setSpacing(4)

        run_dir = self._find_run_dir(run_id)
        btn_s   = f"""
            QPushButton {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 3px;
                color: {_SUBTEXT}; font-size: 10px; padding: 1px 6px;
            }}
            QPushButton:hover {{ color: {_ACCENT}; border-color: {_ACCENT}; }}
            QPushButton:disabled {{ color: #2a3a50; border-color: #1a2233; }}
        """

        folder_btn = QPushButton("📁 Folder")
        folder_btn.setFixedHeight(22)
        folder_btn.setEnabled(run_dir is not None)
        folder_btn.setStyleSheet(btn_s)
        if run_dir:
            folder_btn.clicked.connect(
                lambda _, d=run_dir: QDesktopServices.openUrl(QUrl.fromLocalFile(str(d)))
            )

        report_path = (run_dir / "run_report.html") if run_dir else None
        report_btn  = QPushButton("📊 Report")
        report_btn.setFixedHeight(22)
        report_btn.setEnabled(bool(report_path and report_path.is_file()))
        report_btn.setStyleSheet(btn_s)
        if report_path and report_path.is_file():
            report_btn.clicked.connect(
                lambda _, p=report_path: QDesktopServices.openUrl(QUrl.fromLocalFile(str(p)))
            )

        hl.addWidget(folder_btn)
        hl.addWidget(report_btn)
        hl.addStretch()
        return w

    def _open_purge_dialog(self) -> None:
        dlg = PurgeDialog(RUNS_DIR, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        # Refresh the dir cache and run history so deleted runs disappear from
        # the table immediately and any remaining "Folder" buttons get disabled.
        self.refresh()
        deleted = dlg.deleted_count
        freed   = dlg.freed_bytes
        if deleted == 0:
            return
        msg = QMessageBox(self)
        msg.setWindowTitle("Purge Complete")
        msg.setIcon(QMessageBox.Icon.Information)
        skipped = getattr(dlg, "_skipped", 0)
        body = (
            f"Deleted <b>{deleted}</b> run folder(s) — "
            f"freed <b>{_fmt_bytes(freed)}</b>."
        )
        if skipped:
            body += (
                f"<br><br><span style='color:{_DIM}'>"
                f"{skipped} folder(s) were skipped (likely OneDrive-locked).</span>"
            )
        msg.setText(body)
        msg.setTextFormat(Qt.TextFormat.RichText)
        msg.exec()

    def _export_csv(self) -> None:
        runs = self._visible_runs
        if not runs:
            return
        try:
            tmp = tempfile.NamedTemporaryFile(
                mode="w", suffix=".csv", delete=False,
                prefix="orbit360_vault_", newline=""
            )
            writer = csv.writer(tmp)
            writer.writerow(
                ["Timestamp", "System", "Run ID", "Scripts", "Passed", "Failed", "Duration (s)"]
            )
            for r in runs:
                ts = r.get("timestamp", "")[:19].replace("T", " ")
                writer.writerow([
                    ts,
                    r.get("system",  ""),
                    r.get("run_id",  ""),
                    r.get("total",    0),
                    r.get("passed",   0),
                    r.get("failed",   0) + r.get("errored", 0),
                    round(r.get("duration_secs", 0.0), 1),
                ])
            tmp.close()
            QDesktopServices.openUrl(QUrl.fromLocalFile(tmp.name))
        except Exception as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(self, "Export Failed", f"Could not export CSV:\n{exc}")

    def _build_run_dir_cache(self) -> dict[str, Path]:
        cache: dict[str, Path] = {}
        if RUNS_DIR.is_dir():
            try:
                for d in RUNS_DIR.iterdir():
                    if d.is_dir():
                        cache[d.name] = d
            except OSError:
                pass
        return cache

    def _find_run_dir(self, run_id: str) -> Path | None:
        return self._run_dir_cache.get(run_id) if run_id else None
