# Orbit Hub — CLAUDE.md

Orbit Hub (Orbit360) is a PySide6/QML desktop orchestration platform for healthcare automation. It drives multi-step test sequences across three engine types: UiPath Robot (.xaml), PowerShell (.ps1), Playwright/Python (.py), and read-only SQL (.sql). Runs are triggered from a GUI, logged to disk, and results surfaced back in real time via signals and QML data bindings.

## Entry point

```
python orbit360_gui.py
```

`orbit360_gui.py` bootstraps Qt, launches a Playwright browser check, then opens `core.main_window.Ready360Window`. In frozen (PyInstaller) mode the same executable doubles as a script subprocess wrapper — see the `--orbit-wrapper` early-exit at the top of the file.

## Project layout

```
orbit360_gui.py          # Qt entry point
core/
  main_window.py         # Main window (QMainWindow) — UI wiring only, no business logic
  app_backend.py         # QObject owned by main_window; feeds QML with live run data
  event_bus.py           # Singleton QObject; all RunWorker signals flow through here
  workers.py             # RunWorker (QThread) — script execution, ORBIT protocol parsing
  orbit_logger.py        # Structured logging: run dirs, result.json, run_summary.json
  paths.py               # All directory constants; frozen vs. dev mode handled here
  utils.py               # load_dotenv, find_uirobot, misc helpers
  swimlane_model.py      # SwimlaneLane QObject — per-script log lane for parallel runs
  screenshot_model.py    # ScreenshotModel QAbstractListModel — feeds ScreenshotStrip.qml
  screenshot_watcher.py  # QFileSystemWatcher watching run/screenshots/ for new PNGs
  executors/
    base.py              # BaseExecutor ABC + ExecutionContext dataclass + _run_once()
    registry.py          # get_executor() — routes script to correct executor by extension/hint
    playwright_executor.py
    powershell_executor.py
    uipath_executor.py
    sql_executor.py      # In-process, read-only SQL (sqlite3 / pyodbc)
qml/
  TitleBar.qml           # Draggable frameless title bar
  DropdownCascade.qml    # System/level selector
  ScriptList.qml         # Reorderable script list with tags
  LogConsole.qml         # Sequential run log (single script view)
  SwimlaneView.qml       # Parallel run view — one column per script
  ScreenshotStrip.qml    # Collapsible horizontal screenshot strip
systems/
  MTX/                   # MTX automation scripts and run_sequence.yaml
  CAC/                   # CAC automation scripts and run_sequence.yaml
  Infra/                 # Infrastructure scripts
tests/
  conftest.py            # make_ctx fixture (no Qt required)
  test_sql_executor.py   # 36 tests — parse, connect spec, format, integration
  test_uipath_executor.py # 16 tests — routing and build_command
```

## Architecture

### Signal flow

```
RunWorker signals
    └─► event_bus (singleton QObject)
            ├─► AppBackend  (updates ScreenshotModel + SwimlaneLane list)
            └─► main_window (drives QStackedWidget, status bar, input dialogs)
```

`event_bus.bus` is the central hub. Workers connect their signals to it once at run start; both AppBackend and main_window subscribe with `Qt.ConnectionType.UniqueConnection` so repeated runs never accumulate duplicate handlers.

### Executor dispatch

`registry.get_executor(script_path, engine_hint)` walks `_REGISTRY` in order:

1. `PowerShellExecutor` — `.ps1` or `engine: powershell`
2. `UiPathExecutor` — `.xaml` or `engine: uipath`
3. `SQLExecutor` — `.sql` or `engine: sql`
4. `PlaywrightExecutor` — `.py` fallback (always matches)

`engine_hint` comes from the `engine:` key in `run_sequence.yaml` and takes priority over file extension.

All subprocess-based executors inherit `BaseExecutor._run_once()` (char-by-char stdout reader, ORBIT wire protocol parser, timeout, retry). `SQLExecutor` overrides `execute()` entirely — it runs in-process via DB-API 2.0, never spawns a subprocess.

### AppBackend → QML

`AppBackend` (owned by `main_window`) exposes three QML-bindable properties:

