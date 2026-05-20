"""
orbit360/ui/genesis_panel.py
Genesis screen — patient generator, living ledger, and Excel test data pools.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QPoint, QSettings, QThread, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QFrame, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMenu, QMessageBox, QProgressBar, QPushButton,
    QScrollArea, QSizePolicy, QSpinBox, QSplitter, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from orbit360.utils import excel_data_manager
from orbit360.utils.patient_generator import (
    GenerateResult,
    detect_system,
    generate_patients,
    inspect_template,
    list_templates,
)
from orbit360.utils.paths import PATIENT_TEMPLATES_DIR, TEST_DATA_DIR

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

_STATUS_COLORS: dict[str, tuple[str, str]] = {
    "available": ("#1a3a55", _ACCENT),
    "claimed":   ("#2a2a10", _AMBER),
    "pass":      ("#1a3a2a", _GREEN),
    "fail":      ("#3a1020", _RED),
    "skip":      ("#1a1a2e", _DIM),
}

_BTN = """
    QPushButton {{
        background: {bg}; border: 1px solid {br}; border-radius: 3px;
        color: {fg}; font-size: 10px; padding: 2px 8px;
    }}
    QPushButton:hover {{ background: {hv}; }}
    QPushButton:disabled {{ color: #2a3a50; border-color: #1a2233; }}
"""


def _pill(text: str, bg: str, fg: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(f"""
        QLabel {{
            background: {bg}; color: {fg}; border-radius: 3px;
            font-size: 9px; font-weight: bold; padding: 1px 6px;
        }}
    """)
    lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    lbl.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return lbl


def _titem(text: str, color: str = _TEXT,
           align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
           ) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setForeground(QColor(color))
    item.setTextAlignment(align)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


# ── Per-file pool card ────────────────────────────────────────────────────────

class _PoolCard(QFrame):
    """Card for one Excel test data file — stats, actions, and row detail table."""

    _MAX_EXCEL_COLS = 5  # max extra Excel columns shown in row table

    def __init__(self, excel_path: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._path      = excel_path
        self._rows_loaded = False  # lazy: only call get_all_rows on first expand
        self._row_data: list[dict] = []

        self.setStyleSheet(f"""
            QFrame {{
                background: {_BG_CARD};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 10, 14, 12)
        root.setSpacing(6)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        hdr.setSpacing(8)

        icon = QLabel("◈")
        icon.setStyleSheet(
            f"color: {_ACCENT}; font-size: 13px; background: transparent; border: none;"
        )
        hdr.addWidget(icon)

        name_col = QVBoxLayout()
        name_col.setSpacing(1)
        self._name_lbl = QLabel(excel_path.name)
        self._name_lbl.setStyleSheet(
            f"color: {_TEXT}; font-size: 12px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        self._name_lbl.setToolTip(str(excel_path))
        try:
            rel = excel_path.relative_to(TEST_DATA_DIR)
            path_str = str(rel)
        except ValueError:
            path_str = str(excel_path)
        path_lbl = QLabel(path_str)
        path_lbl.setStyleSheet(
            f"color: {_DIM}; font-size: 10px; background: transparent; border: none;"
        )
        name_col.addWidget(self._name_lbl)
        name_col.addWidget(path_lbl)
        hdr.addLayout(name_col, 1)

        self._status_pill = _pill("", _BORDER, _SUBTEXT)
        hdr.addWidget(self._status_pill)
        root.addLayout(hdr)

        # ── Stats row ─────────────────────────────────────────────────────
        stats_row = QHBoxLayout()
        stats_row.setSpacing(6)
        self._stat_vals: dict[str, QLabel] = {}
        for key, label, (bg, fg) in (
            ("available", "Available", _STATUS_COLORS["available"]),
            ("claimed",   "In Use",    _STATUS_COLORS["claimed"]),
            ("pass",      "Pass",      _STATUS_COLORS["pass"]),
            ("fail",      "Fail",      _STATUS_COLORS["fail"]),
            ("skip",      "Skip",      _STATUS_COLORS["skip"]),
            ("total",     "Total",     ("#1a1a2e", _SUBTEXT)),
        ):
            tile = QFrame()
            tile.setStyleSheet(f"""
                QFrame {{
                    background: {bg};
                    border: 1px solid #1a2233;
                    border-radius: 4px;
                }}
            """)
            tl = QVBoxLayout(tile)
            tl.setContentsMargins(8, 4, 8, 4)
            tl.setSpacing(1)
            val_lbl = QLabel("—")
            val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            val_lbl.setStyleSheet(
                f"color: {fg}; font-size: 14px; font-weight: bold; "
                f"background: transparent; border: none;"
            )
            cap_lbl = QLabel(label)
            cap_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            cap_lbl.setStyleSheet(
                f"color: {_DIM}; font-size: 9px; background: transparent; border: none;"
            )
            tl.addWidget(val_lbl)
            tl.addWidget(cap_lbl)
            stats_row.addWidget(tile, 1)
            self._stat_vals[key] = val_lbl
        root.addLayout(stats_row)

        # ── Action row ────────────────────────────────────────────────────
        act_row = QHBoxLayout()
        act_row.setSpacing(6)

        # Stale warning + recover button (hidden until stale > 0)
        self._stale_lbl = QLabel("")
        self._stale_lbl.setStyleSheet(
            f"color: {_AMBER}; font-size: 10px; background: transparent; border: none;"
        )
        self._stale_lbl.setVisible(False)
        act_row.addWidget(self._stale_lbl)

        self._recover_btn = QPushButton("🔓  Recover Stale")
        self._recover_btn.setFixedHeight(24)
        self._recover_btn.setStyleSheet(
            _BTN.format(bg="#2a2510", br="#5a4a10", fg=_AMBER, hv="#3a3010")
        )
        self._recover_btn.setToolTip("Release stale claimed rows back to Available")
        self._recover_btn.clicked.connect(self._on_recover_stale)
        self._recover_btn.setVisible(False)
        act_row.addWidget(self._recover_btn)

        act_row.addStretch()

        sync_btn = QPushButton("↻  Sync")
        sync_btn.setFixedHeight(24)
        sync_btn.setStyleSheet(
            _BTN.format(bg="#111c30", br=_BORDER, fg=_SUBTEXT, hv="#1a2a40")
        )
        sync_btn.setToolTip("Import any new rows added to the Excel file")
        sync_btn.clicked.connect(self._on_sync)
        act_row.addWidget(sync_btn)

        open_btn = QPushButton("📁  Open")
        open_btn.setFixedHeight(24)
        open_btn.setStyleSheet(
            _BTN.format(bg="#111c30", br=_BORDER, fg=_SUBTEXT, hv="#1a2a40")
        )
        open_btn.setToolTip("Open in system file manager")
        open_btn.clicked.connect(self._on_open_file)
        act_row.addWidget(open_btn)

        self._browse_btn = QPushButton("▶  Browse Rows")
        self._browse_btn.setFixedHeight(24)
        self._browse_btn.setCheckable(True)
        self._browse_btn.setToolTip("Toggle row-level preview for this pool")
        self._browse_btn.setStyleSheet(f"""
            QPushButton {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 3px;
                color: {_SUBTEXT}; font-size: 10px; padding: 2px 8px;
            }}
            QPushButton:checked {{
                background: #132240; border-color: {_ACCENT}; color: {_ACCENT};
            }}
            QPushButton:hover {{ color: {_ACCENT}; border-color: {_ACCENT}; }}
        """)
        self._browse_btn.clicked.connect(self._on_browse_toggle)
        act_row.addWidget(self._browse_btn)

        reset_btn = QPushButton("↺  Reset All")
        reset_btn.setFixedHeight(24)
        reset_btn.setStyleSheet(
            _BTN.format(bg="#1a1a2e", br=_BORDER, fg=_AMBER, hv="#2a2a1e")
        )
        reset_btn.setToolTip("Reset all rows back to Available")
        reset_btn.clicked.connect(self._on_reset)
        act_row.addWidget(reset_btn)

        root.addLayout(act_row)

        # ── Row detail table (collapsed by default) ───────────────────────
        self._row_section = QWidget()
        self._row_section.setStyleSheet("background: transparent;")
        rs_vl = QVBoxLayout(self._row_section)
        rs_vl.setContentsMargins(0, 4, 0, 0)
        rs_vl.setSpacing(4)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {_BORDER}; max-height: 1px; border: none;")
        rs_vl.addWidget(sep)

        self._row_table = QTableWidget(0, 1)
        self._row_table.setMaximumHeight(260)
        self._row_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._row_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._row_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._row_table.setAlternatingRowColors(True)
        self._row_table.verticalHeader().setVisible(False)
        self._row_table.verticalHeader().setDefaultSectionSize(24)
        self._row_table.horizontalHeader().setHighlightSections(False)
        self._row_table.setShowGrid(False)
        self._row_table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._row_table.customContextMenuRequested.connect(self._show_row_context_menu)
        self._row_table.setStyleSheet(f"""
            QTableWidget {{
                background: transparent; color: {_TEXT}; font-size: 11px; border: none;
            }}
            QTableWidget::item:selected {{ background: #132240; color: {_ACCENT}; }}
            QTableWidget::item:alternate {{ background: #0a1525; }}
            QHeaderView::section {{
                background: #080d18; color: {_DIM}; font-size: 10px; font-weight: bold;
                border: none; border-bottom: 1px solid {_BORDER}; padding: 3px 6px;
            }}
        """)
        rs_vl.addWidget(self._row_table)

        self._row_section.setVisible(False)
        root.addWidget(self._row_section)

        self.refresh()

    # ── Public ───────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        try:
            from orbit360.utils.excel_data_manager import get_summary
            s = get_summary(self._path)
        except Exception:
            s = {
                "available": 0, "claimed": 0,
                "pass": 0, "fail": 0, "skip": 0,
                "total": 0, "stale": 0,
            }

        for key, lbl in self._stat_vals.items():
            lbl.setText(str(s.get(key, 0)))

        avail = s.get("available", 0)
        total = s.get("total",     0)
        stale = s.get("stale",     0)

        if total == 0:
            self._status_pill.setText("Empty")
            self._status_pill.setStyleSheet(
                f"QLabel {{ background: #1a1a2e; color: {_DIM}; border-radius: 3px; "
                f"font-size: 9px; font-weight: bold; padding: 1px 6px; }}"
            )
        elif avail == 0:
            self._status_pill.setText("Exhausted")
            self._status_pill.setStyleSheet(
                f"QLabel {{ background: #3a1020; color: {_RED}; border-radius: 3px; "
                f"font-size: 9px; font-weight: bold; padding: 1px 6px; }}"
            )
        else:
            self._status_pill.setText("Ready")
            self._status_pill.setStyleSheet(
                f"QLabel {{ background: #1a3a2a; color: {_GREEN}; border-radius: 3px; "
                f"font-size: 9px; font-weight: bold; padding: 1px 6px; }}"
            )

        if stale:
            self._stale_lbl.setText(f"⚠  {stale} stale")
            self._stale_lbl.setVisible(True)
            self._recover_btn.setVisible(True)
        else:
            self._stale_lbl.setVisible(False)
            self._recover_btn.setVisible(False)

        # If row table is open, reload it too
        if self._row_section.isVisible():
            self._load_row_table()

    def get_summary_counts(self) -> dict:
        """Return summary counts for the cross-pool aggregate bar."""
        try:
            from orbit360.utils.excel_data_manager import get_summary
            return get_summary(self._path)
        except Exception:
            return {"available": 0, "claimed": 0, "total": 0, "stale": 0}

    # ── Private actions ───────────────────────────────────────────────────────

    def _on_reset(self) -> None:
        box = QMessageBox(self)
        box.setWindowTitle("Reset Pool")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(f"Reset all rows in\n{self._path.name}\nback to Available?")
        box.setInformativeText("This clears In Use, PASS, FAIL, and SKIP statuses.")
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        if box.exec() == QMessageBox.StandardButton.Yes:
            from orbit360.utils.excel_data_manager import reset_rows
            reset_rows(self._path)
            self._rows_loaded = False
            self.refresh()

    def _on_recover_stale(self) -> None:
        from orbit360.utils.excel_data_manager import recover_stale_claims
        n = recover_stale_claims(self._path)
        self._rows_loaded = False
        self.refresh()
        if n:
            QMessageBox.information(
                self, "Stale Claims Recovered",
                f"{n} row(s) released back to Available."
            )

    def _on_sync(self) -> None:
        from orbit360.utils.excel_data_manager import sync_from_excel
        total = sync_from_excel(self._path)
        self._rows_loaded = False
        self.refresh()
        QMessageBox.information(
            self, "Sync Complete",
            f"{total} row(s) now tracked for {self._path.name}."
        )

    def _on_open_file(self) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._path)))

    def _on_browse_toggle(self, checked: bool) -> None:
        self._browse_btn.setText("▼  Browse Rows" if checked else "▶  Browse Rows")
        self._row_section.setVisible(checked)
        if checked and not self._rows_loaded:
            self._load_row_table()

    # ── Row table ─────────────────────────────────────────────────────────────

    def _load_row_table(self) -> None:
        try:
            from orbit360.utils.excel_data_manager import get_all_rows
            self._row_data = get_all_rows(self._path)
        except Exception:
            self._row_data = []
        self._rows_loaded = True
        self._rebuild_row_table()

    def _rebuild_row_table(self) -> None:
        rows = self._row_data
        if not rows:
            self._row_table.setColumnCount(1)
            self._row_table.setHorizontalHeaderLabels(["—"])
            self._row_table.setRowCount(1)
            self._row_table.setItem(
                0, 0, _titem("No rows tracked yet — click Sync to import from Excel",
                              _DIM, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            )
            return

        # Fixed columns + first few Excel data columns
        excel_keys = [
            k for k in rows[0].keys()
            if not k.startswith("_")
        ][:self._MAX_EXCEL_COLS]

        fixed_cols = ["Row", "Status", "Run ID", "Completed", "Uses"]
        all_cols   = fixed_cols + excel_keys
        _C         = Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter

        self._row_table.setColumnCount(len(all_cols))
        self._row_table.setHorizontalHeaderLabels(all_cols)
        self._row_table.setRowCount(len(rows))

        hv = self._row_table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)        # Row #
        hv.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)        # Status
        hv.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)      # Run ID
        hv.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Completed
        hv.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)        # Uses
        for i in range(5, len(all_cols)):
            hv.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self._row_table.setColumnWidth(0, 44)
        self._row_table.setColumnWidth(1, 80)
        self._row_table.setColumnWidth(4, 44)

        for i, r in enumerate(rows):
            status    = r.get("_status", "available")
            _, fg     = _STATUS_COLORS.get(status, ("#1a1a2e", _SUBTEXT))
            run_id    = r.get("_run_id", "") or "—"
            completed = (r.get("_completed_at", "") or "")[:16].replace("T", "  ")
            uses      = str(r.get("_history_count", 0))

            self._row_table.setItem(i, 0, _titem(str(r.get("_row_index", i)), _DIM, _C))
            self._row_table.setItem(i, 1, _titem(status.upper(), fg, _C))
            self._row_table.setItem(i, 2, _titem(run_id, _SUBTEXT))
            self._row_table.setItem(i, 3, _titem(completed or "—", _DIM))
            self._row_table.setItem(i, 4, _titem(uses, _SUBTEXT, _C))
            for j, key in enumerate(excel_keys):
                val = r.get(key)
                self._row_table.setItem(
                    i, 5 + j,
                    _titem(str(val) if val is not None else "—", _TEXT)
                )

    def _show_row_context_menu(self, pos: QPoint) -> None:
        idx = self._row_table.indexAt(pos).row()
        if idx < 0 or idx >= len(self._row_data):
            return
        row     = self._row_data[idx]
        row_idx = row.get("_row_index", idx)

        menu = QMenu(self)
        menu.setStyleSheet(f"""
            QMenu {{
                background: #111c30; border: 1px solid {_BORDER};
                color: {_TEXT}; font-size: 11px;
            }}
            QMenu::item:selected {{ background: #132240; color: {_ACCENT}; }}
        """)
        menu.addSection(f"Row {row_idx}  —  {row.get('_status','').upper()}")
        for status, label in (
            ("available", "Set Available"),
            ("pass",      "Set Pass"),
            ("fail",      "Set Fail"),
            ("skip",      "Set Skip"),
        ):
            act = menu.addAction(label)
            act.triggered.connect(
                lambda _, s=status, ri=row_idx: self._set_row_status(ri, s)
            )
        menu.exec(self._row_table.viewport().mapToGlobal(pos))

    def _set_row_status(self, row_index: int, status: str) -> None:
        try:
            from orbit360.utils.excel_data_manager import set_row_status
            set_row_status(self._path, row_index, status)
        except Exception:
            pass
        self._rows_loaded = False
        self.refresh()


