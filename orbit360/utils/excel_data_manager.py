"""
excel_data_manager.py — Orbit360
SQLite-backed test data row tracker for Excel-sourced patient/case pools.

Each test suite declares an Excel file in its run_sequence.yaml:

    test_data:
      path: "test_data/CAC/PreProd/Houston/patients.xlsx"
      sheet: 0
      run_flag_col: "Run"
      reset_on_run: true   # optional — reset pool automatically on each Full Run

Scripts call claim_excel_row() / release_excel_row() to consume one row at a
time atomically.  Multiple analysts never process the same patient.

State DB:    orbit_data/test_data_state.sqlite
History DB:  same file, test_data_row_history table
Excel files: orbit_data/<path from yaml>

All public functions are safe to call when the DB or Excel file is unavailable;
they log the error and return safe defaults so a failure never crashes the app.
"""

from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from orbit360.utils.paths import ORBIT_DATA_DIR

_DB_PATH = ORBIT_DATA_DIR / "test_data_state.sqlite"

# How long a row can stay "claimed" before it is considered stale (minutes).
STALE_CLAIM_MINUTES = 120

log = logging.getLogger(__name__)

# ── Schema ────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS test_data_rows (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    excel_path   TEXT    NOT NULL,
    row_index    INTEGER NOT NULL,
    status       TEXT    NOT NULL DEFAULT 'available',
    run_id       TEXT    NOT NULL DEFAULT '',
    claimed_at   TEXT    NOT NULL DEFAULT '',
    completed_at TEXT    NOT NULL DEFAULT '',
    notes        TEXT    NOT NULL DEFAULT '',
    UNIQUE(excel_path, row_index)
);
CREATE INDEX IF NOT EXISTS idx_tdr_path   ON test_data_rows(excel_path);
CREATE INDEX IF NOT EXISTS idx_tdr_status ON test_data_rows(excel_path, status);

