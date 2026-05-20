"""
orbit_report.py — Orbit360
Cross-run trend and reliability dashboard generator.

The per-run run_report.html (written by orbit_logger.py) captures detail for
a single run.  This module generates a separate trend_report.html that shows
reliability and performance patterns *across* runs — flakiness, pass-rate
trends, average duration changes, and a run history timeline.

Usage:

    from orbit360.utils.orbit_report import generate_trend_report
    from orbit360.utils.paths import ORBIT_DATA_DIR

    path = generate_trend_report(ORBIT_DATA_DIR)
    # → orbit_data/trend_report.html

From the command line:
    python -m orbit360.utils.orbit_report
"""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# ── Database helpers ──────────────────────────────────────────────────────────

def _load_recent_runs(db_path: Path, limit: int) -> List[dict]:
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT run_id, system, timestamp,
                       total, passed, failed, errored, duration_secs
                FROM runs
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _load_script_trends(
    db_path: Path, limit_per_script: int
) -> Dict[str, List[dict]]:
    """Return {script_name: [{status, duration_secs, run_id, timestamp}, ...]} oldest→newest."""
    if not db_path.exists():
        return {}
    try:
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT sr.script_name, sr.status, sr.duration_secs,
                       sr.run_id, r.timestamp
                FROM script_runs sr
                JOIN runs r ON r.run_id = sr.run_id
                ORDER BY r.timestamp DESC
                """
            ).fetchall()
        seen: Dict[str, int] = {}
        trends: Dict[str, List[dict]] = {}
        for row in rows:
            name = row["script_name"]
            seen[name] = seen.get(name, 0) + 1
            if seen[name] <= limit_per_script:
                trends.setdefault(name, []).append(dict(row))
        for k in trends:
            trends[k].reverse()   # oldest first
        return trends
    except Exception:
        return {}


# ── Metric calculations ───────────────────────────────────────────────────────

def _pass_rate(entries: List[dict]) -> float:
    if not entries:
        return 0.0
    return round(sum(1 for e in entries if e["status"] == "passed") / len(entries) * 100, 1)


def _is_flaky(entries: List[dict]) -> bool:
    if len(entries) < 3:
        return False
    statuses = {e["status"] for e in entries}
    return "passed" in statuses and bool(statuses & {"failed", "error"})


def _avg_duration(entries: List[dict]) -> float:
    durations = [e["duration_secs"] for e in entries if e["duration_secs"] > 0]
    return round(sum(durations) / len(durations), 1) if durations else 0.0


# ── HTML primitives ───────────────────────────────────────────────────────────

_DOT = {
    "passed": '<span class="dot pass" title="Passed">●</span>',
    "failed": '<span class="dot fail" title="Failed">●</span>',
    "error":  '<span class="dot err"  title="Error">●</span>',
}


def _dots(entries: List[dict]) -> str:
    return "".join(_DOT.get(e["status"], '<span class="dot unk" title="Unknown">●</span>')
                   for e in entries)


def _rate_bar(pct: float) -> str:
    color = "#a6e3a1" if pct >= 90 else "#fab387" if pct >= 60 else "#f38ba8"
    return (
        f'<div class="rate-bar" title="{pct}%">'
        f'<div class="rate-fill" style="width:{pct}%;background:{color}"></div>'
        f'</div>'
    )


def _run_card(run: dict) -> str:
    total   = run["total"] or 1
    passed  = run["passed"]
    failed  = run["failed"]
    errored = run["errored"]
    pct     = round(passed / total * 100)
    ts      = (run.get("timestamp") or "")[:16].replace("T", " ")
    dur     = f'{run["duration_secs"]:.0f}s'
    ok      = failed == 0 and errored == 0

    fail_badge  = f'<span class="fail"> · {failed} failed</span>'  if failed  else ""
    err_badge   = f'<span class="err"> · {errored} errored</span>' if errored else ""
    abort_badge = '<span class="dim"> · aborted</span>'            if run.get("aborted") else ""

    return (
        f'<div class="run-card">'
        f'<div class="run-id">{run["run_id"]}</div>'
        f'<div class="run-system">{run["system"]}</div>'
        f'<div class="run-bar">{_rate_bar(pct)}<span class="run-pct">{pct}%</span></div>'
        f'<div class="run-stats">'
        f'<span class="{"pass" if ok else "fail"}">{passed}/{total}</span>'
        f'{fail_badge}{err_badge}{abort_badge}'
        f'<br><span class="dim">{ts} · {dur}</span>'
        f'</div></div>'
    )


def _script_row(name: str, entries: List[dict]) -> str:
    pr      = _pass_rate(entries)
    flaky   = _is_flaky(entries)
    avg_dur = _avg_duration(entries)
    count   = len(entries)

    if pr >= 90:
        badge = '<span class="badge badge-pass">Stable</span>'
    elif flaky:
        badge = '<span class="badge badge-flaky">Flaky</span>'
    else:
        badge = '<span class="badge badge-fail">Failing</span>'

    return (
        f"<tr>"
        f'<td class="script-name">{name}</td>'
        f'<td data-val="{pr}">{_rate_bar(pr)}<span class="pct-label">{pr}%</span></td>'
        f'<td class="dots-cell">{_dots(entries)}</td>'
        f'<td>{badge}</td>'
        f'<td data-val="{avg_dur}" class="dim">{avg_dur}s</td>'
        f'<td data-val="{count}" class="dim">{count}</td>'
        f"</tr>"
    )


# ── Inline CSS ────────────────────────────────────────────────────────────────

_CSS = """\
:root {
    --bg:      #1e1e2e;
    --surface: #313244;
    --border:  #45475a;
    --text:    #cdd6f4;
    --dim:     #6c7086;
    --green:   #a6e3a1;
    --red:     #f38ba8;
    --orange:  #fab387;
    --blue:    #89b4fa;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
    background: var(--bg); color: var(--text);
    font-family: 'Segoe UI', system-ui, sans-serif;
    font-size: 14px; padding: 28px 32px;
}
h1 { color: var(--blue); font-size: 22px; margin-bottom: 4px; }
.meta { color: var(--dim); font-size: 12px; margin-bottom: 28px; }
.section-title {
    color: var(--blue); font-size: 14px; font-weight: 600; letter-spacing: .04em;
    text-transform: uppercase; margin: 28px 0 12px;
    border-bottom: 1px solid var(--border); padding-bottom: 6px;
}
/* Run cards */
.runs-grid {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
    gap: 12px; margin-bottom: 8px;
}
.run-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 8px; padding: 14px;
}
.run-id   { color: var(--blue); font-size: 11px; font-weight: 600; margin-bottom: 3px; }
.run-system { font-size: 13px; margin-bottom: 8px; }
.run-bar  { display: flex; align-items: center; gap: 8px; margin-bottom: 6px; }
.run-pct  { font-size: 12px; color: var(--dim); }
.run-stats { font-size: 12px; }
/* Rate bar */
.rate-bar {
    background: var(--border); border-radius: 4px;
    height: 7px; width: 70px; display: inline-block;
    vertical-align: middle; overflow: hidden; flex-shrink: 0;
}
.rate-fill { height: 100%; border-radius: 4px; }
/* Script table */
table { width: 100%; border-collapse: collapse; }
th {
    background: var(--surface); color: var(--dim);
    font-size: 11px; text-transform: uppercase; letter-spacing: .05em;
    padding: 8px 12px; text-align: left; user-select: none;
}
th.sortable { cursor: pointer; }
th.sortable:hover { color: var(--text); }
td { padding: 9px 12px; border-bottom: 1px solid var(--border); vertical-align: middle; }
tr:last-child td { border-bottom: none; }
tr:hover td { background: var(--surface); }
.script-name { font-size: 13px; max-width: 320px; word-break: break-word; }
.dots-cell { letter-spacing: 2px; }
.dot  { font-size: 14px; }
.pass { color: var(--green); }
.fail { color: var(--red); }
.err  { color: var(--orange); }
.dim  { color: var(--dim); }
.unk  { color: var(--border); }
.pct-label { font-size: 12px; color: var(--dim); margin-left: 6px; }
/* Badges */
.badge {
    display: inline-block; padding: 2px 9px; border-radius: 4px;
    font-size: 11px; font-weight: 600; white-space: nowrap;
}
.badge-pass  { background: #1e3a2f; color: var(--green); }
.badge-fail  { background: #3a1e2f; color: var(--red); }
.badge-flaky { background: #3a2e1e; color: var(--orange); }
"""

# ── Inline JS ─────────────────────────────────────────────────────────────────

_JS = """\
function sortTable(th, col) {
    const tbody = th.closest('table').querySelector('tbody');
    const rows  = [...tbody.rows];
    const asc   = th.dataset.asc !== 'true';
    th.dataset.asc = asc;
    rows.sort((a, b) => {
        const av = a.cells[col].dataset.val ?? a.cells[col].textContent.trim();
        const bv = b.cells[col].dataset.val ?? b.cells[col].textContent.trim();
        return asc
            ? av.localeCompare(bv, undefined, {numeric: true})
            : bv.localeCompare(av, undefined, {numeric: true});
    });
    rows.forEach(r => tbody.appendChild(r));
}
"""


# ── Main generator ────────────────────────────────────────────────────────────

def generate_trend_report(
    orbit_data_dir: Path,
    output_path: Optional[Path] = None,
    run_limit: int = 20,
    script_history_limit: int = 15,
) -> Path:
    """
    Read the SQLite run history and write a standalone HTML trend report.

    Args:
        orbit_data_dir:       Path to the orbit_data/ directory.
        output_path:          Destination for the HTML file.
                              Defaults to orbit_data/trend_report.html.
        run_limit:            Maximum number of recent runs to show.
        script_history_limit: Maximum number of past results per script.

    Returns:
        Path to the written HTML file.
    """
    db_path     = orbit_data_dir / "run_history.sqlite"
    output_path = output_path or orbit_data_dir / "trend_report.html"

    runs           = _load_recent_runs(db_path, run_limit)
    script_trends  = _load_script_trends(db_path, script_history_limit)
    generated_at   = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ── Run cards ──────────────────────────────────────────────────────
    if runs:
        runs_html = "\n".join(_run_card(r) for r in runs)
    else:
        runs_html = '<p class="dim" style="padding:12px 0">No run history found.</p>'

    # ── Script reliability table ────────────────────────────────────────
    if script_trends:
        rows_html = "\n    ".join(
            _script_row(name, entries)
            for name, entries in sorted(script_trends.items())
        )
    else:
        rows_html = '<tr><td colspan="6" class="dim">No script history yet.</td></tr>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orbit360 — Trend Report</title>
<style>{_CSS}</style>
</head>
<body>

<h1>Orbit360 — Trend Report</h1>
<p class="meta">
  Generated {generated_at}
  &nbsp;·&nbsp; Last {run_limit} runs
  &nbsp;·&nbsp; Up to {script_history_limit} results per script
</p>

<div class="section-title">Recent Runs</div>
<div class="runs-grid">
{runs_html}
</div>

<div class="section-title">Script Reliability</div>
<table>
  <thead>
    <tr>
      <th class="sortable" onclick="sortTable(this,0)">Script ↕</th>
      <th class="sortable" onclick="sortTable(this,1)">Pass Rate ↕</th>
      <th>Last {script_history_limit} Results</th>
      <th>Status</th>
      <th class="sortable" onclick="sortTable(this,4)">Avg Duration ↕</th>
      <th class="sortable" onclick="sortTable(this,5)">Runs ↕</th>
    </tr>
  </thead>
  <tbody>
    {rows_html}
  </tbody>
</table>

<script>{_JS}</script>
</body>
</html>"""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    return output_path


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    _root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(_root))
    from orbit360.utils.paths import ORBIT_DATA_DIR  # noqa: E402

    out = generate_trend_report(ORBIT_DATA_DIR)
    print(f"Trend report written → {out}")