# ── Patient generator (left side of the Genesis split) ──────────────────────

class _GenerateWorker(QThread):
    """Run generate_patients() off the UI thread.

    Emits progress(sheet_name, done, total) per ~25-row chunk and per sheet
    completion, finished(GenerateResult) on success, failed(message) on error.
    """

    progress = Signal(str, int, int)
    finished = Signal(object)
    failed   = Signal(str)

    def __init__(self, template_path: Path, release: str,
                 count_per_sheet: int, parent=None) -> None:
        super().__init__(parent)
        self._template = template_path
        self._release  = release
        self._count    = count_per_sheet

    def run(self) -> None:
        try:
            result = generate_patients(
                self._template, self._release, self._count,
                progress=lambda s, d, t: self.progress.emit(s, d, t),
            )
            self.finished.emit(result)
        except Exception as exc:
            self.failed.emit(str(exc))


class _GeneratorPane(QWidget):
    """Left pane of Genesis: pick template, set release + count, generate."""

    batchGenerated = Signal(object)   # GenerateResult

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"QWidget {{ background: {_BG}; }}")
        self._worker: _GenerateWorker | None = None
        self._last_result: GenerateResult | None = None

        outer = QVBoxLayout(self)
        outer.setContentsMargins(20, 8, 16, 16)
        outer.setSpacing(10)

        title = QLabel("🧬  PATIENT GENERATOR")
        title.setStyleSheet(
            f"color: {_ACCENT}; font-size: 14px; font-weight: bold; "
            f"letter-spacing: 1px; background: transparent;"
        )
        outer.addWidget(title)

        sub = QLabel(
            "Generate test-patient batches from a template. Output lands in "
            "orbit_data/test_data/generated/ and shows up in the ledger "
            "automatically."
        )
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color: {_DIM}; font-size: 11px; background: transparent;")
        outer.addWidget(sub)

        # ── Form card ─────────────────────────────────────────────────────
        form = QFrame()
        form.setStyleSheet(f"""
            QFrame {{
                background: {_BG_CARD}; border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
            QLabel {{ background: transparent; border: none; }}
        """)
        fl = QVBoxLayout(form)
        fl.setContentsMargins(14, 12, 14, 12)
        fl.setSpacing(8)

        fl.addWidget(self._field_label("Template"))
        self._template_combo = QComboBox()
        self._template_combo.setStyleSheet(self._input_style())
        self._template_combo.setFixedHeight(28)
        self._template_combo.currentIndexChanged.connect(self._on_template_changed)
        fl.addWidget(self._template_combo)

        self._template_meta = QLabel("—")
        self._template_meta.setStyleSheet(
            f"color: {_DIM}; font-size: 10px; background: transparent;"
        )
        fl.addWidget(self._template_meta)

        fl.addSpacing(4)
        fl.addWidget(self._field_label("Release tag"))
        self._release_edit = QLineEdit()
        self._release_edit.setPlaceholderText("e.g. APRGR1.26")
        self._release_edit.setFixedHeight(28)
        self._release_edit.setStyleSheet(self._input_style())
        fl.addWidget(self._release_edit)

        fl.addSpacing(4)
        fl.addWidget(self._field_label("Patients per sheet"))
        self._count_spin = QSpinBox()
        self._count_spin.setRange(1, 9999)
        self._count_spin.setValue(500)
        self._count_spin.setFixedHeight(28)
        self._count_spin.setStyleSheet(self._spin_style())
        fl.addWidget(self._count_spin)

        outer.addWidget(form)

        # ── Generate button + progress ────────────────────────────────────
        self._generate_btn = QPushButton("⚡  Generate")
        self._generate_btn.setFixedHeight(34)
        self._generate_btn.setStyleSheet(f"""
            QPushButton {{
                background: #132240; border: 1px solid {_ACCENT};
                border-radius: 6px; color: {_ACCENT};
                font-size: 12px; font-weight: bold; letter-spacing: 1px;
            }}
            QPushButton:hover {{ background: #1a3055; }}
            QPushButton:disabled {{
                background: #0a1525; border-color: #1a2a40; color: #2a3a50;
            }}
        """)
        self._generate_btn.clicked.connect(self._on_generate)
        outer.addWidget(self._generate_btn)

        self._progress_bar = QProgressBar()
        self._progress_bar.setFixedHeight(8)
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setStyleSheet(f"""
            QProgressBar {{
                background: #0a1525; border: 1px solid {_BORDER};
                border-radius: 4px;
            }}
            QProgressBar::chunk {{
                background: {_ACCENT}; border-radius: 3px;
            }}
        """)
        self._progress_bar.setVisible(False)
        outer.addWidget(self._progress_bar)

        self._status_lbl = QLabel("")
        self._status_lbl.setWordWrap(True)
        self._status_lbl.setStyleSheet(
            f"color: {_DIM}; font-size: 11px; background: transparent;"
        )
        outer.addWidget(self._status_lbl)

        # ── Last batch footer ─────────────────────────────────────────────
        self._open_last_btn = QPushButton("📁  Open last batch folder")
        self._open_last_btn.setFixedHeight(26)
        self._open_last_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; border: 1px solid {_BORDER};
                border-radius: 4px; color: {_SUBTEXT}; font-size: 11px;
                padding: 2px 10px;
            }}
            QPushButton:hover {{ color: {_ACCENT}; border-color: {_ACCENT}; }}
        """)
        self._open_last_btn.setVisible(False)
        self._open_last_btn.clicked.connect(self._on_open_last)
        outer.addWidget(self._open_last_btn)

        outer.addStretch()
        self.refresh_templates()

    # ── Public ──────────────────────────────────────────────────────────────
    def refresh_templates(self) -> None:
        PATIENT_TEMPLATES_DIR.mkdir(parents=True, exist_ok=True)
        templates = list_templates()
        prev = self._template_combo.currentData() if self._template_combo.count() else None
        self._template_combo.blockSignals(True)
        self._template_combo.clear()
        if not templates:
            self._template_combo.addItem("No templates — drop one in orbit_data/patient_templates/", None)
            self._template_combo.setEnabled(False)
            self._generate_btn.setEnabled(False)
            self._template_meta.setText("")
        else:
            self._template_combo.setEnabled(True)
            for path in templates:
                self._template_combo.addItem(path.name, path)
            if prev:
                idx = self._template_combo.findData(prev)
                if idx >= 0:
                    self._template_combo.setCurrentIndex(idx)
            self._generate_btn.setEnabled(True)
        self._template_combo.blockSignals(False)
        self._on_template_changed()

    # ── Internals ───────────────────────────────────────────────────────────
    @staticmethod
    def _field_label(text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {_DIM}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 1px; background: transparent;"
        )
        return lbl

    @staticmethod
    def _input_style() -> str:
        return f"""
            QComboBox, QLineEdit {{
                background: #0a1525; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_TEXT}; font-size: 12px; padding: 2px 8px;
            }}
            QComboBox:hover, QLineEdit:hover {{ border-color: {_ACCENT}; }}
            QComboBox:focus, QLineEdit:focus {{ border-color: {_ACCENT}; }}
            QComboBox::drop-down {{ border: none; width: 18px; }}
            QComboBox QAbstractItemView {{
                background: #0d1520; border: 1px solid {_BORDER};
                color: {_TEXT}; selection-background-color: #132240;
            }}
        """

    @staticmethod
    def _spin_style() -> str:
        return f"""
            QSpinBox {{
                background: #0a1525; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_TEXT}; font-size: 12px; padding: 2px 8px;
            }}
            QSpinBox:hover {{ border-color: {_ACCENT}; }}
            QSpinBox::up-button, QSpinBox::down-button {{ width: 16px; }}
        """

    def _on_template_changed(self, *_args) -> None:
        path = self._template_combo.currentData()
        if not path or not Path(path).is_file():
            self._template_meta.setText("")
            return
        try:
            summary = inspect_template(Path(path))
            self._template_meta.setText(
                f"{summary.system}  ·  {len(summary.sheet_names)} sheets  ·  "
                f"{summary.column_count} columns"
            )
        except Exception as exc:
            self._template_meta.setText(f"Error reading template: {exc}")

    def _on_generate(self) -> None:
        if self._worker is not None:
            return
        path = self._template_combo.currentData()
        if not path or not Path(path).is_file():
            QMessageBox.warning(self, "Generate", "Pick a template first.")
            return
        release = self._release_edit.text().strip()
        if not release:
            QMessageBox.warning(self, "Generate", "Enter a release tag.")
            self._release_edit.setFocus()
            return
        count = self._count_spin.value()

        self._set_running(True)
        self._status_lbl.setText("Starting…")
        self._progress_bar.setVisible(True)
        self._progress_bar.setRange(0, 0)   # indeterminate until first sheet ticks

        self._worker = _GenerateWorker(Path(path), release, count, self)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

    def _set_running(self, running: bool) -> None:
        self._generate_btn.setEnabled(not running)
        self._template_combo.setEnabled(not running)
        self._release_edit.setEnabled(not running)
        self._count_spin.setEnabled(not running)

    def _on_progress(self, sheet: str, done: int, total: int) -> None:
        if total > 0:
            self._progress_bar.setRange(0, total)
            self._progress_bar.setValue(done)
        self._status_lbl.setText(f"Sheet {sheet} — {done}/{total}")

    def _on_done(self, result) -> None:
        self._last_result = result
        self._set_running(False)
        self._progress_bar.setVisible(False)
        self._status_lbl.setText(
            f"✓  {result.total_patients:,} patients across "
            f"{result.sheet_count} sheet(s) in {result.duration_secs:.1f}s"
        )
        self._open_last_btn.setVisible(True)
        self._cleanup_worker()
        self.batchGenerated.emit(result)

    def _on_failed(self, message: str) -> None:
        self._set_running(False)
        self._progress_bar.setVisible(False)
        self._status_lbl.setText(f"⚠  {message}")
        QMessageBox.critical(self, "Generate failed", message)
        self._cleanup_worker()

    def _cleanup_worker(self) -> None:
        if self._worker is not None:
            self._worker.deleteLater()
            self._worker = None

    def _on_open_last(self) -> None:
        if self._last_result and self._last_result.output_dir.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self._last_result.output_dir)))


# ── Living ledger (right side of the Genesis split) ─────────────────────────

_LEDGER_PATIENT_KEYS = (
    "PatientName", "patientname", "Patient Name",
    "MRN", "mrn", "PatientMRN",
    "AccountNumber", "accountnumber", "Account",
)


class _LedgerHistoryDialog(QDialog):
    """Modal: read-only run history for one patient row."""

    def __init__(self, pool_path: Path, row_index: int, patient: str,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"History — {patient or pool_path.name + ' #' + str(row_index + 1)}")
        self.resize(640, 380)
        self.setStyleSheet(f"QDialog {{ background: {_BG}; color: {_TEXT}; }}")

        vl = QVBoxLayout(self)
        vl.setContentsMargins(14, 12, 14, 12)
        vl.setSpacing(8)

        hdr = QLabel(
            f"<b style='color:{_ACCENT}'>{patient or '(no patient name)'}</b>"
            f"  <span style='color:{_DIM}; font-size:10px'>"
            f"{pool_path.name} · row {row_index + 1}</span>"
        )
        hdr.setTextFormat(Qt.TextFormat.RichText)
        hdr.setWordWrap(True)
        vl.addWidget(hdr)

        try:
            history = excel_data_manager.get_row_history(pool_path, row_index)
        except Exception as exc:
            history = []
            err = QLabel(f"Could not load history: {exc}")
            err.setStyleSheet(f"color: {_RED};")
            vl.addWidget(err)

        table = QTableWidget(len(history), 4)
        table.setHorizontalHeaderLabels(["When", "Run ID", "Status", "Notes"])
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setStyleSheet(f"""
            QTableWidget {{
                background: {_BG_CARD}; color: {_TEXT}; border: 1px solid {_BORDER};
                gridline-color: #1a2a40; font-size: 11px;
            }}
            QHeaderView::section {{
                background: #0a1525; color: {_DIM}; border: none;
                border-bottom: 1px solid {_BORDER}; padding: 4px 8px;
                font-size: 10px; font-weight: bold;
            }}
        """)

        for i, h in enumerate(history):
            ts = (h.get("timestamp") or "")[:19].replace("T", " ")
            status = (h.get("status") or "").upper()
            colour = _GREEN if status == "PASS" else _RED if status in ("FAIL", "ERROR") else _AMBER
            table.setItem(i, 0, _titem(ts, _SUBTEXT))
            table.setItem(i, 1, _titem(h.get("run_id") or "—", _SUBTEXT))
            table.setItem(i, 2, _titem(status, colour, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter))
            table.setItem(i, 3, _titem(h.get("notes") or ""))

        if not history:
            table.setRowCount(1)
            empty = _titem("No runs recorded for this row yet.", _DIM,
                           Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(0, 0, empty)
            table.setSpan(0, 0, 1, 4)
        vl.addWidget(table, 1)

        close = QPushButton("Close")
        close.setFixedHeight(28)
        close.setStyleSheet(f"""
            QPushButton {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_SUBTEXT}; font-size: 11px; padding: 4px 18px;
            }}
            QPushButton:hover {{ color: {_ACCENT}; border-color: {_ACCENT}; }}
        """)
        close.clicked.connect(self.accept)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(close)
        vl.addLayout(btn_row)


class _LedgerPane(QWidget):
    """Right pane: flat read-only list of every patient row across pools."""

    _COLS = ["Pool", "Row", "Patient", "Status", "Last Run", "Runs"]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"QWidget {{ background: {_BG}; }}")
        self._all_rows: list[dict] = []

        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 20, 16)
        outer.setSpacing(8)

        # ── Title row ────────────────────────────────────────────────────
        title_row = QHBoxLayout()
        title = QLabel("📖  LIVING LEDGER")
        title.setStyleSheet(
            f"color: {_ACCENT}; font-size: 14px; font-weight: bold; "
            f"letter-spacing: 1px; background: transparent;"
        )
        title_row.addWidget(title)
        title_row.addSpacing(12)
        title_row.addStretch()

        self._refresh_btn = QPushButton("↺  Refresh")
        self._refresh_btn.setFixedHeight(24)
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_SUBTEXT}; font-size: 11px; padding: 2px 10px;
            }}
            QPushButton:hover {{ color: {_ACCENT}; border-color: {_ACCENT}; }}
        """)
        self._refresh_btn.clicked.connect(self.refresh)
        title_row.addWidget(self._refresh_btn)
        outer.addLayout(title_row)

        # ── Filter row ───────────────────────────────────────────────────
        filt_row = QHBoxLayout()
        filt_row.setSpacing(6)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Filter by pool, patient, status…")
        self._search.setFixedHeight(26)
        self._search.setStyleSheet(f"""
            QLineEdit {{
                background: #0a1525; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_TEXT}; font-size: 11px; padding: 2px 8px;
            }}
            QLineEdit:focus {{ border-color: {_ACCENT}; }}
        """)
        self._search.textChanged.connect(self._apply_filter)
        filt_row.addWidget(self._search, 1)

        self._status_combo = QComboBox()
        for label in ("All statuses", "available", "claimed", "pass", "fail", "skip"):
            self._status_combo.addItem(label)
        self._status_combo.setFixedHeight(26)
        self._status_combo.setStyleSheet(f"""
            QComboBox {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_SUBTEXT}; font-size: 11px; padding: 2px 8px;
            }}
            QComboBox:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
            QComboBox::drop-down {{ border: none; }}
            QComboBox QAbstractItemView {{
                background: #111c30; color: {_TEXT}; border: 1px solid {_BORDER};
            }}
        """)
        self._status_combo.currentIndexChanged.connect(self._apply_filter)
        filt_row.addWidget(self._status_combo)
        outer.addLayout(filt_row)

        # ── Summary line ─────────────────────────────────────────────────
        self._summary_lbl = QLabel("—")
        self._summary_lbl.setStyleSheet(
            f"color: {_DIM}; font-size: 11px; background: transparent;"
        )
        outer.addWidget(self._summary_lbl)

        # ── Table ────────────────────────────────────────────────────────
        self._table = QTableWidget(0, len(self._COLS))
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(26)
        self._table.horizontalHeader().setHighlightSections(False)
        self._table.setShowGrid(False)
        self._table.setStyleSheet(f"""
            QTableWidget {{
                background: {_BG_CARD}; color: {_TEXT};
                border: 1px solid {_BORDER}; border-radius: 6px;
                gridline-color: #1a2a40; font-size: 11px;
                alternate-background-color: #0a1525;
            }}
            QTableWidget::item:selected {{ background: #132240; color: {_ACCENT}; }}
            QHeaderView::section {{
                background: #0a0e1a; color: {_DIM}; border: none;
                border-bottom: 1px solid {_BORDER}; padding: 5px 8px;
                font-size: 10px; font-weight: bold; letter-spacing: 1px;
            }}
            QHeaderView::section:hover {{ color: {_ACCENT}; }}
        """)
        hv = self._table.horizontalHeader()
        hv.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)        # Pool
        hv.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)          # Row #
        hv.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)        # Patient
        hv.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)          # Status
        hv.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)          # Last run
        hv.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)          # Runs
        self._table.setColumnWidth(1, 60)
        self._table.setColumnWidth(3, 90)
        self._table.setColumnWidth(4, 150)
        self._table.setColumnWidth(5, 60)
        self._table.itemDoubleClicked.connect(self._on_row_double_clicked)
        outer.addWidget(self._table, 1)

        self.refresh()

    # ── Public ─────────────────────────────────────────────────────────────
    def refresh(self) -> None:
        rows: list[dict] = []
        if TEST_DATA_DIR.is_dir():
            for path in sorted(TEST_DATA_DIR.rglob("*.xlsx")):
                try:
                    pool_rows = excel_data_manager.get_all_rows(path)
                except Exception:
                    continue
                for r in pool_rows:
                    r["_pool_path"] = path
                    r["_pool_name"] = path.name
                    rows.append(r)
        self._all_rows = rows
        self._apply_filter()

    # ── Internals ──────────────────────────────────────────────────────────
    def _patient_label(self, row: dict) -> str:
        for key in _LEDGER_PATIENT_KEYS:
            value = row.get(key)
            if value not in (None, ""):
                return str(value)
        # Fallback: first non-underscore key with a non-empty value
        for k, v in row.items():
            if not k.startswith("_") and v not in (None, ""):
                return str(v)
        return ""

    def _apply_filter(self) -> None:
        needle = self._search.text().strip().lower()
        status_filter = self._status_combo.currentText()
        rows = self._all_rows
        if status_filter and status_filter != "All statuses":
            rows = [r for r in rows if (r.get("_status") or "").lower() == status_filter]
        if needle:
            def _match(r: dict) -> bool:
                hay = " ".join(str(v) for v in (
                    r.get("_pool_name", ""),
                    self._patient_label(r),
                    r.get("_status", ""),
                    r.get("_run_id") or "",
                )).lower()
                return needle in hay
            rows = [r for r in rows if _match(r)]
        self._populate_table(rows)
        self._update_summary(rows)

    def _populate_table(self, rows: list[dict]) -> None:
        _C = Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignVCenter
        self._table.setRowCount(0)
        if not rows:
            self._table.setRowCount(1)
            empty = _titem(
                "No patients yet — use the generator on the left to create your first batch."
                if not self._all_rows
                else "No patient rows match the current filter.",
                _DIM, _C,
            )
            self._table.setItem(0, 0, empty)
            self._table.setSpan(0, 0, 1, len(self._COLS))
            return

        self._table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            status = (r.get("_status") or "").lower()
            bg, fg = _STATUS_COLORS.get(status, (_BG_CARD, _DIM))
            last_run = (r.get("_completed_at") or r.get("_claimed_at") or "")[:19].replace("T", " ")

            self._table.setItem(i, 0, _titem(r.get("_pool_name", ""), _SUBTEXT))
            self._table.setItem(i, 1, _titem(str(r.get("_row_index", -1) + 1), _SUBTEXT, _C))
            self._table.setItem(i, 2, _titem(self._patient_label(r), _TEXT))
            self._table.setItem(i, 3, _titem(status.upper() or "—", fg, _C))
            self._table.setItem(i, 4, _titem(last_run or "—", _SUBTEXT))
            self._table.setItem(i, 5, _titem(str(r.get("_history_count", 0)), _SUBTEXT, _C))

    def _update_summary(self, visible_rows: list[dict]) -> None:
        total      = len(self._all_rows)
        shown      = len(visible_rows)
        avail      = sum(1 for r in self._all_rows if (r.get("_status") or "") == "available")
        in_use     = sum(1 for r in self._all_rows if (r.get("_status") or "") == "claimed")
        try:
            stale = excel_data_manager.get_global_stale_count()
        except Exception:
            stale = 0

        if total == 0:
            self._summary_lbl.setText("No pools yet — generate a batch to get started.")
            return
        filtered = "  (filtered)" if shown < total else ""
        self._summary_lbl.setText(
            f"{shown:,} of {total:,} patient(s){filtered}  ·  "
            f"{avail:,} available  ·  {in_use:,} in use  ·  {stale:,} stale"
        )

    def _on_row_double_clicked(self, item: QTableWidgetItem) -> None:
        row = item.row()
        if 0 <= row < self._table.rowCount() and self._all_rows:
            # Reconstruct the visible-row mapping by reapplying the same filter
            needle = self._search.text().strip().lower()
            status_filter = self._status_combo.currentText()
            rows = self._all_rows
            if status_filter and status_filter != "All statuses":
                rows = [r for r in rows if (r.get("_status") or "").lower() == status_filter]
            if needle:
                rows = [r for r in rows if needle in " ".join(str(v) for v in (
                    r.get("_pool_name", ""), self._patient_label(r),
                    r.get("_status", ""), r.get("_run_id") or "",
                )).lower()]
            if 0 <= row < len(rows):
                target = rows[row]
                dlg = _LedgerHistoryDialog(
                    target["_pool_path"], target["_row_index"],
                    self._patient_label(target), self,
                )
                dlg.exec()


