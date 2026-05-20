"""
orbit360/ui/command_deck_panel.py
Right-side panel for the Command Deck home screen.

Cards (top to bottom):
  • Live Run       — active run status + elapsed time (hidden when idle)
  • System Overview — script / env / test-set counts
  • Recent Runs     — last 4 runs with pass/fail badges
  • Health & Activity — sparkline + flaky scripts + stale pools + today's count
  • Storage         — orbit_data disk usage vs. configured limit
"""
from __future__ import annotations

import datetime
import os

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QProgressBar, QSizePolicy,
    QVBoxLayout, QWidget,
)

from orbit360.backend import history_db
from orbit360.ui._ui_utils import fmt_dur
from orbit360.utils.paths import ORBIT_DATA_DIR, RUNS_DIR

_BG_CARD  = "#0d1520"
_BG_PANEL = "#080d18"
_BORDER   = "#1a2a40"
_ACCENT   = "#89b4fa"
_GREEN    = "#a6e3a1"
_RED      = "#f38ba8"
_AMBER    = "#f9e2af"
_TEXT     = "#cdd6f4"
_DIM      = "#1a2a40"
_TEXT_DIM = "#5a6a88"


# ── Sparkline ─────────────────────────────────────────────────────────────────

class SparklineWidget(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[dict] = []
        self.setMinimumHeight(44)
        self.setMaximumHeight(52)
        self.setStyleSheet("background: transparent;")

    def set_data(self, runs: list[dict]) -> None:
        self._data = runs
        self.update()

    def paintEvent(self, _event) -> None:
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        n    = len(self._data)
        gap  = 2
        bw   = max(4, (w - gap * (n - 1)) // n)
        for i, run in enumerate(self._data):
            total = max(run.get("total", 1), 1)
            ratio = run.get("passed", 0) / total
            x     = i * (bw + gap)
            fh    = h - 4
            ph    = max(2, int(fh * ratio))
            eh    = fh - ph
            if eh > 0:
                painter.fillRect(x, 2, bw, eh, QColor(_RED))
            if ph > 0:
                painter.fillRect(x, 2 + eh, bw, ph, QColor(_GREEN))
        painter.end()


# ── Widget helpers ────────────────────────────────────────────────────────────

def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"background: {_BORDER}; max-height: 1px; border: none;")
    return f


def _card_frame(icon: str, title: str,
                accent: str = _ACCENT) -> tuple[QFrame, QVBoxLayout]:
    """Card with a 3px left accent stripe."""
    card = QFrame()
    card.setStyleSheet(f"""
        QFrame#deckCard {{
            background: {_BG_CARD};
            border: 1px solid {_BORDER};
            border-left: 3px solid {accent};
            border-radius: 8px;
        }}
    """)
    card.setObjectName("deckCard")
    body = QVBoxLayout(card)
    body.setContentsMargins(12, 10, 12, 12)
    body.setSpacing(8)

    hdr = QHBoxLayout()
    hdr.setSpacing(6)
    il = QLabel(icon)
    il.setStyleSheet(
        f"color: {accent}; font-size: 13px; background: transparent; border: none;"
    )
    tl = QLabel(title)
    tl.setStyleSheet(
        f"color: {accent}; font-size: 10px; font-weight: bold; "
        f"letter-spacing: 2px; background: transparent; border: none;"
    )
    hdr.addWidget(il)
    hdr.addWidget(tl)
    hdr.addStretch()
    body.addLayout(hdr)
    return card, body


def _stat_tile(value: str, label: str, color: str = _ACCENT) -> tuple[QFrame, QLabel]:
    tile = QFrame()
    tile.setStyleSheet(f"""
        QFrame {{
            background: #060c18;
            border: 1px solid {_BORDER};
            border-top: 2px solid {color};
            border-radius: 6px;
        }}
    """)
    tl = QVBoxLayout(tile)
    tl.setContentsMargins(6, 10, 6, 10)
    tl.setSpacing(3)
    tl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    val_lbl = QLabel(value)
    val_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    val_lbl.setStyleSheet(
        f"color: {color}; font-size: 22px; font-weight: bold; "
        f"background: transparent; border: none;"
    )
    cap_lbl = QLabel(label)
    cap_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cap_lbl.setWordWrap(True)
    cap_lbl.setStyleSheet(
        f"color: {_TEXT_DIM}; font-size: 9px; letter-spacing: 0.5px; "
        f"background: transparent; border: none;"
    )
    tl.addWidget(val_lbl)
    tl.addWidget(cap_lbl)
    return tile, val_lbl


def _run_row(run: dict) -> QWidget:
    passed  = run.get("passed",  0)
    failed  = run.get("failed",  0)
    errored = run.get("errored", 0)
    total   = run.get("total",   0)
    dur     = run.get("duration_secs", 0.0)
    ts      = run.get("timestamp", "")
    system  = run.get("system", "—")

    ts_short = ts[11:16] if len(ts) >= 16 else ts[:16]
    dur_str  = fmt_dur(dur)

    bad = failed + errored
    if bad == 0 and total > 0:
        badge_text, badge_bg, badge_fg = "Success", "#1a3a2a", _GREEN
        score_text  = f"{passed}/{total} passed"
        score_color = _GREEN
    elif bad > 0 and passed > 0:
        badge_text, badge_bg, badge_fg = "Warning", "#3a2a10", _AMBER
        score_text  = f"{passed}/{total} passed  •  {bad} failed"
        score_color = _AMBER
    else:
        badge_text, badge_bg, badge_fg = "Failed",  "#3a1020", _RED
        score_text  = f"{bad} failed" if total > 0 else "—"
        score_color = _RED

    row = QWidget()
    row.setStyleSheet(
        "QWidget { background: transparent; }"
        "QWidget:hover { background: #101c2e; border-radius: 4px; }"
    )
    hl = QHBoxLayout(row)
    hl.setContentsMargins(2, 5, 2, 5)
    hl.setSpacing(8)

    icon_lbl = QLabel("▣")
    icon_lbl.setStyleSheet(f"color: {_DIM}; font-size: 12px; background: transparent;")
    hl.addWidget(icon_lbl)

    info_col = QVBoxLayout()
    info_col.setSpacing(2)

    sys_lbl = QLabel(system)
    sys_lbl.setStyleSheet(
        f"color: {_TEXT}; font-size: 12px; font-weight: 600; background: transparent;"
    )
    meta_lbl = QLabel(f"{ts_short}  •  {dur_str}")
    meta_lbl.setStyleSheet(
        f"color: {_TEXT_DIM}; font-size: 10px; background: transparent;"
    )
    score_lbl = QLabel(score_text)
    score_lbl.setStyleSheet(
        f"color: {score_color}; font-size: 10px; background: transparent;"
    )

    info_col.addWidget(sys_lbl)
    info_col.addWidget(meta_lbl)
    info_col.addWidget(score_lbl)
    hl.addLayout(info_col, 1)

    badge = QLabel(badge_text)
    badge.setStyleSheet(f"""
        QLabel {{
            background: {badge_bg}; color: {badge_fg};
            border: 1px solid {badge_fg}; border-radius: 3px;
            font-size: 9px; font-weight: bold; padding: 2px 6px;
        }}
    """)
    badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
    hl.addWidget(badge)
    return row


def _health_row(icon: str, text: str, color: str) -> QLabel:
    lbl = QLabel(f"{icon}  {text}")
    lbl.setStyleSheet(
        f"color: {color}; font-size: 11px; background: transparent; border: none;"
    )
    return lbl


def _storage_bar(used_bytes: int, limit_bytes: int) -> QWidget:
    """Return a compact usage bar widget that fills the available width."""
    def _fmt(b: int) -> str:
        if b >= 1_073_741_824:
            return f"{b / 1_073_741_824:.1f} GB"
        if b >= 1_048_576:
            return f"{b / 1_048_576:.0f} MB"
        return f"{b / 1024:.0f} KB"

    ratio     = min(used_bytes / limit_bytes, 1.0) if limit_bytes else 0.0
    pct       = int(ratio * 100)
    bar_color = _RED if ratio > 0.9 else (_AMBER if ratio > 0.75 else _GREEN)

    w = QWidget()
    w.setStyleSheet("background: transparent;")
    vl = QVBoxLayout(w)
    vl.setContentsMargins(0, 0, 0, 0)
    vl.setSpacing(4)

    text_row = QHBoxLayout()
    used_lbl = QLabel(_fmt(used_bytes))
    used_lbl.setStyleSheet(f"color: {_TEXT}; font-size: 11px; background: transparent;")
    pct_lbl  = QLabel(f"{pct}% of {_fmt(limit_bytes)}")
    pct_lbl.setStyleSheet(f"color: {_TEXT_DIM}; font-size: 10px; background: transparent;")
    text_row.addWidget(used_lbl)
    text_row.addStretch()
    text_row.addWidget(pct_lbl)
    vl.addLayout(text_row)

    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(pct)
    bar.setTextVisible(False)
    bar.setFixedHeight(6)
    bar.setStyleSheet(f"""
        QProgressBar {{
            background: {_BORDER}; border: none; border-radius: 3px;
        }}
        QProgressBar::chunk {{
            background: {bar_color}; border-radius: 3px;
        }}
    """)
    vl.addWidget(bar)

    return w


# ── Main panel ───────────────────────────────────────────────────────────────

class CommandDeckPanel(QWidget):
    """Right-side info panel on the Command Deck screen."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedWidth(340)
        self.setStyleSheet(f"QWidget {{ background: {_BG_PANEL}; }}")
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        self._live_system:    str | None       = None
        self._live_start:     datetime.datetime | None = None
        self._elapsed_timer = QTimer(self)
        self._elapsed_timer.setInterval(1000)
        self._elapsed_timer.timeout.connect(self._tick_elapsed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(8)

        # ── Live Run card (hidden when idle) ─────────────────────────────
        self._live_card = QFrame()
        self._live_card.setStyleSheet(f"""
            QFrame {{
                background: #0d1e10;
                border: 1px solid {_GREEN};
                border-radius: 8px;
            }}
        """)
        live_body = QVBoxLayout(self._live_card)
        live_body.setContentsMargins(12, 10, 12, 10)
        live_body.setSpacing(4)

        live_hdr = QHBoxLayout()
        live_dot = QLabel("●  LIVE RUN")
        live_dot.setStyleSheet(
            f"color: {_GREEN}; font-size: 10px; font-weight: bold; "
            f"letter-spacing: 1px; background: transparent; border: none;"
        )
        live_hdr.addWidget(live_dot)
        live_hdr.addStretch()
        live_body.addLayout(live_hdr)

        self._live_sys_lbl = QLabel("")
        self._live_sys_lbl.setStyleSheet(
            f"color: {_TEXT}; font-size: 12px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        live_body.addWidget(self._live_sys_lbl)

        self._live_elapsed_lbl = QLabel("")
        self._live_elapsed_lbl.setStyleSheet(
            f"color: {_TEXT_DIM}; font-size: 10px; background: transparent; border: none;"
        )
        live_body.addWidget(self._live_elapsed_lbl)

        self._live_card.hide()
        layout.addWidget(self._live_card)

        # ── System Overview ───────────────────────────────────────────────
        ov_card, ov_body = _card_frame("⚡", "SYSTEM OVERVIEW", _ACCENT)
        stat_row = QHBoxLayout()
        stat_row.setSpacing(6)
        self._stat_scripts, self._sv_scripts = _stat_tile("—", "SCRIPTS", _ACCENT)
        self._stat_envs,    self._sv_envs    = _stat_tile("—", "ENVS",    "#94e2d5")
        self._stat_modules, self._sv_modules = _stat_tile("—", "TEST SETS","#cba6f7")
        stat_row.addWidget(self._stat_scripts, 1)
        stat_row.addWidget(self._stat_envs,    1)
        stat_row.addWidget(self._stat_modules, 1)
        ov_body.addLayout(stat_row)
        layout.addWidget(ov_card)

        # ── Recent Runs ───────────────────────────────────────────────────
        rr_card, rr_body = _card_frame("◈", "RECENT RUNS", "#fab387")
        self._runs_container = QWidget()
        self._runs_container.setStyleSheet("background: transparent;")
        self._runs_layout = QVBoxLayout(self._runs_container)
        self._runs_layout.setContentsMargins(0, 0, 0, 0)
        self._runs_layout.setSpacing(0)
        rr_body.addWidget(self._runs_container)
        layout.addWidget(rr_card)

        # ── Health & Activity ─────────────────────────────────────────────
        ha_card, ha_body = _card_frame("◉", "HEALTH & ACTIVITY", _GREEN)

        self._sparkline = SparklineWidget()
        ha_body.addWidget(self._sparkline)
        ha_body.addWidget(_hline())

        self._health_container = QWidget()
        self._health_container.setStyleSheet("background: transparent;")
        self._health_layout = QVBoxLayout(self._health_container)
        self._health_layout.setContentsMargins(0, 2, 0, 0)
        self._health_layout.setSpacing(3)
        ha_body.addWidget(self._health_container)

        today_row = QHBoxLayout()
        today_lbl = QLabel("Today's runs")
        today_lbl.setStyleSheet(
            f"color: {_TEXT_DIM}; font-size: 10px; background: transparent;"
        )
        self._today_val = QLabel("0")
        self._today_val.setStyleSheet(
            f"color: {_TEXT}; font-size: 11px; font-weight: bold; background: transparent;"
        )
        self._today_rate = QLabel("")
        self._today_rate.setStyleSheet(
            f"color: {_TEXT_DIM}; font-size: 10px; background: transparent;"
        )
        today_row.addWidget(today_lbl)
        today_row.addStretch()
        today_row.addWidget(self._today_rate)
        today_row.addSpacing(6)
        today_row.addWidget(self._today_val)
        ha_body.addLayout(today_row)

        layout.addWidget(ha_card)

        # ── Storage ───────────────────────────────────────────────────────
        st_card, st_body = _card_frame("💾", "STORAGE")
        self._storage_container = QWidget()
        self._storage_container.setStyleSheet("background: transparent;")
        self._storage_layout = QVBoxLayout(self._storage_container)
        self._storage_layout.setContentsMargins(0, 0, 0, 0)
        self._storage_layout.setSpacing(4)
        st_body.addWidget(self._storage_container)
        layout.addWidget(st_card)

        layout.addStretch()

        self.refresh()

    # ── Public ──────────────────────────────────────────────────────────────

    def set_stats(self, scripts: int, envs: int, modules: int) -> None:
        self._sv_scripts.setText(str(scripts))
        self._sv_envs.setText(str(envs))
        self._sv_modules.setText(str(modules))

    def set_live_run(self, system: str, script_count: int) -> None:
        self._live_system = system
        self._live_start  = datetime.datetime.now()
        self._live_sys_lbl.setText(system or "—")
        self._live_elapsed_lbl.setText(f"{script_count} scripts  •  Starting...")
        self._live_card.show()
        self._elapsed_timer.start()

    def clear_live_run(self) -> None:
        self._elapsed_timer.stop()
        self._live_system = None
        self._live_start  = None
        self._live_card.hide()
        QTimer.singleShot(400, self.refresh)

    def refresh(self) -> None:
        self._refresh_runs()
        self._refresh_health()
        self._refresh_storage()

    def on_run_completed(self) -> None:
        """Called by main_window after a run finishes — clear_live_run handles the refresh."""
        pass

    # ── Private ─────────────────────────────────────────────────────────────

    def _tick_elapsed(self) -> None:
        if self._live_start is None:
            return
        elapsed = int((datetime.datetime.now() - self._live_start).total_seconds())
        m, s    = divmod(elapsed, 60)
        elapsed_str = f"{m}m {s:02d}s" if m else f"{s}s"
        scripts_text = self._live_elapsed_lbl.text().split("  •  ")[0]
        self._live_elapsed_lbl.setText(f"{scripts_text}  •  {elapsed_str}")

    def _refresh_runs(self) -> None:
        while self._runs_layout.count():
            item = self._runs_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        runs = history_db.get_recent_runs(limit=4)
        if not runs:
            lbl = QLabel("No runs recorded yet")
            lbl.setStyleSheet(
                f"color: {_TEXT_DIM}; font-size: 11px; padding: 8px 2px; background: transparent;"
            )
            self._runs_layout.addWidget(lbl)
            return

        for i, run in enumerate(runs):
            if i > 0:
                self._runs_layout.addWidget(_hline())
            self._runs_layout.addWidget(_run_row(run))

    def _refresh_health(self) -> None:
        trend  = history_db.get_run_trend(limit=20)
        self._sparkline.set_data(trend)

        today_runs = history_db.get_recent_runs(limit=999, since_days=1)
        self._today_val.setText(str(len(today_runs)))

        # Pass rate for today's runs
        if today_runs:
            clean = sum(
                1 for r in today_runs
                if r.get("failed", 0) == 0 and r.get("errored", 0) == 0
                and r.get("total", 0) > 0
            )
            pct = int(clean / len(today_runs) * 100)
            rate_color = _GREEN if pct >= 90 else (_AMBER if pct >= 70 else _RED)
            self._today_rate.setText(f"{clean}/{len(today_runs)} clean")
            self._today_rate.setStyleSheet(
                f"color: {rate_color}; font-size: 10px; background: transparent;"
            )
        else:
            self._today_rate.setText("")

        # Rebuild health alerts
        while self._health_layout.count():
            item = self._health_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        flaky_count = history_db.get_flaky_script_count()
        stale_count = 0
        try:
            from orbit360.utils.excel_data_manager import get_global_stale_count
            stale_count = get_global_stale_count()
        except Exception:
            pass

        if flaky_count == 0 and stale_count == 0:
            self._health_layout.addWidget(
                _health_row("✓", "All systems nominal", _GREEN)
            )
        else:
            if flaky_count:
                self._health_layout.addWidget(
                    _health_row("⚠", f"{flaky_count} flaky script(s)", _AMBER)
                )
            if stale_count:
                self._health_layout.addWidget(
                    _health_row("⚠", f"{stale_count} stale pool row(s)", _AMBER)
                )

    def _refresh_storage(self) -> None:
        while self._storage_layout.count():
            item = self._storage_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        try:
            used_bytes = sum(
                f.stat().st_size
                for f in ORBIT_DATA_DIR.rglob("*")
                if f.is_file()
            ) if ORBIT_DATA_DIR.is_dir() else 0
        except Exception:
            used_bytes = 0

        try:
            limit_gb   = float(os.environ.get("ORBIT_STORAGE_LIMIT_GB", "100"))
        except ValueError:
            limit_gb   = 100.0
        limit_bytes = int(limit_gb * 1_073_741_824)

        runs_count = sum(1 for d in RUNS_DIR.iterdir() if d.is_dir()) if RUNS_DIR.is_dir() else 0

        self._storage_layout.addWidget(_storage_bar(used_bytes, limit_bytes))

        arc_lbl = QLabel(f"{runs_count} run archive(s) in orbit_data/runs/")
        arc_lbl.setStyleSheet(
            f"color: {_TEXT_DIM}; font-size: 10px; background: transparent;"
        )
        self._storage_layout.addWidget(arc_lbl)
