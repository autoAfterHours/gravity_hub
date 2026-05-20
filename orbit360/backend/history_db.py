"""
history_db.py — Orbit360 v4.0
SQLite-backed run history store.

Schema (two tables):

  runs
    id            INTEGER PRIMARY KEY AUTOINCREMENT
    run_id        TEXT UNIQUE         — the OrbitLogger run_id (e.g. "20260306_143022")
    system        TEXT                — human label (e.g. "CAC / QA / CER")
    timestamp     TEXT                — ISO-8601 UTC of run start
    total         INTEGER
    passed        INTEGER
    failed        INTEGER
    errored       INTEGER
    duration_secs REAL

  script_runs
    id            INTEGER PRIMARY KEY AUTOINCREMENT
    run_id        TEXT                — FK → runs.run_id
    script_name   TEXT
    status        TEXT                — "passed" | "failed" | "error"
    duration_secs REAL

The DB lives at ORBIT_DATA_DIR/run_history.sqlite and is created on first use.
All public methods are safe to call even when the DB is unavailable — they log
the error and return safe defaults so a DB failure never crashes the app.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from orbit360.orbit_logger import ScriptResult

from orbit360.utils.paths import ORBIT_DATA_DIR

_DB_PATH = ORBIT_DATA_DIR / "run_history.sqlite"
_HISTORY_LIMIT = 10  # how many recent runs to show in sparklines

log = logging.getLogger(__name__)

# ── DDL ───────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT    NOT NULL UNIQUE,
    system        TEXT    NOT NULL DEFAULT '',
    timestamp     TEXT    NOT NULL DEFAULT '',
    total         INTEGER NOT NULL DEFAULT 0,
    passed        INTEGER NOT NULL DEFAULT 0,
    failed        INTEGER NOT NULL DEFAULT 0,
    errored       INTEGER NOT NULL DEFAULT 0,
    duration_secs REAL    NOT NULL DEFAULT 0.0
);

CREATE TABLE IF NOT EXISTS script_runs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id        TEXT    NOT NULL,
    script_name   TEXT    NOT NULL,
    status        TEXT    NOT NULL,
    duration_secs REAL    NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_script_runs_name ON script_runs(script_name);
CREATE INDEX IF NOT EXISTS idx_script_runs_run  ON script_runs(run_id);
"""


def _connect() -> sqlite3.Connection:
    """Open (and if necessary create) the history DB."""
    ORBIT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


# ── Public API ────────────────────────────────────────────────────────────────

def record_run(
    run_id: str,
    system: str,
    timestamp: str,
    results: "list[ScriptResult]",
    duration_secs: float,
) -> None:
    """
    Persist a completed run.  Safe to call from any thread; uses its own
    short-lived connection so it never contends with the GUI thread.
    """
    passed  = sum(1 for r in results if r.status == "passed")
    failed  = sum(1 for r in results if r.status == "failed")
    errored = sum(1 for r in results if r.status == "error")
    total   = len(results)
    try:
        conn = _connect()
        with conn:
            conn.execute(
                "INSERT OR REPLACE INTO runs "
                "(run_id, system, timestamp, total, passed, failed, errored, duration_secs) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (run_id, system, timestamp, total, passed, failed, errored, round(duration_secs, 3)),
            )
            conn.executemany(
                "INSERT INTO script_runs (run_id, script_name, status, duration_secs) "
                "VALUES (?, ?, ?, ?)",
                [(run_id, r.script_name, r.status, round(r.duration_seconds, 3)) for r in results],
            )
        conn.close()
    except Exception as exc:
        log.warning("history_db.record_run failed: %s", exc)


def get_script_history(script_name: str, limit: int = _HISTORY_LIMIT) -> list[str]:
    """
    Return the last `limit` run statuses for `script_name`, oldest first.
    e.g. ["passed", "passed", "failed", "passed"]
    Returns [] when the DB is missing or the script has no history.
    """
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT status FROM script_runs "
            "WHERE script_name = ? "
            "ORDER BY id DESC LIMIT ?",
            (script_name, limit),
        ).fetchall()
        conn.close()
        return [r[0] for r in reversed(rows)]   # oldest → newest
    except Exception as exc:
        log.warning("history_db.get_script_history failed: %s", exc)
        return []


def get_all_script_histories(
    script_names: list[str], limit: int = _HISTORY_LIMIT
) -> dict[str, list[str]]:
    """
    Batch version of get_script_history.  One DB round-trip for all scripts.
    Returns {script_name: [status, ...]} for every name in `script_names`.
    Missing scripts map to [].
    """
    if not script_names:
        return {}
    try:
        placeholders = ",".join("?" * len(script_names))
        conn = _connect()
        rows = conn.execute(
            f"SELECT script_name, status, id FROM script_runs "
            f"WHERE script_name IN ({placeholders}) "
            f"ORDER BY id ASC",
            script_names,
        ).fetchall()
        conn.close()

        # Group and trim to `limit` most recent per script
        from collections import defaultdict
        grouped: dict[str, list[str]] = defaultdict(list)
        for script_name, status, _ in rows:
            grouped[script_name].append(status)
        return {
            name: grouped[name][-limit:] if name in grouped else []
            for name in script_names
        }
    except Exception as exc:
        log.warning("history_db.get_all_script_histories failed: %s", exc)
        return {name: [] for name in script_names}


