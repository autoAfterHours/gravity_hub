"""
sql_executor.py — Orbit360 SQL executor (Phase 5, read-only).

Unlike subprocess-based executors, SQL runs in-process via Python's DB-API 2.0.
execute() is fully overridden; build_command() is never called.

Read-only policy
    Only SELECT statements are executed.  Any other keyword (INSERT, UPDATE,
    DELETE, DROP, CREATE, EXEC, …) is logged as a warning and skipped.
    sqlite connections are opened with ?mode=ro so the driver itself enforces
    read-only access at the file level.  pyodbc connections use autocommit=True
    so no transaction can be left open by accident.

Supported dialects (ORBIT_SQL_DIALECT env var):
    sqlite  — local .db file via stdlib sqlite3; no extra dependencies
    mssql   — SQL Server via pyodbc (requires pyodbc + ODBC driver install)
    oracle  — Oracle via pyodbc (driver TBD — DSN string carries all auth)

ORBIT environment variables:
    ORBIT_SQL_DIALECT       sqlite | mssql | oracle  (required)
    ORBIT_SQL_DB_PATH       Absolute path to .db file (sqlite only)
    ORBIT_SQL_DSN           Full pyodbc connection string (mssql / oracle)
    ORBIT_SQL_TIMEOUT       Per-statement timeout in seconds (default: 30)
    ORBIT_SQL_OUTPUT_FORMAT csv | json | log  (default: log)

Result output:
    log   — each row emitted as a formatted log line
    csv   — written to ORBIT_LOG_DIR/results_<n>.csv; path emitted to log
            and to ORBIT_OUTPUT|sql_results_<n>=<path> (feeds context.json)
    json  — written to ORBIT_LOG_DIR/results_<n>.json; same ORBIT_OUTPUT feed

Activation:
    engine hint 'sql' in run_sequence.yaml   OR   .sql file extension.
"""

from __future__ import annotations

import csv
import io
import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from orbit360.executors.base import BaseExecutor, ExecutionContext, ExecutionResult


# ── Dialect ──────────────────────────────────────────────────────────────── #

class SQLDialect(Enum):
    SQLITE = "sqlite"
    MSSQL  = "mssql"
    ORACLE = "oracle"


# ── Connection spec ───────────────────────────────────────────────────────── #

@dataclass
class SQLConnectionSpec:
    """
    Resolved connection parameters for one SQL executor run.
    Built from ORBIT env vars by _resolve_connection_spec().
    """
    dialect:        SQLDialect
    db_path:        Optional[Path] = None   # sqlite only
    dsn:            Optional[str]  = None   # mssql / oracle — carries all auth
    timeout_sec:    int            = 30
    output_format:  str            = "log"  # csv | json | log
    extra_options:  dict           = field(default_factory=dict)


# ── Helpers ───────────────────────────────────────────────────────────────── #

# SQL keywords that mutate state — skipped under read-only policy.
_WRITE_KEYWORDS = frozenset({
    "INSERT", "UPDATE", "DELETE", "MERGE", "REPLACE",
    "CREATE", "ALTER", "DROP", "TRUNCATE",
    "EXEC", "EXECUTE", "CALL", "GRANT", "REVOKE",
    "BEGIN", "COMMIT", "ROLLBACK",
})

_COMMENT_SINGLE = re.compile(r"--[^\n]*")
_COMMENT_BLOCK  = re.compile(r"/\*.*?\*/", re.DOTALL)


# ── Executor ──────────────────────────────────────────────────────────────── #