CREATE TABLE IF NOT EXISTS test_data_row_history (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    excel_path TEXT    NOT NULL,
    row_index  INTEGER NOT NULL,
    run_id     TEXT    NOT NULL DEFAULT '',
    status     TEXT    NOT NULL,
    notes      TEXT    NOT NULL DEFAULT '',
    timestamp  TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tdrh_path  ON test_data_row_history(excel_path, row_index);
CREATE INDEX IF NOT EXISTS idx_tdrh_run   ON test_data_row_history(run_id);
"""

# ── Internal helpers ──────────────────────────────────────────────────────────

def _connect() -> sqlite3.Connection:
    ORBIT_DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH), timeout=10)
    conn.executescript(_SCHEMA)
    conn.commit()
    return conn


def _norm(path: str | Path) -> str:
    """Normalise a path to a consistent string key for DB lookups."""
    return str(Path(path).resolve())


def _load_openpyxl():
    try:
        import openpyxl
        return openpyxl
    except ImportError:
        raise RuntimeError(
            "openpyxl is required for Excel data management. "
            "Install it with:  pip install openpyxl"
        )


def _read_excel_rows(
    excel_path: Path,
    sheet: str | int = 0,
    run_flag_col: str | None = None,
) -> list[dict[str, Any]]:
    """Read all data rows from an Excel sheet. Returns list of {header: value} dicts."""
    openpyxl = _load_openpyxl()
    wb = openpyxl.load_workbook(str(excel_path), data_only=True)

    if isinstance(sheet, int):
        ws = wb.worksheets[sheet]
    else:
        if sheet not in wb.sheetnames:
            raise ValueError(f"Sheet {sheet!r} not found. Available: {wb.sheetnames}")
        ws = wb[sheet]

    raw = list(ws.iter_rows(values_only=True))
    if not raw:
        return []

    headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(raw[0])]
    rows = [dict(zip(headers, row)) for row in raw[1:] if any(c is not None for c in row)]

    if run_flag_col:
        if run_flag_col not in headers:
            raise ValueError(f"run_flag_col {run_flag_col!r} not in headers: {headers}")
        rows = [r for r in rows if str(r.get(run_flag_col) or "").strip().upper() == "Y"]

    return rows


def _read_excel_headers(excel_path: Path, sheet: str | int = 0) -> list[str]:
    """Return just the header row of an Excel sheet without loading all data."""
    openpyxl = _load_openpyxl()
    wb = openpyxl.load_workbook(str(excel_path), data_only=True, read_only=True)
    if isinstance(sheet, int):
        ws = wb.worksheets[sheet]
    else:
        ws = wb[sheet]
    for row in ws.iter_rows(min_row=1, max_row=1, values_only=True):
        return [str(h) if h is not None else f"col_{i}" for i, h in enumerate(row)]
    return []


def _write_excel_result(
    excel_path: Path,
    row_index: int,
    status: str,
    notes: str,
    sheet: str | int = 0,
) -> None:
    """Write Result/Notes/Timestamp columns back to the Excel file."""
    openpyxl = _load_openpyxl()
    wb = openpyxl.load_workbook(str(excel_path))

    if isinstance(sheet, int):
        ws = wb.worksheets[sheet]
    else:
        ws = wb[sheet]

    header_row = [cell.value for cell in ws[1]]
    result_cols: dict[str, int | None] = {"Result": None, "Notes": None, "Timestamp": None}
    for col_idx, header in enumerate(header_row, start=1):
        if header in result_cols:
            result_cols[header] = col_idx

    next_col = len(header_row) + 1
    for col_name in ("Result", "Notes", "Timestamp"):
        if result_cols[col_name] is None:
            ws.cell(row=1, column=next_col, value=col_name)
            result_cols[col_name] = next_col
            next_col += 1

    excel_row = row_index + 2
    ws.cell(row=excel_row, column=result_cols["Result"],    value=status.upper())
    ws.cell(row=excel_row, column=result_cols["Notes"],     value=notes)
    ws.cell(row=excel_row, column=result_cols["Timestamp"],
            value=datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"))
    wb.save(str(excel_path))


# ── Public API ────────────────────────────────────────────────────────────────

def sync_from_excel(
    excel_path: str | Path,
    sheet: str | int = 0,
    run_flag_col: str | None = None,
) -> int:
    """
    Import rows from an Excel file into the state DB.
    Only inserts rows not yet tracked (INSERT OR IGNORE).
    Returns the total number of rows now tracked for this file.
    """
    excel_path = Path(excel_path)
    if not excel_path.exists():
        log.warning("sync_from_excel: file not found: %s", excel_path)
        return 0
    try:
        rows = _read_excel_rows(excel_path, sheet, run_flag_col)
        key  = _norm(excel_path)
        conn = _connect()
        with conn:
            conn.executemany(
                "INSERT OR IGNORE INTO test_data_rows "
                "(excel_path, row_index, status) VALUES (?, ?, 'available')",
                [(key, i) for i in range(len(rows))],
            )
        total = conn.execute(
            "SELECT COUNT(*) FROM test_data_rows WHERE excel_path=?", (key,)
        ).fetchone()[0]
        conn.close()
        log.debug("sync_from_excel: %d rows tracked for %s", total, excel_path.name)
        return total
    except Exception as exc:
        log.warning("sync_from_excel failed: %s", exc)
        return 0


def claim_row(
    excel_path: str | Path,
    run_id: str = "",
    sheet: str | int = 0,
    run_flag_col: str | None = None,
    force_row_index: int | None = None,
) -> tuple[int, dict] | tuple[None, None]:
    """
    Atomically claim a row from the pool.
    Auto-syncs from Excel if no rows are tracked yet.

    If force_row_index is given, that specific row is claimed (if available).
    Falls back to the next available row if the forced row is not claimable.

    Returns (row_index, row_dict) on success, or (None, None) when exhausted.
    """
    excel_path = Path(excel_path)
    key = _norm(excel_path)

    try:
        conn = _connect()

        # Auto-sync on first use
        tracked = conn.execute(
            "SELECT COUNT(*) FROM test_data_rows WHERE excel_path=?", (key,)
        ).fetchone()[0]
        if tracked == 0:
            conn.close()
            sync_from_excel(excel_path, sheet, run_flag_col)
            conn = _connect()

        # BEGIN IMMEDIATE prevents two concurrent callers from claiming the same row
        conn.execute("BEGIN IMMEDIATE")

        # Try forced row first, then fall back to next available
        row = None
        if force_row_index is not None:
            row = conn.execute(
                "SELECT row_index FROM test_data_rows "
                "WHERE excel_path=? AND row_index=? AND status='available'",
                (key, force_row_index),
            ).fetchone()
        if row is None:
            row = conn.execute(
                "SELECT row_index FROM test_data_rows "
                "WHERE excel_path=? AND status='available' ORDER BY row_index LIMIT 1",
                (key,),
            ).fetchone()

        if row is None:
            conn.rollback()
            conn.close()
            log.info("claim_row: pool exhausted for %s", excel_path.name)
            return None, None

        row_index = row[0]
        now = datetime.now().isoformat()
        conn.execute(
            "UPDATE test_data_rows SET status='claimed', run_id=?, claimed_at=? "
            "WHERE excel_path=? AND row_index=?",
            (run_id, now, key, row_index),
        )
        conn.commit()
        conn.close()

        rows = _read_excel_rows(excel_path, sheet, run_flag_col)
        row_dict = rows[row_index] if row_index < len(rows) else {}
        log.info("claim_row: claimed row %d from %s (run_id=%r)", row_index, excel_path.name, run_id)
        return row_index, row_dict

    except Exception as exc:
        log.warning("claim_row failed: %s", exc)
        return None, None


def release_row(
    excel_path: str | Path,
    row_index: int,
    status: str,
    notes: str = "",
    sheet: str | int = 0,
) -> None:
    """
    Mark a claimed row as done in the DB, append to row history, and write
    the result back to Excel.
    status should be one of: "pass" | "fail" | "skip"
    """
    excel_path = Path(excel_path)
    key    = _norm(excel_path)
    status = status.lower()
    now    = datetime.now().isoformat()

    try:
        conn = _connect()
        # Fetch run_id before updating so we can log it in history
        cur_row = conn.execute(
            "SELECT run_id FROM test_data_rows WHERE excel_path=? AND row_index=?",
            (key, row_index),
        ).fetchone()
        run_id = cur_row[0] if cur_row else ""

        with conn:
            conn.execute(
                "UPDATE test_data_rows "
                "SET status=?, notes=?, completed_at=? "
                "WHERE excel_path=? AND row_index=?",
                (status, notes, now, key, row_index),
            )
            conn.execute(
                "INSERT INTO test_data_row_history "
                "(excel_path, row_index, run_id, status, notes, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (key, row_index, run_id, status, notes, now),
            )
        conn.close()
        log.info("release_row: row %d → %s (%s)", row_index, status, excel_path.name)
    except Exception as exc:
        log.warning("release_row DB update failed: %s", exc)

    try:
        if excel_path.exists():
            _write_excel_result(excel_path, row_index, status, notes, sheet)
    except Exception as exc:
        log.warning("release_row Excel write failed: %s", exc)


def set_row_status(
    excel_path: str | Path,
    row_index: int,
    status: str,
    notes: str = "",
    sheet: str | int = 0,
) -> None:
    """
    Manually force a row to any status (for right-click GUI actions).
    Appends a history entry and, for terminal statuses, writes back to Excel.
    """
    excel_path = Path(excel_path)
    key    = _norm(excel_path)
    status = status.lower()
    now    = datetime.now().isoformat()

    terminal = status in ("pass", "fail", "skip")
    try:
        conn = _connect()
        with conn:
            conn.execute(
                "UPDATE test_data_rows "
                "SET status=?, notes=?, completed_at=? "
                "WHERE excel_path=? AND row_index=?",
                (status, notes, now if terminal else "", key, row_index),
            )
            conn.execute(
                "INSERT INTO test_data_row_history "
                "(excel_path, row_index, run_id, status, notes, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (key, row_index, "manual", status, notes, now),
            )
        conn.close()
    except Exception as exc:
        log.warning("set_row_status failed: %s", exc)
        return

    if terminal:
        try:
            if excel_path.exists():
                _write_excel_result(excel_path, row_index, status, notes, sheet)
        except Exception as exc:
            log.warning("set_row_status Excel write failed: %s", exc)


def get_all_rows(
    excel_path: str | Path,
    sheet: str | int = 0,
    run_flag_col: str | None = None,
) -> list[dict]:
    """
    Return all tracked rows for a file with their current status and history.
    Each dict contains DB state fields + the original Excel column values.
    If no rows are tracked yet, attempts a sync first.
    """
    excel_path = Path(excel_path)
    key = _norm(excel_path)

    try:
        conn = _connect()
        tracked = conn.execute(
            "SELECT COUNT(*) FROM test_data_rows WHERE excel_path=?", (key,)
        ).fetchone()[0]
        conn.close()

        if tracked == 0 and excel_path.exists():
            sync_from_excel(excel_path, sheet, run_flag_col)

        excel_rows: list[dict] = []
        if excel_path.exists():
            try:
                excel_rows = _read_excel_rows(excel_path, sheet, run_flag_col)
            except Exception as exc:
                log.warning("get_all_rows: Excel read failed: %s", exc)

        conn = _connect()
        db_rows = conn.execute(
            "SELECT row_index, status, run_id, claimed_at, completed_at, notes "
            "FROM test_data_rows WHERE excel_path=? ORDER BY row_index",
            (key,),
        ).fetchall()

        # Fetch history counts per row in one query
        history_counts = dict(conn.execute(
            "SELECT row_index, COUNT(*) FROM test_data_row_history "
            "WHERE excel_path=? GROUP BY row_index",
            (key,),
        ).fetchall())
        conn.close()

        result = []
        for row_index, status, run_id, claimed_at, completed_at, notes in db_rows:
            entry: dict = {
                "_row_index":    row_index,
                "_status":       status,
                "_run_id":       run_id,
                "_claimed_at":   claimed_at,
                "_completed_at": completed_at,
                "_notes":        notes,
                "_history_count": history_counts.get(row_index, 0),
            }
            if row_index < len(excel_rows):
                entry.update(excel_rows[row_index])
            result.append(entry)
        return result

    except Exception as exc:
        log.warning("get_all_rows failed: %s", exc)
        return []


def get_row_history(excel_path: str | Path, row_index: int) -> list[dict]:
    """
    Return the full run history for a single row, newest first.
    Each entry: {run_id, status, notes, timestamp}
    """
    key = _norm(excel_path)
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT run_id, status, notes, timestamp "
            "FROM test_data_row_history "
            "WHERE excel_path=? AND row_index=? ORDER BY id DESC",
            (key, row_index),
        ).fetchall()
        conn.close()
        return [
            {"run_id": r, "status": s, "notes": n, "timestamp": t}
            for r, s, n, t in rows
        ]
    except Exception as exc:
        log.warning("get_row_history failed: %s", exc)
        return []


def get_summary(excel_path: str | Path) -> dict:
    """Return {available, claimed, pass, fail, skip, total, stale} counts for a file."""
    key = _norm(excel_path)
    defaults = {
        "available": 0, "claimed": 0,
        "pass": 0, "fail": 0, "skip": 0,
        "total": 0, "stale": 0,
    }
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT status, COUNT(*) FROM test_data_rows "
            "WHERE excel_path=? GROUP BY status",
            (key,),
        ).fetchall()
        conn.close()
        result = dict(defaults)
        for status, count in rows:
            if status in result:
                result[status] = count
        result["total"] = sum(
            result[s] for s in ("available", "claimed", "pass", "fail", "skip")
        )
        result["stale"] = len(get_stale_claims(excel_path))
        return result
    except Exception as exc:
        log.warning("get_summary failed: %s", exc)
        return defaults


def get_stale_claims(
    excel_path: str | Path,
    timeout_minutes: int = STALE_CLAIM_MINUTES,
) -> list[dict]:
    """
    Return rows that have been 'claimed' for longer than timeout_minutes.
    Each entry: {row_index, run_id, claimed_at, minutes_elapsed}
    """
    key      = _norm(excel_path)
    cutoff   = (datetime.now() - timedelta(minutes=timeout_minutes)).isoformat()
    try:
        conn = _connect()
        rows = conn.execute(
            "SELECT row_index, run_id, claimed_at FROM test_data_rows "
            "WHERE excel_path=? AND status='claimed' AND claimed_at != '' AND claimed_at < ?",
            (key, cutoff),
        ).fetchall()
        conn.close()
        result = []
        for row_index, run_id, claimed_at in rows:
            try:
                dt = datetime.fromisoformat(claimed_at)
                elapsed = int((datetime.now() - dt).total_seconds() / 60)
            except ValueError:
                elapsed = -1
            result.append({
                "row_index":      row_index,
                "run_id":         run_id,
                "claimed_at":     claimed_at,
                "minutes_elapsed": elapsed,
            })
        return result
    except Exception as exc:
        log.warning("get_stale_claims failed: %s", exc)
        return []


def recover_stale_claims(
    excel_path: str | Path,
    timeout_minutes: int = STALE_CLAIM_MINUTES,
) -> int:
    """
    Reset stale claimed rows back to 'available'.
    Returns the number of rows recovered.
    """
    stale = get_stale_claims(excel_path, timeout_minutes)
    if not stale:
        return 0
    key = _norm(excel_path)
    now = datetime.now().isoformat()
    try:
        conn = _connect()
        with conn:
            for entry in stale:
                conn.execute(
                    "UPDATE test_data_rows "
                    "SET status='available', run_id='', claimed_at='', notes='' "
                    "WHERE excel_path=? AND row_index=?",
                    (key, entry["row_index"]),
                )
                conn.execute(
                    "INSERT INTO test_data_row_history "
                    "(excel_path, row_index, run_id, status, notes, timestamp) "
                    "VALUES (?, ?, ?, 'available', ?, ?)",
                    (key, entry["row_index"], entry["run_id"], "stale-recovered", now),
                )
        conn.close()
        log.info(
            "recover_stale_claims: recovered %d rows for %s",
            len(stale), Path(excel_path).name,
        )
        return len(stale)
    except Exception as exc:
        log.warning("recover_stale_claims failed: %s", exc)
        return 0


def reset_rows(excel_path: str | Path) -> int:
    """
    Reset all rows for a file back to 'available'.
    Returns the number of rows reset.
    """
    key = _norm(excel_path)
    now = datetime.now().isoformat()
    try:
        conn = _connect()
        rows_to_reset = conn.execute(
            "SELECT row_index, run_id FROM test_data_rows "
            "WHERE excel_path=? AND status != 'available'",
            (key,),
        ).fetchall()
        with conn:
            conn.execute(
                "UPDATE test_data_rows "
                "SET status='available', run_id='', claimed_at='', completed_at='', notes='' "
                "WHERE excel_path=?",
                (key,),
            )
            if rows_to_reset:
                conn.executemany(
                    "INSERT INTO test_data_row_history "
                    "(excel_path, row_index, run_id, status, notes, timestamp) "
                    "VALUES (?, ?, ?, 'available', 'manual-reset', ?)",
                    [(key, ri, rid, now) for ri, rid in rows_to_reset],
                )
        count = len(rows_to_reset)
        conn.close()
        log.info("reset_rows: %d rows reset for %s", count, Path(excel_path).name)
        return count
    except Exception as exc:
        log.warning("reset_rows failed: %s", exc)
        return 0


def get_excel_headers(excel_path: str | Path, sheet: str | int = 0) -> list[str]:
    """Return the column headers from an Excel file without loading all row data."""
    try:
        return _read_excel_headers(Path(excel_path), sheet)
    except Exception as exc:
        log.warning("get_excel_headers failed: %s", exc)
        return []


def get_global_stale_count(timeout_minutes: int = STALE_CLAIM_MINUTES) -> int:
    """
    Return the total number of stale claimed rows across ALL tracked Excel files.
    Safe to call when the DB is unavailable — returns 0 on any error.
    """
    cutoff = (datetime.now() - timedelta(minutes=timeout_minutes)).isoformat()
    try:
        conn  = _connect()
        count = conn.execute(
            "SELECT COUNT(*) FROM test_data_rows "
            "WHERE status = 'claimed' AND claimed_at != '' AND claimed_at < ?",
            (cutoff,),
        ).fetchone()[0]
        conn.close()
        return count
    except Exception as exc:
        log.warning("get_global_stale_count failed: %s", exc)
        return 0
