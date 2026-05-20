"""
orbit_context.py — Orbit360
Shared runtime for Playwright test scripts.

Replaces the ~115-line boilerplate block duplicated across every script.
Each script now only needs its four config constants and a short bootstrap
import to get the full logging / step-timing / screenshot / manual-prompt
infrastructure.

Usage in each script
--------------------
    import os, sys, time
    from pathlib import Path
    from playwright.sync_api import Playwright, sync_playwright, expect

    SYSTEM      = "CAC"
    ENVIRONMENT = "QA"
    PILLAR      = "ENT"
    RUN_TYPE    = "Full Regression"
    TEST_SET    = "CLI"          # optional — sub-suite name (e.g. CLI, ED, EMD)

    _env_root = os.environ.get("ORBIT_ROOT")
    if _env_root:
        sys.path.insert(0, _env_root)
    else:
        _p = Path(__file__).resolve().parent
        while not (_p / "orbit360").is_dir():
            if _p.parent == _p:
                raise RuntimeError("Could not locate Orbit project root.")
            _p = _p.parent
        sys.path.insert(0, str(_p))

    from orbit360.backend.orbit_context import (
        setup, step, end_step, section_break,
        screenshot, manual_prompt, handle_failure, format_duration,
        crs_frame, start_trace, save_trace,
        prompt_value, load_excel, write_excel_result,
        base_url,
    )

    ctx    = setup(SYSTEM, ENVIRONMENT, PILLAR, RUN_TYPE, TEST_SET)
    logger = ctx.logger
"""

from __future__ import annotations

import atexit
import json
import logging
import os
import sys
import time
import traceback as _traceback
from datetime import datetime
from pathlib import Path


class SkipStep(BaseException):
    """Raised by handle_failure() when the analyst chooses to skip the failed
    step and let automation continue.  Inherits from BaseException (not
    Exception) so the script's outer ``except Exception`` block does NOT catch
    it — it propagates past the outer handler and is caught only by an
    opt-in ``step_guard()`` context manager wrapping the step."""

# ── Log formatters ────────────────────────────────────────────────────────────

class _PlainFormatter(logging.Formatter):
    """
    Plain-text formatter for execution.log.
    Produces:  9:30:45 AM | INFO     | message
    12-hour time computed directly from datetime — avoids locale %p issues.
    No ANSI codes so the file is readable in any text editor.
    """

    def formatTime(self, record: logging.LogRecord, datefmt=None) -> str:
        dt   = datetime.fromtimestamp(record.created)
        hour = str(int(dt.strftime("%I")))           # drop leading zero, locale-safe
        ampm = "AM" if dt.hour < 12 else "PM"        # locale-independent
        return f"{hour}:{dt.strftime('%M:%S')} {ampm}"


class _ColorFormatter(logging.Formatter):
    """
    ANSI color formatter for the console StreamHandler.

    Behaviour differs by whether the stream is a live terminal or a pipe:

    TTY (direct terminal run)
        Section breaks  → blank line + bold bright-blue text + blank line
        Other messages  → ANSI-colored message only; no level prefix so
                          there is no duplicate timestamp or label clutter

    Pipe (GUI subprocess — workers.py captures stdout/stderr merged)
        Section breaks  → "LEVEL    | ─── TITLE ───"  (─ prefix signals _log_line_color)
        Other messages  → "LEVEL    | message"         (level parsed by _log_line_color)
        ANSI codes are NOT emitted; workers.py strips them anyway

    Level → ANSI color (TTY only):
        DEBUG    dim grey
        INFO     bright green
        WARNING  bright yellow
        ERROR    bright red
        CRITICAL bold magenta
    Section breaks: bold bright blue
    """

    _RESET = "\033[0m"

    # (level-name color, message color) — used in TTY mode
    _LEVEL_STYLE: dict[str, tuple[str, str]] = {
        "DEBUG":    ("\033[2;37m",  "\033[2;37m"),
        "INFO":     ("\033[1;92m",  "\033[92m"),
        "WARNING":  ("\033[1;93m",  "\033[93m"),
        "ERROR":    ("\033[1;91m",  "\033[91m"),
        "CRITICAL": ("\033[1;95m",  "\033[1;95m"),
    }

    def format(self, record: logging.LogRecord) -> str:
        import sys
        msg    = record.getMessage()
        is_tty = getattr(sys.stderr, "isatty", lambda: False)()

        # ── Section breaks (message starts with ─) ────────────────────────
        if msg.startswith("─"):
            if is_tty:
                # Leading \n gives a blank line before; handler appends \n after
                return f"\n\033[1;94m{msg}\033[0m"
            # Pipe: include level prefix so _log_line_color can detect "─" in msg
            return f"{record.levelname:<8} | {msg}"

        # ── Regular messages ───────────────────────────────────────────────
        if is_tty:
            # Terminal: colored message only — no level label, no timestamp
            _, msg_clr = self._LEVEL_STYLE.get(record.levelname, (self._RESET, self._RESET))
            return f"{msg_clr}{msg}{self._RESET}"
        # Pipe: plain "LEVEL    | message" — ANSI stripped by workers.py
        return f"{record.levelname:<8} | {msg}"


