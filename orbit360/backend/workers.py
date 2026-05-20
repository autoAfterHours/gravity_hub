"""
workers.py — Orbit360 v4.1
QThread-based execution engine. Runs scripts via the executor layer,
emits signals to the GUI. No UI logic. No direct imports from main_window.py.

Execution flow:
    RunWorker._run()
        └─ _run_single_script()
               ├─ _build_env()          — assembles full ORBIT_* env dict
               ├─ registry.get_executor() — selects engine (PS/UiPath/Python/SQL)
               └─ executor.execute()    — subprocess + ORBIT protocol + retry
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QThread, Signal

from orbit360.executors.base import ExecutionContext
from orbit360.executors.registry import get_executor
from orbit360.orbit_logger import OrbitLogger, ScriptResult
from orbit360.utils.paths import BASE_DIR, PYTHON_EXECUTABLE, _IS_FROZEN, _RESOURCE_BASE
from orbit360.utils import utils


class RunWorker(QThread):
    """
    Executes a sequence of scripts from a tests.yaml in a background thread.
    Supports sequential and parallel (ORBIT_PARALLEL=N) execution modes.

    Signal contract (queued connections — all GUI updates happen on main thread):

        run_started(run_root: str)
            Emitted once after the run directory is created, before any script
            starts.  Useful for wiring filesystem watchers (e.g. screenshot strip).

        script_started(name: str, index: int, total: int)
            Emitted immediately before a script's subprocess is launched.
            In parallel mode multiple script_started signals may arrive before
            any script_finished.

        script_finished(result: ScriptResult)
            Emitted after each script completes (pass, fail, or error).

        progress_updated(script_name: str, line: str)
            Emitted for each stdout line captured during execution.
            script_name is "" for run-level messages (section breaks, dry-run
            output, retry notices, etc.).

        run_completed(summary_path: str, passed: int, failed: int, errored: int)
            Emitted once after all scripts run and finalize_run() returns.

        run_aborted(summary_path: str, passed: int, failed: int, errored: int)
            Emitted instead of run_completed when the user stopped the run early.

        run_failed(error_message: str)
            Emitted if the worker encounters an unrecoverable error
            (e.g., tests.yaml unreadable after the worker starts).

        manual_input_required(prompt: str)
            Emitted when a script appears to be waiting for stdin input.

        failure_input_required(prompt: str)
            Emitted when a script failure recovery prompt is active.
            The GUI shows Skip Step / Manual Complete / Mark Failed buttons
            in addition to the standard Continue button.

        value_input_requested(field: str)
            Emitted when a script requests a named value via ORBIT_VALUE_REQUEST.
    """

    run_started              = Signal(str)            # run_root path
    script_started           = Signal(str, int, int)  # name, index, total
    script_finished          = Signal(object)         # ScriptResult
    progress_updated         = Signal(str, str)       # script_name, stdout line
    run_completed            = Signal(str, int, int, int)  # summary_path, p, f, e
    run_aborted              = Signal(str, int, int, int)  # summary_path, p, f, e
    run_failed               = Signal(str)            # error_message
    manual_input_required    = Signal(str)            # prompt text
    failure_input_required   = Signal(str)            # failure recovery prompt text
    value_input_requested    = Signal(str)            # field label — show OrbitInputDialog

    def __init__(
        self,
        system_name: str,
        tests_yaml_path: Path,
        hierarchy: Optional[list[str]] = None,
        script_name_filter: Optional[str] = None,
        selected_row_index: Optional[int] = None,
        resume_context_path: Optional[Path] = None,
        parent=None,
    ) -> None:
        """
        Args:
            system_name:          Used as the top-level run directory segment.
            tests_yaml_path:      Absolute path to the tests.yaml to execute.
            hierarchy:            Ordered list of raw cascade selections
                                  (e.g. ["QA", "ENT", "PUV"]) used to build
                                  the run directory path under system_name.
            script_name_filter:   If set, only the script with this name is run.
            selected_row_index:   Excel row to pin for Single Run.
            resume_context_path:  Path to a previous run's context.json for resume.
            parent:               Optional Qt parent object.
        """
        super().__init__(parent)
        self.system_name = system_name
        self.tests_yaml_path = tests_yaml_path
        self.hierarchy: list[str] = hierarchy or []
        self.script_name_filter = script_name_filter
        self.selected_row_index = selected_row_index
        self.resume_context_path = resume_context_path
        self._abort_requested = False
        self._logger: Optional[OrbitLogger] = None
        self._td_cfg: Optional[dict] = None   # test_data config, loaded once in _run()
        # Thread-safe map of script_name → active subprocess.Popen.
        # Populated/cleared by _register_proc/_unregister_proc.
        # Read by request_abort() and send_input().
        self._active_procs: dict[str, subprocess.Popen] = {}
        self._procs_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Control API (called from the GUI thread)                            #
    # ------------------------------------------------------------------ #

    def request_abort(self) -> None:
        """
        Signal the worker to stop and immediately kill ALL active subprocesses
        (in parallel mode there may be more than one).
        """
        self._abort_requested = True
        with self._procs_lock:
            for proc in list(self._active_procs.values()):
                try:
                    proc.kill()
                except OSError:
                    pass

    def send_input(self, text: str = "\n") -> None:
        """
        Write text to the running subprocess's stdin.  Called from the main
        thread when the user clicks Continue after a manual_prompt pause.
        Only meaningful in sequential mode (one active process at a time).
        """
        with self._procs_lock:
            procs = list(self._active_procs.values())
        if len(procs) != 1:
            return   # ambiguous in parallel mode — ignore
        proc = procs[0]
        if proc is None or proc.stdin is None:
            return
        try:
            if not text.endswith("\n"):
                text += "\n"
            proc.stdin.write(text)
            proc.stdin.flush()
        except (OSError, BrokenPipeError):
            pass

    # ------------------------------------------------------------------ #
    # QThread entry point                                                  #
    # ------------------------------------------------------------------ #

    def run(self) -> None:
        """QThread entry point. Full execution sequence."""
        try:
            self._run()
        except Exception as exc:  # noqa: BLE001
            self.run_failed.emit(f"Unexpected worker error: {exc}")

    def _run(self) -> None:
        """Inner execution body, separated so the outer run() can catch all exceptions."""
        self._logger = OrbitLogger(self.system_name, self.hierarchy)
        self._logger.begin_run()

        # Announce the run root so filesystem watchers (e.g. screenshot strip)
        # can start watching before any script has produced output.
        if self._logger.run_root:
            self.run_started.emit(str(self._logger.run_root))

        all_scripts = utils.load_tests_yaml(self.tests_yaml_path)
        if self.script_name_filter:
            scripts = [s for s in all_scripts if s["name"] == self.script_name_filter]
        else:
            scripts = all_scripts
        if not scripts:
            self.run_failed.emit(
                f"No scripts found in: {self.tests_yaml_path}\n"
                "Check that tests.yaml exists and contains a non-empty 'scripts:' list."
            )
            return

        # ── Pre-flight: verify every script file exists ────────────────────────
        missing = [
            entry["name"]
            for entry in scripts
            if not (self.tests_yaml_path.parent / entry["path"]).is_file()
        ]
        if missing:
            names = "\n  ".join(missing)
            self.run_failed.emit(
                f"Pre-flight check failed — missing script files:\n  {names}\n"
                "Fix the paths in tests.yaml or restore the missing files."
            )
            return

        # ── Load test data config once (shared by all scripts in this run) ────
        self._td_cfg = utils.load_test_data_config(self.tests_yaml_path)
        excel_path_str = ""
        if self._td_cfg and self._td_cfg.get("path"):
            from orbit360.utils.paths import ORBIT_DATA_DIR
            td_raw     = self._td_cfg["path"]
            td_path    = Path(td_raw) if os.path.isabs(td_raw) else ORBIT_DATA_DIR / td_raw
            excel_path_str = str(td_path)

        # ── Write initial context.json ─────────────────────────────────────────
        self._logger.write_context_json(scripts, excel_path=excel_path_str)

        # ── Resume: skip already-passed scripts ────────────────────────────────
        if self.resume_context_path and self.resume_context_path.is_file():
            try:
                ctx_data = json.loads(
                    self.resume_context_path.read_text(encoding="utf-8")
                )
                completed = {
                    s["name"]
                    for s in ctx_data.get("scripts", [])
                    if s.get("status") in ("passed", "manual_complete")
                }
                scripts_resuming = [s for s in scripts if s["name"] not in completed]
                skipped = len(scripts) - len(scripts_resuming)
                if skipped:
                    self.progress_updated.emit(
                        "", f"Resume Run — skipping {skipped} already-passed script(s)"
                    )
                scripts = scripts_resuming
            except Exception:
                pass

        # ── Expand repeat entries ──────────────────────────────────────────────
        # Only in Full Run — Single Run (script_name_filter set) ignores repeat.
        if not self.script_name_filter:
            expanded: list[dict] = []
            for entry in scripts:
                count = entry.get("repeat", 1)
                count = count if isinstance(count, int) and count >= 1 else 1
                for i in range(count):
                    rep = dict(entry)
                    if count > 1:
                        rep["_repeat_index"] = i + 1
                        rep["_repeat_total"] = count
                    expanded.append(rep)
            scripts = expanded

        # ── Dry-run mode ───────────────────────────────────────────────────────
        if os.environ.get("ORBIT_DRY_RUN") == "1":
            hier = " / ".join(self.hierarchy) if self.hierarchy else "(root)"
            self.progress_updated.emit("", f"[DRY RUN]  {self.system_name}  →  {hier}")
            self.progress_updated.emit("", f"[DRY RUN]  {len(scripts)} script(s) would run:")
            for i, entry in enumerate(scripts, 1):
                rep_sfx = (
                    f"  [iteration {entry['_repeat_index']}/{entry['_repeat_total']}]"
                    if entry.get("_repeat_total", 1) > 1 else ""
                )
                self.progress_updated.emit("", f"[DRY RUN]    {i:>3}.  {entry['name']}{rep_sfx}")
                self.progress_updated.emit("", f"[DRY RUN]         {entry['path']}")
            summary_path = self._logger.finalize_run([], aborted=False)
            self.run_completed.emit(str(summary_path), 0, 0, 0)
            return

        # ── Execution ──────────────────────────────────────────────────────────
        results: list[ScriptResult] = []
        total = len(scripts)
        parallel = max(1, min(int(os.environ.get("ORBIT_PARALLEL", "1")), 32))

        if parallel == 1:
            # Sequential mode — original behaviour, one script at a time.
            for index, entry in enumerate(scripts):
                if self._abort_requested:
                    break
                result = self._run_single_script(entry, index, total)
                if result is not None:
                    results.append(result)
                    self._logger.update_context_script(result.script_name, result)
        else:
            # Parallel mode — run up to `parallel` scripts concurrently.
            with concurrent.futures.ThreadPoolExecutor(max_workers=parallel) as executor:
                futures = [
                    executor.submit(self._run_single_script, entry, index, total)
                    for index, entry in enumerate(scripts)
                ]
                for future in concurrent.futures.as_completed(futures):
                    result = future.result()
                    if result is not None:
                        results.append(result)
                        self._logger.update_context_script(result.script_name, result)

        summary_path = self._logger.finalize_run(results, aborted=self._abort_requested)

        passed  = sum(1 for r in results if r.status == "passed")
        failed  = sum(1 for r in results if r.status == "failed")
        errored = sum(1 for r in results if r.status == "error")

        if self._abort_requested:
            self._logger.finalize_context("aborted")
        elif failed == 0 and errored == 0:
            self._logger.finalize_context("passed")
        else:
            self._logger.finalize_context("failed")

        self._logger.write_run_csvs(results, scripts)

        if self._abort_requested:
            self.run_aborted.emit(str(summary_path), passed, failed, errored)
        else:
            self.run_completed.emit(str(summary_path), passed, failed, errored)

    # ------------------------------------------------------------------ #
    # Per-script execution (called sequentially or from executor threads) #
    # ------------------------------------------------------------------ #

    def _run_single_script(
        self,
        entry: dict,
        index: int,
        total: int,
    ) -> Optional[ScriptResult]:
        """
        Dispatch one script to the appropriate executor and map the raw
        ExecutionResult to a ScriptResult via OrbitLogger.

        Emits script_started before launch and script_finished on completion.
        Thread-safe: may be called concurrently from ThreadPoolExecutor workers.

        Returns the ScriptResult, or None if the run was aborted before this
        script could start.
        """
        if self._abort_requested:
            return None

        script_name     = entry["name"]
        script_path_str = entry["path"]
        rep_idx         = entry.get("_repeat_index")
        rep_total       = entry.get("_repeat_total")

        self.script_started.emit(script_name, index, total)

        if rep_idx is not None:
            self.progress_updated.emit(
                script_name,
                f"─── Iteration {rep_idx} of {rep_total} ───────────────────────────",
            )

        log_dir, screenshot_dir = self._logger.prepare_script_dirs(script_name)
        resolved = self._resolve_script_path(script_path_str)

        start_time      = time.monotonic()
        started_at_wall = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # ── Build environment FIRST (fixes pre-existing reference-before-assign
        #    bug in the original UiPath branch) ─────────────────────────────────
        env = self._build_env(entry, index, total, log_dir, screenshot_dir)

        # ── Select executor based on optional 'engine:' YAML field or extension ─
        engine_hint = entry.get("engine")
        executor = get_executor(resolved, engine_hint)

        # ── Build execution context — keeps executor decoupled from Qt ──────────
        ctx = ExecutionContext(
            script_path=resolved,
            script_name=script_name,
            env=env,
            cwd=self.tests_yaml_path.parent,
            timeout_minutes=(
                float(os.environ["ORBIT_TIMEOUT_MINUTES"])
                if os.environ.get("ORBIT_TIMEOUT_MINUTES") else None
            ),
            max_retries=max(0, int(os.environ.get("ORBIT_RETRY_COUNT", "0"))),
            on_output=lambda line: self.progress_updated.emit(script_name, line),
            on_manual_input=self.manual_input_required.emit,
            on_failure_recovery=self.failure_input_required.emit,
            on_value_requested=self.value_input_requested.emit,
            on_context_output=self._logger.set_context_output,
            abort_flag=lambda: self._abort_requested,
            register_proc=lambda proc: self._register_proc(script_name, proc),
            unregister_proc=lambda: self._unregister_proc(script_name),
        )

        exec_result = executor.execute(ctx)
        end_time = time.monotonic()

        # ── Map ExecutionResult → ScriptResult via OrbitLogger ──────────────────
        if exec_result.error_message:
            result = self._logger.record_failure(
                script_name=script_name,
                script_path=script_path_str,
                error_message=exec_result.error_message,
                log_dir=log_dir,
                screenshot_dir=screenshot_dir,
                started_at=started_at_wall,
            )
        else:
            result = self._logger.record_script(
                script_name=script_name,
                script_path=script_path_str,
                return_code=exec_result.exit_code,
                stdout="\n".join(exec_result.stdout_lines),
                stderr="",
                start_time=start_time,
                end_time=end_time,
                log_dir=log_dir,
                screenshot_dir=screenshot_dir,
                started_at=started_at_wall,
            )

        self.script_finished.emit(result)
        return result

    # ------------------------------------------------------------------ #
    # Environment builder                                                  #
    # ------------------------------------------------------------------ #

    def _build_env(
        self,
        entry: dict,
        index: int,
        total: int,
        log_dir: Path,
        screenshot_dir: Path,
    ) -> dict:
        """
        Assemble the full subprocess environment dict for one script.

        ORBIT_* keys form the data contract between the orchestrator and
        automation scripts.  JSON, XLSX, and CSV data files are referenced
        via ORBIT_EXCEL_PATH and ORBIT_CONTEXT_PATH so scripts can locate
        them without hard-coded paths.
        """
        env = os.environ.copy()
        # Ensure project root is on PYTHONPATH so scripts can import from orbit360.*
        _pp = env.get("PYTHONPATH", "")
        env["PYTHONPATH"]           = str(BASE_DIR) + (os.pathsep + _pp if _pp else "")
        env["PYTHONUNBUFFERED"]     = "1"
        env["PYTHONIOENCODING"]     = "utf-8"   # prevent cp1252 errors on Windows
        env["ORBIT_ROOT"]           = str(BASE_DIR)
        env["ORBIT_RUN_ID"]         = self._logger.run_id or ""
        env["ORBIT_LOG_DIR"]        = str(log_dir)
        env["ORBIT_SCREENSHOT_DIR"] = str(screenshot_dir)
        env["ORBIT_SCRIPT_NAME"]    = entry["name"]
        env["ORBIT_SCRIPT_INDEX"]   = str(index)
        env["ORBIT_SCRIPT_TOTAL"]   = str(total)

        # ── Excel / CSV / JSON test data path ──────────────────────────────────
        # Pre-loaded once in _run() to avoid repeated I/O per script.
        td_cfg = self._td_cfg
        if td_cfg and td_cfg.get("path"):
            from orbit360.utils.paths import ORBIT_DATA_DIR
            td_raw  = td_cfg["path"]
            td_path = Path(td_raw) if os.path.isabs(td_raw) else ORBIT_DATA_DIR / td_raw
            env["ORBIT_EXCEL_PATH"]  = str(td_path)
            env["ORBIT_EXCEL_SHEET"] = str(td_cfg.get("sheet", 0))

        # ── Shared context.json path ───────────────────────────────────────────
        if self._logger and self._logger.context_path:
            env["ORBIT_CONTEXT_PATH"] = str(self._logger.context_path)

        # ── Pinned row (Single Run only) ───────────────────────────────────────
        # Full Run auto-claims rows sequentially; pinning only applies when the
        # user selects a specific script from the list.
        if self.selected_row_index is not None and self.script_name_filter:
            env["ORBIT_EXCEL_ROW_INDEX"] = str(self.selected_row_index)

        # ── Per-entry env overrides from run_sequence.yaml `env:` key ─────────
        entry_env: dict = entry.get("env") or {}
        if entry_env:
            env.update(entry_env)

        return env

    # ------------------------------------------------------------------ #
    # Process registry helpers (thread-safe)                              #
    # ------------------------------------------------------------------ #

    def _register_proc(self, script_name: str, proc: subprocess.Popen) -> None:
        """Register an active subprocess so request_abort() can kill it."""
        with self._procs_lock:
            self._active_procs[script_name] = proc

    def _unregister_proc(self, script_name: str) -> None:
        """Remove a completed subprocess from the active registry."""
        with self._procs_lock:
            self._active_procs.pop(script_name, None)

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def _resolve_script_path(self, relative_path: str) -> Path:
        """Resolve a path from tests.yaml relative to the yaml's parent directory."""
        return (self.tests_yaml_path.parent / relative_path).resolve()
