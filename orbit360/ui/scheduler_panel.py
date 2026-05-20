"""
orbit360/ui/scheduler_panel.py
Scheduled-run panel for Orbit360.

Schedules are persisted to ORBIT_DATA_DIR/schedules.json.
A QTimer fires every 60 s to check whether any enabled schedule is due;
when one is, trigger_run(system, cascade) is emitted so main_window can
navigate to the Launcher and start the run.

Schedule record (JSON):
{
    "id":         "<8-char hex>",
    "label":      "CAC / QA / CER — Full Regression",
    "system":     "CAC",
    "cascade":    ["QA", "CER", "FullRegression"],
    "time":       "08:00",          -- HH:MM 24-hour
    "days":       [0,1,2,3,4],      -- 0=Mon … 6=Sun; [] = fire once
    "enabled":    true,
    "last_fired": null | "YYYY-MM-DD"
}
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from PySide6.QtCore import QSize, Qt, QTime, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from orbit360.utils import utils
from orbit360.utils.paths import ORBIT_DATA_DIR, SYSTEMS_DIR

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

_SCHEDULES_FILE = ORBIT_DATA_DIR / "schedules.json"

_DAY_NAMES  = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
_DAY_PRESET = {
    "Every day":  list(range(7)),
    "Weekdays":   list(range(5)),
    "Weekends":   [5, 6],
    "Custom":     [],
}

_BTN = """
QPushButton {{
    background: {bg};
    border: 1px solid {bd};
    border-radius: 4px;
    color: {fg};
    font-size: 11px;
    padding: 3px 10px;
}}
QPushButton:hover {{ border-color: {ac}; color: {ac}; }}
"""

_COMBO_SHEET = f"""
QComboBox {{
    background: #111c30;
    border: 1px solid {_BORDER};
    border-radius: 4px;
    color: {_TEXT};
    font-size: 11px;
    padding: 3px 8px;
}}
QComboBox::drop-down {{ border: none; width: 18px; }}
QComboBox QAbstractItemView {{
    background: #0d1520;
    border: 1px solid {_BORDER};
    color: {_TEXT};
    selection-background-color: #132240;
}}
"""


# ── Helpers ──────────────────────────────────────────────────────────────────

def _load_schedules() -> list[dict]:
    if not _SCHEDULES_FILE.exists():
        return []
    try:
        with open(_SCHEDULES_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_schedules(schedules: list[dict]) -> None:
    ORBIT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(_SCHEDULES_FILE, "w", encoding="utf-8") as f:
        json.dump(schedules, f, indent=2)


def _next_fire(schedule: dict) -> str:
    """Return a human-readable next-fire description."""
    if not schedule.get("enabled"):
        return "Disabled"
    hm   = schedule.get("time", "00:00")
    days = schedule.get("days", [])
    now  = datetime.now()
    h, m = (int(x) for x in hm.split(":"))

    if not days:
        last = schedule.get("last_fired")
        if last:
            return "Done (one-shot)"
        today_fire = now.replace(hour=h, minute=m, second=0, microsecond=0)
        if now >= today_fire:
            return "Missed today"
        return f"Today at {hm}"

    # Find next weekday that matches
    for offset in range(8):
        candidate = (now + timedelta(days=offset)).replace(
            hour=h, minute=m, second=0, microsecond=0
        )
        if offset == 0 and now >= candidate:
            continue
        if candidate.weekday() in days:
            if offset == 0:
                return f"Today at {hm}"
            if offset == 1:
                return f"Tomorrow at {hm}"
            return f"{_DAY_NAMES[candidate.weekday()]} at {hm}"
    return "—"


def _is_due(schedule: dict) -> bool:
    """True if this schedule should fire right now (within the current minute)."""
    if not schedule.get("enabled"):
        return False
    hm   = schedule.get("time", "00:00")
    days = schedule.get("days", [])
    now  = datetime.now()
    h, m = (int(x) for x in hm.split(":"))

    if now.hour != h or now.minute != m:
        return False

    today_str = date.today().isoformat()
    if schedule.get("last_fired") == today_str:
        return False

    if not days:
        # One-shot — fire if never fired
        return schedule.get("last_fired") is None

    return now.weekday() in days


# ── Add/Edit dialog ──────────────────────────────────────────────────────────

class _AddScheduleDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Add Schedule")
        self.setMinimumWidth(420)
        self.setStyleSheet(f"""
            QDialog {{ background: {_BG}; color: {_TEXT}; }}
            QLabel  {{ color: {_TEXT}; font-size: 11px; background: transparent; }}
        """)

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 18, 20, 16)
        root.setSpacing(12)

        # ── System ───────────────────────────────────────────────────────
        root.addWidget(_field_label("System"))
        self._sys_combo = QComboBox()
        self._sys_combo.setStyleSheet(_COMBO_SHEET)
        self._sys_combo.addItem("")
        for raw in utils.scan_subdirectories(SYSTEMS_DIR):
            disp = utils.resolve_display_name(
                raw, utils.load_display_names(SYSTEMS_DIR / "display_names.json")
            )
            self._sys_combo.addItem(disp, userData=raw)
        self._sys_combo.currentIndexChanged.connect(self._on_system_changed)
        root.addWidget(self._sys_combo)

        # ── Cascade levels (up to 5, shown dynamically) ──────────────────
        self._cascade_frame = QWidget()
        self._cascade_frame.setStyleSheet("background: transparent;")
        self._cascade_layout = QVBoxLayout(self._cascade_frame)
        self._cascade_layout.setContentsMargins(0, 0, 0, 0)
        self._cascade_layout.setSpacing(6)
        self._level_combos: list[QComboBox] = []
        for _ in range(5):
            cb = QComboBox()
            cb.setStyleSheet(_COMBO_SHEET)
            cb.setVisible(False)
            self._level_combos.append(cb)
            self._cascade_layout.addWidget(cb)
        root.addWidget(self._cascade_frame)

        # wire each level to populate the next
        for i, cb in enumerate(self._level_combos):
            cb.currentIndexChanged.connect(
                lambda _idx, lvl=i: self._on_level_changed(lvl)
            )

        # ── Time ─────────────────────────────────────────────────────────
        root.addWidget(_field_label("Time (24-hour)"))
        self._time_edit = QTimeEdit()
        self._time_edit.setDisplayFormat("HH:mm")
        self._time_edit.setTime(QTime(8, 0))
        self._time_edit.setStyleSheet(f"""
            QTimeEdit {{
                background: #111c30;
                border: 1px solid {_BORDER};
                border-radius: 4px;
                color: {_TEXT};
                font-size: 11px;
                padding: 3px 8px;
            }}
        """)
        root.addWidget(self._time_edit)

        # ── Days ─────────────────────────────────────────────────────────
        root.addWidget(_field_label("Repeat"))
        preset_hl = QHBoxLayout()
        preset_hl.setSpacing(6)
        self._preset_combo = QComboBox()
        self._preset_combo.setStyleSheet(_COMBO_SHEET)
        for label in _DAY_PRESET:
            self._preset_combo.addItem(label)
        self._preset_combo.addItem("One-shot (run once)")
        self._preset_combo.currentTextChanged.connect(self._on_preset_changed)
        preset_hl.addWidget(self._preset_combo, 1)
        root.addLayout(preset_hl)

        day_frame = QWidget()
        day_frame.setStyleSheet("background: transparent;")
        day_hl = QHBoxLayout(day_frame)
        day_hl.setContentsMargins(0, 0, 0, 0)
        day_hl.setSpacing(4)
        self._day_checks: list[QCheckBox] = []
        for d in _DAY_NAMES:
            cb = QCheckBox(d)
            cb.setStyleSheet(f"color: {_SUBTEXT}; font-size: 11px;")
            self._day_checks.append(cb)
            day_hl.addWidget(cb)
        day_hl.addStretch()
        root.addWidget(day_frame)
        self._day_frame = day_frame

        # default to weekdays
        self._preset_combo.setCurrentText("Weekdays")

        # ── Dialog buttons ────────────────────────────────────────────────
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.setStyleSheet(f"""
            QPushButton {{
                background: #111c30;
                border: 1px solid {_BORDER};
                border-radius: 4px;
                color: {_TEXT};
                font-size: 11px;
                padding: 5px 16px;
                min-width: 70px;
            }}
            QPushButton:hover {{ border-color: {_ACCENT}; color: {_ACCENT}; }}
        """)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        root.addWidget(btns)

        self._current_path = SYSTEMS_DIR

    # ── Build result ─────────────────────────────────────────────────────

    def get_schedule(self) -> dict | None:
        system = self._sys_combo.currentData(Qt.ItemDataRole.UserRole)
        if not system:
            return None

        cascade: list[str] = []
        path = SYSTEMS_DIR / system
        for cb in self._level_combos:
            if not cb.isVisible():
                break
            raw = cb.currentData(Qt.ItemDataRole.UserRole)
            if not raw:
                break
            cascade.append(raw)
            path = path / raw

        time_str = self._time_edit.time().toString("HH:mm")
        preset   = self._preset_combo.currentText()

        if preset == "One-shot (run once)":
            days: list[int] = []
        elif preset == "Custom":
            days = [i for i, cb in enumerate(self._day_checks) if cb.isChecked()]
        else:
            days = _DAY_PRESET.get(preset, list(range(7)))

        # Build label
        sys_disp = self._sys_combo.currentText()
        cascade_disp: list[str] = []
        p = SYSTEMS_DIR / system
        for raw in cascade:
            dm = utils.load_display_names(p / "display_names.json")
            cascade_disp.append(utils.resolve_display_name(raw, dm))
            p = p / raw
        label_parts = [sys_disp] + cascade_disp
        label = " / ".join(label_parts)

        return {
            "id":         uuid.uuid4().hex[:8],
            "label":      label,
            "system":     system,
            "cascade":    cascade,
            "time":       time_str,
            "days":       days,
            "enabled":    True,
            "last_fired": None,
        }

    # ── Private ──────────────────────────────────────────────────────────

    def _on_system_changed(self, _: int) -> None:
        raw = self._sys_combo.currentData(Qt.ItemDataRole.UserRole)
        for cb in self._level_combos:
            cb.setVisible(False)
            cb.blockSignals(True)
            cb.clear()
            cb.blockSignals(False)
        if not raw:
            return
        self._populate_level(0, SYSTEMS_DIR / raw)

    def _on_level_changed(self, level: int) -> None:
        # Clear all levels below
        for i in range(level + 1, len(self._level_combos)):
            self._level_combos[i].setVisible(False)
            self._level_combos[i].blockSignals(True)
            self._level_combos[i].clear()
            self._level_combos[i].blockSignals(False)

        cb  = self._level_combos[level]
        raw = cb.currentData(Qt.ItemDataRole.UserRole)
        if not raw:
            return

        # Build path up to this level
        system = self._sys_combo.currentData(Qt.ItemDataRole.UserRole)
        if not system:
            return
        path = SYSTEMS_DIR / system
        for i in range(level):
            r = self._level_combos[i].currentData(Qt.ItemDataRole.UserRole)
            if not r:
                return
            path = path / r
        path = path / raw

        if level + 1 < len(self._level_combos):
            self._populate_level(level + 1, path)

    def _populate_level(self, level: int, parent_path: Path) -> None:
        subs = utils.scan_subdirectories(parent_path)
        if not subs:
            return
        dm = utils.load_display_names(parent_path / "display_names.json")
        cb = self._level_combos[level]
        cb.blockSignals(True)
        cb.clear()
        cb.addItem("", userData=None)
        for raw in subs:
            disp = utils.resolve_display_name(raw, dm)
            cb.addItem(disp, userData=raw)
        cb.blockSignals(False)
        cb.setVisible(True)

    def _on_preset_changed(self, text: str) -> None:
        is_custom = text == "Custom"
        is_once   = text == "One-shot (run once)"
        self._day_frame.setVisible(is_custom)
        if not is_custom and not is_once:
            days = _DAY_PRESET.get(text, [])
            for i, cb in enumerate(self._day_checks):
                cb.setChecked(i in days)


# ── Schedule row widget ───────────────────────────────────────────────────────

class _ScheduleRow(QFrame):
    delete_clicked  = Signal(str)   # schedule id
    toggle_enabled  = Signal(str, bool)

    def __init__(self, schedule: dict, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._id = schedule["id"]
        self.setStyleSheet(f"""
            QFrame {{
                background: {_BG_CARD};
                border: 1px solid {_BORDER};
                border-radius: 6px;
            }}
        """)
        self.setMinimumHeight(56)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)

        hl = QHBoxLayout(self)
        hl.setContentsMargins(12, 0, 8, 0)
        hl.setSpacing(10)

        # Enable toggle
        self._toggle = QCheckBox()
        self._toggle.setChecked(schedule.get("enabled", True))
        self._toggle.setToolTip("Enable / disable this schedule")
        self._toggle.stateChanged.connect(
            lambda s: self.toggle_enabled.emit(
                self._id, Qt.CheckState(s) == Qt.CheckState.Checked
            )
        )
        hl.addWidget(self._toggle)

        # Label + next-fire
        info = QVBoxLayout()
        info.setSpacing(1)
        _label_text = schedule.get("label", "—")
        self._label_lbl = QLabel(_label_text)
        self._label_lbl.setStyleSheet(
            f"color: {_TEXT}; font-size: 12px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        self._label_lbl.setWordWrap(True)
        self._label_lbl.setToolTip(_label_text)

        self._next_lbl = QLabel(_next_fire(schedule))
        self._next_lbl.setStyleSheet(
            f"color: {_DIM}; font-size: 10px; background: transparent; border: none;"
        )
        info.addWidget(self._label_lbl)
        info.addWidget(self._next_lbl)
        hl.addLayout(info, 1)

        # Time badge
        time_badge = QLabel(schedule.get("time", "—"))
        time_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        time_badge.setFixedSize(52, 24)
        time_badge.setStyleSheet(f"""
            background: #111c30;
            border: 1px solid {_BORDER};
            border-radius: 4px;
            color: {_ACCENT};
            font-size: 11px;
            font-weight: bold;
        """)
        hl.addWidget(time_badge)

        # Days badge
        days = schedule.get("days", [])
        if not days:
            day_text = "Once"
        elif days == list(range(7)):
            day_text = "Daily"
        elif days == list(range(5)):
            day_text = "M–F"
        else:
            day_text = " ".join(_DAY_NAMES[d][:2] for d in sorted(days))
        day_lbl = QLabel(day_text)
        day_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        day_lbl.setFixedSize(60, 24)
        day_lbl.setStyleSheet(f"""
            background: #111c30;
            border: 1px solid {_BORDER};
            border-radius: 4px;
            color: {_SUBTEXT};
            font-size: 10px;
        """)
        hl.addWidget(day_lbl)

        # Delete button
        del_btn = QPushButton("✕")
        del_btn.setFixedSize(26, 26)
        del_btn.setToolTip("Remove schedule")
        del_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {_BORDER};
                border-radius: 4px;
                color: {_DIM};
                font-size: 12px;
            }}
            QPushButton:hover {{ border-color: {_RED}; color: {_RED}; }}
        """)
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(self._id))
        hl.addWidget(del_btn)

    def update_next(self, schedule: dict) -> None:
        self._next_lbl.setText(_next_fire(schedule))
        self._toggle.setChecked(schedule.get("enabled", True))


