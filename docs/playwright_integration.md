# Playwright Integration Guide — Orbit360

This guide covers everything you need to write Playwright scripts that run
inside Orbit360's GUI runner: environment variables, the shared runtime
(`orbit_context.py`), screenshots, parallel execution, and the script template.

---

## How the runner works

When you press **Run All** or **Run Selected**, Orbit360 launches each script
as a subprocess via `orbit_wrapper.py`.  Before the script starts, the runner
injects a set of `ORBIT_*` environment variables into the subprocess
environment.  Your script reads them (either directly or through
`orbit_context.py`) to know where to log, where to save screenshots, which
environment to hit, and so on.

The GUI receives every `stdout` line in real time and displays it in the log
console (or, in parallel mode, in the script's dedicated swimlane).

---

## Environment variables injected at runtime

| Variable | Example | Description |
|---|---|---|
| `ORBIT_ROOT` | `/home/user/orbit_hub` | Absolute path to the project root. Add to `sys.path` to import `core.*`. |
| `ORBIT_RUN_ID` | `2026-03-06_14-30-00` | Unique ID for the current run. Same for all scripts in one run. |
| `ORBIT_LOG_DIR` | `…/runs/MySystem_QA_2026-03-06_14-30-00/Login_Test/` | Write logs here. The runner already creates `output.log`. |
| `ORBIT_SCREENSHOT_DIR` | `…/Login_Test/screenshots/` | **Save all screenshots here** so the GUI strip shows them. |
| `ORBIT_SCRIPT_NAME` | `Login Test` | The name from `tests.yaml`. Useful for log headings. |
| `ORBIT_SCRIPT_INDEX` | `0` | 0-based position of this script in the run order. |
| `ORBIT_SCRIPT_TOTAL` | `5` | Total number of scripts in the run. |

### Optional / user-configurable

Set these in your shell or `.env` file. They pass through to every script
automatically via `os.environ.copy()`.

| Variable | Default | Description |
|---|---|---|
| `ORBIT_BASE_URL` | *(empty)* | Target environment URL (e.g. `https://qa.example.com`). Read with `base_url()`. |
| `ORBIT_HEADLESS` | `0` | Set to `1` to run Playwright in headless mode (no visible browser). |
| `ORBIT_PAUSE_ON_FAIL` | *(unset)* | Set to any value to pause and show the browser on script failure. |
| `ORBIT_PARALLEL` | `1` | Number of scripts to run concurrently (see [Parallel execution](#parallel-execution)). |
| `ORBIT_RETRY_COUNT` | `0` | Retry a failed script up to N times before marking it failed. |
| `ORBIT_TIMEOUT_MINUTES` | *(unset)* | Kill a script that runs longer than N minutes. |
| `ORBIT_DRY_RUN` | `0` | Set to `1` to preview the run plan without executing anything. |

---

## The script template

Copy `core/script_template.py` as the starting point for every new script.
The bootstrap block at the top locates the project root whether the script is
run standalone (from the terminal) or through the Orbit360 GUI.

```python
import os
import sys
import time
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect

# ── 1. Configuration ──────────────────────────────────────────────────────
SYSTEM      = "MySystem"   # matches the system name in the GUI cascade
ENVIRONMENT = "QA"
PILLAR      = "ENT"
RUN_TYPE    = "CLI"

# ── 2. Bootstrap — locate project root ───────────────────────────────────
_env_root = os.environ.get("ORBIT_ROOT")
if _env_root:
    sys.path.insert(0, _env_root)
else:
    _p = Path(__file__).resolve()
    while _p.name.lower() not in ("orbit360_v3.0", "orbit_hub"):
        if _p.parent == _p:
            raise RuntimeError("Could not locate Orbit project root.")
        _p = _p.parent
    sys.path.insert(0, str(_p))

from core.orbit_context import (
    setup, step, end_step, section_break,
    screenshot, manual_prompt, handle_failure, format_duration,
    base_url,
)

# ── 3. Setup ─────────────────────────────────────────────────────────────
ctx    = setup(SYSTEM, ENVIRONMENT, PILLAR, RUN_TYPE)
logger = ctx.logger

# ── 4. Your test steps go here ────────────────────────────────────────────
def run(playwright: Playwright) -> None:
    browser = playwright.chromium.launch(
        headless=os.getenv("ORBIT_HEADLESS", "0") == "1"
    )
    page = browser.new_page()

    with step(ctx, "Navigate to application"):
        page.goto(base_url() or "https://app.example.com")

    with step(ctx, "Log in"):
        page.fill("#username", "demo")
        page.fill("#password", "password")
        page.click("button[type=submit]")
        expect(page.locator(".dashboard")).to_be_visible()
        screenshot(ctx, page, "after_login")   # saved to ORBIT_SCREENSHOT_DIR

    browser.close()

with sync_playwright() as p:
    run(p)
```

---

## Screenshots

Screenshots are the most important integration point between your script and
the GUI's **screenshot strip**.

### Using `orbit_context.screenshot()`

```python
from core.orbit_context import screenshot

# Inside a step:
screenshot(ctx, page, "payment_confirmation")
# → saves to ORBIT_SCREENSHOT_DIR/payment_confirmation_<timestamp>.png
```

`screenshot()` reads `ORBIT_SCREENSHOT_DIR` from the environment and saves
there automatically.  The Orbit360 GUI watches that directory with a
`QFileSystemWatcher`; the thumbnail strip appears as soon as the first PNG
lands.

### Saving screenshots manually

If you aren't using `orbit_context`, save directly to `ORBIT_SCREENSHOT_DIR`:

```python
import os
from pathlib import Path

ss_dir = Path(os.environ.get("ORBIT_SCREENSHOT_DIR", "."))
ss_dir.mkdir(parents=True, exist_ok=True)

page.screenshot(path=str(ss_dir / "my_screenshot.png"))
```

Any `.png` file placed in `ORBIT_SCREENSHOT_DIR` (or any subdirectory of the
run root) will appear in the GUI strip.

### Naming conventions

Use descriptive names — the filename becomes the thumbnail's tooltip:

```python
screenshot(ctx, page, "step_3_confirm_order")   # good
screenshot(ctx, page, "img1")                   # avoid
```

---

## Parallel execution

Set `ORBIT_PARALLEL=N` in your `.env` to run up to N scripts simultaneously.

```bash
# .env
ORBIT_PARALLEL=4
```

### Swimlane view

When `ORBIT_PARALLEL > 1` the GUI switches from the single log console to the
**swimlane view**: one dedicated panel per script, showing that script's live
output.  Each panel has a status dot:

| Dot colour | Meaning |
|---|---|
| Gray | Script is queued (not started yet) |
| Blue | Script is running |
| Green | Script passed |
| Red | Script failed or errored |

### Writing parallel-safe scripts

Scripts launched in parallel share no state.  Each gets its own:
- `ORBIT_LOG_DIR` and `ORBIT_SCREENSHOT_DIR` (separate subdirectories)
- `ORBIT_SCRIPT_INDEX` (the slot it was submitted at)
- Browser instance (Playwright launches an isolated browser per script)

**Do not share files between scripts** during a run — write to `ORBIT_LOG_DIR`
only, or use a dedicated output path per script derived from `ORBIT_SCRIPT_NAME`.

```python
# Safe: each script writes to its own directory
output_dir = Path(os.environ["ORBIT_LOG_DIR"]) / "output"
output_dir.mkdir(exist_ok=True)
```

### Input prompts and parallel mode

`manual_prompt()` / `input()` pauses execution waiting for the user to press
**Continue** in the GUI.  In parallel mode this is **ambiguous** (which script
gets the input?).  Avoid interactive prompts in scripts intended for parallel
runs.  Use `ORBIT_RETRY_COUNT` for transient failures instead.

---

## The HTML run report

After every run, Orbit360 generates `run_report.html` in the run root
directory.  Click **View Report** to open it.

The report includes:
- Run metadata: system, hierarchy, run ID, start/finish times, total duration
- Pass-rate progress bar (green = passed, red = failed)
- Per-script collapsible sections with:
  - Status badge and duration
  - Full coloured stdout (same colour scheme as the GUI log)
  - Screenshot thumbnails (click to open full-size)

Failed and errored script sections are **expanded by default** so the relevant
error output is immediately visible without scrolling.

---

## tests.yaml reference

Orbit360 discovers scripts through a `tests.yaml` file placed inside each
system/level folder.

```yaml
# systems/MySystem/QA/tests.yaml
scripts:
  - name: Login Test
    path: scripts/login_test.py

  - name: Patient Search
    path: scripts/patient_search.py

  - name: Export PDF
    path: scripts/export_pdf.py
```

| Key | Required | Description |
|---|---|---|
| `name` | Yes | Display name in the GUI and in logs / reports. |
| `path` | Yes | Path to the `.py` script, **relative to the tests.yaml file**. |

Scripts run in the listed order (sequential mode) or up to `ORBIT_PARALLEL`
at a time (parallel mode).

---

## Troubleshooting

### "Pre-flight check failed — missing script files"

The `path` in `tests.yaml` can't be found.  Paths are resolved relative to the
`tests.yaml` file — double-check subdirectory names and trailing slashes.

### Screenshots don't appear in the strip

- Make sure your script saves to `ORBIT_SCREENSHOT_DIR` (not to a hardcoded path).
- Verify the file extension is `.png` (`.jpg` / `.jpeg` are not watched).

### Parallel scripts interfere with each other

Each script should write only to `ORBIT_LOG_DIR` and `ORBIT_SCREENSHOT_DIR`.
Avoid shared temp files, shared Excel workbooks open for writing, or in-process
globals.

### Script hangs waiting for input in parallel mode

Remove or guard `input()` / `manual_prompt()` calls with a check:

```python
if os.environ.get("ORBIT_PARALLEL", "1") == "1":
    manual_prompt(ctx, "Press ENTER when ready")
else:
    logger.info("Skipping manual prompt in parallel mode")
```