# ── Main widget ───────────────────────────────────────────────────────────────

class GenesisPanel(QWidget):
    """Genesis screen — test data pool browser with row-level drill-down."""

    launch_requested = Signal()   # user clicked "Go to Launcher"

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"QWidget {{ background: {_BG}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        # ── Fixed header ──────────────────────────────────────────────────
        hdr_bar = QWidget()
        hdr_bar.setStyleSheet(f"background: {_BG};")
        hdr_layout = QHBoxLayout(hdr_bar)
        hdr_layout.setContentsMargins(20, 16, 20, 8)
        hdr_layout.setSpacing(12)

        title = QLabel("◈  GENESIS")
        title.setStyleSheet(
            f"color: {_ACCENT}; font-size: 18px; font-weight: bold; letter-spacing: 2px;"
        )
        sub = QLabel("Test data pool management")
        sub.setStyleSheet(f"color: {_DIM}; font-size: 11px;")
        hdr_layout.addWidget(title)
        hdr_layout.addSpacing(12)
        hdr_layout.addWidget(sub)
        hdr_layout.addStretch()

        self._refresh_btn = QPushButton("↺  Refresh")
        self._refresh_btn.setFixedHeight(26)
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_SUBTEXT}; font-size: 11px; padding: 2px 12px;
            }}
            QPushButton:hover {{ color: {_ACCENT}; border-color: {_ACCENT}; }}
        """)
        self._refresh_btn.clicked.connect(self.refresh)
        hdr_layout.addWidget(self._refresh_btn)

        launch_btn = QPushButton("▶  Go to Launcher")
        launch_btn.setFixedHeight(26)
        launch_btn.setStyleSheet(f"""
            QPushButton {{
                background: #111c30; border: 1px solid #1e3a5f; border-radius: 4px;
                color: {_ACCENT}; font-size: 11px; padding: 2px 12px;
            }}
            QPushButton:hover {{ background: #132240; border-color: {_ACCENT}; }}
        """)
        launch_btn.clicked.connect(self.launch_requested)
        hdr_layout.addWidget(launch_btn)

        outer.addWidget(hdr_bar)

        # ── Cross-pool summary bar ────────────────────────────────────────
        summary_frame = QFrame()
        summary_frame.setStyleSheet(f"""
            QFrame {{
                background: {_BG_CARD};
                border: 1px solid {_BORDER};
                border-radius: 6px;
                margin: 0px 20px 4px 20px;
            }}
        """)
        sf_hl = QHBoxLayout(summary_frame)
        sf_hl.setContentsMargins(14, 8, 14, 8)
        sf_hl.setSpacing(6)

        pool_lbl = QLabel("POOL SUMMARY")
        pool_lbl.setStyleSheet(
            f"color: {_ACCENT}; font-size: 10px; font-weight: bold; letter-spacing: 1px; "
            f"background: transparent; border: none;"
        )
        sf_hl.addWidget(pool_lbl)
        sf_hl.addSpacing(8)

        self._summary_lbl = QLabel("—")
        self._summary_lbl.setStyleSheet(
            f"color: {_SUBTEXT}; font-size: 11px; background: transparent; border: none;"
        )
        sf_hl.addWidget(self._summary_lbl, 1)
        outer.addWidget(summary_frame)

        # ── Top split: generator (left) + ledger (right) ──────────────────
        self._generator_pane = _GeneratorPane()
        self._ledger_pane    = _LedgerPane()
        self._generator_pane.batchGenerated.connect(self._on_batch_generated)

        top_split = QSplitter(Qt.Orientation.Horizontal)
        top_split.setStyleSheet(f"""
            QSplitter::handle {{ background: {_BORDER}; width: 3px; }}
            QSplitter::handle:hover {{ background: {_ACCENT}; }}
        """)
        top_split.addWidget(self._generator_pane)
        top_split.addWidget(self._ledger_pane)
        top_split.setStretchFactor(0, 0)
        top_split.setStretchFactor(1, 1)
        top_split.setSizes([360, 900])
        top_split.setCollapsible(0, False)
        top_split.setCollapsible(1, False)

        # ── Scrollable card list (kept below the split, collapsible) ─────
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._scroll.setStyleSheet(f"""
            QScrollArea {{ background: {_BG}; border: none; }}
            QScrollBar:vertical {{
                background: {_BG}; width: 8px; border: none; border-radius: 4px;
            }}
            QScrollBar::handle:vertical {{
                background: #2a3a50; border-radius: 4px; min-height: 20px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        """)

        self._cards_widget = QWidget()
        self._cards_widget.setStyleSheet(f"background: {_BG};")
        self._cards_layout = QVBoxLayout(self._cards_widget)
        self._cards_layout.setContentsMargins(20, 4, 20, 20)
        self._cards_layout.setSpacing(10)
        self._cards_layout.addStretch()

        self._scroll.setWidget(self._cards_widget)
        self._cards: list[_PoolCard] = []

        # Vertical splitter so the user can hide the per-pool cards if they
        # want a full-height ledger.
        body_split = QSplitter(Qt.Orientation.Vertical)
        body_split.setStyleSheet(f"""
            QSplitter::handle {{ background: {_BORDER}; height: 3px; }}
            QSplitter::handle:hover {{ background: {_ACCENT}; }}
        """)
        body_split.addWidget(top_split)
        body_split.addWidget(self._scroll)
        body_split.setStretchFactor(0, 1)
        body_split.setStretchFactor(1, 0)
        body_split.setSizes([520, 200])
        body_split.setCollapsible(0, False)
        body_split.setCollapsible(1, True)
        outer.addWidget(body_split, 1)

        # Persist splitter geometry across launches
        self._settings = QSettings("Orbit360", "Genesis")
        if self._settings.contains("topSplit"):
            top_split.restoreState(self._settings.value("topSplit"))
        if self._settings.contains("bodySplit"):
            body_split.restoreState(self._settings.value("bodySplit"))
        top_split.splitterMoved.connect(
            lambda *_: self._settings.setValue("topSplit", top_split.saveState())
        )
        body_split.splitterMoved.connect(
            lambda *_: self._settings.setValue("bodySplit", body_split.saveState())
        )
        self._top_split  = top_split
        self._body_split = body_split

        self.refresh()

    # ── Public ───────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        xl_files: list[Path] = []
        if TEST_DATA_DIR.is_dir():
            xl_files = sorted(TEST_DATA_DIR.rglob("*.xlsx"))

        # Always refresh the side panes — they're cheap and may have new data
        # from a fresh batch even when the pool-card list hasn't changed.
        if hasattr(self, "_generator_pane"):
            self._generator_pane.refresh_templates()
        if hasattr(self, "_ledger_pane"):
            self._ledger_pane.refresh()

        # Rebuild cards only if the file list changed
        current_paths = [c._path for c in self._cards]
        if xl_files == current_paths:
            for card in self._cards:
                card.refresh()
            self._update_summary_bar()
            return

        # Clear and rebuild
        while self._cards_layout.count() > 1:
            item = self._cards_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self._cards.clear()

        if not xl_files:
            empty = QLabel(
                "No test data files found.\n\n"
                "Excel (.xlsx) files placed under\n"
                f"orbit_data/test_data/\nwill appear here."
            )
            empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
            empty.setStyleSheet(
                f"color: {_DIM}; font-size: 12px; background: transparent;"
            )
            self._cards_layout.insertWidget(0, empty)
            self._summary_lbl.setText("No files found")
            return

        for path in xl_files:
            card = _PoolCard(path, self._cards_widget)
            self._cards.append(card)
            self._cards_layout.insertWidget(self._cards_layout.count() - 1, card)

        self._update_summary_bar()

    # ── Slots ────────────────────────────────────────────────────────────────

    def _on_batch_generated(self, _result) -> None:
        """A fresh batch landed — re-scan TEST_DATA_DIR so the new pool files
        appear as cards and patients show up in the ledger."""
        self.refresh()

    # ── Private ──────────────────────────────────────────────────────────────

    def _update_summary_bar(self) -> None:
        if not self._cards:
            self._summary_lbl.setText("No files found")
            return

        totals = {"total": 0, "available": 0, "claimed": 0, "stale": 0}
        for card in self._cards:
            s = card.get_summary_counts()
            for k in totals:
                totals[k] += s.get(k, 0)

        n      = len(self._cards)
        files  = f"{n} file{'s' if n != 1 else ''}"
        parts  = [
            files,
            f"{totals['total']} total accounts",
            f"{totals['available']} available",
            f"{totals['claimed']} in use",
        ]
        if totals["stale"]:
            parts.append(f"⚠ {totals['stale']} stale")

        self._summary_lbl.setText("  •  ".join(parts))
