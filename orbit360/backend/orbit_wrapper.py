"""
orbit_wrapper.py — Orbit360 v4.0

Thin launcher used by workers.py instead of running scripts directly.
Provides two invisible services to every test script:

1. Screenshot redirect
   Monkey-patches playwright.sync_api.Page.screenshot at the class level
   so that *any* call to page.screenshot() — whether from a plain codegen
   script or a script with a custom screenshot() helper — saves the file
   inside ORBIT_SCREENSHOT_DIR.  Only the directory is forced; the original
   filename (if any) is preserved, and a sequential name is generated when
   the caller passed no path.

2. Clean sys.argv
   Resets sys.argv to [script_path] so the target script sees itself as
   argv[0] and doesn't inherit the wrapper's own arguments.

Usage (workers.py):
    python orbit_wrapper.py /absolute/path/to/script.py
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

# Ensure the project root (parent of orbit360/) is on sys.path so that
# "from orbit360.X import ..." works regardless of cwd or how this script
# is invoked (python -m orbit360.backend.orbit_wrapper).
_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

_counter = [0]


from orbit360.utils.utils import load_dotenv as _load_dotenv


def _patch_playwright_screenshots(shot_dir: Path) -> None:
    """
    Replace Page.screenshot with a version that always saves to shot_dir.

    The original filename is kept; only the directory is redirected.
    Scripts that already build a correct path (via shot_dir / filename)
    end up writing to the same place, so they are unaffected.
    Scripts that pass a hardcoded path or no path at all get their
    screenshots captured in the run folder automatically.
    """
    try:
        from playwright.sync_api import Page  # noqa: PLC0415
    except ImportError:
        return  # Playwright not available — skip

    _original_screenshot = Page.screenshot
    _original_close      = Page.close

    def _redirected(self, **kwargs):
        _counter[0] += 1
        original_path = kwargs.get("path")
        if original_path:
            # Keep the caller's filename, redirect the directory only
            filename = Path(original_path).name
        else:
            filename = f"{_counter[0]:02d}_screenshot.png"
        kwargs["path"] = str(shot_dir / filename)
        return _original_screenshot(self, **kwargs)

    def _autoshot_close(self, **kwargs):
        # Capture the final page state before it closes.
        # Silently skipped if the page is already closed or the browser has
        # gone away (e.g. browser crash, network error, early exit).
        try:
            if not self.is_closed():
                _counter[0] += 1
                _original_screenshot(
                    self, path=str(shot_dir / f"{_counter[0]:02d}_final.png")
                )
        except Exception:
            pass
        return _original_close(self, **kwargs)

    Page.screenshot = _redirected
    Page.close      = _autoshot_close



def _patch_playwright_browser(headless: bool | None, slow_mo: int | None) -> None:
    """
    Override BrowserType.launch so that every `playwright.chromium.launch()`
    call in any test script automatically picks up ORBIT_HEADLESS / ORBIT_SLOW_MO.

    ORBIT_HEADLESS=1  — run the browser invisibly (CI / background runs).
    ORBIT_SLOW_MO=N   — insert N ms between Playwright actions (visual debug).

    Both settings are no-ops when the env vars are absent so normal headful
    runs are completely unaffected.
    """
    if headless is None and slow_mo is None:
        return
    try:
        from playwright.sync_api import BrowserType  # noqa: PLC0415
    except ImportError:
        return

    _original_launch = BrowserType.launch

    def _patched_launch(self, **kwargs):
        if headless is not None:
            kwargs["headless"] = headless
        if slow_mo is not None:
            kwargs["slow_mo"] = slow_mo
        return _original_launch(self, **kwargs)

    BrowserType.launch = _patched_launch


def main() -> None:
    # Reconfigure stdout/stderr to UTF-8 before any logging is set up.
    # On Windows, piped subprocesses default to the system code page (e.g.
    # cp1252), which can't encode box-drawing characters (U+2500 etc.).
    # Python then falls back to backslashreplace, writing literal "\u2500"
    # instead of "─".  Forcing UTF-8 here prevents that.
    import io as _io
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = _io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )
    if hasattr(sys.stderr, "buffer"):
        sys.stderr = _io.TextIOWrapper(
            sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True
        )

    _load_dotenv()
    if len(sys.argv) < 2:
        print("orbit_wrapper: no script specified", file=sys.stderr)
        sys.exit(1)

    script_path = sys.argv[1]

    # ── Screenshot redirect ─────────────────────────────────────────────
    shot_dir_str = os.environ.get("ORBIT_SCREENSHOT_DIR")
    if shot_dir_str:
        shot_dir = Path(shot_dir_str)
        shot_dir.mkdir(parents=True, exist_ok=True)
        _patch_playwright_screenshots(shot_dir)

    # ── Browser behavior flags ──────────────────────────────────────────
    # ORBIT_HEADLESS=1      run Chromium with no visible window
    # ORBIT_SLOW_MO=N       insert N ms between every Playwright action
    _headless_env = os.environ.get("ORBIT_HEADLESS")
    _slow_mo_env  = os.environ.get("ORBIT_SLOW_MO")
    _headless = (_headless_env == "1") if _headless_env is not None else None
    _slow_mo  = int(_slow_mo_env) if (_slow_mo_env or "").isdigit() else None
    _patch_playwright_browser(_headless, _slow_mo)

    # ── Run target script as __main__ with clean argv ───────────────────
    # Add the script's own directory to sys.path so local imports resolve.
    script_dir = str(Path(script_path).parent)
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    sys.argv = [script_path]
    runpy.run_path(script_path, run_name="__main__")


if __name__ == "__main__":
    main()