def get_recent_runs(limit: int = 6, since_days: int | None = None) -> list[dict]:
    """
    Return the last `limit` runs in reverse-chronological order (newest first).
    If `since_days` is given, only runs whose timestamp is within that many days
    of now are included.
    Each dict has keys: run_id, system, timestamp, total, passed, failed, errored,
    duration_secs.  Returns [] when the DB is missing or empty.
    """
    try:
        conn = _connect()
        base = (
            "SELECT run_id, system, timestamp, total, passed, failed, errored, duration_secs "
            "FROM runs"
        )
        if since_days is not None:
            rows = conn.execute(
                base + " WHERE timestamp >= datetime('now', ?) ORDER BY id DESC LIMIT ?",
                (f"-{since_days} days", limit),
            ).fetchall()
        else:
            rows = conn.execute(base + " ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        conn.close()
        keys = ("run_id", "system", "timestamp", "total", "passed", "failed", "errored", "duration_secs")
        return [dict(zip(keys, row)) for row in rows]
    except Exception as exc:
        log.warning("history_db.get_recent_runs failed: %s", exc)
        return []


def get_script_failure_summary(limit: int = 10) -> list[dict]:
    """
    Return the top `limit` scripts ordered by failure count.
    Each dict has: script_name, total_runs, failures, passes, pass_rate, flaky.
    Only scripts that have at least one failure are returned.
    """
    try:
        conn = _connect()
        rows = conn.execute(
            """
            SELECT
                script_name,
                COUNT(*) AS total_runs,
                SUM(CASE WHEN status IN ('failed','error') THEN 1 ELSE 0 END) AS failures,
                SUM(CASE WHEN status = 'passed'            THEN 1 ELSE 0 END) AS passes
            FROM script_runs
            GROUP BY script_name
            HAVING failures > 0
            ORDER BY failures DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        conn.close()
        result = []
        for script_name, total_runs, failures, passes in rows:
            pass_rate = (passes / total_runs * 100) if total_runs else 0.0
            statuses  = get_script_history(script_name, limit=20)
            result.append({
                "script_name": script_name,
                "total_runs":  total_runs,
                "failures":    failures,
                "passes":      passes,
                "pass_rate":   pass_rate,
                "flaky":       is_flaky(statuses),
            })
        return result
    except Exception as exc:
        log.warning("history_db.get_script_failure_summary failed: %s", exc)
        return []


def get_run_trend(limit: int = 20) -> list[dict]:
    """
    Return the last `limit` runs oldest-first, suitable for a sparkline.
    Each dict has keys: passed, failed, errored, total.
    Returns [] when the DB is missing or empty.
    """
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT passed, failed, errored, total FROM runs ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        conn.close()
        keys = ("passed", "failed", "errored", "total")
        return [dict(zip(keys, row)) for row in reversed(rows)]
    except Exception as exc:
        log.warning("history_db.get_run_trend failed: %s", exc)
        return []


def get_run_scripts(run_id: str) -> list[dict]:
    """
    Return per-script results for a single run, in execution order.
    Each dict has: script_name, status, duration_secs.
    """
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT script_name, status, duration_secs FROM script_runs "
            "WHERE run_id = ? ORDER BY id",
            (run_id,),
        ).fetchall()
        conn.close()
        return [{"script_name": n, "status": s, "duration_secs": d} for n, s, d in rows]
    except Exception as exc:
        log.warning("history_db.get_run_scripts failed: %s", exc)
        return []


def get_flaky_script_count() -> int:
    """
    Return the number of scripts whose recent history is flaky (both passes
    and failures in at least 3 runs).  Single SQL query — no N+1 calls.
    """
    try:
        conn  = _connect()
        count = conn.execute(
            """
            SELECT COUNT(*) FROM (
                SELECT script_name,
                       SUM(CASE WHEN status = 'passed'            THEN 1 ELSE 0 END) AS passes,
                       SUM(CASE WHEN status IN ('failed','error')  THEN 1 ELSE 0 END) AS fails,
                       COUNT(*) AS total
                FROM script_runs
                GROUP BY script_name
                HAVING total >= 3 AND passes > 0 AND fails > 0
            )
            """,
        ).fetchone()[0]
        conn.close()
        return count
    except Exception as exc:
        log.warning("history_db.get_flaky_script_count failed: %s", exc)
        return 0


def is_flaky(statuses: list[str]) -> bool:
    """
    A script is considered flaky if its recent history contains BOTH a pass
    AND a failure (not all-pass and not all-fail).  Requires at least 3 runs
    of data to avoid false-positives on brand-new scripts.
    """
    if len(statuses) < 3:
        return False
    has_pass = any(s == "passed" for s in statuses)
    has_fail = any(s in ("failed", "error") for s in statuses)
    return has_pass and has_fail
