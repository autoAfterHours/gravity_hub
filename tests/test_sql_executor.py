"""
test_sql_executor.py — Unit tests for core/executors/sql_executor.py.

All tests are pure-Python (no Qt, no PySide6). SQLExecutor runs in-process
via DB-API 2.0, so most logic is exercised by creating a real temp sqlite
database and calling execute() directly.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from io import StringIO
from pathlib import Path

import pytest

from orbit360.executors.sql_executor import SQLExecutor, SQLConnectionSpec, SQLDialect


# ── Helpers ───────────────────────────────────────────────────────────────── #

def _exec(executor, ctx):
    """Run execute() and return (result, collected_lines)."""
    lines: list[str] = []
    ctx.on_output = lambda line: lines.append(line)
    result = executor.execute(ctx)
    return result, lines


# ── _parse_sql_file ───────────────────────────────────────────────────────── #

class TestParseSqlFile:
    def test_splits_on_semicolons(self, tmp_path):
        f = tmp_path / "q.sql"
        f.write_text("SELECT 1; SELECT 2; SELECT 3")
        stmts = SQLExecutor()._parse_sql_file(f)
        assert stmts == ["SELECT 1", "SELECT 2", "SELECT 3"]

    def test_drops_blank_statements(self, tmp_path):
        f = tmp_path / "q.sql"
        f.write_text("SELECT 1;;  ;SELECT 2")
        stmts = SQLExecutor()._parse_sql_file(f)
        assert stmts == ["SELECT 1", "SELECT 2"]

    def test_strips_single_line_comments(self, tmp_path):
        f = tmp_path / "q.sql"
        f.write_text("-- header\nSELECT 1 -- inline")
        stmts = SQLExecutor()._parse_sql_file(f)
        assert len(stmts) == 1
        assert "--" not in stmts[0]

    def test_strips_block_comments(self, tmp_path):
        f = tmp_path / "q.sql"
        f.write_text("/* block */\nSELECT /* mid */ 1")
        stmts = SQLExecutor()._parse_sql_file(f)
        assert len(stmts) == 1
        assert "/*" not in stmts[0]

    def test_multiline_block_comment(self, tmp_path):
        f = tmp_path / "q.sql"
        f.write_text("/*\n  multi\n  line\n*/\nSELECT 42")
        stmts = SQLExecutor()._parse_sql_file(f)
        assert stmts == ["SELECT 42"]

    def test_empty_file_returns_empty_list(self, tmp_path):
        f = tmp_path / "q.sql"
        f.write_text("-- only a comment")
        stmts = SQLExecutor()._parse_sql_file(f)
        assert stmts == []


# ── _resolve_connection_spec ──────────────────────────────────────────────── #

class TestResolveConnectionSpec:
    def _ctx(self, make_ctx, env):
        return make_ctx(env=env)

    def test_missing_dialect_raises(self, make_ctx):
        ctx = make_ctx(env={})
        with pytest.raises(ValueError, match="ORBIT_SQL_DIALECT"):
            SQLExecutor()._resolve_connection_spec(ctx)

    def test_unknown_dialect_raises(self, make_ctx):
        ctx = make_ctx(env={"ORBIT_SQL_DIALECT": "mysql"})
        with pytest.raises(ValueError, match="Unknown ORBIT_SQL_DIALECT"):
            SQLExecutor()._resolve_connection_spec(ctx)

    def test_sqlite_missing_db_path_raises(self, make_ctx):
        ctx = make_ctx(env={"ORBIT_SQL_DIALECT": "sqlite"})
        with pytest.raises(ValueError, match="ORBIT_SQL_DB_PATH"):
            SQLExecutor()._resolve_connection_spec(ctx)

    def test_sqlite_nonexistent_path_raises(self, make_ctx):
        ctx = make_ctx(env={
            "ORBIT_SQL_DIALECT": "sqlite",
            "ORBIT_SQL_DB_PATH": "/nonexistent/path.db",
        })
        with pytest.raises(ValueError, match="does not exist"):
            SQLExecutor()._resolve_connection_spec(ctx)

    def test_sqlite_valid(self, make_ctx, tmp_path):
        db = tmp_path / "test.db"
        db.write_bytes(b"")
        ctx = make_ctx(env={
            "ORBIT_SQL_DIALECT": "sqlite",
            "ORBIT_SQL_DB_PATH": str(db),
        })
        spec = SQLExecutor()._resolve_connection_spec(ctx)
        assert spec.dialect == SQLDialect.SQLITE
        assert spec.db_path == db
        assert spec.output_format == "log"
        assert spec.timeout_sec == 30

    def test_mssql_missing_dsn_raises(self, make_ctx):
        ctx = make_ctx(env={"ORBIT_SQL_DIALECT": "mssql"})
        with pytest.raises(ValueError, match="ORBIT_SQL_DSN"):
            SQLExecutor()._resolve_connection_spec(ctx)

    def test_mssql_valid(self, make_ctx):
        ctx = make_ctx(env={
            "ORBIT_SQL_DIALECT": "mssql",
            "ORBIT_SQL_DSN": "DSN=MyServer;UID=sa;PWD=x",
        })
        spec = SQLExecutor()._resolve_connection_spec(ctx)
        assert spec.dialect == SQLDialect.MSSQL
        assert spec.dsn == "DSN=MyServer;UID=sa;PWD=x"

    def test_invalid_output_format_falls_back_to_log(self, make_ctx, tmp_path):
        db = tmp_path / "test.db"
        db.write_bytes(b"")
        ctx = make_ctx(env={
            "ORBIT_SQL_DIALECT": "sqlite",
            "ORBIT_SQL_DB_PATH": str(db),
            "ORBIT_SQL_OUTPUT_FORMAT": "xml",
        })
        spec = SQLExecutor()._resolve_connection_spec(ctx)
        assert spec.output_format == "log"

    def test_custom_timeout(self, make_ctx, tmp_path):
        db = tmp_path / "test.db"
        db.write_bytes(b"")
        ctx = make_ctx(env={
            "ORBIT_SQL_DIALECT": "sqlite",
            "ORBIT_SQL_DB_PATH": str(db),
            "ORBIT_SQL_TIMEOUT": "60",
        })
        spec = SQLExecutor()._resolve_connection_spec(ctx)
        assert spec.timeout_sec == 60

    def test_bad_timeout_falls_back_to_30(self, make_ctx, tmp_path):
        db = tmp_path / "test.db"
        db.write_bytes(b"")
        ctx = make_ctx(env={
            "ORBIT_SQL_DIALECT": "sqlite",
            "ORBIT_SQL_DB_PATH": str(db),
            "ORBIT_SQL_TIMEOUT": "notanumber",
        })
        spec = SQLExecutor()._resolve_connection_spec(ctx)
        assert spec.timeout_sec == 30


# ── _format_rows_log ──────────────────────────────────────────────────────── #

class TestFormatRowsLog:
    def test_emits_header_separator_and_rows(self):
        lines: list[str] = []
        SQLExecutor()._format_rows_log(
            columns=["id", "name"],
            rows=[(1, "Alice"), (2, "Bob")],
            emit=lambda line: lines.append(line),
        )
        assert any("id | name" in l for l in lines)
        assert any("---" in l for l in lines)
        assert any("Alice" in l for l in lines)
        assert any("Bob" in l for l in lines)

    def test_none_values_rendered_as_empty(self):
        lines: list[str] = []
        SQLExecutor()._format_rows_log(
            columns=["x"],
            rows=[(None,)],
            emit=lambda line: lines.append(line),
        )
        assert any(l.endswith("| ") or l.strip().endswith("|") for l in lines)

    def test_no_columns_emits_nothing(self):
        lines: list[str] = []
        SQLExecutor()._format_rows_log(columns=[], rows=[], emit=lambda l: lines.append(l))
        assert lines == []


# ── _write_csv ────────────────────────────────────────────────────────────── #

class TestWriteCsv:
    def test_writes_header_and_rows(self, tmp_path):
        out = tmp_path / "out.csv"
        SQLExecutor()._write_csv(
            columns=["id", "val"],
            rows=[(1, "a"), (2, "b")],
            out_path=out,
        )
        rows = list(csv.reader(StringIO(out.read_text())))
        assert rows[0] == ["id", "val"]
        assert rows[1] == ["1", "a"]
        assert rows[2] == ["2", "b"]

    def test_empty_rows_writes_header_only(self, tmp_path):
        out = tmp_path / "out.csv"
        SQLExecutor()._write_csv(columns=["x"], rows=[], out_path=out)
        rows = list(csv.reader(StringIO(out.read_text())))
        assert rows == [["x"]]


# ── _write_json ───────────────────────────────────────────────────────────── #

class TestWriteJson:
    def test_writes_array_of_objects(self, tmp_path):
        out = tmp_path / "out.json"
        SQLExecutor()._write_json(
            columns=["id", "name"],
            rows=[(1, "Alice")],
            out_path=out,
        )
        data = json.loads(out.read_text())
        assert data == [{"id": 1, "name": "Alice"}]

    def test_empty_rows_writes_empty_array(self, tmp_path):
        out = tmp_path / "out.json"
        SQLExecutor()._write_json(columns=["x"], rows=[], out_path=out)
        assert json.loads(out.read_text()) == []


# ── _run_statements SELECT guard ──────────────────────────────────────────── #

class TestRunStatementsSelectGuard:
    def _make_spec(self, tmp_path):
        db_path = tmp_path / "guard.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE t (id INTEGER)")
        conn.execute("INSERT INTO t VALUES (99)")
        conn.commit()
        conn.close()
        return SQLConnectionSpec(
            dialect=SQLDialect.SQLITE,
            db_path=db_path,
            timeout_sec=5,
            output_format="log",
        )

    def test_non_select_skipped_with_warning(self, make_ctx, tmp_path):
        spec = self._make_spec(tmp_path)
        conn = SQLExecutor()._connect_sqlite(spec)
        lines: list[str] = []

        class _Ctx:
            abort_flag = lambda self: False

        ctx = make_ctx()
        try:
            SQLExecutor()._run_statements(
                connection=conn,
                statements=["INSERT INTO t VALUES (1)"],
                spec=spec,
                ctx=ctx,
                emit=lambda l: lines.append(l),
                deadline=None,
            )
        finally:
            conn.close()

        assert any("skipped" in l.lower() for l in lines)
        assert any("INSERT" in l for l in lines)

    def test_select_executes_and_returns_rows(self, make_ctx, tmp_path):
        spec = self._make_spec(tmp_path)
        conn = SQLExecutor()._connect_sqlite(spec)
        lines: list[str] = []
        ctx = make_ctx()
        try:
            SQLExecutor()._run_statements(
                connection=conn,
                statements=["SELECT id FROM t"],
                spec=spec,
                ctx=ctx,
                emit=lambda l: lines.append(l),
                deadline=None,
            )
        finally:
            conn.close()

        assert any("1 row" in l for l in lines)
        assert any("99" in l for l in lines)

    def test_abort_stops_execution(self, make_ctx, tmp_path):
        spec = self._make_spec(tmp_path)
        conn = SQLExecutor()._connect_sqlite(spec)
        executed: list[str] = []
        ctx = make_ctx()
        ctx.abort_flag = lambda: True
        try:
            SQLExecutor()._run_statements(
                connection=conn,
                statements=["SELECT id FROM t", "SELECT id FROM t"],
                spec=spec,
                ctx=ctx,
                emit=lambda l: executed.append(l),
                deadline=None,
            )
        finally:
            conn.close()

        assert any("aborted" in l.lower() for l in executed)


# ── Full execute() integration ────────────────────────────────────────────── #

class TestExecuteIntegration:
    def _make_db(self, tmp_path) -> Path:
        db_path = tmp_path / "data.db"
        conn = sqlite3.connect(str(db_path))
        conn.execute("CREATE TABLE employees (id INTEGER, name TEXT, dept TEXT)")
        conn.executemany(
            "INSERT INTO employees VALUES (?, ?, ?)",
            [(1, "Alice", "Eng"), (2, "Bob", "HR"), (3, "Carol", "Eng")],
        )
        conn.commit()
        conn.close()
        return db_path

    def test_select_returns_exit_code_0(self, make_ctx, tmp_path):
        db_path = self._make_db(tmp_path)
        script = tmp_path / "query.sql"
        script.write_text("SELECT * FROM employees")
        ctx = make_ctx(
            env={
                "ORBIT_SQL_DIALECT": "sqlite",
                "ORBIT_SQL_DB_PATH": str(db_path),
            },
            script_path=script,
        )
        result = SQLExecutor().execute(ctx)
        assert result.exit_code == 0

    def test_select_output_contains_rows(self, make_ctx, tmp_path):
        db_path = self._make_db(tmp_path)
        script = tmp_path / "query.sql"
        script.write_text("SELECT name FROM employees WHERE dept = 'Eng'")
        lines: list[str] = []
        ctx = make_ctx(
            env={
                "ORBIT_SQL_DIALECT": "sqlite",
                "ORBIT_SQL_DB_PATH": str(db_path),
            },
            script_path=script,
        )
        ctx.on_output = lambda l: lines.append(l)
        SQLExecutor().execute(ctx)
        assert any("Alice" in l for l in lines)
        assert any("Carol" in l for l in lines)

    def test_csv_output_writes_file(self, make_ctx, tmp_path):
        db_path = self._make_db(tmp_path)
        script = tmp_path / "query.sql"
        script.write_text("SELECT id, name FROM employees")
        ctx = make_ctx(
            env={
                "ORBIT_SQL_DIALECT": "sqlite",
                "ORBIT_SQL_DB_PATH": str(db_path),
                "ORBIT_SQL_OUTPUT_FORMAT": "csv",
                "ORBIT_LOG_DIR": str(tmp_path),
            },
            script_path=script,
        )
        SQLExecutor().execute(ctx)
        csv_file = tmp_path / "results_1.csv"
        assert csv_file.exists()
        rows = list(csv.reader(StringIO(csv_file.read_text())))
        assert rows[0] == ["id", "name"]
        assert len(rows) == 4  # header + 3 rows

    def test_json_output_writes_file(self, make_ctx, tmp_path):
        db_path = self._make_db(tmp_path)
        script = tmp_path / "query.sql"
        script.write_text("SELECT id, name FROM employees WHERE id = 1")
        context_outputs: dict[str, str] = {}
        ctx = make_ctx(
            env={
                "ORBIT_SQL_DIALECT": "sqlite",
                "ORBIT_SQL_DB_PATH": str(db_path),
                "ORBIT_SQL_OUTPUT_FORMAT": "json",
                "ORBIT_LOG_DIR": str(tmp_path),
            },
            script_path=script,
        )
        ctx.on_context_output = lambda k, v: context_outputs.update({k: v})
        SQLExecutor().execute(ctx)
        json_file = tmp_path / "results_1.json"
        assert json_file.exists()
        data = json.loads(json_file.read_text())
        assert data == [{"id": 1, "name": "Alice"}]
        assert "sql_results_1" in context_outputs

    def test_missing_dialect_returns_exit_code_minus1(self, make_ctx, tmp_path):
        script = tmp_path / "query.sql"
        script.write_text("SELECT 1")
        ctx = make_ctx(env={}, script_path=script)
        result = SQLExecutor().execute(ctx)
        assert result.exit_code == -1
        assert "ORBIT_SQL_DIALECT" in (result.error_message or "")

    def test_non_select_skipped_script_still_succeeds(self, make_ctx, tmp_path):
        db_path = self._make_db(tmp_path)
        script = tmp_path / "mixed.sql"
        # Only the SELECT should run; the INSERT is silently skipped
        script.write_text("INSERT INTO employees VALUES (99,'X','Y'); SELECT COUNT(*) FROM employees")
        ctx = make_ctx(
            env={
                "ORBIT_SQL_DIALECT": "sqlite",
                "ORBIT_SQL_DB_PATH": str(db_path),
            },
            script_path=script,
        )
        result = SQLExecutor().execute(ctx)
        assert result.exit_code == 0

    def test_can_handle_sql_extension(self, tmp_path):
        assert SQLExecutor().can_handle(tmp_path / "q.sql", None)

    def test_can_handle_engine_hint(self, tmp_path):
        assert SQLExecutor().can_handle(tmp_path / "q.py", "sql")

    def test_cannot_handle_py_without_hint(self, tmp_path):
        assert not SQLExecutor().can_handle(tmp_path / "q.py", None)

    def test_build_command_raises(self, make_ctx, tmp_path):
        ctx = make_ctx()
        with pytest.raises(RuntimeError, match="build_command"):
            SQLExecutor().build_command(ctx)