class SQLExecutor(BaseExecutor):
    """
    In-process, read-only SQL executor backed by DB-API 2.0.

    Routing:  can_handle() matches engine: sql or .sql extension.
    Runtime:  execute() is fully overridden; build_command() is never used.
    Policy:   Only SELECT statements are executed.  Everything else is skipped.
    """

    # ── Routing ───────────────────────────────────────────────────────────── #

    def can_handle(self, script_path: Path, engine_hint: Optional[str]) -> bool:
        if engine_hint:
            return engine_hint == "sql"
        return script_path.suffix.lower() == ".sql"

    def build_command(self, ctx: ExecutionContext) -> list[str]:
        # SQL runs in-process; this method is never reached because execute()
        # is overridden.  Required only to satisfy the abstract base class.
        raise RuntimeError(
            "SQLExecutor.build_command() should never be called — "
            "execute() is fully overridden for in-process SQL execution."
        )

    # ── Main entry point ──────────────────────────────────────────────────── #

    def execute(self, ctx: ExecutionContext) -> ExecutionResult:
        """
        Drive a full SQL script run with retry and abort support.

        Flow:
            1. Resolve connection spec from ORBIT env vars
            2. Parse .sql file into individual statements
            3. Acquire a DB connection for the resolved dialect
            4. Execute SELECT statements; skip and warn on anything else
            5. Surface results via log / csv / json + ORBIT_OUTPUT protocol
            6. Honour timeout, abort flag, and retry policy
        """
        start       = time.monotonic()
        stdout_log: list[str] = []

        def _emit(line: str) -> None:
            stdout_log.append(line)
            ctx.on_output(line)

        try:
            spec = self._resolve_connection_spec(ctx)
        except ValueError as exc:
            return ExecutionResult(
                exit_code=-1,
                stdout_lines=stdout_log,
                error_message=f"SQL config error: {exc}",
            )

        _emit(
            f"INFO     | SQL executor — dialect={spec.dialect.value}  "
            f"output={spec.output_format}  script={ctx.script_path.name}"
        )

        for attempt in range(ctx.max_retries + 1):
            if ctx.abort_flag():
                return ExecutionResult(exit_code=-1, stdout_lines=stdout_log)

            if attempt > 0:
                _emit(
                    f"  ↺ Retry {attempt}/{ctx.max_retries} "
                    f"— {ctx.script_name} (3s delay)"
                )
                time.sleep(3)

            result = self._run_script(ctx, spec, stdout_log, _emit, start)

            if (
                result.exit_code == 0
                or result.error_message
                or result.timed_out
                or attempt >= ctx.max_retries
            ):
                return result

        return ExecutionResult(exit_code=-1, stdout_lines=stdout_log)

    # ── Single attempt ────────────────────────────────────────────────────── #

    def _run_script(
        self,
        ctx: ExecutionContext,
        spec: SQLConnectionSpec,
        stdout_log: list[str],
        emit: Callable[[str], None],
        start: float,
    ) -> ExecutionResult:
        """Parse → connect → execute → close for one attempt."""
        deadline = (
            start + ctx.timeout_minutes * 60
            if ctx.timeout_minutes else None
        )

        try:
            statements = self._parse_sql_file(ctx.script_path)
            emit(f"INFO     | {len(statements)} statement(s) parsed")

            connection = self._get_connection(spec)
            try:
                self._run_statements(
                    connection=connection,
                    statements=statements,
                    spec=spec,
                    ctx=ctx,
                    emit=emit,
                    deadline=deadline,
                )
            finally:
                self._close_connection(connection)

            elapsed = time.monotonic() - start
            emit(f"INFO     | SQL script completed in {elapsed:.1f}s")
            return ExecutionResult(exit_code=0, stdout_lines=stdout_log)

        except Exception as exc:  # noqa: BLE001
            return ExecutionResult(
                exit_code=1,
                stdout_lines=stdout_log,
                error_message=f"{type(exc).__name__}: {exc}",
            )

    # ── Connection resolution ─────────────────────────────────────────────── #

    def _resolve_connection_spec(self, ctx: ExecutionContext) -> SQLConnectionSpec:
        """
        Build a SQLConnectionSpec from ORBIT_* env vars.
        Raises ValueError with a human-readable message on bad config.
        """
        env = ctx.env

        raw_dialect = env.get("ORBIT_SQL_DIALECT", "").lower()
        if not raw_dialect:
            raise ValueError(
                "ORBIT_SQL_DIALECT is not set. "
                "Add it to the run_sequence.yaml env: block or the system environment."
            )
        try:
            dialect = SQLDialect(raw_dialect)
        except ValueError:
            valid = ", ".join(d.value for d in SQLDialect)
            raise ValueError(
                f"Unknown ORBIT_SQL_DIALECT '{raw_dialect}'. Valid values: {valid}"
            )

        db_path: Optional[Path] = None
        dsn: Optional[str]      = None

        if dialect == SQLDialect.SQLITE:
            raw_path = env.get("ORBIT_SQL_DB_PATH", "")
            if not raw_path:
                raise ValueError(
                    "ORBIT_SQL_DB_PATH is required when ORBIT_SQL_DIALECT=sqlite."
                )
            db_path = Path(raw_path)
            if not db_path.exists():
                raise ValueError(
                    f"ORBIT_SQL_DB_PATH does not exist: {db_path}"
                )
        else:
            dsn = env.get("ORBIT_SQL_DSN", "")
            if not dsn:
                raise ValueError(
                    f"ORBIT_SQL_DSN is required when ORBIT_SQL_DIALECT={dialect.value}. "
                    "The DSN string carries all connection and auth details."
                )

        try:
            timeout_sec = int(env.get("ORBIT_SQL_TIMEOUT", "30"))
        except ValueError:
            timeout_sec = 30

        output_format = env.get("ORBIT_SQL_OUTPUT_FORMAT", "log").lower()
        if output_format not in ("csv", "json", "log"):
            ctx.on_output(
                f"  [WARN] ORBIT_SQL_OUTPUT_FORMAT '{output_format}' is not recognised "
                "(expected csv | json | log) — defaulting to log"
            )
            output_format = "log"

        return SQLConnectionSpec(
            dialect=dialect,
            db_path=db_path,
            dsn=dsn,
            timeout_sec=timeout_sec,
            output_format=output_format,
        )

    # ── SQL file parsing ──────────────────────────────────────────────────── #

    def _parse_sql_file(self, script_path: Path) -> list[str]:
        """
        Read script_path and return a list of individual SQL statements.

        Strips single-line (--) and block (/* */) comments, then splits
        on semicolons.  Blank and whitespace-only statements are dropped.
        Note: semicolons inside string literals are not handled — scripts
        using those patterns should restructure to avoid them.
        """
        text = script_path.read_text(encoding="utf-8")
        text = _COMMENT_SINGLE.sub("", text)
        text = _COMMENT_BLOCK.sub("", text)
        parts = [s.strip() for s in text.split(";")]
        return [s for s in parts if s]

    # ── Connection acquisition ────────────────────────────────────────────── #

    def _get_connection(self, spec: SQLConnectionSpec) -> object:
        """Dispatch to the dialect-specific connector."""
        if spec.dialect == SQLDialect.SQLITE:
            return self._connect_sqlite(spec)
        return self._connect_pyodbc(spec)

    def _connect_sqlite(self, spec: SQLConnectionSpec) -> sqlite3.Connection:
        """
        Open a read-only sqlite3 connection to spec.db_path.

        Uses the URI filename format (?mode=ro) so the driver enforces
        read-only access at the OS level — writes are rejected by sqlite
        itself, not just by our SELECT guard.
        """
        uri = f"file:{spec.db_path}?mode=ro"
        conn = sqlite3.connect(uri, uri=True, timeout=spec.timeout_sec)
        conn.row_factory = sqlite3.Row
        return conn

    def _connect_pyodbc(self, spec: SQLConnectionSpec) -> object:
        """
        Open a pyodbc connection using spec.dsn.

        The DSN string is passed through verbatim — connection details,
        server, database, and authentication all live there.  autocommit
        is set to True; since we only run SELECT statements no transaction
        management is needed and there is no risk of an accidental commit.

        Requires: pip install pyodbc  and the appropriate ODBC driver for
        the target database (MSSQL: "ODBC Driver 17/18 for SQL Server").
        """
        try:
            import pyodbc  # noqa: PLC0415
        except ImportError:
            raise RuntimeError(
                "pyodbc is not installed. "
                "Run: pip install pyodbc  "
                "and ensure the correct ODBC driver is available on this machine."
            )
        conn = pyodbc.connect(spec.dsn, timeout=spec.timeout_sec)
        conn.autocommit = True
        return conn

    # ── Statement execution ───────────────────────────────────────────────── #

    def _run_statements(
        self,
        connection: object,
        statements: list[str],
        spec: SQLConnectionSpec,
        ctx: ExecutionContext,
        emit: Callable[[str], None],
        deadline: Optional[float],
    ) -> None:
        """
        Execute each statement in order under the read-only policy.

        Non-SELECT statements are skipped with a warning.
        Abort flag and deadline are checked before each statement.
        Results are surfaced via _format_rows().
        """
        cursor = connection.cursor()
        total  = len(statements)

        for i, sql in enumerate(statements, 1):
            if ctx.abort_flag():
                emit(f"INFO     | Run aborted before statement {i}/{total}")
                return

            if deadline and time.monotonic() > deadline:
                emit(f"WARNING  | Timeout reached before statement {i}/{total} — stopping")
                return

            # Read-only guard — check the leading keyword
            first_word = sql.split()[0].upper() if sql.split() else ""
            if first_word != "SELECT":
                emit(
                    f"WARNING  | Statement {i}/{total} skipped "
                    f"(read-only mode — got {first_word or 'empty'}, expected SELECT)"
                )
                continue

            emit(f"INFO     | Executing statement {i}/{total}")
            cursor.execute(sql)

            columns = (
                [desc[0] for desc in cursor.description]
                if cursor.description else []
            )
            rows = cursor.fetchall()
            emit(f"INFO     | {len(rows)} row(s) returned")

            if columns:
                self._format_rows(
                    columns=columns,
                    rows=[tuple(r) for r in rows],
                    output_format=spec.output_format,
                    emit=emit,
                    ctx=ctx,
                    statement_index=i,
                )

    # ── Result formatting ─────────────────────────────────────────────────── #

    def _format_rows(
        self,
        columns: list[str],
        rows: list[tuple],
        output_format: str,
        emit: Callable[[str], None],
        ctx: ExecutionContext,
        statement_index: int = 1,
    ) -> None:
        """
        Surface query result rows to the log and optionally to a file.

        output_format='log'
            Each row is emitted as a pipe-delimited log line.  Column
            headers and a separator line are emitted first.

        output_format='csv'
            Results written to ORBIT_LOG_DIR/results_<n>.csv.  The file
            path is emitted to the log and published via ORBIT_OUTPUT so
            downstream scripts can read it from context.json.

        output_format='json'
            Results written to ORBIT_LOG_DIR/results_<n>.json as a JSON
            array of objects.  Same ORBIT_OUTPUT feed as csv.
        """
        if output_format == "log":
            self._format_rows_log(columns, rows, emit)

        elif output_format == "csv":
            log_dir  = Path(ctx.env.get("ORBIT_LOG_DIR", "."))
            out_path = log_dir / f"results_{statement_index}.csv"
            self._write_csv(columns, rows, out_path)
            emit(f"INFO     | Results → {out_path}")
            ctx.on_context_output(f"sql_results_{statement_index}", str(out_path))

        elif output_format == "json":
            log_dir  = Path(ctx.env.get("ORBIT_LOG_DIR", "."))
            out_path = log_dir / f"results_{statement_index}.json"
            self._write_json(columns, rows, out_path)
            emit(f"INFO     | Results → {out_path}")
            ctx.on_context_output(f"sql_results_{statement_index}", str(out_path))

    def _format_rows_log(
        self,
        columns: list[str],
        rows: list[tuple],
        emit: Callable[[str], None],
    ) -> None:
        """Emit rows as pipe-delimited log lines with a header."""
        if not columns:
            return
        header = " | ".join(columns)
        sep    = "-" * len(header)
        emit(f"INFO     | {header}")
        emit(f"INFO     | {sep}")
        for row in rows:
            emit(f"INFO     | {' | '.join('' if v is None else str(v) for v in row)}")

    def _write_csv(
        self,
        columns: list[str],
        rows: list[tuple],
        out_path: Path,
    ) -> None:
        """Write columns + rows to a UTF-8 CSV file."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        if columns:
            writer.writerow(columns)
        writer.writerows(rows)
        out_path.write_text(buf.getvalue(), encoding="utf-8")

    def _write_json(
        self,
        columns: list[str],
        rows: list[tuple],
        out_path: Path,
    ) -> None:
        """Write rows as a JSON array of column-keyed objects."""
        data = [dict(zip(columns, row)) for row in rows]
        out_path.write_text(
            json.dumps(data, indent=2, default=str),
            encoding="utf-8",
        )

    # ── Teardown ──────────────────────────────────────────────────────────── #

    def _close_connection(self, connection: object) -> None:
        """Close the DB connection, suppressing errors."""
        try:
            connection.close()
        except Exception:  # noqa: BLE001
            pass