| Property | Type | Fed by |
|---|---|---|
| `screenshotModel` | `QAbstractListModel` | `ScreenshotWatcher` new-file events |
| `lanes` | `QVariantList` of `SwimlaneLane` | `setup_lanes()` + `_on_script_started()` |
| `screenshotCount` | `int` | emitted on model change |

`main_window` sets `appBackend` as a context property on both `SwimlaneView.qml` and `ScreenshotStrip.qml`.

### Parallel vs. sequential mode

`ORBIT_PARALLEL=N` (default 1) enables parallel execution in `RunWorker`. When `N > 1`, `main_window` switches `QStackedWidget` to `SwimlaneView.qml` (index 1); sequential runs stay on `LogConsole.qml` (index 0). `AppBackend.setup_lanes(script_names)` must be called before the run starts so the QML `Repeater` renders all lane columns at once and remains stable throughout.

## ORBIT wire protocol

Scripts communicate structured events back to the runner via stdout:

| Token | Effect |
|---|---|
| `ORBIT_OUTPUT\|key=value` | Stored in `context.json`; forwarded to downstream scripts |
| `ORBIT_VALUE_REQUEST\|Field Label` | Shows `OrbitInputDialog` for user input |
| `ORBIT_FAILURE_RECOVERY` | Triggers failure-recovery input flow |

Anything else is a plain log line routed to the active console view.

## SQL executor

`SQLExecutor` is read-only by design — three enforcement layers:

1. **sqlite**: URI `?mode=ro` — driver rejects writes at the OS level
2. **pyodbc**: `autocommit=True` — no open transaction possible
3. **Application guard**: only `SELECT` statements execute; anything else is warned and skipped

Env vars that drive it:

| Variable | Required | Default |
|---|---|---|
| `ORBIT_SQL_DIALECT` | yes | — (sqlite \| mssql \| oracle) |
| `ORBIT_SQL_DB_PATH` | sqlite only | — |
| `ORBIT_SQL_DSN` | mssql/oracle | — |
| `ORBIT_SQL_TIMEOUT` | no | 30s |
| `ORBIT_SQL_OUTPUT_FORMAT` | no | log (csv \| json \| log) |

CSV and JSON results are written to `ORBIT_LOG_DIR/results_<n>.<ext>` and published to `context.json` via `ORBIT_OUTPUT|sql_results_<n>=<path>`.

## Run directory layout

```
orbit_data/runs/<System>_<Level0>_<Level1>_<YYYY-MM-DD_HH-MM-SS>/
    run_summary.json
    <Script_Name>/
        result.json
        output.log
        screenshots/
```

`ORBIT_LOG_DIR` is set to the script's subdirectory before each script runs.

## Running tests

```bash
pip install pytest pytest-mock   # one-time
python -m pytest tests/ -v
```

Tests require only stdlib + pytest — no PySide6, no running Qt app.

## Key env vars (`.env` in project root)

| Variable | Purpose |
|---|---|
| `ORBIT_UIROBOT_PATH` | Override UiRobot.exe discovery (optional) |
| `ORBIT_UIPATH_LOG_LEVEL` | UiRobot log level piped to console (default: Verbose; options: Verbose \| Trace \| Information \| Warning \| Error \| Critical \| Off) |
| `ORBIT_PARALLEL` | Number of parallel workers (default: 1) |
| `ORBIT_SQL_*` | SQL executor config (see above) |

## Adding a new executor

1. Create `core/executors/my_executor.py` subclassing `BaseExecutor`
2. Implement `can_handle(script_path, engine_hint)` and `build_command(ctx)`
3. Import and insert before `PlaywrightExecutor` in `core/executors/registry.py`
4. If it runs in-process (like SQL), override `execute()` instead of `build_command()`

## PyInstaller build

```
build_exe.bat
```

Uses `orbit360.spec`. Frozen-mode path resolution is handled in `core/paths.py` — `_RESOURCE_BASE` (bundled read-only assets) and `BASE_DIR` (writable data next to the .exe) diverge only in frozen mode.