# ── Core context class ────────────────────────────────────────────────────────

class OrbitContext:
    def __init__(
        self,
        system: str,
        environment: str,
        pillar: str,
        run_type: str,
        test_set: str = "",
    ) -> None:
        self._current_step:     str | None   = None
        self._step_start_time:  float | None = None
        self._screenshot_counter: int        = 0

        # ── Resolve project root ──────────────────────────────────────────────
        _env_root = os.environ.get("ORBIT_ROOT")
        if _env_root:
            project_root = Path(_env_root)
        else:
            p = Path(__file__).resolve().parent
            while not (p / "orbit360").is_dir():
                if p.parent == p:
                    raise RuntimeError("Could not locate Orbit project root.")
                p = p.parent
            project_root = p

        self._project_root = project_root  # used by load_excel for relative paths

        # ── Resolve log / screenshot directories ─────────────────────────────
        _log_dir_env  = os.environ.get("ORBIT_LOG_DIR")
        _shot_dir_env = os.environ.get("ORBIT_SCREENSHOT_DIR")

        if _log_dir_env and _shot_dir_env:
            self.log_dir  = Path(_log_dir_env)
            self.shot_dir = Path(_shot_dir_env)
        else:
            timestamp = datetime.now().strftime("%Y-%m-%d_%I-%M-%S_%p")
            path_parts = [system, environment, pillar, run_type]
            if test_set:
                path_parts.append(test_set)
            base = project_root / "runs"
            for part in path_parts:
                base = base / part
            base = base / timestamp
            self.log_dir  = base / "logs"
            self.shot_dir = base / "screenshots"

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.shot_dir.mkdir(parents=True, exist_ok=True)

        # ── Logger ────────────────────────────────────────────────────────────
        self.logger = logging.getLogger("orbit")
        self.logger.setLevel(logging.DEBUG)
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        # File handler — full timestamped record, plain text, no ANSI
        fh = logging.FileHandler(self.log_dir / "execution.log", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(_PlainFormatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
        ))

        # Console handler — level + message only (no timestamp here; the GUI
        # adds its own left-column timestamp via LogEntryModel, and the
        # execution.log holds the full timestamped record for terminal runs)
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(_ColorFormatter())

        self.logger.addHandler(fh)
        self.logger.addHandler(ch)
        self.logger.debug("Run Started")

        # Phase timing (opt-in; saved to phases.json on process exit)
        self._phase_timings: dict[str, float] = {}
        self._current_phase: str | None = None
        self._phase_start: float | None = None
        atexit.register(self._save_phases)

    # ── Duration helpers ──────────────────────────────────────────────────────

    def format_duration(self, seconds: float) -> str:
        seconds = int(seconds)
        minutes, sec = divmod(seconds, 60)
        return f"{minutes} min {sec} sec" if minutes > 0 else f"{sec} sec"

    # ── Step timing ───────────────────────────────────────────────────────────

    def step(self, step_name: str, message: str) -> None:
        self._current_step    = step_name
        self._step_start_time = time.time()
        self.logger.info(message)

    def end_step(self) -> None:
        if self._step_start_time is not None:
            duration = time.time() - self._step_start_time
            self.logger.debug(
                f"Step duration | {self._current_step} | {self.format_duration(duration)}"
            )
        self._current_step    = None
        self._step_start_time = None

    # ── Phase timing (opt-in; aggregated across the run) ─────────────────────

    def begin_phase(self, name: str) -> None:
        """Start timing a named phase. Calling again auto-closes the previous phase."""
        if self._current_phase is not None:
            self.end_phase()
        self._current_phase = name
        self._phase_start   = time.time()
        self.logger.debug(f"Phase start | {name}")

    def end_phase(self) -> None:
        """Close the current phase and accumulate its elapsed time."""
        if self._current_phase and self._phase_start is not None:
            elapsed = time.time() - self._phase_start
            self._phase_timings[self._current_phase] = round(
                self._phase_timings.get(self._current_phase, 0.0) + elapsed, 3
            )
            self.logger.debug(
                f"Phase end | {self._current_phase} | {self.format_duration(elapsed)}"
            )
        self._current_phase = None
        self._phase_start   = None

    def _save_phases(self) -> None:
        """Flush any open phase and write phases.json to the script log directory."""
        if self._current_phase:
            self.end_phase()
        if not self._phase_timings:
            return
        try:
            (self.log_dir / "phases.json").write_text(
                json.dumps(self._phase_timings, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    # ── Section break ─────────────────────────────────────────────────────────

    def section_break(
        self,
        title: str | None = None,
        width: int = 60,
        pad_char: str = "─",
    ) -> None:
        """
        Emit a visual divider line to both the console and execution.log.

        Routes through logger.info() so the line appears in all handlers
        with consistent formatting.  The leading ─ character is the signal
        that _ColorFormatter (terminal) and _log_line_color (GUI) use to
        apply section-break colour (bold blue) instead of the INFO colour.

        Terminal output (TTY):   blank line + bold blue ─── TITLE ─── + blank line
        GUI log panel:           blue-coloured ─── TITLE ─── entry
        execution.log:           9:30:45 AM | INFO     | ─── TITLE ───
        """
        if not title:
            return
        inner     = f"  {title.upper()}  "
        total_pad = max(0, width - len(inner))
        left_pad  = total_pad // 2
        right_pad = total_pad - left_pad
        line      = pad_char * left_pad + inner + pad_char * right_pad
        self.logger.info(line)

    # ── Failure handling ──────────────────────────────────────────────────────

    def handle_failure(self, error: Exception, page=None) -> None:
        step_name = self._current_step or "unknown step"

        # ── 1. Build a filtered traceback (strip library/Playwright frames) ──
        _skip_markers = (
            "site-packages",
            "playwright",
            os.sep + "lib" + os.sep + "python",
            "importlib",
            "<frozen ",
        )
        raw_lines   = _traceback.format_exc().splitlines()
        user_frames = [
            ln for ln in raw_lines
            if not any(m in ln for m in _skip_markers)
        ]
        # Always keep the final error line (last non-empty line)
        error_line  = next((ln for ln in reversed(raw_lines) if ln.strip()), "")
        # Take up to last 6 user-land frame lines + the error line
        clean_lines = user_frames[-6:] + (
            [error_line] if error_line not in user_frames[-6:] else []
        )

        # ── 2. Log a clean, readable failure block ───────────────────────────
        self.logger.error("")
        self.logger.error("=" * 52)
        self.logger.error(f"  FAILED AT : {step_name}")
        self.logger.error(f"  ERROR     : {type(error).__name__}: {error}")
        self.logger.error("  " + "-" * 50)
        for ln in clean_lines:
            self.logger.error(f"  {ln}")
        self.logger.error("=" * 52)
        self.logger.error("")

        # ── 3. Screenshot ────────────────────────────────────────────────────
        if page:
            try:
                self.screenshot(page, "failure_state")
            except Exception:
                pass

        # ── 4. Recovery prompt — emit special marker so the GUI can show
        #       Skip Step / Manual Complete / Mark Failed buttons, then pause.
        print("ORBIT_FAILURE_RECOVERY", flush=True)
        try:
            self.manual_prompt(
                message=(
                    f"[FAILURE] Step: {step_name}\n"
                    f"Error: {type(error).__name__}: {error}\n\n"
                    "The browser is still open. Fix the issue manually, "
                    "then choose an outcome below."
                ),
                completion_note="Recovery prompt acknowledged",
            )
        except Exception:
            sys.exit(1)

        # ── 5. Three-way outcome ─────────────────────────────────────────────
        try:
            answer = self.prompt_value(
                "Outcome — s = skip this step & continue automation  "
                "| y = I manually completed all remaining steps  "
                "| n = mark as failed",
                default="n",
            ).strip().lower()
        except Exception:
            answer = "n"

        if answer == "s":
            self.logger.warning(f"Step skipped by analyst — attempting to continue automation")
            raise SkipStep(f"Analyst skipped: {step_name}")
        elif answer == "y":
            self.logger.warning("Run marked as MANUAL COMPLETE by analyst")
            sys.exit(2)
        else:
            self.logger.warning("Run marked as FAILED — no manual recovery")
            sys.exit(1)

    # ── Screenshot ────────────────────────────────────────────────────────────

    def screenshot(self, page, label: str, anchor: str | None = None) -> None:
        self._screenshot_counter += 1
        clean_label = label.replace(" ", "_").lower()
        file_path   = self.shot_dir / f"{self._screenshot_counter:02d}_{clean_label}.png"

        if anchor:
            try:
                page.locator(anchor).wait_for(state="visible", timeout=15000)
            except Exception:
                self.logger.debug(f"Anchor not found for {label}")

        try:
            page.bring_to_front()
            page.wait_for_timeout(300)
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            page.screenshot(path=str(file_path), full_page=True)
            self.logger.debug(f"Screenshot captured: {label}")
        except Exception as e:
            self.logger.warning(f"Screenshot failed: {label} | {e}")

    # ── CRS iframe shortcut ───────────────────────────────────────────────────

    def crs_frame(self, page):
        """
        Return the CRS inner content frame.

        Eliminates the repeated chain:
            page.locator("#crsOuterIframe")
                .content_frame
                .get_by_text("</body> </html>")
                .content_frame
        Usage in scripts:
            crs = crs_frame(page1)
            crs.get_by_role("button", name="Complete").click()
        """
        return (
            page.locator("#crsOuterIframe")
            .content_frame
            .get_by_text("</body> </html>")
            .content_frame
        )

    # ── Playwright trace helpers ───────────────────────────────────────────────
    # Gated behind the ORBIT_TRACE environment variable.
    # Scripts always call start_trace() / save_trace() so the plumbing stays
    # in place; when ORBIT_TRACE is absent or not "1" the calls are no-ops.
    # Set ORBIT_TRACE=1 in the shell (or in a .env) to activate recording.

    def start_trace(self, playwright_context) -> None:
        """Start a Playwright trace on the given BrowserContext (if ORBIT_TRACE=1)."""
        if os.environ.get("ORBIT_TRACE", "0") != "1":
            return
        try:
            playwright_context.tracing.start(screenshots=True, snapshots=True, sources=True)
            self.logger.debug("Trace recording started")
        except Exception as e:
            self.logger.warning(f"Could not start trace: {e}")

    def save_trace(self, playwright_context, label: str = "trace") -> None:
        """Stop and save the Playwright trace alongside screenshots (if ORBIT_TRACE=1)."""
        if os.environ.get("ORBIT_TRACE", "0") != "1":
            return
        clean      = label.replace(" ", "_").lower()
        trace_path = self.shot_dir / f"{clean}.zip"
        try:
            playwright_context.tracing.stop(path=str(trace_path))
            self.logger.info(f"Trace saved: {trace_path.name}")
        except Exception as e:
            self.logger.warning(f"Could not save trace: {e}")

    # ── Manual prompt ─────────────────────────────────────────────────────────

    def manual_prompt(
        self,
        message: str,
        completion_note: str = "Manual Step complete",
    ) -> None:
        self.logger.warning(f"MANUAL STEP REQUIRED: | {message}")
        print("\n" + "=" * 60)
        print("MANUAL STEP REQUIRED")
        print(message)
        print("=" * 60)
        print("Press ENTER once complete...")
        input()
        self.logger.info(completion_note)

    # ── Runtime value prompt ───────────────────────────────────────────────────

    @property
    def base_url(self) -> str:
        """
        Return the target environment base URL from ORBIT_BASE_URL.

        Set this in .env or the shell so scripts never hard-code an environment:

            # .env
            ORBIT_BASE_URL=https://qa.example.com

            # script
            page.goto(ctx.base_url + "/login")

        Returns an empty string when the variable is unset.
        """
        return os.environ.get("ORBIT_BASE_URL", "")

    def prompt_value(
        self,
        label: str,
        default: str | None = None,
    ) -> str:
        """
        Pause and ask the operator to type in a value.

        When running as an Orbit GUI subprocess (ORBIT_LOG_DIR is set), emits
        a protocol marker so workers.py can intercept it and pop up the
        OrbitInputDialog.  The GUI sends the entered value back via stdin and
        this method returns it.

        In plain terminal mode the existing interactive prompt is used instead.

        Usage:
            mrn  = prompt_value("Enter Patient MRN")
            date = prompt_value("Enter Procedure Date (MM/DD/YYYY)", default="01/01/2026")
        """
        self.logger.warning(f"INPUT REQUIRED: {label}")

        if os.environ.get("ORBIT_LOG_DIR"):
            # GUI subprocess mode — signal the GUI via stdout and block on stdin
            print(f"ORBIT_VALUE_REQUEST|{label}", flush=True)
            raw = input()  # workers.py shows the dialog; GUI sends the value here
        else:
            # Terminal / standalone mode — interactive fallback
            print("\n" + "=" * 60)
            print("  INPUT REQUIRED")
            print(f"  {label}")
            if default is not None:
                print(f"  (Press ENTER to use default: {default})")
            print("=" * 60)
            raw = input("  Value: ").strip()

        value = raw.strip() if raw else (default or "")
        self.logger.info(f"Value entered | {label} | {value!r}")
        return value

    # ── Excel data loader ─────────────────────────────────────────────────────

    def load_excel(
        self,
        path: str | Path,
        sheet: str | int = 0,
        run_flag_col: str | None = None,
    ) -> list[dict]:
        """
        Load an Excel workbook sheet and return every data row as a dict
        keyed by the column headers in row 1.  Empty cells become None.

        run_flag_col (optional): name of a column whose value must equal "Y"
        (case-insensitive) for the row to be included.  Rows where that cell
        is anything else (blank, "N", "Done", etc.) are silently skipped.
        This lets you control which patients/cases run without touching the script.

        Requires openpyxl:  pip install openpyxl

        Usage:
            # All rows
            rows = load_excel("test_data.xlsx")

            # Only rows where the "Run" column == "Y"
            rows = load_excel("test_data.xlsx", run_flag_col="Run")

            patient = rows[0]
            mrn     = patient["PatientMRN"]
            code    = patient["CPTCode"]
        """
        try:
            import openpyxl  # lazy import — only needed when caller uses this method
        except ImportError:
            raise RuntimeError(
                "openpyxl is required for load_excel. "
                "Install it with:  pip install openpyxl"
            )

        path = Path(path)
        if not path.is_absolute():
            path = self._project_root / path

        if not path.exists():
            raise FileNotFoundError(f"Excel file not found: {path}")

        wb = openpyxl.load_workbook(path, data_only=True)

        if isinstance(sheet, int):
            ws = wb.worksheets[sheet]
        else:
            if sheet not in wb.sheetnames:
                raise ValueError(
                    f"Sheet {sheet!r} not found. Available: {wb.sheetnames}"
                )
            ws = wb[sheet]

        rows = list(ws.iter_rows(values_only=True))
        if not rows:
            self.logger.warning(f"Excel file is empty: {path.name}")
            return []

        headers = [str(h) if h is not None else f"col_{i}" for i, h in enumerate(rows[0])]
        data    = [dict(zip(headers, row)) for row in rows[1:] if any(c is not None for c in row)]

        if run_flag_col is not None:
            if run_flag_col not in headers:
                raise ValueError(
                    f"run_flag_col {run_flag_col!r} not found in headers: {headers}"
                )
            before = len(data)
            data   = [r for r in data if str(r.get(run_flag_col) or "").strip().upper() == "Y"]
            self.logger.info(
                f"Run-flag filter | col: {run_flag_col!r} | "
                f"{len(data)} of {before} rows flagged to run"
            )

        self.logger.info(f"Excel loaded | {path.name} | sheet: {ws.title} | {len(data)} rows")
        return data

    # ── Single-row claim / release (dynamic pool) ─────────────────────────────

    def claim_excel_row(
        self,
        path: str | Path | None = None,
        sheet: str | int = 0,
        run_flag_col: str | None = None,
    ) -> tuple[dict, int]:
        """
        Atomically claim one available row from the Excel test data pool.

        path defaults to the ORBIT_EXCEL_PATH environment variable when not
        given.  The first unclaimed row is locked to this run so no other
        concurrent process can claim the same row.

        Returns (row_dict, row_index) on success or ({}, -1) when the pool is
        exhausted or the file is unavailable.

        Usage:
            row, idx = claim_excel_row()   # uses ORBIT_EXCEL_PATH from env
            if idx == -1:
                logger.info("No rows available — pool exhausted.")
                return
            mrn = row.get("PatientMRN")
            ...
            release_excel_row(idx, "PASS")
        """
        from orbit360.utils.excel_data_manager import claim_row

        if path is None:
            env_path = os.environ.get("ORBIT_EXCEL_PATH", "")
            if not env_path:
                self.logger.warning("claim_excel_row: no path given and ORBIT_EXCEL_PATH not set")
                return {}, -1
            path = Path(env_path)
        else:
            path = Path(path)
            if not path.is_absolute():
                path = self._project_root / path

        run_id = os.environ.get("ORBIT_RUN_ID", "")
        _forced = os.environ.get("ORBIT_EXCEL_ROW_INDEX")
        force_row_index = int(_forced) if _forced is not None else None
        row_index, row_dict = claim_row(
            path, run_id=run_id, sheet=sheet,
            run_flag_col=run_flag_col, force_row_index=force_row_index,
        )
        if row_index is None:
            return {}, -1
        return row_dict, row_index

    def release_excel_row(
        self,
        row_index: int,
        status: str,
        notes: str = "",
        path: str | Path | None = None,
        sheet: str | int = 0,
    ) -> None:
        """
        Mark a previously claimed row as done and write the result back to Excel.

        status should be one of: "PASS" | "FAIL" | "SKIP"  (case-insensitive).
        path defaults to ORBIT_EXCEL_PATH if not given.

        Usage:
            release_excel_row(idx, "PASS")
            release_excel_row(idx, "FAIL", notes=str(exception))
        """
        from orbit360.utils.excel_data_manager import release_row

        if path is None:
            env_path = os.environ.get("ORBIT_EXCEL_PATH", "")
            if not env_path:
                self.logger.warning("release_excel_row: no path given and ORBIT_EXCEL_PATH not set")
                return
            path = Path(env_path)
        else:
            path = Path(path)
            if not path.is_absolute():
                path = self._project_root / path

        release_row(path, row_index, status, notes, sheet)
        self.logger.info(
            f"Excel row released | row {row_index} | {status.upper()}"
            + (f" | {notes}" if notes else "")
        )

    # ── Excel result writer ───────────────────────────────────────────────────

    def write_excel_result(
        self,
        path: str | Path,
        row_index: int,
        status: str,
        notes: str = "",
        sheet: str | int = 0,
    ) -> None:
        """
        Write a test result back to the source Excel file for the given row.

        Finds or creates three columns at the end of the sheet:
            Result    — the status string  (e.g. "PASS", "FAIL", "SKIP")
            Notes     — optional detail    (e.g. error message, step that failed)
            Timestamp — ISO datetime of when the result was written

        row_index is 0-based, matching the list returned by load_excel.
        Excel row = row_index + 2  (row 1 is the header).

        Requires openpyxl:  pip install openpyxl

        Usage:
            rows = load_excel("test_data.xlsx", run_flag_col="Run")
            for i, patient in enumerate(rows):
                try:
                    # ... run test for patient ...
                    write_excel_result("test_data.xlsx", i, "PASS")
                except Exception as e:
                    write_excel_result("test_data.xlsx", i, "FAIL", notes=str(e))
        """
        try:
            import openpyxl
        except ImportError:
            raise RuntimeError(
                "openpyxl is required for write_excel_result. "
                "Install it with:  pip install openpyxl"
            )

        path = Path(path)
        if not path.is_absolute():
            path = self._project_root / path

        if not path.exists():
            raise FileNotFoundError(f"Excel file not found: {path}")

        wb = openpyxl.load_workbook(path)

        if isinstance(sheet, int):
            ws = wb.worksheets[sheet]
        else:
            if sheet not in wb.sheetnames:
                raise ValueError(
                    f"Sheet {sheet!r} not found. Available: {wb.sheetnames}"
                )
            ws = wb[sheet]

        # ── Locate or create result columns ──────────────────────────────────
        header_row  = [cell.value for cell in ws[1]]
        result_cols = {"Result": None, "Notes": None, "Timestamp": None}

        for col_idx, header in enumerate(header_row, start=1):
            if header in result_cols:
                result_cols[header] = col_idx

        next_col = len(header_row) + 1
        for col_name in ("Result", "Notes", "Timestamp"):
            if result_cols[col_name] is None:
                ws.cell(row=1, column=next_col, value=col_name)
                result_cols[col_name] = next_col
                next_col += 1

        # ── Write values  (row_index 0 → Excel row 2) ────────────────────────
        excel_row = row_index + 2
        ws.cell(row=excel_row, column=result_cols["Result"],    value=status)
        ws.cell(row=excel_row, column=result_cols["Notes"],     value=notes)
        ws.cell(row=excel_row, column=result_cols["Timestamp"], value=datetime.now().strftime("%Y-%m-%d %I:%M:%S %p"))

        wb.save(path)
        self.logger.info(f"Result written | row {row_index} | {status}" + (f" | {notes}" if notes else ""))


# ── Module-level active context + delegate functions ──────────────────────────
# Scripts import these directly so the calling convention inside run() is
# identical to the old boilerplate — no 'ctx.' prefix required.

_active: OrbitContext | None = None


def setup(
    system: str,
    environment: str,
    pillar: str,
    run_type: str,
    test_set: str = "",
) -> OrbitContext:
    """Initialise the shared runtime and return the context object."""
    global _active
    _active = OrbitContext(system, environment, pillar, run_type, test_set)
    return _active


def format_duration(seconds: float) -> str:
    return _active.format_duration(seconds)          # type: ignore[union-attr]


def step(step_name: str, message: str) -> None:
    _active.step(step_name, message)                 # type: ignore[union-attr]


def end_step() -> None:
    _active.end_step()                               # type: ignore[union-attr]


def begin_phase(name: str) -> None:
    _active.begin_phase(name)                        # type: ignore[union-attr]


def end_phase() -> None:
    _active.end_phase()                              # type: ignore[union-attr]


def section_break(
    title: str | None = None,
    width: int = 60,
    pad_char: str = "─",
) -> None:
    _active.section_break(title, width, pad_char)    # type: ignore[union-attr]


def handle_failure(error: Exception, page=None, fallback_page=None) -> None:
    """Call with the most specific page available.

    Scripts may pass two pages — handle_failure(e, page2, page1 or page) —
    and the first truthy one is used for the screenshot/recovery prompt.
    """
    _active.handle_failure(error, page or fallback_page)  # type: ignore[union-attr]


def screenshot(page, label: str, anchor: str | None = None) -> None:
    _active.screenshot(page, label, anchor)          # type: ignore[union-attr]


def manual_prompt(
    message: str,
    completion_note: str = "Manual Step complete",
) -> None:
    _active.manual_prompt(message, completion_note)  # type: ignore[union-attr]


def crs_frame(page):
    return _active.crs_frame(page)                   # type: ignore[union-attr]


def start_trace(playwright_context) -> None:
    _active.start_trace(playwright_context)          # type: ignore[union-attr]


def save_trace(playwright_context, label: str = "trace") -> None:
    _active.save_trace(playwright_context, label)    # type: ignore[union-attr]


def base_url() -> str:
    """Return ORBIT_BASE_URL env var, or empty string if unset."""
    return _active.base_url  # type: ignore[union-attr]


def prompt_value(label: str, default: str | None = None) -> str:
    return _active.prompt_value(label, default)      # type: ignore[union-attr]


def load_excel(
    path,
    sheet: str | int = 0,
    run_flag_col: str | None = None,
) -> list[dict]:
    return _active.load_excel(path, sheet, run_flag_col)  # type: ignore[union-attr]


def write_excel_result(
    path,
    row_index: int,
    status: str,
    notes: str = "",
    sheet: str | int = 0,
) -> None:
    _active.write_excel_result(path, row_index, status, notes, sheet)  # type: ignore[union-attr]


def claim_excel_row(
    path=None,
    sheet: str | int = 0,
    run_flag_col: str | None = None,
) -> tuple[dict, int]:
    return _active.claim_excel_row(path, sheet, run_flag_col)  # type: ignore[union-attr]


def release_excel_row(
    row_index: int,
    status: str,
    notes: str = "",
    path=None,
    sheet: str | int = 0,
) -> None:
    _active.release_excel_row(row_index, status, notes, path, sheet)  # type: ignore[union-attr]
