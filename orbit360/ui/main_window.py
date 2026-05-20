from __future__ import annotations

import json
import os
import shutil
import sys
import time
import py_compile
from pathlib import Path
from typing import Optional

import html as _html_module

import orbit360.backend.orbit_runtime as runtime 
from orbit360.ui.orbit_ui_input import OrbitInputDialog
from PySide6.QtCore import Qt, QTimer, QUrl, QSettings
from PySide6.QtGui import (
    QColor, QDesktopServices, QFont, QIcon, QKeySequence,
    QPixmap, QShortcut,
)
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import (
    QApplication,
    QLabel,
    QMessageBox,
    QStackedWidget,
    QStyleFactory,
    QSystemTrayIcon,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QMainWindow,
    QFileDialog,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStatusBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from orbit360.ui.cascade_bridge import CascadeBridge
from orbit360.ui.nav_sidebar import NavSidebar
from orbit360.ui.command_deck_panel import CommandDeckPanel
from orbit360.ui.pulse_panel import PulsePanel
from orbit360.ui.genesis_panel import GenesisPanel
from orbit360.ui.reports_panel import ReportsPanel
from orbit360.ui.settings_panel import SettingsPanel
from orbit360.ui.about_panel import AboutPanel
from orbit360.ui.scheduler_panel import SchedulerPanel
from orbit360.ui.tray_manager import TrayManager
from orbit360.models.cascade_model import CascadeModel
from orbit360.backend.event_bus import bus as _event_bus
from orbit360.ui.log_bridge import LogBridge
from orbit360.models.log_model import LogEntryModel
from orbit360.models.models import TestScriptModel
from orbit360.ui.qml_bridge import DeckNavBridge, SelectionBridge, TagsBridge
from orbit360.backend import history_db
from orbit360.backend.app_backend import AppBackend
from orbit360.utils.paths import SYSTEMS_DIR, RUNS_DIR, ORBIT_DATA_DIR, TEST_DATA_DIR, _IS_FROZEN, _RESOURCE_BASE
from orbit360.backend.script_sync import ScriptSyncWorker, is_git_repo
from orbit360.backend.workers import RunWorker
from orbit360.utils import utils


# ---------------------------------------------------------------------------
# Dropdown hierarchy definitions — label names only, not filesystem values.
# Actual directory names that fill each level are always read at runtime.
# To onboard a new system: add the key here + create the directory tree.
# ---------------------------------------------------------------------------
SYSTEM_HIERARCHIES: dict[str, list[str]] = {
    "CAC":              ["Environment", "Pillar",     "Test Type", "Module"],
    "Cloverleaf":       ["Environment", "Pillar",     "Facility",  "Data Feed"],
    "Meditech_Expanse": ["Environment", "Division",   "Facility",  "Module",   "Test Set"],
    "Meditech_56":      ["Environment", "Division",   "HCIS",      "Test Type"],
    "MTX":              ["Environment", "Division",   "HCIS",      "Test Type"],
    "Flash":            ["Flash Type",  "Test Set"],
    "Infra":            ["Tool",        "Environment", "Site"],
}


# ---------------------------------------------------------------------------
# Log color palette — Catppuccin Mocha
# ---------------------------------------------------------------------------
_CLR_TEXT    = "#cdd6f4"   # default / neutral text
_CLR_DIM     = "#6c7086"   # paths, timestamps, dim metadata
_CLR_SUBTEXT = "#a6adc8"   # progress / live stdout lines
_CLR_SURFACE = "#45475a"   # separator lines (─ ═)
_CLR_BLUE    = "#89b4fa"   # run headings, script name indicators
_CLR_GREEN   = "#a6e3a1"   # passed
_CLR_RED     = "#f38ba8"   # failed / run errors
_CLR_AMBER   = "#f9e2af"   # manual_complete — analyst finished remaining steps
_CLR_ORANGE  = "#fab387"   # launch errors (OSError)

def _log_line_color(line: str) -> str:
    """
    Map a raw stdout line (ANSI already stripped) to a Catppuccin color.
    Console format: "LEVEL    | message"  (no leading timestamp)

    Section breaks are INFO lines whose message starts with "─".
    Milestone messages (Run Started, Total Run Duration) are blue.
    """
    parts    = line.split("|", 1)
    level    = parts[0].strip().upper()
    msg_part = parts[1].strip() if len(parts) > 1 else ""

    if msg_part.startswith("─"):
        return _CLR_BLUE
    if "Total Run Duration" in msg_part or msg_part == "Run Started":
        return _CLR_BLUE
    if level in ("ERROR", "CRITICAL") or "SCRIPT FAILED" in line:
        return _CLR_RED
    if level == "WARNING" or "MANUAL STEP" in line:
        return _CLR_ORANGE
    if level == "INFO":
        return _CLR_GREEN
    if level == "DEBUG":
        return _CLR_DIM
    return _CLR_SUBTEXT


# Path to the qml/ directory — use _RESOURCE_BASE (project root in dev, _MEIPASS in frozen)
_QML_DIR = _RESOURCE_BASE / "qml"




class Ready360Window(QMainWindow):

    def register_input_handler(self):

        def handler(fields):
            dialog = OrbitInputDialog(fields, self)

            if dialog.exec():
                return dialog.inputs
            return {}
        runtime.orbit_input_handler = handler

    def __init__(self) -> None:
        super().__init__()
        self._worker: Optional[RunWorker] = None
        self._current_system: Optional[str] = None
        self._current_run_results: list = []      # ScriptResult objects from current run
        self._run_start_time: float = 0.0           # monotonic, set at run start
        self._last_run_root: Optional[str] = None
        self._last_context_path: Optional[Path] = None
        self._script_start_mono: float = 0.0
        self._active_script_name: str = ""

        # Elapsed-time ticker — updates status bar every second while a script runs
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._on_elapsed_tick)

        # Thin progress bar — shown during runs, lives in the status bar
        self._progress_bar = QProgressBar()
        self._progress_bar.setTextVisible(False)
        self._progress_bar.setFixedHeight(4)
        self._progress_bar.setVisible(False)

        # Parallel-mode tracking and dedup state
        self._parallel_active:               bool         = False
        self._last_prog_line:                str          = ""
        self._test_data_selected_row_index:  Optional[int] = None
        self._last_prog_script: str  = ""
        self._last_prog_count:  int  = 0

        # AppBackend owns ScreenshotModel, ScreenshotWatcher, and SwimlaneLanes.
        # Created before _setup_ui so the QML widgets can reference it.
        self._app_backend = AppBackend(self)

        # Models + bridges — created before _setup_ui
        self._cascade_model    = CascadeModel(self)
        self._cascade_bridge   = CascadeBridge(self)
        self._script_model     = TestScriptModel(self)
        self._selection_bridge = SelectionBridge(self)
        self._tags_bridge = TagsBridge(self)
        self._log_model        = LogEntryModel(self)
        self._log_bridge       = LogBridge(self._log_model, self)

        # Test data panel state — populated in _build_test_data_panel
        self._test_data_table:        Optional[QTableWidget] = None
        self._test_data_summary_lbl:  Optional[QLabel]      = None
        self._test_data_stale_lbl:    Optional[QLabel]      = None
        self._test_data_path_lbl:     Optional[QLabel]      = None
        self._test_data_excel_path:   Optional[Path]        = None
        self._test_data_sheet:        str | int             = 0
        self._test_data_run_flag:     Optional[str]         = None
        self._test_data_display_cols: list[str]             = []

        self._setup_ui()
        self._status_bar.addPermanentWidget(self._progress_bar, 1)
        self._wire_shortcuts()
        self._setup_tray()
        self._populate_system_dropdown()
        self._sync_worker: Optional[ScriptSyncWorker] = None
        self._auto_sync_on_startup()

    # ------------------------------------------------------------------ #
    # Public interface                                                     #
    # ------------------------------------------------------------------ #

    @property
    def script_model(self) -> TestScriptModel:
        """
        Expose the test script list model for external QML engine binding:
            engine.rootContext().setContextProperty("scriptModel", w.script_model)
        """
        return self._script_model

    # ------------------------------------------------------------------ #
    # UI construction                                                      #
    # ------------------------------------------------------------------ #

    def _setup_ui(self) -> None:
        self.setWindowTitle("Orbit360")
        self.setMinimumSize(1024, 680)
        self.resize(1280, 800)

        central = QWidget()
        central.setObjectName("centralWidget")
        self.setCentralWidget(central)

        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── Body: NavSidebar | Content area ─────────────────────────────
        body = QWidget()
        body.setObjectName("appBody")
        body.setStyleSheet("QWidget#appBody { background: #080d18; }")
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)

        # Left nav sidebar
        self._nav_sidebar = NavSidebar(body)
        self._nav_sidebar.navigate.connect(self._on_nav_changed)
        body_layout.addWidget(self._nav_sidebar)

        # Right: top bar + app stack
        content_area = QWidget()
        content_area.setStyleSheet("background: #0a0e1a;")
        content_layout = QVBoxLayout(content_area)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(0)

        # App stack (Command Deck, Launcher, placeholders)
        self._app_stack = QStackedWidget()
        self._app_stack.setStyleSheet("background: transparent;")

        # Build all child widgets first (they reference self.* attributes set below)
        self._build_qml_widgets()       # creates _cascade_widget, _script_list_widget, etc.
        self._test_data_panel = self._build_test_data_panel()

        self._app_stack.addWidget(self._build_command_deck_view())  # index 0
        self._app_stack.addWidget(self._build_launcher_view())      # index 1
        self._pulse_panel = PulsePanel()
        self._app_stack.addWidget(self._pulse_panel)                # index 2
        self._genesis_panel = GenesisPanel()
        self._app_stack.addWidget(self._genesis_panel)              # index 3
        self._reports_panel = ReportsPanel()
        self._app_stack.addWidget(self._reports_panel)              # index 4
        self._settings_panel = SettingsPanel()
        self._app_stack.addWidget(self._settings_panel)             # index 5
        self._about_panel = AboutPanel()
        self._app_stack.addWidget(self._about_panel)                # index 6
        self._scheduler_panel = SchedulerPanel()
        self._scheduler_panel.trigger_run.connect(self._trigger_scheduled_run)
        self._app_stack.addWidget(self._scheduler_panel)            # index 7

        self._genesis_panel.launch_requested.connect(
            lambda: self._on_nav_changed(1)
        )

        content_layout.addWidget(self._app_stack, 1)
        body_layout.addWidget(content_area, 1)
        root_layout.addWidget(body, 1)

        # ── Status bar ───────────────────────────────────────────────────
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

        self._progress_label = QLabel()
        self._progress_label.setStyleSheet(
            "color: #89b4fa; font-size: 11px; padding-right: 8px;"
        )
        self._progress_label.hide()
        self._status_bar.addPermanentWidget(self._progress_label)

    # ------------------------------------------------------------------ #
    # UI sub-builders                                                      #
    # ------------------------------------------------------------------ #

    def _build_qml_widgets(self) -> None:
        """Instantiate all QML-backed widgets (no layout yet)."""
        # Cascade
        self._cascade_bridge.levelSelected.connect(self._on_cascade_changed)
        self._cascade_bridge.popupOpened.connect(self._on_cascade_popup_opened)
        self._cascade_bridge.popupClosed.connect(self._on_cascade_popup_closed)

        self._cascade_widget = QQuickWidget()
        self._cascade_widget.setClearColor(QColor("#0a0e1a"))
        self._cascade_widget.rootContext().setContextProperty("cascadeModel",  self._cascade_model)
        self._cascade_widget.rootContext().setContextProperty("cascadeBridge", self._cascade_bridge)
        self._cascade_widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self._cascade_widget.setSource(QUrl.fromLocalFile(str(_QML_DIR / "DropdownCascade.qml")))
        self._cascade_widget.setFixedHeight(0)
        self._cascade_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

        # Script list
        self._selection_bridge.rowChanged.connect(self._on_test_selection_changed)

        self._script_list_widget = QQuickWidget()
        self._script_list_widget.setClearColor(QColor("#181825"))
        self._script_list_widget.rootContext().setContextProperty("scriptModel",    self._script_model)
        self._script_list_widget.rootContext().setContextProperty("selectionBridge", self._selection_bridge)
        self._script_list_widget.rootContext().setContextProperty("tagsBridge",      self._tags_bridge)
        self._script_list_widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self._script_list_widget.setSource(QUrl.fromLocalFile(str(_QML_DIR / "ScriptList.qml")))
        self._script_list_widget.setMinimumHeight(100)
        self._script_list_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Log console
        self._log_widget = QQuickWidget()
        self._log_widget.setClearColor(QColor("#181825"))
        self._log_widget.rootContext().setContextProperty("logModel",  self._log_model)
        self._log_widget.rootContext().setContextProperty("logBridge", self._log_bridge)
        self._log_widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self._log_widget.setSource(QUrl.fromLocalFile(str(_QML_DIR / "LogConsole.qml")))
        self._log_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Swimlane view (parallel mode)
        self._swimlane_widget = QQuickWidget()
        self._swimlane_widget.setClearColor(QColor("#181825"))
        self._swimlane_widget.rootContext().setContextProperty("appBackend", self._app_backend)
        self._swimlane_widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self._swimlane_widget.setSource(QUrl.fromLocalFile(str(_QML_DIR / "SwimlaneView.qml")))
        self._swimlane_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self._log_stack = QStackedWidget()
        self._log_stack.addWidget(self._log_widget)       # index 0 — sequential
        self._log_stack.addWidget(self._swimlane_widget)  # index 1 — parallel
        self._log_stack.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Screenshot strip
        self._screenshot_strip_widget = QQuickWidget()
        self._screenshot_strip_widget.setClearColor(QColor("#1e1e2e"))
        self._screenshot_strip_widget.rootContext().setContextProperty("appBackend", self._app_backend)
        self._screenshot_strip_widget.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self._screenshot_strip_widget.setSource(QUrl.fromLocalFile(str(_QML_DIR / "ScreenshotStrip.qml")))
        self._screenshot_strip_widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._screenshot_strip_widget.setMinimumHeight(0)
        self._screenshot_strip_widget.setMaximumHeight(174)

    def _build_command_deck_view(self) -> QWidget:
        """Index 0: Command Deck hero + cards + right stats panel."""
        view = QWidget()
        view.setStyleSheet("background: transparent;")
        hl = QHBoxLayout(view)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)

        # Left: QML hero + cards
        self._command_deck_qml = QQuickWidget()
        self._command_deck_qml.setClearColor(QColor("#080d18"))
        self._command_deck_qml.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        self._command_deck_qml.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        # Bridge context property — QML calls deckNavBridge.navigate(screenIndex)
        # directly as a @Slot, same pattern as selectionBridge / cascadeBridge.
        # This avoids rootObject().signal.connect() which misses Ready if QML
        # loads synchronously.
        self._deck_nav_bridge = DeckNavBridge(self)
        self._deck_nav_bridge.navigated.connect(self._on_nav_changed)
        self._command_deck_qml.rootContext().setContextProperty(
            "deckNavBridge", self._deck_nav_bridge
        )
        self._command_deck_qml.setSource(QUrl.fromLocalFile(str(_QML_DIR / "CommandDeck.qml")))

        hl.addWidget(self._command_deck_qml, 1)

        # Right: stats panel
        self._deck_panel = CommandDeckPanel()
        hl.addWidget(self._deck_panel)

        return view

    def _build_launcher_view(self) -> QWidget:
        """Index 1: full automation launcher — cascade + scripts + console."""
        view = QWidget()
        view.setStyleSheet("background: #0a0e1a;")
        vl = QVBoxLayout(view)
        vl.setContentsMargins(10, 6, 10, 4)
        vl.setSpacing(4)

        # ── System + Cascade bar ─────────────────────────────────────────
        # System selector sits left of the cascade, matching its 56px height.
        # Combo is created here (not earlier) to avoid a parentless QWidget
        # becoming a top-level floating window before it's embedded.
        # Match the cascade combos (DropdownCascade.qml) so the System combo
        # looks like the same control: surface0 #313244 fill, blue hover edge.
        _combo_sheet = """
            QComboBox {
                background: #313244;
                border: 1px solid #45475a;
                border-radius: 6px;
                color: #cdd6f4;
                font-size: 13px;
                padding: 2px 10px;
            }
            QComboBox:hover {
                background: #3d3f52;
                border: 1px solid #89b4fa;
            }
            QComboBox::drop-down { border: none; width: 22px; }
            QComboBox QAbstractItemView {
                background: #1e1e2e;
                border: 1px solid #45475a;
                color: #cdd6f4;
                selection-background-color: #45475a;
                selection-color: #cdd6f4;
                outline: none;
                padding: 2px;
            }
        """
        self._system_combo = QComboBox()
        self._system_combo.setStyle(QStyleFactory.create("Fusion"))  # dark stylesheet on Windows
        self._system_combo.setMinimumWidth(140)
        self._system_combo.currentIndexChanged.connect(self._on_system_changed)

        sys_block = QWidget()
        sys_block.setFixedHeight(56)
        sys_block.setFixedWidth(160)
        sys_block.setStyleSheet(
            "background: #1e1e2e; border-right: 1px solid #313244;"
        )
        sb = QVBoxLayout(sys_block)
        sb.setContentsMargins(8, 6, 8, 6)
        sb.setSpacing(3)
        sys_lbl = QLabel("System")
        sys_lbl.setStyleSheet("color: #6c7086; font-size: 11px; font-family: 'Segoe UI';")
        self._system_combo.setStyleSheet(_combo_sheet)
        self._system_combo.setFixedHeight(32)
        sb.addWidget(sys_lbl)
        sb.addWidget(self._system_combo)

        # MUST use setMinimumHeight only — NOT setFixedHeight or setMaximumHeight.
        # The QQuickWidget inside grows temporarily when a popup opens; capping
        # the row height clips the popup and swallows its mouse events.
        cascade_row = QWidget()
        cascade_row.setMinimumHeight(56)
        cascade_row.setStyleSheet(
            "background: #1e1e2e; border-bottom: 1px solid #1a2233;"
        )
        cr = QHBoxLayout(cascade_row)
        cr.setContentsMargins(0, 0, 0, 0)
        cr.setSpacing(0)
        cr.addWidget(sys_block)
        cr.addWidget(self._cascade_widget, 1)
        vl.addWidget(cascade_row)

        # ── Zone 1: Run controls strip (above console) ───────────────────
        run_strip = QWidget()
        run_strip.setFixedHeight(36)
        run_strip.setStyleSheet("""
            QWidget { background: #0d1520; border-bottom: 1px solid #141e30; }
            QPushButton {
                background: #111c30;
                border: 1px solid #1e3a5f;
                border-radius: 4px;
                color: #cdd6f4;
                font-size: 12px;
                padding: 3px 14px;
                min-width: 80px;
            }
            QPushButton:hover   { background: #162440; border-color: #89b4fa; }
            QPushButton:disabled { color: #3a4a60; border-color: #1a2a40; }
            QPushButton#abortButton  { border-color: #f38ba8; color: #f38ba8; }
            QPushButton#abortButton:hover  { background: #2a1020; }
            QPushButton#resumeButton { border-color: #f9e2af; color: #f9e2af; }
        """)
        rs_layout = QHBoxLayout(run_strip)
        rs_layout.setContentsMargins(6, 3, 6, 3)
        rs_layout.setSpacing(6)

        self._full_run_button = QPushButton("▶  Full Run")
        self._full_run_button.setEnabled(False)
        self._full_run_button.setToolTip("Run every script in order  (F5)")
        self._full_run_button.clicked.connect(self._on_full_run_clicked)
        rs_layout.addWidget(self._full_run_button)

        self._single_run_button = QPushButton("▶  Single")
        self._single_run_button.setEnabled(False)
        self._single_run_button.setToolTip("Run only the selected script")
        self._single_run_button.clicked.connect(self._on_single_run_clicked)
        rs_layout.addWidget(self._single_run_button)

        _vline(rs_layout)

        self._stop_button = QPushButton("■  Stop")
        self._stop_button.setObjectName("abortButton")
        self._stop_button.setEnabled(False)
        self._stop_button.setVisible(False)
        self._stop_button.setToolTip("Kill the running script  (Esc)")
        self._stop_button.clicked.connect(self._on_abort_clicked)
        rs_layout.addWidget(self._stop_button)

        self._resume_button = QPushButton("↺  Resume")
        self._resume_button.setObjectName("resumeButton")
        self._resume_button.setEnabled(False)
        self._resume_button.setVisible(False)
        self._resume_button.setToolTip("Resume from first failed/pending script")
        self._resume_button.clicked.connect(self._on_resume_clicked)
        rs_layout.addWidget(self._resume_button)

        rs_layout.addStretch()

        self._refresh_button = QPushButton("↺  Refresh")
        self._refresh_button.setToolTip("Re-scan filesystem and reload scripts")
        self._refresh_button.clicked.connect(self._on_refresh_clicked)
        rs_layout.addWidget(self._refresh_button)

        # ── Zone 2: Recovery banner (hidden by default) ──────────────────
        self._recovery_banner = QWidget()
        self._recovery_banner.setFixedHeight(38)
        self._recovery_banner.setVisible(False)
        self._recovery_banner.setStyleSheet("""
            QWidget { background: #2a1e08; border-bottom: 1px solid #f9e2af; }
            QLabel  { color: #f9e2af; font-size: 11px; font-weight: bold;
                      background: transparent; }
            QPushButton {
                background: #1e1608;
                border: 1px solid #f9e2af;
                border-radius: 4px;
                color: #f9e2af;
                font-size: 11px;
                padding: 2px 10px;
            }
            QPushButton:hover { background: #3a2a10; }
        """)
        rb_layout = QHBoxLayout(self._recovery_banner)
        rb_layout.setContentsMargins(10, 3, 10, 3)
        rb_layout.setSpacing(6)

        rb_layout.addWidget(QLabel("⚠  Action Required:"))

        self._continue_button = QPushButton("▶ Continue")
        self._continue_button.setObjectName("continueButton")
        self._continue_button.setVisible(False)
        self._continue_button.clicked.connect(self._on_continue_clicked)
        rb_layout.addWidget(self._continue_button)

        self._skip_step_button = QPushButton("⏭ Skip Step")
        self._skip_step_button.setObjectName("skipStepButton")
        self._skip_step_button.setToolTip("Skip this failed step and continue")
        self._skip_step_button.setVisible(False)
        self._skip_step_button.clicked.connect(self._on_skip_step_clicked)
        rb_layout.addWidget(self._skip_step_button)

        self._manual_complete_button = QPushButton("✓ Manual Complete")
        self._manual_complete_button.setObjectName("manualCompleteButton")
        self._manual_complete_button.setToolTip("Mark run as manually completed")
        self._manual_complete_button.setVisible(False)
        self._manual_complete_button.clicked.connect(self._on_manual_complete_clicked)
        rb_layout.addWidget(self._manual_complete_button)

        self._mark_failed_button = QPushButton("✗ Mark Failed")
        self._mark_failed_button.setObjectName("markFailedButton")
        self._mark_failed_button.setToolTip("Mark run as failed with no recovery")
        self._mark_failed_button.setVisible(False)
        self._mark_failed_button.clicked.connect(self._on_mark_failed_clicked)
        rb_layout.addWidget(self._mark_failed_button)

        rb_layout.addStretch()

        # ── Main horizontal splitter ─────────────────────────────────────
        h_splitter = QSplitter(Qt.Orientation.Horizontal)
        h_splitter.setStyleSheet("""
            QSplitter::handle { background: #141e30; width: 3px; }
            QSplitter::handle:hover { background: #1e3a5f; }
        """)

        # Left pane: script list (top) + test data (bottom)
        left_splitter = QSplitter(Qt.Orientation.Vertical)
        left_splitter.setStyleSheet("""
            QSplitter::handle { background: #141e30; height: 3px; }
            QSplitter::handle:hover { background: #1e3a5f; }
        """)
        left_splitter.addWidget(self._script_list_widget)
        left_splitter.addWidget(self._test_data_panel)
        left_splitter.setCollapsible(1, True)
        left_splitter.setStretchFactor(0, 1)  # script list takes all available space
        left_splitter.setStretchFactor(1, 0)  # test data panel keeps its natural height

        # Right pane: console + screenshot + utility strip
        right_pane = QWidget()
        right_pane.setStyleSheet("background: transparent;")
        rp_layout = QVBoxLayout(right_pane)
        rp_layout.setContentsMargins(0, 0, 0, 0)
        rp_layout.setSpacing(0)

        rp_layout.addWidget(run_strip)
        rp_layout.addWidget(self._recovery_banner)
        rp_layout.addWidget(self._log_stack, 1)
        rp_layout.addWidget(self._screenshot_strip_widget)

        # Zone 3: utility strip (below console)
        util_strip = QWidget()
        util_strip.setFixedHeight(30)
        util_strip.setStyleSheet("""
            QWidget { background: #0d1520; border-top: 1px solid #141e30; }
            QPushButton {
                background: transparent;
                border: none;
                color: #3a4a60;
                font-size: 11px;
                padding: 2px 10px;
            }
            QPushButton:hover   { color: #89b4fa; }
            QPushButton:enabled { color: #5a6a88; }
            QPushButton:disabled { color: #2a3a50; }
        """)
        us_layout = QHBoxLayout(util_strip)
        us_layout.setContentsMargins(6, 0, 6, 0)
        us_layout.setSpacing(0)
        us_layout.addStretch()

        self._clear_button = QPushButton("✕  Clear Console")
        self._clear_button.clicked.connect(self._on_clear_console)
        us_layout.addWidget(self._clear_button)

        self._open_folder_button = QPushButton("📁  Open Results")
        self._open_folder_button.setEnabled(False)
        self._open_folder_button.setToolTip("Open run output folder")
        self._open_folder_button.clicked.connect(self._on_open_folder_clicked)
        us_layout.addWidget(self._open_folder_button)

        self._view_report_button = QPushButton("📊  View Report")
        self._view_report_button.setEnabled(False)
        self._view_report_button.setToolTip("Open run_report.html in browser")
        self._view_report_button.clicked.connect(self._on_view_report_clicked)
        us_layout.addWidget(self._view_report_button)

        rp_layout.addWidget(util_strip)

        h_splitter.addWidget(left_splitter)
        h_splitter.addWidget(right_pane)
        h_splitter.setSizes([420, 780])
        h_splitter.setCollapsible(0, False)
        h_splitter.setCollapsible(1, False)

        # Restore splitter state
        settings = QSettings("Orbit360", "Launcher")
        if settings.contains("hSplitter"):
            h_splitter.restoreState(settings.value("hSplitter"))
        # leftSplitter intentionally not restored — always starts 50/50

        h_splitter.splitterMoved.connect(
            lambda: settings.setValue("hSplitter", h_splitter.saveState())
        )
        left_splitter.splitterMoved.connect(
            lambda: settings.setValue("leftSplitter", left_splitter.saveState())
        )

        vl.addWidget(h_splitter, 1)
        return view

    # ------------------------------------------------------------------ #
    # Navigation                                                           #
    # ------------------------------------------------------------------ #

    def _on_nav_changed(self, index: int) -> None:
        """Switch the app stack and keep the nav sidebar in sync."""
        self._app_stack.setCurrentIndex(index)
        self._nav_sidebar.set_active(index)
        if index == 2:
            self._pulse_panel.refresh()
        elif index == 3:
            self._genesis_panel.refresh()
        elif index == 4:
            self._reports_panel.refresh()
        elif index == 5:
            self._settings_panel.refresh()
        elif index == 7:
            self._scheduler_panel.refresh()

    def _trigger_scheduled_run(self, system: str, cascade: list) -> None:
        """Called by SchedulerPanel when a scheduled run fires."""
        self._on_nav_changed(1)

        idx = self._system_combo.findData(system, Qt.ItemDataRole.UserRole)
        if idx < 0:
            return
        self._system_combo.setCurrentIndex(idx)
        self._on_system_changed(idx)

        # Walk cascade levels synchronously using filesystem scan
        for level, raw in enumerate(cascade):
            if level >= self._cascade_model.level_count():
                break
            parent = SYSTEMS_DIR / system
            for l in range(level):
                parent = parent / cascade[l]
            subs = utils.scan_subdirectories(parent)
            if raw not in subs:
                break
            opt_idx = subs.index(raw) + 1   # 1-based (0 = blank placeholder)
            self._cascade_model.set_selected(level, opt_idx)
            next_path = parent / raw
            if level + 1 < self._cascade_model.level_count():
                self._fill_cascade_level(level + 1, next_path)

        self._update_run_button()
        QTimer.singleShot(300, self._on_full_run_clicked)

    def _set_recovery_banner(self, visible: bool) -> None:
        """Show or hide the amber recovery banner."""
        if hasattr(self, "_recovery_banner"):
            self._recovery_banner.setVisible(visible)

    # ------------------------------------------------------------------ #
    # Test Data panel                                                      #
    # ------------------------------------------------------------------ #

    # Status → (display label, background color, text color)
    _TD_STATUS_STYLE: dict[str, tuple[str, str, str]] = {
        "available": ("Available", "#45475a", "#cdd6f4"),
        "claimed":   ("In Use",    "#f9e2af", "#1e1e2e"),
        "pass":      ("PASS",      "#a6e3a1", "#1e1e2e"),
        "fail":      ("FAIL",      "#f38ba8", "#1e1e2e"),
        "skip":      ("SKIP",      "#89b4fa", "#1e1e2e"),
    }

    def _build_test_data_panel(self) -> QWidget:
        """Build the collapsible Test Data panel widget (initially hidden)."""
        panel = QWidget()
        panel.setObjectName("testDataPanel")
        panel.setVisible(False)
        panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(4)

        # ── Header row ───────────────────────────────────────────────────
        header_row = QHBoxLayout()
        header_row.setSpacing(6)

        td_icon = QLabel("◈ Test Data")
        td_icon.setStyleSheet("color: #89b4fa; font-weight: bold; font-size: 12px;")
        header_row.addWidget(td_icon)

        # File picker "…" button — sits right after the title
        pick_btn = QPushButton("…")
        pick_btn.setFixedWidth(26)
        pick_btn.setFixedHeight(22)
        pick_btn.setToolTip("Browse for an Excel test data file")
        pick_btn.clicked.connect(self._on_test_data_pick_file)
        header_row.addWidget(pick_btn)

        # Hidden labels kept so existing setter calls don't crash
        self._test_data_path_lbl = QLabel("")
        self._test_data_path_lbl.setVisible(False)
        header_row.addWidget(self._test_data_path_lbl)

        self._test_data_summary_lbl = QLabel("")
        self._test_data_summary_lbl.setVisible(False)
        header_row.addWidget(self._test_data_summary_lbl)

        header_row.addStretch(1)

        self._test_data_pin_lbl = QLabel("")
        self._test_data_pin_lbl.setStyleSheet(
            "color: #a6e3a1; font-size: 11px; font-weight: bold;"
        )
        self._test_data_pin_lbl.setVisible(False)
        header_row.addWidget(self._test_data_pin_lbl)

        self._test_data_stale_lbl = QLabel("")
        self._test_data_stale_lbl.setStyleSheet(
            "color: #f38ba8; font-size: 11px; font-weight: bold;"
        )
        self._test_data_stale_lbl.setVisible(False)
        header_row.addWidget(self._test_data_stale_lbl)

        # Column selector button
        cols_btn = QPushButton("⚙  Columns")
        cols_btn.setFixedHeight(22)
        cols_btn.setToolTip("Choose which columns to display")
        cols_btn.clicked.connect(self._on_test_data_select_cols)
        header_row.addWidget(cols_btn)

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(58)
        refresh_btn.setFixedHeight(22)
        refresh_btn.clicked.connect(self._on_test_data_refresh)
        header_row.addWidget(refresh_btn)

        reset_btn = QPushButton("Reset All")
        reset_btn.setObjectName("testDataResetBtn")
        reset_btn.setFixedWidth(64)
        reset_btn.setFixedHeight(22)
        reset_btn.clicked.connect(self._on_test_data_reset)
        header_row.addWidget(reset_btn)

        layout.addLayout(header_row)

        # ── Data table ───────────────────────────────────────────────────
        self._test_data_table = QTableWidget()
        self._test_data_table.setMinimumHeight(56)
        self._test_data_table.setMaximumHeight(400)
        self._test_data_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._test_data_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self._test_data_table.setSelectionMode(
            QTableWidget.SelectionMode.SingleSelection
        )
        self._test_data_table.setAlternatingRowColors(True)
        self._test_data_table.horizontalHeader().setStretchLastSection(False)
        self._test_data_table.horizontalHeader().setHighlightSections(False)
        # "#" and "Status" columns are fixed; data columns share remaining space equally
        from PySide6.QtWidgets import QHeaderView
        self._test_data_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self._test_data_table.verticalHeader().setVisible(False)
        self._test_data_table.verticalHeader().setDefaultSectionSize(26)
        self._test_data_table.setShowGrid(False)
        self._test_data_table.setObjectName("testDataTable")
        self._test_data_table.setStyleSheet("""
            QTableWidget {
                background: #0d1520;
                alternate-background-color: #091018;
                color: #cdd6f4;
                font-size: 11px;
                border: 1px solid #1a2a40;
                border-radius: 4px;
                gridline-color: #1a2a40;
            }
            QTableWidget::item { padding: 2px 6px; }
            QTableWidget::item:selected { background: #132240; color: #89b4fa; }
            QHeaderView::section {
                background: #080d18;
                color: #5a6a88;
                font-size: 10px;
                font-weight: bold;
                letter-spacing: 1px;
                border: none;
                border-bottom: 1px solid #1a2a40;
                padding: 3px 6px;
            }
            QScrollBar:vertical {
                background: #0a0e1a; width: 8px; border: none; border-radius: 4px;
            }
            QScrollBar::handle:vertical {
                background: #2a3a50; border-radius: 4px; min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
        """)
        self._test_data_table.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded
        )
        self._test_data_table.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self._test_data_table.customContextMenuRequested.connect(
            self._on_test_data_context_menu
        )
        self._test_data_table.itemClicked.connect(self._on_test_data_row_clicked)
        layout.addWidget(self._test_data_table)

        return panel

    def _resolve_test_data_excel_path(self, cfg: dict) -> Optional[Path]:
        raw = cfg.get("path", "")
        if not raw:
            return None
        p = Path(raw)
        return p if p.is_absolute() else ORBIT_DATA_DIR / raw

    def _refresh_test_data_panel(self) -> None:
        """Re-read the state DB and repopulate the table. Shows/hides the panel."""
        tests_yaml = self._resolve_tests_yaml()
        cfg = utils.load_test_data_config(tests_yaml) if tests_yaml else None

        if not cfg or not cfg.get("path"):
            self._test_data_panel.setVisible(False)
            return

        excel_path   = self._resolve_test_data_excel_path(cfg)
        sheet        = cfg.get("sheet", 0)
        run_flag_col = cfg.get("run_flag_col")

        # Reset column selection when the data file changes (different test selected)
        if excel_path != self._test_data_excel_path:
            self._test_data_display_cols = []

        self._test_data_excel_path = excel_path
        self._test_data_sheet      = sheet
        self._test_data_run_flag   = run_flag_col

        if excel_path is None:
            self._test_data_panel.setVisible(False)
            return

        self._test_data_panel.setVisible(True)

        try:
            rel = excel_path.relative_to(ORBIT_DATA_DIR)
            self._test_data_path_lbl.setText(str(rel))
        except ValueError:
            self._test_data_path_lbl.setText(str(excel_path))

        if not excel_path.exists():
            self._test_data_path_lbl.setStyleSheet("color: #f38ba8; font-size: 11px;")
            self._test_data_summary_lbl.setText("file not found")
            self._test_data_stale_lbl.setVisible(False)
            self._test_data_table.setRowCount(0)
            self._test_data_table.setColumnCount(0)
            return

        self._test_data_path_lbl.setStyleSheet("color: #6c7086; font-size: 11px;")

        try:
            from orbit360.utils.excel_data_manager import sync_from_excel, get_all_rows, get_summary
            sync_from_excel(excel_path, sheet, run_flag_col)
            rows    = get_all_rows(excel_path, sheet, run_flag_col)
            summary = get_summary(excel_path)
        except Exception as exc:
            self._test_data_summary_lbl.setText(f"Error: {exc}")
            return

        avail = summary.get("available", 0)
        done  = summary.get("pass", 0) + summary.get("fail", 0) + summary.get("skip", 0)
        inuse = summary.get("claimed", 0)
        total = summary.get("total", 0)
        stale = summary.get("stale", 0)
        self._test_data_summary_lbl.setText(
            f"{avail} available  •  {inuse} in use  •  {done} done  •  {total} total"
        )
        if stale:
            self._test_data_stale_lbl.setText(f"⚠ {stale} stale")
            self._test_data_stale_lbl.setToolTip(
                f"{stale} row(s) have been 'In Use' for too long — "
                "they will be auto-recovered at next run start."
            )
            self._test_data_stale_lbl.setVisible(True)
        else:
            self._test_data_stale_lbl.setVisible(False)

        # Determine which data columns to display
        # Strip internal/system columns — run_flag_col is administrative, not meaningful to show
        _system_cols = {"Result", "Notes", "Timestamp"}
        if self._test_data_run_flag:
            _system_cols.add(self._test_data_run_flag)
        all_data_cols = [
            k for k in (rows[0].keys() if rows else [])
            if not k.startswith("_") and k not in _system_cols
        ]
        # Respect user's column selection; default to just the first column (the account ID)
        if not hasattr(self, "_test_data_display_cols") or not self._test_data_display_cols:
            self._test_data_display_cols = all_data_cols[:1]

        data_cols   = [c for c in self._test_data_display_cols if c in all_data_cols]
        col_headers = ["#", "Status"] + data_cols
        self._test_data_table.setColumnCount(len(col_headers))
        self._test_data_table.setHorizontalHeaderLabels(col_headers)
        # Pin fixed-width columns; stretch data columns equally
        hdr = self._test_data_table.horizontalHeader()
        from PySide6.QtWidgets import QHeaderView
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self._test_data_table.setColumnWidth(0, 36)
        self._test_data_table.setColumnWidth(1, 84)
        for i in range(2, len(col_headers)):
            hdr.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
        _MAX_PREVIEW = 15
        self._test_data_table.setRowCount(min(len(rows), _MAX_PREVIEW))

        for r, row in enumerate(rows[:_MAX_PREVIEW]):
            row_index = row.get("_row_index", r)
            status    = row.get("_status", "available")
            style_label, bg, fg = self._TD_STATUS_STYLE.get(
                status, ("?", "#313244", "#cdd6f4")
            )

            # Build tooltip with run history
            history_count = row.get("_history_count", 0)
            tooltip_parts = []
            if row.get("_run_id"):
                tooltip_parts.append(f"Run: {row['_run_id']}")
            if row.get("_claimed_at"):
                tooltip_parts.append(f"Claimed: {row['_claimed_at'][:19]}")
            if row.get("_completed_at"):
                tooltip_parts.append(f"Completed: {row['_completed_at'][:19]}")
            if row.get("_notes"):
                tooltip_parts.append(f"Notes: {row['_notes']}")
            if history_count:
                tooltip_parts.append(f"History: {history_count} run(s) — right-click to view")
            tooltip = "\n".join(tooltip_parts) if tooltip_parts else ""

            # # column
            num_item = QTableWidgetItem(str(row_index + 1))
            num_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            num_item.setForeground(QColor("#6c7086"))
            if tooltip:
                num_item.setToolTip(tooltip)
            self._test_data_table.setItem(r, 0, num_item)

            # Status badge
            status_item = QTableWidgetItem(style_label)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            status_item.setBackground(QColor(bg))
            status_item.setForeground(QColor(fg))
            # QTableWidgetItem.font() returns an unsized QFont (pointSize == -1)
            # before the item is laid into a table; copying the table's own font
            # avoids "QFont::setPointSize: Point size <= 0 (-1)" warnings on
            # downstream font assignments.
            status_font = QFont(self._test_data_table.font())
            status_font.setBold(True)
            status_item.setFont(status_font)
            if tooltip:
                status_item.setToolTip(tooltip)
            self._test_data_table.setItem(r, 1, status_item)

            # Data columns
            for c, col in enumerate(data_cols, start=2):
                val  = row.get(col)
                cell = QTableWidgetItem("" if val is None else str(val))
                cell.setForeground(QColor("#cdd6f4"))
                if tooltip:
                    cell.setToolTip(tooltip)
                self._test_data_table.setItem(r, c, cell)

        self._test_data_table.resizeColumnsToContents()
        self._test_data_table.setColumnWidth(0, 32)
        if self._test_data_table.columnCount() > 1:
            self._test_data_table.setColumnWidth(1, max(80, self._test_data_table.columnWidth(1)))
        self._test_data_table.horizontalHeader().setStretchLastSection(True)

        # Size table to fit rows exactly (up to 15 shown; summary bar shows full count)
        ROW_H    = 26
        HEADER_H = self._test_data_table.horizontalHeader().height() or 28
        visible  = min(len(rows), _MAX_PREVIEW)
        self._test_data_table.setMaximumHeight(HEADER_H + visible * ROW_H + 2)

    # ── Test Data panel — event handlers ─────────────────────────────────────

    def _on_test_data_row_clicked(self, item) -> None:
        """Pin a specific account for the next Single Run."""
        r = item.row()
        status_item = self._test_data_table.item(r, 1)
        num_item    = self._test_data_table.item(r, 0)
        if status_item is None or num_item is None:
            return
        if status_item.text() != "Available":
            # Only available rows can be pinned
            self._test_data_selected_row_index = None
            self._test_data_pin_lbl.setVisible(False)
            return
        row_index = int(num_item.text()) - 1
        if self._test_data_selected_row_index == row_index:
            # Click the same row again to unpin
            self._test_data_selected_row_index = None
            self._test_data_pin_lbl.setVisible(False)
        else:
            self._test_data_selected_row_index = row_index
            # Show the account number in the pin label if possible
            acct_item = self._test_data_table.item(r, 2)
            acct = acct_item.text() if acct_item else f"row {row_index + 1}"
            self._test_data_pin_lbl.setText(f"  Pinned: {acct}")
            self._test_data_pin_lbl.setVisible(True)

    def _on_test_data_refresh(self) -> None:
        self._refresh_test_data_panel()

    def _on_test_data_reset(self) -> None:
        if self._test_data_excel_path is None:
            return
        box = QMessageBox(self)
        box.setWindowTitle("Reset Test Data")
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(
            f"Reset all rows in\n{self._test_data_excel_path.name}\nback to Available?"
        )
        box.setInformativeText("This clears In Use, PASS, FAIL, and SKIP statuses.")
        box.setStandardButtons(
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel
        )
        if box.exec() != QMessageBox.StandardButton.Yes:
            return
        from orbit360.utils.excel_data_manager import reset_rows
        count = reset_rows(self._test_data_excel_path)
        self._append_log(
            f"Test data reset: {count} row(s) returned to Available "
            f"({self._test_data_excel_path.name})",
            _CLR_AMBER,
        )
        self._refresh_test_data_panel()

    def _on_test_data_pick_file(self) -> None:
        """Open file dialog; write the chosen path back into run_sequence.yaml."""
        start_dir = str(ORBIT_DATA_DIR / "test_data")
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Test Data File",
            start_dir,
            "Excel files (*.xlsx *.xls);;All files (*)",
        )
        if not path:
            return
        excel_path = Path(path)

        # Try to store as a path relative to ORBIT_DATA_DIR
        try:
            rel = str(excel_path.relative_to(ORBIT_DATA_DIR))
        except ValueError:
            rel = str(excel_path)

        tests_yaml = self._resolve_tests_yaml()
        if tests_yaml is None:
            self._status_bar.showMessage("No run_sequence.yaml found for current selection.")
            return

        try:
            import yaml as _yaml
            with tests_yaml.open("r", encoding="utf-8") as fh:
                data = _yaml.safe_load(fh) or {}

            if "test_data" not in data or not isinstance(data["test_data"], dict):
                data["test_data"] = {}
            data["test_data"]["path"] = rel

            with tests_yaml.open("w", encoding="utf-8") as fh:
                _yaml.dump(data, fh, default_flow_style=False, allow_unicode=True)
        except Exception as exc:
            QMessageBox.warning(self, "File Picker Error", str(exc))
            return

        # Reset column selection so new file gets fresh defaults
        self._test_data_display_cols = []
        self._append_log(f"Test data file set: {rel}", _CLR_AMBER)
        self._refresh_test_data_panel()

    def _on_test_data_select_cols(self) -> None:
        """Show a dialog letting the user choose which Excel columns to display."""
        if self._test_data_excel_path is None or not self._test_data_excel_path.exists():
            return
        from orbit360.utils.excel_data_manager import get_excel_headers
        _sys = {"Result", "Notes", "Timestamp"}
        if self._test_data_run_flag:
            _sys.add(self._test_data_run_flag)
        all_headers = [
            h for h in get_excel_headers(
                self._test_data_excel_path, self._test_data_sheet
            )
            if h not in _sys
        ]
        if not all_headers:
            return

        from PySide6.QtWidgets import QDialog, QCheckBox, QDialogButtonBox
        dlg = QDialog(self)
        dlg.setWindowTitle("Select Display Columns")
        dlg.setMinimumWidth(240)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel("Choose up to 6 columns to show in the table:"))

        current = getattr(self, "_test_data_display_cols", [])
        checkboxes: list[QCheckBox] = []
        for h in all_headers:
            cb = QCheckBox(h)
            cb.setChecked(h in current)
            layout.addWidget(cb)
            checkboxes.append(cb)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)
        layout.addWidget(buttons)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            return

        selected = [cb.text() for cb in checkboxes if cb.isChecked()][:6]
        self._test_data_display_cols = selected if selected else all_headers[:1]
        self._refresh_test_data_panel()

    def _on_test_data_context_menu(self, pos) -> None:
        """Right-click context menu on a table row for manual status actions."""
        if self._test_data_excel_path is None:
            return
        row = self._test_data_table.rowAt(pos.y())
        if row < 0:
            return

        # Retrieve row_index from column 0 (displayed as row_index+1)
        num_item = self._test_data_table.item(row, 0)
        if num_item is None:
            return
        try:
            row_index = int(num_item.text()) - 1
        except ValueError:
            return

        from PySide6.QtWidgets import QMenu
        from orbit360.utils.excel_data_manager import set_row_status, get_row_history

        menu = QMenu(self)

        act_reset = menu.addAction("↩  Reset to Available")
        act_pass  = menu.addAction("✓  Mark PASS")
        act_fail  = menu.addAction("✗  Mark FAIL")
        act_skip  = menu.addAction("⊘  Mark SKIP")
        menu.addSeparator()
        act_hist  = menu.addAction("📋  View History")

        chosen = menu.exec(self._test_data_table.viewport().mapToGlobal(pos))

        if chosen == act_reset:
            set_row_status(
                self._test_data_excel_path, row_index, "available",
                sheet=self._test_data_sheet,
            )
            self._refresh_test_data_panel()
        elif chosen == act_pass:
            set_row_status(
                self._test_data_excel_path, row_index, "pass",
                sheet=self._test_data_sheet,
            )
            self._refresh_test_data_panel()
        elif chosen == act_fail:
            set_row_status(
                self._test_data_excel_path, row_index, "fail",
                sheet=self._test_data_sheet,
            )
            self._refresh_test_data_panel()
        elif chosen == act_skip:
            set_row_status(
                self._test_data_excel_path, row_index, "skip",
                sheet=self._test_data_sheet,
            )
            self._refresh_test_data_panel()
        elif chosen == act_hist:
            history = get_row_history(self._test_data_excel_path, row_index)
            if not history:
                QMessageBox.information(self, f"Row {row_index + 1} History", "No history recorded yet.")
                return
            lines = [f"Row {row_index + 1} — {len(history)} run(s)\n"]
            for h in history:
                ts   = h["timestamp"][:19] if h.get("timestamp") else "?"
                rid  = h.get("run_id") or "manual"
                st   = h.get("status", "?").upper()
                note = f" — {h['notes']}" if h.get("notes") else ""
                lines.append(f"{ts}  {st}  [{rid}]{note}")
            QMessageBox.information(
                self, f"Row {row_index + 1} History", "\n".join(lines)
            )

    # ------------------------------------------------------------------ #
    # System dropdown                                                      #
    # ------------------------------------------------------------------ #

    def _populate_system_dropdown(self) -> None:
        # Save current selection so refresh doesn't lose it
        saved = self._system_combo.currentData(Qt.ItemDataRole.UserRole)

        self._system_combo.blockSignals(True)
        self._system_combo.clear()
        self._system_combo.addItem("")
        systems = utils.scan_subdirectories(SYSTEMS_DIR)
        for s in systems:
            display = utils.resolve_display_name(
                s, utils.load_display_names(SYSTEMS_DIR / "display_names.json")
            )
            self._system_combo.addItem(display, userData=s)

        if saved:
            idx = self._system_combo.findData(saved, Qt.ItemDataRole.UserRole)
            if idx >= 0:
                self._system_combo.setCurrentIndex(idx)

        self._system_combo.blockSignals(False)

        # Re-trigger _on_system_changed unconditionally: rebuilds the cascade
        # for the restored system, or clears it when the previous selection
        # is no longer available (folder removed, etc.).
        self._on_system_changed(self._system_combo.currentIndex())

    def _on_system_changed(self, index: int) -> None:
        raw_name = self._system_combo.itemData(index, Qt.ItemDataRole.UserRole)
        if not raw_name:
            self._cascade_model.set_levels([])
            self._update_cascade_height()
            self._current_system = None
            self._full_run_button.setEnabled(False)
            self._single_run_button.setEnabled(False)
            return

        self._current_system = raw_name
        labels = SYSTEM_HIERARCHIES.get(raw_name, [])
        self._cascade_model.set_levels(labels)
        self._update_cascade_height()

        if labels:
            self._fill_cascade_level(0, SYSTEMS_DIR / raw_name)

        self._update_run_button()
        self._update_deck_stats()
        self._update_window_title()

    def _update_window_title(self) -> None:
        """Reflect the current system + cascade selection in the window title."""
        if not self._current_system:
            self.setWindowTitle("Orbit360")
            return
        parts = [self._current_system]
        for level in range(self._cascade_model.level_count()):
            raw = self._cascade_model.get_raw_at(level)
            if raw:
                parts.append(raw)
            else:
                break
        self.setWindowTitle("Orbit360  —  " + "  /  ".join(parts))

    def _update_deck_stats(self) -> None:
        """Refresh the Command Deck system overview tile counts."""
        if not hasattr(self, "_deck_panel") or not self._current_system:
            return
        sys_path = SYSTEMS_DIR / self._current_system
        script_count = sum(
            1 for p in sys_path.rglob("*")
            if p.suffix in (".py", ".ps1", ".xaml", ".sql") and p.is_file()
        )
        env_count = getattr(self, "_level0_option_count", 0)
        test_set_count = sum(
            1 for p in sys_path.rglob("run_sequence.yaml") if p.is_file()
        )
        self._deck_panel.set_stats(script_count, max(env_count, 0), test_set_count)

    # ------------------------------------------------------------------ #
    # Dropdown cascade                                                     #
    # ------------------------------------------------------------------ #

    def _update_cascade_height(self) -> None:
        n = self._cascade_model.level_count()
        # Popup now opens upward (DropdownCascade.qml), so widget only needs
        # to fit the label (16px) + combo (32px) + spacing (4px) = 52px.
        # Always stay visible so the QHBoxLayout's stretch=1 slot keeps its
        # space — otherwise sys_block (160px fixed) is the only widget left
        # in the row and Qt drifts it toward the centre after a refresh.
        self._cascade_widget.setVisible(True)
        self._cascade_widget.setFixedHeight(56 if n > 0 else 0)

    def _fill_cascade_level(self, level: int, parent_path: Path) -> None:
        display_map = utils.load_display_names(parent_path / "display_names.json")
        options = [
            (raw, utils.resolve_display_name(raw, display_map))
            for raw in utils.scan_subdirectories(parent_path)
        ]
        self._cascade_model.set_options(level, options)
        self._cascade_model.clear_from(level + 1)
        self._update_run_button()
        if level == 0:
            self._level0_option_count = len(options)

    def _on_cascade_popup_opened(self, popup_height: int) -> None:
        self._cascade_widget.setFixedHeight(56 + popup_height + 4)

    def _on_cascade_popup_closed(self) -> None:
        if self._cascade_model.level_count() > 0:
            self._cascade_widget.setFixedHeight(56)

    def _on_cascade_changed(self, level: int, option_index: int) -> None:
        self._cascade_model.set_selected(level, option_index)
        raw = self._cascade_model.get_raw_at(level)

        if raw:
            path = self._get_path_up_to(level)
            if path and level + 1 < self._cascade_model.level_count():
                self._fill_cascade_level(level + 1, path)
            else:
                self._cascade_model.clear_from(level + 1)
        else:
            self._cascade_model.clear_from(level + 1)

        self._update_window_title()

        # Cascade change means the last run no longer applies to this selection
        self._last_context_path = None
        self._resume_button.setEnabled(False)

        self._update_run_button()
        self._refresh_test_data_panel()

    def _get_selected_hierarchy(self) -> list[str]:
        result = []
        for level in range(self._cascade_model.level_count()):
            raw = self._cascade_model.get_raw_at(level)
            if not raw:
                break
            result.append(raw)
        return result

    def _get_path_up_to(self, level_index: int) -> Optional[Path]:
        if not self._current_system:
            return None
        path = SYSTEMS_DIR / self._current_system
        for li in range(level_index + 1):
            raw = self._cascade_model.get_raw_at(li)
            if not raw:
                return None
            path = path / raw
        return path

    def _resolve_tests_yaml(self) -> Optional[Path]:
        n = self._cascade_model.level_count()
        if n == 0:
            return None
        for level in range(n - 1, -1, -1):
            path = self._get_path_up_to(level)
            if path is None:
                continue
            for fname in ("run_sequence.yaml", "tests.yaml"):
                yaml_path = path / fname
                if yaml_path.is_file():
                    return yaml_path
        return None

    # ------------------------------------------------------------------ #
    # Script list                                                          #
    # ------------------------------------------------------------------ #

    def _populate_test_list(self) -> None:
        tests_yaml = self._resolve_tests_yaml()
        if tests_yaml is None:
            self._script_model.clear()
            self._selection_bridge.reset()
            return
        scripts = utils.load_tests_yaml(tests_yaml)
        self._script_model.set_scripts(scripts)

        # Publish unique tags for the QML chip-filter row
        all_tags: list[str] = []
        for s in scripts:
            raw = s.get("tags") or []
            all_tags.extend([str(t) for t in raw] if isinstance(raw, list) else ([str(raw)] if raw else []))
        self._tags_bridge.set_tags(all_tags)

        # Load sparkline histories from the metrics DB (one round-trip)
        names = [s["name"] for s in scripts]
        histories = history_db.get_all_script_histories(names)
        for name, statuses in histories.items():
            self._script_model.set_script_history(name, statuses)
        self._selection_bridge.reset()

    def _update_run_button(self) -> None:
        has_tests = self._resolve_tests_yaml() is not None
        self._populate_test_list()
        self._full_run_button.setEnabled(has_tests)
        self._single_run_button.setEnabled(
            has_tests and self._selection_bridge.currentRow >= 0
        )

    def _on_test_selection_changed(self, row: int) -> None:
        has_tests = self._resolve_tests_yaml() is not None
        self._single_run_button.setEnabled(has_tests and row >= 0)

    # ------------------------------------------------------------------ #
    # Run control                                                          #
    # ------------------------------------------------------------------ #

    def _on_refresh_clicked(self) -> None:
        # _populate_system_dropdown saves the current system, rescans the
        # filesystem, and re-fires _on_system_changed to rebuild the cascade
        # in-place when the previous selection still exists. Don't clobber
        # the cascade afterwards — doing so blanks out the dropdowns and
        # leaves the combo at its restored index, so re-picking the same
        # system fires no currentIndexChanged and the cascade never returns.
        self._populate_system_dropdown()
        self._status_bar.showMessage("Refreshed.")

    # ------------------------------------------------------------------ #
    # Script sync                                                          #
    # ------------------------------------------------------------------ #

    def _auto_sync_on_startup(self) -> None:
        """Start a background git pull on launch if the sidecar is a git repo."""
        if not is_git_repo(SYSTEMS_DIR):
            return
        self._status_bar.showMessage("Syncing scripts…")
        self._sync_worker = ScriptSyncWorker(SYSTEMS_DIR, parent=self)
        self._sync_worker.sync_finished.connect(self._on_sync_finished)
        self._sync_worker.start()

    def _on_sync_finished(self, success: bool, message: str) -> None:
        self._status_bar.showMessage(f"Sync: {message}")
        if success:
            # Reload the system dropdown so any newly added/renamed scripts appear
            self._on_refresh_clicked()

    def _on_full_run_clicked(self) -> None:
        self.register_input_handler()
        self._start_run(script_name_filter=None)

    def _on_single_run_clicked(self) -> None:
        self.register_input_handler()
        entry = self._script_model.script_at(self._selection_bridge.currentRow)
        if not entry:
            self._status_bar.showMessage("No test selected.")
            return
        self._start_run(script_name_filter=entry["name"])

    def _on_clear_console(self) -> None:
        self._log_model.clear()
        self._app_backend.clear_screenshots()

    def _on_open_folder_clicked(self) -> None:
        if self._last_run_root:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self._last_run_root))

    def _on_view_report_clicked(self) -> None:
        if self._last_run_root:
            report = Path(self._last_run_root) / "run_report.html"
            if report.is_file():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(report)))

    # ------------------------------------------------------------------
    # Storage guard
    # ------------------------------------------------------------------

    @staticmethod
    def _orbit_data_size_gb() -> float:
        try:
            return (
                sum(f.stat().st_size for f in ORBIT_DATA_DIR.rglob("*") if f.is_file())
                / 1e9
            )
        except Exception:
            return 0.0

    def _check_storage(self) -> bool:
        limit_gb  = float(os.getenv("ORBIT_STORAGE_LIMIT_GB",  "20"))
        warn_pct  = float(os.getenv("ORBIT_STORAGE_WARN_PCT",  "80"))
        used_gb   = self._orbit_data_size_gb()
        threshold = limit_gb * warn_pct / 100.0

        if used_gb < threshold:
            return True

        pct_used = (used_gb / limit_gb * 100) if limit_gb else 0

        box = QMessageBox(self)
        box.setWindowTitle("Storage Warning")
        box.setIcon(QMessageBox.Icon.Warning)
        box.setText(
            f"orbit_data/ is using <b>{used_gb:.1f} GB</b> of your "
            f"<b>{limit_gb:.0f} GB</b> limit ({pct_used:.0f}%).<br><br>"
        )
        box.setTextFormat(Qt.TextFormat.RichText)

        prune_btn    = box.addButton("Prune Old Runs",   QMessageBox.ButtonRole.ActionRole)
        archive_btn  = box.addButton("Archive…",         QMessageBox.ButtonRole.ActionRole)
        continue_btn = box.addButton("Continue Anyway",  QMessageBox.ButtonRole.AcceptRole)
        cancel_btn   = box.addButton("Cancel",           QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(cancel_btn)

        box.exec()
        clicked = box.clickedButton()

        if clicked is cancel_btn:
            return False

        if clicked is prune_btn:
            self._prune_runs(keep=100)

        elif clicked is archive_btn:
            if not self._archive_old_runs(keep=100):
                return False  # user cancelled the folder picker

        return True  # continue_btn or post-action

    def _prune_runs(self, keep: int = 100) -> None:
        try:
            folders = sorted(
                (d for d in RUNS_DIR.iterdir() if d.is_dir()),
                key=lambda d: d.stat().st_mtime,
            )
            to_delete = folders[: max(0, len(folders) - keep)]
            for old in to_delete:
                shutil.rmtree(old, ignore_errors=True)
            after_gb = self._orbit_data_size_gb()
            self._append_log(
                f"Pruned {len(to_delete)} run folder(s). "
                f"orbit_data/ now {after_gb:.1f} GB.",
                _CLR_DIM,
            )
        except Exception:
            pass

    def _archive_old_runs(self, keep: int = 100) -> bool:
        dest = QFileDialog.getExistingDirectory(
            self,
            "Choose Archive Destination",
            str(Path.home()),
        )
        if not dest:
            return False

        dest_path = Path(dest)
        try:
            folders = sorted(
                (d for d in RUNS_DIR.iterdir() if d.is_dir()),
                key=lambda d: d.stat().st_mtime,
            )
            to_move = folders[: max(0, len(folders) - keep)]
            moved = 0
            for src in to_move:
                shutil.move(str(src), str(dest_path / src.name))
                moved += 1
            after_gb = self._orbit_data_size_gb()
            self._append_log(
                f"Archived {moved} run folder(s) to {dest_path}. "
                f"orbit_data/ now {after_gb:.1f} GB.",
                _CLR_DIM,
            )
        except Exception:
            pass

        return True

    # ------------------------------------------------------------------

    def _preflight_check(
        self, tests_yaml: Path, script_name_filter: Optional[str]
    ) -> list[str]:
        scripts = utils.load_tests_yaml(tests_yaml)
        if script_name_filter:
            scripts = [s for s in scripts if s.get("name") == script_name_filter]

        errors: list[str] = []
        base = tests_yaml.parent
        for s in scripts:
            name = s.get("name", "<unnamed>")
            rel  = s.get("path", "")
            path = base / rel
            if not path.is_file():
                errors.append(f"  • {name}: file not found ({rel})")
                continue
            if path.suffix.lower() == ".py":
                try:
                    py_compile.compile(str(path), doraise=True)
                except py_compile.PyCompileError as exc:
                    errors.append(f"  • {name}: syntax error — {exc.msg}")
        return errors

    def _start_run(
        self,
        script_name_filter: Optional[str],
        resume_context_path: Optional[Path] = None,
    ) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._status_bar.showMessage("A run is already in progress.")
            return

        tests_yaml = self._resolve_tests_yaml()
        if tests_yaml is None:
            self._status_bar.showMessage("No valid test set selected.")
            return

        # Storage guard: warn if orbit_data/ is approaching the configured limit
        if not self._check_storage():
            return

        # ── Test data pre-flight checks ───────────────────────────────────
        td_cfg = utils.load_test_data_config(tests_yaml)
        if td_cfg and td_cfg.get("path"):
            td_excel = self._resolve_test_data_excel_path(td_cfg)
            if td_excel and td_excel.exists():
                from orbit360.utils.excel_data_manager import (
                    get_summary, reset_rows, recover_stale_claims,
                    STALE_CLAIM_MINUTES,
                )

                # reset_on_run: auto-reset pool before this run starts
                if td_cfg.get("reset_on_run") and not script_name_filter:
                    reset_count = reset_rows(td_excel)
                    if reset_count:
                        self._append_log(
                            f"reset_on_run: {reset_count} row(s) reset to Available"
                            f" ({td_excel.name})",
                            _CLR_AMBER,
                        )

                summary = get_summary(td_excel)

                # Stale claim recovery — auto-recover without prompting
                if summary.get("stale", 0):
                    recovered = recover_stale_claims(td_excel)
                    if recovered:
                        self._append_log(
                            f"Stale claim recovery: {recovered} row(s) returned to"
                            f" Available (>{STALE_CLAIM_MINUTES} min idle)",
                            _CLR_AMBER,
                        )
                        summary = get_summary(td_excel)   # refresh after recovery

                # Pool exhaustion guard — warn if no rows available
                if summary["total"] > 0 and summary["available"] == 0 and not script_name_filter:
                    done  = summary["pass"] + summary["fail"] + summary["skip"]
                    inuse = summary["claimed"]
                    box = QMessageBox(self)
                    box.setWindowTitle("Test Data Pool Empty")
                    box.setIcon(QMessageBox.Icon.Warning)
                    box.setText(
                        f"No available rows in {td_excel.name}.\n\n"
                        f"{done} done, {inuse} in use, {summary['total']} total."
                    )
                    box.setInformativeText(
                        "Reset the pool to re-run, or continue anyway if scripts "
                        "don't depend on this data file."
                    )
                    reset_btn = box.addButton("Reset Pool & Run", QMessageBox.ButtonRole.AcceptRole)
                    box.addButton("Run Anyway", QMessageBox.ButtonRole.DestructiveRole)
                    box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
                    box.exec()
                    clicked = box.clickedButton()
                    if clicked is None or clicked.text() == "Cancel":
                        return
                    if clicked is reset_btn:
                        reset_rows(td_excel)
                        self._append_log(
                            f"Pool reset: all rows in {td_excel.name} returned to Available.",
                            _CLR_AMBER,
                        )

        # Pre-flight: warn if any scripts have missing files or syntax errors
        issues = self._preflight_check(tests_yaml, script_name_filter)
        if issues:
            detail = "\n".join(issues)
            box = QMessageBox(self)
            box.setWindowTitle("Pre-flight Warning")
            box.setIcon(QMessageBox.Icon.Warning)
            box.setText(
                f"{len(issues)} script(s) have issues that will cause them to fail:"
            )
            box.setDetailedText(detail)
            box.setStandardButtons(
                QMessageBox.StandardButton.Ok | QMessageBox.StandardButton.Cancel
            )
            box.button(QMessageBox.StandardButton.Ok).setText("Run Anyway")
            box.button(QMessageBox.StandardButton.Cancel).setText("Cancel")
            if box.exec() == QMessageBox.StandardButton.Cancel:
                return

        label = script_name_filter or "Full Run"
        self._script_model.reset_statuses()
        self._append_log(f"Starting run: {self._current_system}  [{label}]", _CLR_BLUE)
        self._append_log(f"Test set: {tests_yaml}", _CLR_DIM)
        self._append_log("─" * 60, _CLR_SURFACE)

        self._worker = RunWorker(
            self._current_system, tests_yaml,
            hierarchy=self._get_selected_hierarchy(),
            script_name_filter=script_name_filter,
            selected_row_index=self._test_data_selected_row_index,
            resume_context_path=resume_context_path,
            parent=self,
        )
        # ── Forward worker signals to event bus ───────────────────────────
        # The bus decouples producers (workers) from consumers (GUI, headless
        # logger, future webhooks).  Handlers remain unchanged — they now
        # receive events via the bus instead of directly from the worker.
        _bus = _event_bus
        self._worker.run_started.connect(_bus.run_started)
        self._worker.script_started.connect(_bus.script_started)
        self._worker.script_finished.connect(_bus.script_finished)
        self._worker.progress_updated.connect(_bus.progress_updated)
        self._worker.run_completed.connect(_bus.run_completed)
        self._worker.run_aborted.connect(_bus.run_aborted)
        self._worker.run_failed.connect(_bus.run_failed)
        self._worker.manual_input_required.connect(_bus.manual_input_required)
        self._worker.failure_input_required.connect(_bus.failure_input_required)
        self._worker.value_input_requested.connect(_bus.value_input_requested)
        self._worker.finished.connect(_bus.worker_finished)

        # ── Subscribe handlers to bus (UniqueConnection prevents double-fire
        #    if _start_run is called again without a worker restart) ───────
        _ct = Qt.ConnectionType.UniqueConnection
        _bus.script_started.connect(self._on_script_started, _ct)
        _bus.script_finished.connect(self._on_script_finished, _ct)
        _bus.progress_updated.connect(self._on_progress_updated, _ct)
        _bus.run_completed.connect(self._on_run_completed, _ct)
        _bus.run_aborted.connect(self._on_run_aborted, _ct)
        _bus.run_failed.connect(self._on_run_failed, _ct)
        _bus.manual_input_required.connect(self._on_manual_input_required, _ct)
        _bus.failure_input_required.connect(self._on_failure_input_required, _ct)
        _bus.value_input_requested.connect(self._on_value_input_requested, _ct)
        _bus.worker_finished.connect(self._on_worker_finished, _ct)

        self._full_run_button.setVisible(False)
        self._single_run_button.setVisible(False)
        self._stop_button.setVisible(True)
        self._stop_button.setEnabled(True)
        self._resume_button.setVisible(True)
        self._resume_button.setEnabled(False)
        self._status_bar.showMessage(f"Running: {self._current_system}")

        # In parallel mode switch to the swimlane view and pre-create one lane
        # per script so QML delegates are stable before the first line arrives.
        self._parallel_active = int(os.environ.get("ORBIT_PARALLEL", "1")) > 1
        if self._parallel_active:
            all_scripts = utils.load_tests_yaml(tests_yaml)
            scripts = (
                [s for s in all_scripts if s["name"] == script_name_filter]
                if script_name_filter else all_scripts
            )
            self._app_backend.setup_lanes([s["name"] for s in scripts])
            self._log_stack.setCurrentIndex(1)
        else:
            self._app_backend.setup_lanes([])
            self._log_stack.setCurrentIndex(0)

        # Notify the Command Deck panel that a live run is starting
        if hasattr(self, "_deck_panel"):
            _live_scripts = utils.load_tests_yaml(tests_yaml)
            if script_name_filter:
                _live_scripts = [s for s in _live_scripts if s["name"] == script_name_filter]
            self._deck_panel.set_live_run(self._current_system, len(_live_scripts))

        self._worker.start()

    def _on_resume_clicked(self) -> None:
        if self._last_context_path and self._last_context_path.is_file():
            self._start_run(
                script_name_filter=None,
                resume_context_path=self._last_context_path,
            )

    def _on_abort_clicked(self) -> None:
        if self._worker:
            self._worker.request_abort()
            self._stop_button.setEnabled(False)
            self._continue_button.setVisible(False)
            self._skip_step_button.setVisible(False)
            self._manual_complete_button.setVisible(False)
            self._mark_failed_button.setVisible(False)
            self._set_recovery_banner(False)
            self._status_bar.showMessage("Abort requested — finishing current script...")

    def _on_manual_input_required(self, _prompt: str) -> None:
        self._continue_button.setVisible(True)
        self._set_recovery_banner(True)
        self._status_bar.showMessage(
            "Manual step required — complete the action then click Continue"
        )

    def _on_continue_clicked(self) -> None:
        if self._worker:
            self._worker.send_input("\n")
        self._continue_button.setVisible(False)
        self._skip_step_button.setVisible(False)
        self._manual_complete_button.setVisible(False)
        self._mark_failed_button.setVisible(False)
        self._set_recovery_banner(False)
        self._status_bar.showMessage(f"Running: {self._current_system}")

    def _on_failure_input_required(self, _prompt: str) -> None:
        """Show Continue + recovery action buttons when a failure recovery prompt fires."""
        self._continue_button.setVisible(True)
        self._skip_step_button.setVisible(True)
        self._manual_complete_button.setVisible(True)
        self._mark_failed_button.setVisible(True)
        self._set_recovery_banner(True)
        self._status_bar.showMessage(
            "Script failed — fix in browser, then choose an outcome"
        )

    def _on_skip_step_clicked(self) -> None:
        """Analyst chose to skip the failed step and try to continue automation."""
        if self._worker:
            self._worker.send_input("s\n")
        self._continue_button.setVisible(False)
        self._skip_step_button.setVisible(False)
        self._manual_complete_button.setVisible(False)
        self._mark_failed_button.setVisible(False)
        self._set_recovery_banner(False)
        self._status_bar.showMessage(f"Running: {self._current_system}")

    def _on_manual_complete_clicked(self) -> None:
        """Analyst manually completed all remaining steps — mark run as manual_complete."""
        if self._worker:
            self._worker.send_input("y\n")
        self._continue_button.setVisible(False)
        self._skip_step_button.setVisible(False)
        self._manual_complete_button.setVisible(False)
        self._mark_failed_button.setVisible(False)
        self._set_recovery_banner(False)
        self._status_bar.showMessage(f"Running: {self._current_system}")

    def _on_mark_failed_clicked(self) -> None:
        """Analyst chose to mark the run as failed with no recovery."""
        if self._worker:
            self._worker.send_input("n\n")
        self._continue_button.setVisible(False)
        self._skip_step_button.setVisible(False)
        self._manual_complete_button.setVisible(False)
        self._mark_failed_button.setVisible(False)
        self._set_recovery_banner(False)
        self._status_bar.showMessage(f"Running: {self._current_system}")

    def _on_value_input_requested(self, field: str) -> None:
        """Show OrbitInputDialog when a script calls prompt_value()."""
        dialog = OrbitInputDialog([field], self)
        if dialog.exec():
            value = dialog.inputs.get(field.lower(), "")
        else:
            value = ""
        if self._worker:
            self._worker.send_input(value)

    # ------------------------------------------------------------------ #
    # RunWorker signal handlers                                            #
    # ------------------------------------------------------------------ #

    def _on_script_started(
        self, script_name: str, script_index: int, total_scripts: int
    ) -> None:
        self._script_model.set_script_status(script_name, "running")
        self._progress_label.setText(f"[{script_index + 1} / {total_scripts}]")
        self._progress_label.show()
        self._script_start_mono = time.monotonic()
        self._active_script_name = script_name
        self._last_prog_line   = ""
        self._last_prog_script = ""
        self._last_prog_count  = 0
        self._elapsed_timer.start()
        self._progress_bar.setValue(script_index)
        if script_index == 0:
            self._progress_bar.setRange(0, total_scripts)
            self._progress_bar.setVisible(True)
        self.setWindowTitle(
            f"▶ {script_name}  [{script_index + 1}/{total_scripts}] — Orbit360"
        )
        # AppBackend updates lane dot color; in sequential mode write to log
        if not self._parallel_active:
            self._append_log("")
            self._append_log(
                f"[{script_index + 1}/{total_scripts}] Running: {script_name}", _CLR_BLUE
            )
        self._status_bar.showMessage(
            f"{self._current_system} — [{script_index + 1}/{total_scripts}] {script_name}"
        )

    def _on_script_finished(self, result: object) -> None:
        self._elapsed_timer.stop()
        self._active_script_name = ""
        self._progress_bar.setValue(self._progress_bar.value() + 1)
        from orbit360.orbit_logger import ScriptResult
        if not isinstance(result, ScriptResult):
            return

        duration_str = utils.format_duration(result.duration_seconds)
        self._current_run_results.append(result)
        self._script_model.set_script_status(result.script_name, result.status)
        self._script_model.set_script_duration(result.script_name, result.duration_seconds)
        self._refresh_test_data_panel()

        # AppBackend updates lane dot color; write completion line to log in sequential
        if not self._parallel_active:
            if result.status == "passed":
                self._append_log(f"  -> passed ({duration_str})", _CLR_GREEN)
            elif result.status == "manual_complete":
                self._append_log(f"  -> MANUAL COMPLETE ({duration_str})", _CLR_AMBER)
            elif result.status == "failed":
                self._append_log(f"  -> FAILED ({duration_str})", _CLR_RED)
                lines = result.stdout.splitlines()
                error_lines = [
                    ln for ln in lines
                    if any(k in ln for k in ("ERROR", "CRITICAL", "SCRIPT FAILED"))
                ]
                hint_raw = (
                    error_lines[-1].strip() if error_lines
                    else "\n".join(lines[-3:]).strip()
                )
                if hint_raw:
                    parts = hint_raw.split("|", 1)
                    hint = parts[1].strip() if len(parts) == 2 else hint_raw
                    self._append_log(f"     {hint[:300]}", _CLR_RED)
            else:
                self._append_log(
                    f"  -> ERROR ({duration_str}): "
                    f"{result.stderr[:200] or result.stdout[-200:]}",
                    _CLR_ORANGE,
                )

    def _on_progress_updated(self, script_name: str, message: str) -> None:
        color = _log_line_color(message)
        # Strip the "LEVEL    | " prefix that the pipe-mode formatter adds for
        # color detection — it's an implementation detail, not display content.
        parts = message.split("|", 1)
        if len(parts) == 2:
            level_token = parts[0].strip().upper()
            if level_token == "DEBUG":
                return
            msg_body = parts[1].strip()
            if msg_body.startswith("─"):
                display = msg_body
            else:
                display = f"  | {msg_body}"
        else:
            display = f"  | {message}"

        # In parallel mode AppBackend routes lines to the QML swimlane lanes.
        if self._parallel_active and script_name:
            return

        # ── Consecutive-duplicate suppressor (sequential mode) ────────────
        if display == self._last_prog_line and script_name == self._last_prog_script:
            self._last_prog_count += 1
            self._log_model.update_last(
                f"{display}  (\u00d7{self._last_prog_count})", color
            )
        else:
            self._last_prog_line   = display
            self._last_prog_script = script_name
            self._last_prog_count  = 1
            self._append_log(display, color)

    def _on_run_completed(
        self, summary_path: str, passed: int, failed: int, errored: int
    ) -> None:
        total = passed + failed + errored
        all_passed = failed == 0 and errored == 0
        self._append_log("")
        self._append_log("═" * 60, _CLR_SURFACE)
        self._append_log(
            f"Run complete: {passed}/{total} passed"
            + (f", {failed} failed" if failed else "")
            + (f", {errored} error(s)" if errored else ""),
            _CLR_GREEN if all_passed else _CLR_RED,
        )
        self._append_log(f"Summary: {summary_path}", _CLR_DIM)
        self._status_bar.showMessage(
            f"Done — {passed} passed, {failed} failed, {errored} errors"
        )
        self._last_run_root = str(Path(summary_path).parent)
        self._open_folder_button.setEnabled(True)
        report = Path(summary_path).parent / "run_report.html"
        self._view_report_button.setEnabled(report.is_file())
        self._update_resume_button(summary_path)
        body = f"{passed}/{total} passed"
        if failed:  body += f", {failed} failed"
        if errored: body += f", {errored} errored"
        self._notify("Orbit360 — Run Complete", body, success=all_passed)
        self._record_and_refresh_history(summary_path)
        self._generate_trend_report()
        self._test_data_selected_row_index = None
        self._test_data_pin_lbl.setVisible(False)


    def _generate_trend_report(self) -> None:
        """Regenerate the cross-run trend report in a background thread."""
        import threading
        def _worker():
            try:
                from orbit360.utils.orbit_report import generate_trend_report
                path = generate_trend_report(ORBIT_DATA_DIR)
                self._append_log(f"Trend report updated: {path}", _CLR_DIM)
            except Exception as exc:  # never crash the UI
                self._append_log(f"Trend report skipped: {exc}", _CLR_DIM)
        threading.Thread(target=_worker, daemon=True).start()


    def _on_run_aborted(
        self, summary_path: str, passed: int, failed: int, errored: int
    ) -> None:
        total = passed + failed + errored
        self._append_log("")
        self._append_log("─" * 60, _CLR_SURFACE)
        self._append_log(
            f"Run stopped by user — {passed}/{total} completed"
            + (f", {failed} failed" if failed else "")
            + (f", {errored} error(s)" if errored else ""),
            _CLR_ORANGE,
        )
        self._append_log(f"Summary: {summary_path}", _CLR_DIM)
        self._status_bar.showMessage(
            f"Stopped — {passed} passed, {failed} failed, {errored} errors"
        )
        self._last_run_root = str(Path(summary_path).parent)
        self._open_folder_button.setEnabled(True)
        report = Path(summary_path).parent / "run_report.html"
        self._view_report_button.setEnabled(report.is_file())
        self._update_resume_button(summary_path)
        run_total = passed + failed + errored
        self._notify(
            "Orbit360 — Run Stopped",
            f"{passed}/{run_total} completed before stop",
            success=False,
        )
        self._record_and_refresh_history(summary_path)
        self._test_data_selected_row_index = None
        self._test_data_pin_lbl.setVisible(False)

    def _update_resume_button(self, summary_path: str) -> None:
        """Enable Resume if context.json shows partial completion (some passed, some not)."""
        context_p = Path(summary_path).parent / "context.json"
        self._last_context_path = None
        self._resume_button.setEnabled(False)
        if not context_p.is_file():
            return
        try:
            ctx = json.loads(context_p.read_text(encoding="utf-8"))
            statuses = [s.get("status") for s in ctx.get("scripts", [])]
            has_passed = any(s in ("passed", "manual_complete") for s in statuses)
            has_incomplete = any(s not in ("passed", "manual_complete") for s in statuses)
            if has_passed and has_incomplete:
                self._last_context_path = context_p
                self._resume_button.setEnabled(True)
        except Exception:
            pass

    def _record_and_refresh_history(self, summary_path: str) -> None:
        if not self._current_run_results:
            return
        from datetime import datetime, timezone
        run_id    = Path(summary_path).parent.name
        system    = self._current_system or ""
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        duration  = time.monotonic() - self._run_start_time
        history_db.record_run(run_id, system, timestamp, self._current_run_results, duration)

        # Refresh sparklines for the scripts that just ran
        names     = [r.script_name for r in self._current_run_results]
        histories = history_db.get_all_script_histories(names)
        for name, statuses in histories.items():
            self._script_model.set_script_history(name, statuses)

        # Refresh Command Deck recent-runs panel
        if hasattr(self, "_deck_panel"):
            self._deck_panel.on_run_completed()

    def _on_run_failed(self, error_message: str) -> None:
        self._append_log("")
        self._append_log(f"RUN FAILED: {error_message}", _CLR_RED)
        self._status_bar.showMessage("Run failed — see log for details")

    def _on_worker_finished(self) -> None:
        if hasattr(self, "_deck_panel"):
            self._deck_panel.clear_live_run()
        self._elapsed_timer.stop()
        self._active_script_name = ""
        self._parallel_active    = False
        self._log_stack.setCurrentIndex(0)   # restore sequential log view
        self._progress_bar.setVisible(False)
        self._update_window_title()
        # AppBackend clears the watcher via bus.worker_finished
        has_tests = self._resolve_tests_yaml() is not None
        self._full_run_button.setEnabled(has_tests)
        self._single_run_button.setEnabled(
            has_tests and self._selection_bridge.currentRow >= 0
        )
        self._full_run_button.setVisible(True)
        self._single_run_button.setVisible(True)
        self._stop_button.setVisible(False)
        self._stop_button.setEnabled(False)
        self._resume_button.setVisible(False)
        self._continue_button.setVisible(False)
        self._set_recovery_banner(False)
        self._view_report_button.setEnabled(False)
        self._progress_label.hide()
        self._worker = None

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #


    def _setup_tray(self) -> None:
        self._tray_manager = TrayManager(self)

    def _notify(self, title: str, body: str, success: bool = True) -> None:
        """Show a native OS notification; falls back silently when unavailable."""
        if not hasattr(self, "_tray_manager"):
            return
        icon = (
            QSystemTrayIcon.MessageIcon.Information
            if success
            else QSystemTrayIcon.MessageIcon.Warning
        )
        self._tray_manager.notify(title, body, icon)

    def closeEvent(self, event) -> None:
        """Minimize to tray on close if tray is available; otherwise quit."""
        if hasattr(self, "_tray_manager") and self._tray_manager.available:
            event.ignore()
            self.hide()
            self._tray_manager.notify(
                "Orbit360",
                "Running in the background. Double-click the tray icon to restore.",
                ms=3000,
            )
        else:
            event.accept()

    def _wire_shortcuts(self) -> None:
        run_sc    = QShortcut(QKeySequence("F5"),     self)
        stop_sc   = QShortcut(QKeySequence("Escape"), self)
        search_sc = QShortcut(QKeySequence("Ctrl+F"), self)
        run_sc.activated.connect(
            lambda: self._full_run_button.click() if self._full_run_button.isEnabled() else None
        )
        stop_sc.activated.connect(
            lambda: self._stop_button.click() if self._stop_button.isEnabled() else None
        )
        search_sc.activated.connect(self._log_bridge.openSearch)

    def _on_elapsed_tick(self) -> None:
        if not self._active_script_name:
            return
        elapsed = int(time.monotonic() - self._script_start_mono)
        mins, secs = divmod(elapsed, 60)
        ts = f"{mins}:{secs:02d}" if mins > 0 else f"0:{secs:02d}"
        self._status_bar.showMessage(
            f"{self._current_system} — {self._active_script_name}  ({ts})"
        )

    def _append_log(self, text: str, color: str = _CLR_TEXT) -> None:
        for line in text.split("\n"):
            self._log_model.append(line, color)

# ---------------------------------------------------------------------------
# Module-level UI helpers
# ---------------------------------------------------------------------------

def _placeholder_view(icon: str, title: str, description: str) -> QWidget:
    """Full-screen placeholder card for screens not yet built."""
    w = QWidget()
    w.setStyleSheet("background: #0a0e1a;")
    vl = QVBoxLayout(w)
    vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    vl.setSpacing(12)

    icon_lbl = QLabel(icon)
    icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    icon_lbl.setStyleSheet("color: #2a4a6a; font-size: 52px; background: transparent;")
    vl.addWidget(icon_lbl)

    title_lbl = QLabel(title)
    title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    title_lbl.setStyleSheet(
        "color: #3a5a88; font-size: 22px; font-weight: bold; "
        "letter-spacing: 3px; background: transparent;"
    )
    vl.addWidget(title_lbl)

    phase_lbl = QLabel("Coming in Phase 2")
    phase_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    phase_lbl.setStyleSheet("color: #89b4fa; font-size: 12px; background: transparent;")
    vl.addWidget(phase_lbl)

    desc_lbl = QLabel(description)
    desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    desc_lbl.setStyleSheet("color: #2a3a55; font-size: 12px; background: transparent;")
    vl.addWidget(desc_lbl)

    return w


def _vline(layout: QHBoxLayout) -> None:
    """Insert a thin vertical separator into a horizontal layout."""
    sep = QFrame()
    sep.setFrameShape(QFrame.Shape.VLine)
    sep.setStyleSheet("background: #1a2a40; max-width: 1px; border: none;")
    sep.setFixedWidth(1)
    layout.addWidget(sep)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("Orbit360")
    app.setApplicationVersion("4.0")
    window = Ready360Window()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
