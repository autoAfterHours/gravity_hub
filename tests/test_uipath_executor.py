"""
test_uipath_executor.py — Unit tests for core/executors/uipath_executor.py.

Tests cover routing (can_handle) and command construction (build_command).
The actual subprocess launch is not tested here — that belongs to integration
tests requiring a Windows machine with UiRobot.exe installed.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from orbit360.executors.uipath_executor import UiPathExecutor
from orbit360.executors.base import ExecutionContext


# ── Fixtures ──────────────────────────────────────────────────────────────── #

@pytest.fixture()
def ctx(tmp_path, make_ctx):
    env = {
        "ORBIT_RUN_ID":       "run-001",
        "ORBIT_CONTEXT_PATH": str(tmp_path / "context.json"),
        "ORBIT_EXCEL_PATH":   str(tmp_path / "data.xlsx"),
        "ORBIT_EXCEL_SHEET":  "Sheet1",
        "ORBIT_LOG_DIR":      str(tmp_path / "logs"),
        "ORBIT_SCRIPT_NAME":  "dummy",
        "ORBIT_SCRIPT_INDEX": "0",
        "ORBIT_SCRIPT_TOTAL": "1",
    }
    return make_ctx(env=env, script_path=tmp_path / "workflow.xaml")


# ── can_handle ────────────────────────────────────────────────────────────── #

class TestCanHandle:
    def test_xaml_extension(self, tmp_path):
        assert UiPathExecutor().can_handle(tmp_path / "flow.xaml", None)

    def test_xaml_case_insensitive(self, tmp_path):
        assert UiPathExecutor().can_handle(tmp_path / "flow.XAML", None)

    def test_engine_hint_uipath(self, tmp_path):
        assert UiPathExecutor().can_handle(tmp_path / "anything.py", "uipath")

    def test_engine_hint_takes_priority(self, tmp_path):
        # .sql file explicitly marked as uipath should be routed to UiPath
        assert UiPathExecutor().can_handle(tmp_path / "oddly_named.sql", "uipath")

    def test_rejects_py_without_hint(self, tmp_path):
        assert not UiPathExecutor().can_handle(tmp_path / "script.py", None)

    def test_rejects_ps1_without_hint(self, tmp_path):
        assert not UiPathExecutor().can_handle(tmp_path / "script.ps1", None)

    def test_rejects_wrong_engine_hint(self, tmp_path):
        assert not UiPathExecutor().can_handle(tmp_path / "flow.xaml", "powershell")


# ── build_command ─────────────────────────────────────────────────────────── #

class TestBuildCommand:
    # Helper: patch both find_uirobot and shutil.which so the "not on PATH"
    # guard doesn't trigger when we're testing with a real-looking path.
    @staticmethod
    def _patch_found(real_path: str = r"C:\UiPath\UiRobot.exe"):
        from unittest.mock import patch as _p
        return _p("orbit360.utils.utils.find_uirobot", return_value=real_path)

    @staticmethod
    def _patch_fallback_on_path():
        """find_uirobot returned bare name AND it IS on PATH → should proceed."""
        from unittest.mock import patch as _p, MagicMock
        p1 = _p("orbit360.utils.utils.find_uirobot", return_value="UiRobot.exe")
        p2 = _p("shutil.which", return_value=r"C:\Windows\UiRobot.exe")
        return p1, p2

    def test_command_starts_with_uirobot(self, ctx):
        with self._patch_found(r"C:\UiPath\UiRobot.exe"):
            cmd = UiPathExecutor().build_command(ctx)
        assert cmd[0] == r"C:\UiPath\UiRobot.exe"

    def test_execute_subcommand_present(self, ctx):
        p1, p2 = self._patch_fallback_on_path()
        with p1, p2:
            cmd = UiPathExecutor().build_command(ctx)
        assert "execute" in cmd

    def test_file_flag_points_to_script(self, ctx, tmp_path):
        p1, p2 = self._patch_fallback_on_path()
        with p1, p2:
            cmd = UiPathExecutor().build_command(ctx)
        file_idx = cmd.index("--file")
        assert cmd[file_idx + 1] == str(tmp_path / "workflow.xaml")

    def test_input_flag_present(self, ctx):
        p1, p2 = self._patch_fallback_on_path()
        with p1, p2:
            cmd = UiPathExecutor().build_command(ctx)
        assert "--input" in cmd

    def test_orbit_args_valid_json(self, ctx):
        p1, p2 = self._patch_fallback_on_path()
        with p1, p2:
            cmd = UiPathExecutor().build_command(ctx)
        input_idx = cmd.index("--input")
        args = json.loads(cmd[input_idx + 1])
        assert isinstance(args, dict)

    def test_orbit_run_id_forwarded(self, ctx):
        p1, p2 = self._patch_fallback_on_path()
        with p1, p2:
            cmd = UiPathExecutor().build_command(ctx)
        args = json.loads(cmd[cmd.index("--input") + 1])
        assert args["ORBIT_RUN_ID"] == "run-001"

    def test_orbit_excel_path_forwarded(self, ctx, tmp_path):
        p1, p2 = self._patch_fallback_on_path()
        with p1, p2:
            cmd = UiPathExecutor().build_command(ctx)
        args = json.loads(cmd[cmd.index("--input") + 1])
        assert args["ORBIT_EXCEL_PATH"] == str(tmp_path / "data.xlsx")

    def test_script_name_forwarded(self, ctx):
        p1, p2 = self._patch_fallback_on_path()
        with p1, p2:
            cmd = UiPathExecutor().build_command(ctx)
        args = json.loads(cmd[cmd.index("--input") + 1])
        assert args["ORBIT_SCRIPT_NAME"] == "dummy"

    def test_all_orbit_vars_forwarded(self, ctx):
        """All ORBIT_* keys in ctx.env must appear in the --input JSON."""
        p1, p2 = self._patch_fallback_on_path()
        with p1, p2:
            cmd = UiPathExecutor().build_command(ctx)
        args = json.loads(cmd[cmd.index("--input") + 1])
        orbit_keys = {k for k in ctx.env if k.startswith("ORBIT_")}
        assert orbit_keys <= set(args)

    def test_raises_when_uirobot_not_found_and_not_on_path(self, ctx):
        """If find_uirobot returns the bare name and it's not on PATH, raise FileNotFoundError."""
        with patch("orbit360.utils.utils.find_uirobot", return_value="UiRobot.exe"), \
             patch("shutil.which", return_value=None):
            with pytest.raises(FileNotFoundError, match="ORBIT_UIROBOT_PATH"):
                UiPathExecutor().build_command(ctx)
