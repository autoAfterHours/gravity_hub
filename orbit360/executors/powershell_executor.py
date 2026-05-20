"""
powershell_executor.py — PowerShell (.ps1) script executor.

Uses -Command rather than -File so that *>&1 can merge all PowerShell
output streams (including stream 6 / Write-Host) into stdout before the
OS pipe captures them.  -File only surfaces streams 1 and 2.

Forces UTF-8 console encoding so emoji and non-ASCII Write-Host output
round-trips correctly through the utf-8 subprocess pipe.

ORBIT_* env vars set in ExecutionContext.env are visible inside the .ps1
as $env:ORBIT_LOG_DIR, $env:ORBIT_RUN_ID, etc. — no additional plumbing
needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from orbit360.executors.base import BaseExecutor, ExecutionContext


class PowerShellExecutor(BaseExecutor):
    """
    Executor for PowerShell automation scripts (.ps1).

    Activated when:
      • engine hint is 'powershell'
      • script extension is .ps1 (and no other executor claimed it)
    """

    def can_handle(self, script_path: Path, engine_hint: Optional[str]) -> bool:
        if engine_hint:
            return engine_hint == "powershell"
        return script_path.suffix.lower() == ".ps1"

    def build_command(self, ctx: ExecutionContext) -> list[str]:
        # Escape single quotes in the path for the PS inline string.
        ps_path = str(ctx.script_path).replace("'", "''")
        ps_command = (
            "[Console]::OutputEncoding = [System.Text.Encoding]::UTF8; "
            f"& {{ & '{ps_path}' }} *>&1"
        )
        return [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-Command", ps_command,
        ]
