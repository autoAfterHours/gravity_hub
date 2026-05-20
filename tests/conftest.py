"""
conftest.py — Shared pytest fixtures for Orbit Hub tests.

ExecutionContext is a pure dataclass (no Qt) so we can build a real one
with no-op callables. Tests that need a live Qt app are skipped automatically
when PySide6 is not importable.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from orbit360.executors.base import ExecutionContext


@pytest.fixture()
def make_ctx(tmp_path):
    """
    Factory fixture: make_ctx(env={}) → ExecutionContext pointed at tmp_path.
    All callbacks are no-ops unless the caller replaces them.
    """
    def _factory(env: dict | None = None, script_path: Path | None = None):
        return ExecutionContext(
            script_path=script_path or (tmp_path / "dummy.sql"),
            script_name="dummy",
            env=env or {},
            cwd=tmp_path,
            timeout_minutes=None,
            max_retries=0,
            on_output=lambda line: None,
            on_manual_input=lambda text: None,
            on_failure_recovery=lambda text: None,
            on_value_requested=lambda label: None,
            on_context_output=lambda key, val: None,
            abort_flag=lambda: False,
            register_proc=lambda proc: None,
            unregister_proc=lambda: None,
        )
    return _factory
