"""
orbit360/ui/pulse_panel.py
Pulse screen — quick health overview: stats, trend, per-system summary, alerts.
"""
from __future__ import annotations

import datetime
from collections import defaultdict

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel,
    QPushButton, QScrollArea,
    QToolTip, QVBoxLayout, QWidget,
)

from orbit360.backend import history_db
from orbit360.ui._ui_utils import fmt_dur as _fmt_dur

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


def _rate_color(pct: float) -> str:
    if pct >= 90:
        return _GREEN
    if pct >= 70:
        return _AMBER
    return _RED


def _trend_direction(runs: list[dict]) -> tuple[str, str]:
    n = len(runs)
    if n < 4:
        return ("→", _DIM)
    mid = n // 2
    def _rate(rs: list[dict]) -> float:
        t = sum(r.get("total", 0) for r in rs)
        p = sum(r.get("passed", 0) for r in rs)
        return (p / t * 100) if t else 0.0
    diff = _rate(runs[:mid]) - _rate(runs[mid:])
    if diff > 5:
        return ("↑", _GREEN)
    if diff < -5:
        return ("↓", _RED)
    return ("→", _DIM)


# ── Trend chart ───────────────────────────────────────────────────────────────

class _TrendChart(QWidget):
    """Bar-per-run pass/fail chart with hover tooltip."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._data: list[dict] = []
        self._bar_w = 8
        self._gap   = 2
        self.setMinimumHeight(72)
        self.setMaximumHeight(88)
        self.setStyleSheet("background: transparent;")
        self.setMouseTracking(True)

    def set_data(self, runs: list[dict]) -> None:
        self._data = runs
        self._recalc_bar_w()
        self.update()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._recalc_bar_w()

    def _recalc_bar_w(self) -> None:
        n = len(self._data)
        if n:
            self._bar_w = max(6, (self.width() - self._gap * (n - 1)) // n)

    def _bar_index_at(self, x: int) -> int:
        step = self._bar_w + self._gap
        idx  = x // step
        return idx if 0 <= idx < len(self._data) else -1

    def mouseMoveEvent(self, event) -> None:
        idx = self._bar_index_at(int(event.position().x()))
        if idx < 0:
            QToolTip.hideText()
            return
        run   = self._data[idx]
        ts    = run.get("timestamp", "")
        ts_s  = ts[:16].replace("T", "  ") if len(ts) >= 16 else ts
        total = run.get("total",  0)
        p     = run.get("passed", 0)
        f     = run.get("failed", 0) + run.get("errored", 0)
        sys_  = run.get("system", "")
        dur   = _fmt_dur(run.get("duration_secs", 0))
        lines = [ts_s]
        if sys_:
            lines.append(sys_)
        lines.append(f"{p}/{total} passed" + (f"  •  {f} failed" if f else ""))
        lines.append(dur)
        QToolTip.showText(event.globalPosition().toPoint(), "\n".join(lines), self)

    def leaveEvent(self, event) -> None:
        QToolTip.hideText()

    def paintEvent(self, _event) -> None:
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        h, bw, gap = self.height(), self._bar_w, self._gap
        for i, run in enumerate(self._data):
            total  = max(run.get("total", 1), 1)
            ratio  = run.get("passed", 0) / total
            x      = i * (bw + gap)
            fh     = h - 8
            ph     = max(2, int(fh * ratio))
            eh     = fh - ph
            if eh > 0:
                painter.fillRect(x, 4, bw, eh, QColor(_RED))
            if ph > 0:
                painter.fillRect(x, 4 + eh, bw, ph, QColor(_GREEN))
        painter.end()


# ── Widget helpers ─────────────────────────────────────────────────────────────

def _hline() -> QFrame:
    f = QFrame()
    f.setFrameShape(QFrame.Shape.HLine)
    f.setStyleSheet(f"background: {_BORDER}; max-height: 1px; border: none;")
    return f


def _card(title: str, accent: str = _ACCENT) -> tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setStyleSheet(f"""
        QFrame {{
            background: {_BG_CARD};
            border: 1px solid {_BORDER};
            border-left: 3px solid {accent};
            border-radius: 8px;
        }}
    """)
    vl = QVBoxLayout(f)
    vl.setContentsMargins(14, 10, 14, 12)
    vl.setSpacing(8)
    lbl = QLabel(title)
    lbl.setStyleSheet(
        f"color: {accent}; font-size: 10px; font-weight: bold; "
        f"letter-spacing: 2px; background: transparent; border: none;"
    )
    vl.addWidget(lbl)
    return f, vl


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
    vl = QVBoxLayout(tile)
    vl.setContentsMargins(6, 10, 6, 10)
    vl.setSpacing(3)
    vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
    val = QLabel(value)
    val.setAlignment(Qt.AlignmentFlag.AlignCenter)
    val.setStyleSheet(
        f"color: {color}; font-size: 22px; font-weight: bold; "
        f"background: transparent; border: none;"
    )
    cap = QLabel(label)
    cap.setAlignment(Qt.AlignmentFlag.AlignCenter)
    cap.setWordWrap(True)
    cap.setStyleSheet(
        f"color: {_DIM}; font-size: 9px; letter-spacing: 0.5px; "
        f"background: transparent; border: none;"
    )
    vl.addWidget(val)
    vl.addWidget(cap)
    return tile, val


def _sys_row(system: str, runs: int, pass_rate: float | None, avg_dur_s: float) -> QWidget:
    row = QWidget()
    row.setStyleSheet(
        "QWidget { background: transparent; }"
        "QWidget:hover { background: #101c2e; border-radius: 4px; }"
    )
    hl = QHBoxLayout(row)
    hl.setContentsMargins(4, 7, 4, 7)
    hl.setSpacing(10)

    name_lbl = QLabel(system)
    name_lbl.setStyleSheet(
        f"color: {_TEXT}; font-size: 12px; font-weight: 600; background: transparent;"
    )
    hl.addWidget(name_lbl, 1)

    meta_lbl = QLabel(f"{runs} run{'s' if runs != 1 else ''}  ·  avg {_fmt_dur(avg_dur_s)}")
    meta_lbl.setStyleSheet(f"color: {_DIM}; font-size: 10px; background: transparent;")
    hl.addWidget(meta_lbl)

    if pass_rate is not None:
        color = _rate_color(pass_rate)
        rate_lbl = QLabel(f"{pass_rate:.0f}%")
        rate_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        rate_lbl.setFixedWidth(44)
        rate_lbl.setStyleSheet(f"""
            QLabel {{
                color: {color}; font-size: 11px; font-weight: bold;
                border: 1px solid {color}; border-radius: 3px;
                padding: 1px 4px; background: transparent;
            }}
        """)
        hl.addWidget(rate_lbl)
    else:
        dash = QLabel("—")
        dash.setStyleSheet(f"color: {_DIM}; font-size: 11px; background: transparent;")
        hl.addWidget(dash)

    return row


def _alert_row(script: str, sub: str, status: str, color: str) -> QWidget:
    row = QWidget()
    row.setStyleSheet("background: transparent;")
    hl = QHBoxLayout(row)
    hl.setContentsMargins(4, 5, 4, 5)
    hl.setSpacing(8)

    dot = QLabel("⚠")
    dot.setStyleSheet(f"color: {color}; font-size: 11px; background: transparent;")
    hl.addWidget(dot)

    info_col = QVBoxLayout()
    info_col.setSpacing(1)
    name_lbl = QLabel(script)
    name_lbl.setStyleSheet(
        f"color: {_TEXT}; font-size: 11px; font-weight: 600; background: transparent;"
    )
    sub_lbl = QLabel(sub)
    sub_lbl.setStyleSheet(f"color: {_DIM}; font-size: 10px; background: transparent;")
    info_col.addWidget(name_lbl)
    info_col.addWidget(sub_lbl)
    hl.addLayout(info_col, 1)

    badge = QLabel(status)
    badge.setStyleSheet(f"""
        QLabel {{
            color: {color}; font-size: 9px; font-weight: bold;
            border: 1px solid {color}; border-radius: 3px;
            padding: 1px 5px; background: transparent;
        }}
    """)
    hl.addWidget(badge)

    return row


# ── Main widget ───────────────────────────────────────────────────────────────

class PulsePanel(QWidget):
    """Pulse screen — metrics, trends, and per-system health."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setStyleSheet(f"QWidget {{ background: {_BG}; }}")

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

        body = QWidget()
        body.setStyleSheet(f"background: {_BG};")
        root = QVBoxLayout(body)
        root.setContentsMargins(20, 16, 20, 20)
        root.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────
        hdr = QHBoxLayout()
        title = QLabel("▲  PULSE")
        title.setStyleSheet(
            f"color: {_ACCENT}; font-size: 18px; font-weight: bold; letter-spacing: 2px;"
        )
        sub = QLabel("Run metrics and system health")
        sub.setStyleSheet(f"color: {_DIM}; font-size: 11px;")
        hdr.addWidget(title)
        hdr.addSpacing(12)
        hdr.addWidget(sub)
        hdr.addStretch()

        self._period_combo = QComboBox()
        for label, _ in _PERIOD_OPTIONS:
            self._period_combo.addItem(label)
        self._period_combo.setFixedHeight(26)
        self._period_combo.setMinimumWidth(110)
        self._period_combo.setStyleSheet(f"""
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
        """)
        self._period_combo.setToolTip("Filter metrics by time window")
        self._period_combo.currentIndexChanged.connect(self.refresh)
        hdr.addWidget(self._period_combo)
        hdr.addSpacing(6)

        self._refresh_btn = QPushButton("↺  Refresh")
        self._refresh_btn.setFixedHeight(26)
        self._refresh_btn.setToolTip("Reload health metrics and trend chart")
        self._refresh_btn.setStyleSheet(f"""
            QPushButton {{
                background: #111c30; border: 1px solid {_BORDER}; border-radius: 4px;
                color: {_SUBTEXT}; font-size: 11px; padding: 2px 12px;
            }}
            QPushButton:hover {{ color: {_ACCENT}; border-color: {_ACCENT}; }}
        """)
        self._refresh_btn.clicked.connect(self.refresh)
        hdr.addWidget(self._refresh_btn)
        root.addLayout(hdr)

        self._updated_lbl = QLabel("")
        self._updated_lbl.setStyleSheet(
            f"color: {_DIM}; font-size: 10px; background: transparent;"
        )
        self._updated_lbl.setAlignment(Qt.AlignmentFlag.AlignRight)
        root.addWidget(self._updated_lbl)

        # ── 4 stat tiles ──────────────────────────────────────────────────
        tile_row = QHBoxLayout()
        tile_row.setSpacing(8)
        self._tile_total,    self._v_total    = _stat_tile("—", "TOTAL RUNS",   _ACCENT)
        self._tile_passrate, self._v_passrate = _stat_tile("—", "PASS RATE",    _GREEN)
        self._tile_avgdur,   self._v_avgdur   = _stat_tile("—", "AVG DURATION", _ACCENT)
        self._tile_clean,    self._v_clean    = _stat_tile("—", "CLEAN TODAY",  _GREEN)
        for tile in (self._tile_total, self._tile_passrate,
                     self._tile_avgdur, self._tile_clean):
            tile_row.addWidget(tile, 1)
        root.addLayout(tile_row)

        # ── Trend chart ───────────────────────────────────────────────────
        trend_card, trend_body = _card("PASS / FAIL TREND", _ACCENT)
        self._trend_chart = _TrendChart()
        trend_body.addWidget(self._trend_chart)

        trend_footer = QHBoxLayout()
        legend = QLabel(
            f"<span style='color:{_GREEN}'>■</span> Passed  "
            f"<span style='color:{_RED}'>■</span> Failed  "
            f"<span style='color:{_DIM}'>Hover a bar for details</span>"
        )
        legend.setTextFormat(Qt.TextFormat.RichText)
        legend.setStyleSheet(
            "background: transparent; border: none; font-size: 10px; color: #5a6a88;"
        )
        trend_footer.addWidget(legend)
        trend_footer.addStretch()
        self._trend_range_lbl = QLabel("")
        self._trend_range_lbl.setStyleSheet(
            f"color: {_DIM}; font-size: 10px; background: transparent; border: none;"
        )
        trend_footer.addWidget(self._trend_range_lbl)
        trend_body.addLayout(trend_footer)
        root.addWidget(trend_card)

        # ── By System + Attention Needed ──────────────────────────────────
        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(12)

        sys_card, sys_body = _card("BY SYSTEM", "#94e2d5")
        self._sys_container = QWidget()
        self._sys_container.setStyleSheet("background: transparent;")
        self._sys_layout = QVBoxLayout(self._sys_container)
        self._sys_layout.setContentsMargins(0, 0, 0, 0)
        self._sys_layout.setSpacing(0)
        sys_body.addWidget(self._sys_container)
        sys_body.addStretch()
        bottom_row.addWidget(sys_card, 1)

        att_card, att_body = _card("ATTENTION NEEDED", _AMBER)
        self._att_container = QWidget()
        self._att_container.setStyleSheet("background: transparent;")
        self._att_layout = QVBoxLayout(self._att_container)
        self._att_layout.setContentsMargins(0, 0, 0, 0)
        self._att_layout.setSpacing(0)
        att_body.addWidget(self._att_container)
        att_body.addStretch()
        bottom_row.addWidget(att_card, 1)

        root.addLayout(bottom_row)

        # ── Empty state ───────────────────────────────────────────────────
        self._empty_card = QFrame()
        self._empty_card.setStyleSheet(f"""
            QFrame {{
                background: {_BG_CARD};
                border: 1px solid {_BORDER};
                border-radius: 8px;
            }}
        """)
        ec_vl = QVBoxLayout(self._empty_card)
        ec_vl.setContentsMargins(20, 36, 20, 36)
        ec_vl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ec_title = QLabel("No run data for this period")
        ec_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ec_title.setStyleSheet(
            f"color: {_SUBTEXT}; font-size: 14px; font-weight: bold; "
            f"background: transparent; border: none;"
        )
        ec_sub = QLabel("Runs are recorded automatically after each execution.")
        ec_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ec_sub.setStyleSheet(
            f"color: {_DIM}; font-size: 11px; background: transparent; border: none;"
        )
        ec_vl.addWidget(ec_title)
        ec_vl.addWidget(ec_sub)
        self._empty_card.hide()
        root.addWidget(self._empty_card)

        root.addStretch()
        scroll.setWidget(body)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        self.refresh()

    # ── Public ───────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        idx        = self._period_combo.currentIndex()
        since_days = _PERIOD_OPTIONS[idx][1] if 0 <= idx < len(_PERIOD_OPTIONS) else None
        runs       = history_db.get_recent_runs(limit=200, since_days=since_days)
        trend      = list(reversed(runs[:40]))

        has_data = bool(runs)
        for w in (self._tile_total, self._tile_passrate,
                  self._tile_avgdur, self._tile_clean):
            w.setVisible(has_data)
        self._empty_card.setVisible(not has_data)

        self._updated_lbl.setText(
            "Updated " + datetime.datetime.now().strftime("%H:%M:%S")
        )
        self._trend_chart.set_data(trend)
        self._update_trend_range(trend)
        self._populate_stats(runs)
        self._populate_systems(runs)
        self._populate_attention()

    # ── Private ──────────────────────────────────────────────────────────────

    def _populate_stats(self, runs: list[dict]) -> None:
        if not runs:
            for v in (self._v_total, self._v_passrate, self._v_avgdur, self._v_clean):
                v.setText("—")
            return

        total      = len(runs)
        total_pass = sum(r.get("passed", 0) for r in runs)
        total_scr  = sum(r.get("total",  0) for r in runs)
        rate_pct   = (total_pass / total_scr * 100) if total_scr else 0.0
        avg_dur_s  = sum(r.get("duration_secs", 0) for r in runs) / total

        self._v_total.setText(str(total))

        self._v_passrate.setText(f"{rate_pct:.0f}%" if total_scr else "—")
        self._v_passrate.setStyleSheet(
            f"color: {_rate_color(rate_pct)}; font-size: 22px; font-weight: bold; "
            f"background: transparent; border: none;"
        )

        self._v_avgdur.setText(_fmt_dur(avg_dur_s))

        today_runs = history_db.get_recent_runs(limit=999, since_days=1)
        if today_runs:
            clean = sum(
                1 for r in today_runs
                if r.get("failed", 0) == 0 and r.get("errored", 0) == 0
                and r.get("total", 0) > 0
            )
            self._v_clean.setText(f"{clean}/{len(today_runs)}")
            self._v_clean.setStyleSheet(
                f"color: {_rate_color(clean / len(today_runs) * 100)}; font-size: 22px; "
                f"font-weight: bold; background: transparent; border: none;"
            )
        else:
            self._v_clean.setText("—")

    def _populate_systems(self, runs: list[dict]) -> None:
        while self._sys_layout.count():
            item = self._sys_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not runs:
            lbl = QLabel("No data")
            lbl.setStyleSheet(
                f"color: {_DIM}; font-size: 11px; padding: 8px 4px; background: transparent;"
            )
            self._sys_layout.addWidget(lbl)
            return

        buckets: dict[str, dict] = defaultdict(
            lambda: {"runs": 0, "passed": 0, "total": 0, "dur": 0.0}
        )
        for r in runs:
            sys_ = r.get("system") or "Unknown"
            b    = buckets[sys_]
            b["runs"]   += 1
            b["passed"] += r.get("passed", 0)
            b["total"]  += r.get("total",  0)
            b["dur"]    += r.get("duration_secs", 0.0)

        sorted_rows = sorted(buckets.items(), key=lambda x: x[1]["runs"], reverse=True)
        for i, (sys_, b) in enumerate(sorted_rows):
            if i > 0:
                self._sys_layout.addWidget(_hline())
            rate = (b["passed"] / b["total"] * 100) if b["total"] else None
            avg  = b["dur"] / b["runs"] if b["runs"] else 0.0
            self._sys_layout.addWidget(_sys_row(sys_, b["runs"], rate, avg))

    def _populate_attention(self) -> None:
        while self._att_layout.count():
            item = self._att_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        rows = history_db.get_script_failure_summary(limit=5)
        if not rows:
            ok = QLabel("✓  All scripts nominal")
            ok.setStyleSheet(
                f"color: {_GREEN}; font-size: 12px; padding: 8px 4px; background: transparent;"
            )
            self._att_layout.addWidget(ok)
            return

        for i, r in enumerate(rows):
            if i > 0:
                self._att_layout.addWidget(_hline())
            name     = r.get("script_name", "")
            total    = r.get("total_runs",  0)
            failures = r.get("failures",    0)
            rate_val = r.get("pass_rate",   0.0)
            flaky    = r.get("flaky", False)

            if flaky:
                status, color = "FLAKY",    _AMBER
            elif rate_val < 50:
                status, color = "FAILING",  _RED
            else:
                status, color = "UNSTABLE", _AMBER

            sub = (
                f"{failures} failure{'s' if failures != 1 else ''} "
                f"in {total} runs  ·  {rate_val:.0f}% pass"
            )
            self._att_layout.addWidget(_alert_row(name, sub, status, color))

    def _update_trend_range(self, trend: list[dict]) -> None:
        if len(trend) < 2:
            self._trend_range_lbl.setText("")
            return
        oldest = trend[0].get("timestamp",  "")[:10]
        newest = trend[-1].get("timestamp", "")[:10]
        self._trend_range_lbl.setText(f"{oldest} → {newest}  ({len(trend)} runs)")
