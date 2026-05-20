"""
uipath_executor.py — UiPath Robot (.xaml) executor.

Invokes UiRobot.exe with Orbit runtime values passed as UiPath
in-arguments (--input JSON), so XAML workflows can read them via the
Arguments panel without environment variable lookup.

UiRobot.exe location is discovered by utils.find_uirobot(); set
ORBIT_UIROBOT_PATH in .env to override the default search locations.

Data contract: all ORBIT_* env vars built by _build_env() are forwarded
as UiPath in-arguments so XAML workflows can read them directly via the
Arguments panel — no GetEnvironmentVariable() calls needed.
Custom env: overrides from run_sequence.yaml are also in the subprocess
environment and are accessible via GetEnvironmentVariable() in XAML.

Log level:
    UiRobot is launched with --log-level Verbose by default so robot-level
    log messages flow into the Orbit console alongside Write Line output.
    Set ORBIT_UIPATH_LOG_LEVEL in .env to override (e.g. Information,
    Warning).  Set it to "Off" to suppress robot-level logs entirely.
    Workflows should still use Write Line for step-level output and
    ORBIT_OUTPUT|key=value lines to pass values to downstream scripts.

Exit code:
    Some UiRobot versions exit 0 even when a workflow faults.  execute()
    scans stdout for UiRobot fault/success markers and remaps the exit
    code so Orbit can correctly mark runs as passed or failed.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from orbit360.executors.base import BaseExecutor, ExecutionContext, ExecutionResult
from orbit360.utils import utils

# Robot log levels accepted by UiRobot.exe --log-level
_VALID_LOG_LEVELS = {"Verbose", "Trace", "Information", "Warning", "Error", "Critical", "Off"}
_DEFAULT_LOG_LEVEL = "Verbose"

# Substrings that indicate UiRobot reported a workflow fault (case-insensitive).
# Checked when exit_code == 0 to catch versions that swallow failure exit codes.
_FAULT_MARKERS = (
    "execution ended with state: faulted",
    "execution has faulted",
    "job faulted",
)
# If one of these is present, exit_code 0 is confirmed as a genuine success
# even when fault markers were also somehow present (shouldn't happen in practice).
_SUCCESS_MARKERS = (
    "execution ended with state: successful",
    "job completed",
)


class UiPathExecutor(BaseExecutor):
    """
    Executor for UiPath Robot automation workflows (.xaml).

    Activated when:
      • engine hint is 'uipath'
      • script extension is .xaml (and no other executor claimed it)
    """

    def can_handle(self, script_path: Path, engine_hint: Optional[str]) -> bool:
        if engine_hint:
            return engine_hint == "uipath"
        return script_path.suffix.lower() == ".xaml"

    def execute(self, ctx: ExecutionContext) -> ExecutionResult:
        """
        Run with retry policy, then correct exit code from stdout markers.

        UiRobot.exe in some versions exits 0 even when a workflow faults.
        After each attempt we scan stdout for known fault/success strings and
        remap exit_code so OrbitLogger can mark the result correctly.
        """
        result = super().execute(ctx)

        if result.exit_code == 0 and not result.error_message:
            # Scan lines in reverse so the *last* status marker wins — a workflow
            # can recover from an early fault, so we honour the final outcome.
            final_status = None
            for line in reversed(result.stdout_lines):
                ll = line.lower()
                if final_status is None:
                    for m in _FAULT_MARKERS:
                        if m in ll:
                            final_status = "faulted"
                            break
                    if final_status is None:
                        for m in _SUCCESS_MARKERS:
                            if m in ll:
                                final_status = "success"
                                break
                if final_status is not None:
                    break

            if final_status == "faulted":
                ctx.on_output(
                    "  [ORBIT] UiRobot reported Faulted state — marking run as failed"
                )
                return ExecutionResult(
                    exit_code=1,
                    stdout_lines=result.stdout_lines,
                    timed_out=result.timed_out,
                )

        return result

    def build_command(self, ctx: ExecutionContext) -> list[str]:
        uirobot = utils.find_uirobot()
        if uirobot == "UiRobot.exe":
            # find_uirobot() returned the bare fallback name — check PATH now
            # and raise immediately so the error surfaces as a clean script
            # failure rather than a buried Popen FileNotFoundError.
            import shutil
            if not shutil.which("UiRobot.exe"):
                raise FileNotFoundError(
                    "UiRobot.exe not found on PATH or in standard install locations. "
                    "Set ORBIT_UIROBOT_PATH in .env to point to the correct executable."
                )

        log_level = os.environ.get("ORBIT_UIPATH_LOG_LEVEL", _DEFAULT_LOG_LEVEL).strip()
        if log_level not in _VALID_LOG_LEVELS:
            ctx.on_output(
                f"  [WARN] ORBIT_UIPATH_LOG_LEVEL '{log_level}' is not recognised — "
                f"falling back to {_DEFAULT_LOG_LEVEL}"
            )
            log_level = _DEFAULT_LOG_LEVEL

        # Forward all ORBIT_* env vars as UiPath in-arguments so XAML workflows
        # can bind them directly via the Arguments panel.  This includes every
        # variable _build_env() sets: ORBIT_ROOT, ORBIT_RUN_ID, ORBIT_LOG_DIR,
        # ORBIT_SCREENSHOT_DIR, ORBIT_SCRIPT_NAME, ORBIT_SCRIPT_INDEX,
        # ORBIT_SCRIPT_TOTAL, ORBIT_EXCEL_PATH, ORBIT_EXCEL_SHEET,
        # ORBIT_CONTEXT_PATH, and ORBIT_EXCEL_ROW_INDEX (when applicable).
        # Custom env: overrides from run_sequence.yaml are in the subprocess
        # environment and remain accessible via GetEnvironmentVariable().
        orbit_args = {k: v for k, v in ctx.env.items() if k.startswith("ORBIT_")}

        return [
            uirobot,
            "execute",
            "--file",      str(ctx.script_path),
            "--input",     json.dumps(orbit_args),
            "--log-level", log_level,
        ]