# ── Main panel ────────────────────────────────────────────────────────────────

def _field_label(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setStyleSheet(
        f"color: {_DIM}; font-size: 10px; font-weight: bold; "
        f"letter-spacing: 1px; background: transparent;"
    )
    return lbl


class SchedulerPanel(QWidget):
    """Scheduled-run panel — add, enable/disable, and delete run schedules."""

    trigger_run = Signal(str, list)   # system, cascade path

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"QWidget {{ background: {_BG}; }}")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QWidget()
        hdr.setStyleSheet(f"background: {_BG};")
        hdr_hl = QHBoxLayout(hdr)
        hdr_hl.setContentsMargins(20, 16, 20, 8)
        hdr_hl.setSpacing(12)

        title = QLabel("⏱  SCHEDULER")
        title.setStyleSheet(
            f"color: {_ACCENT}; font-size: 18px; font-weight: bold; letter-spacing: 2px;"
        )
        sub = QLabel("Automate run triggers on a time-based schedule")
        sub.setStyleSheet(f"color: {_DIM}; font-size: 11px;")
        hdr_hl.addWidget(title)
        hdr_hl.addSpacing(12)
        hdr_hl.addWidget(sub)
        hdr_hl.addStretch()

        add_btn = QPushButton("＋  Add Schedule")
        add_btn.setFixedHeight(28)
        add_btn.setStyleSheet(_BTN.format(
            bg="#111c30", bd=_BORDER, fg=_SUBTEXT, ac=_ACCENT
        ))
        add_btn.clicked.connect(self._on_add)
        hdr_hl.addWidget(add_btn)

        outer.addWidget(hdr)

        # ── Status bar ────────────────────────────────────────────────────
        status_bar = QFrame()
        status_bar.setFixedHeight(32)
        status_bar.setStyleSheet(f"""
            QFrame {{
                background: {_BG_CARD};
                border: 1px solid {_BORDER};
                border-radius: 6px;
                margin: 0 20px 6px 20px;
            }}
        """)
        sb_hl = QHBoxLayout(status_bar)
        sb_hl.setContentsMargins(14, 0, 14, 0)

        dot = QLabel("●")
        dot.setStyleSheet("color: #a6e3a1; font-size: 9px; background: transparent; border: none;")
        self._status_lbl = QLabel("Scheduler active — checks every 60 s")
        self._status_lbl.setStyleSheet(
            f"color: {_SUBTEXT}; font-size: 11px; background: transparent; border: none;"
        )
        sb_hl.addWidget(dot)
        sb_hl.addSpacing(6)
        sb_hl.addWidget(self._status_lbl, 1)
        outer.addWidget(status_bar)

        # ── Scroll area for schedule rows ─────────────────────────────────
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

        self._rows_widget = QWidget()
        self._rows_widget.setStyleSheet(f"background: {_BG};")
        self._rows_layout = QVBoxLayout(self._rows_widget)
        self._rows_layout.setContentsMargins(20, 4, 20, 20)
        self._rows_layout.setSpacing(6)
        self._rows_layout.addStretch()
        scroll.setWidget(self._rows_widget)

        self._empty_lbl = QLabel(
            "No schedules yet.\n\nClick  ＋ Add Schedule  to create one."
        )
        self._empty_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_lbl.setStyleSheet(f"color: {_DIM}; font-size: 12px; background: transparent;")
        self._rows_layout.insertWidget(0, self._empty_lbl)

        # ── Internal state ────────────────────────────────────────────────
        self._schedules: list[dict] = _load_schedules()
        self._row_widgets: dict[str, _ScheduleRow] = {}

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.start(60_000)

        self._rebuild_rows()

    # ── Public ──────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self._schedules = _load_schedules()
        self._rebuild_rows()

    # ── Private ─────────────────────────────────────────────────────────────

    def _rebuild_rows(self) -> None:
        # Remove existing rows
        for w in list(self._row_widgets.values()):
            self._rows_layout.removeWidget(w)
            w.deleteLater()
        self._row_widgets.clear()

        self._empty_lbl.setVisible(not self._schedules)

        for sched in self._schedules:
            row = _ScheduleRow(sched, self._rows_widget)
            row.delete_clicked.connect(self._on_delete)
            row.toggle_enabled.connect(self._on_toggle)
            self._row_widgets[sched["id"]] = row
            self._rows_layout.insertWidget(
                self._rows_layout.count() - 1, row
            )

    def _on_add(self) -> None:
        dlg = _AddScheduleDialog(self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        sched = dlg.get_schedule()
        if not sched:
            return
        self._schedules.append(sched)
        _save_schedules(self._schedules)
        self._rebuild_rows()

    def _on_delete(self, sid: str) -> None:
        self._schedules = [s for s in self._schedules if s["id"] != sid]
        _save_schedules(self._schedules)
        self._rebuild_rows()

    def _on_toggle(self, sid: str, enabled: bool) -> None:
        for s in self._schedules:
            if s["id"] == sid:
                s["enabled"] = enabled
                break
        _save_schedules(self._schedules)
        if sid in self._row_widgets:
            sched = next((s for s in self._schedules if s["id"] == sid), None)
            if sched:
                self._row_widgets[sid].update_next(sched)

    def _tick(self) -> None:
        fired = False
        today = date.today().isoformat()
        for sched in self._schedules:
            if _is_due(sched):
                sched["last_fired"] = today
                fired = True
                self.trigger_run.emit(
                    sched["system"],
                    list(sched["cascade"]),
                )
                # Update next-fire label
                if sched["id"] in self._row_widgets:
                    self._row_widgets[sched["id"]].update_next(sched)
        if fired:
            _save_schedules(self._schedules)
            now_str = datetime.now().strftime("%H:%M")
            self._status_lbl.setText(
                f"Scheduler active — last checked {now_str}"
            )
