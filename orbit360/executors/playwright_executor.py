"""
playwright_executor.py — Python / Playwright script executor.

Handles any .py automation script.  In source-mode it delegates to
orbit_wrapper.py; in frozen (EXE) mode it re-invokes the bundle via the
--orbit-wrapper flag so the bundle entry point can route to
orbit360.backend.orbit_wrapper.main() without starting the GUI.

Playwright scripts in systems/ are NEVER rewritten by this executor —
it only controls how they are launched.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from orbit360.executors.base import BaseExecutor, ExecutionContext
from orbit360.utils.paths import PYTHON_EXECUTABLE, _IS_FROZEN, _RESOURCE_BASE

_WRAPPER = _RESOURCE_BASE / "orbit360" / "backend" / "orbit_wrapper.py"


class PlaywrightExecutor(BaseExecutor):
    """
    Default executor for Python-based automation scripts.

    Activated when:
      • engine hint is 'playwright' or 'python'
      • script extension is .py (and no other executor claimed it)

    This is the fallback executor in the registry.
    """

    def can_handle(self, script_path: Path, engine_hint: Optional[str]) -> bool:
        if engine_hint:
            return engine_hint in ("playwright", "python")
        return script_path.suffix.lower() == ".py"

    def build_command(self, ctx: ExecutionContext) -> list[str]:
        if _IS_FROZEN:
            # Frozen EXE: re-invoke the bundle in wrapper mode.
            # The bundle's entry point detects --orbit-wrapper and delegates
            # to orbit360.backend.orbit_wrapper.main() without starting the GUI.
            return [PYTHON_EXECUTABLE, "--orbit-wrapper", str(ctx.script_path)]
        # Source / venv mode: delegate to the wrapper script directly.
        return [PYTHON_EXECUTABLE, str(_WRAPPER), str(ctx.script_path)]
