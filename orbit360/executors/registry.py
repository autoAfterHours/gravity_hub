"""
registry.py — Executor registry and dispatch.

get_executor() returns the first executor in _REGISTRY that claims the
given script.  Order matters: more-specific executors must precede the
generic Python fallback so a .ps1 file is never accidentally routed to
PlaywrightExecutor.

Adding a new engine in Phase 5:
    1. Create orbit360/executors/my_executor.py with MyExecutor(BaseExecutor)
    2. Import it here and insert it before PlaywrightExecutor in _REGISTRY
    3. Add engine hint string to can_handle()
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from orbit360.executors.base import BaseExecutor
from orbit360.executors.playwright_executor import PlaywrightExecutor
from orbit360.executors.powershell_executor import PowerShellExecutor
from orbit360.executors.sql_executor import SQLExecutor
from orbit360.executors.uipath_executor import UiPathExecutor

# Singletons — executors are stateless; one instance per type is sufficient.
_REGISTRY: list[BaseExecutor] = [
    PowerShellExecutor(),  # .ps1 files and engine: powershell
    UiPathExecutor(),      # .xaml files and engine: uipath
    SQLExecutor(),         # .sql files and engine: sql  (Phase 5)
    PlaywrightExecutor(),  # .py files — fallback, must be last
]


def get_executor(
    script_path: Path,
    engine_hint: Optional[str] = None,
) -> BaseExecutor:
    """
    Return the executor responsible for script_path.

    engine_hint is the optional 'engine:' field from run_sequence.yaml.
    When present it takes priority over file-extension detection.
    Falls back to PlaywrightExecutor if nothing else matches.
    """
    for executor in _REGISTRY:
        if executor.can_handle(script_path, engine_hint):
            return executor
    return PlaywrightExecutor()
