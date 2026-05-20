"""
base.py — Orbit360 Executor Framework
======================================
BaseExecutor provides the full subprocess runtime (char reader, ORBIT
protocol parsing, timeout, retry).  Subclasses only implement:

    can_handle(script_path, engine_hint) -> bool
    build_command(ctx)                  -> list[str]

The shared _run_once() method is identical for all engine types, so
all scripts — Python, PowerShell, UiPath — get the same stdin-detection,
timeout, and ORBIT protocol handling automatically.
"""

from __future__ import annotations

import queue
import re
import subprocess
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

_ANSI_ESCAPE = re.compile(r'\x1b\[[0-9;]*[mGKHF]')


@dataclass
class ExecutionContext:
    """
    Everything an executor needs to run one script.

    Callbacks decouple the executor from Qt signals — the RunWorker
    builds these lambdas so the executor emits nothing directly.

    Data-passing contract (env keys consumed by scripts):
        ORBIT_RUN_ID, ORBIT_LOG_DIR, ORBIT_SCREENSHOT_DIR,
        ORBIT_SCRIPT_NAME, ORBIT_SCRIPT_INDEX, ORBIT_SCRIPT_TOTAL,
        ORBIT_ROOT, ORBIT_CONTEXT_PATH,
        ORBIT_EXCEL_PATH, ORBIT_EXCEL_SHEET, ORBIT_EXCEL_ROW_INDEX
    All of these are pre-populated by RunWorker before the executor is
    called; executors must not add or remove ORBIT_* keys.
    """

    # Script identification
    script_path: Path
    script_name: str

    # Runtime environment — fully built by RunWorker before executor dispatch
    env: dict
    cwd: Path

    # Limits
    timeout_minutes: Optional[float]
    max_retries: int

    # Output callbacks (thread-safe — Qt queued connections handle delivery)
    on_output: Callable[[str], None]            # one stdout line
    on_manual_input: Callable[[str], None]      # stdin wait detected
    on_failure_recovery: Callable[[str], None]  # ORBIT_FAILURE_RECOVERY marker
    on_value_requested: Callable[[str], None]   # ORBIT_VALUE_REQUEST|field
    on_context_output: Callable[[str, str], None]  # ORBIT_OUTPUT|key=value

    # Lifecycle callbacks
    abort_flag: Callable[[], bool]              # returns True when user aborts
    register_proc: Callable[[subprocess.Popen], None]   # for kill-on-abort support
    unregister_proc: Callable[[], None]                  # cleanup after script ends


@dataclass
class ExecutionResult:
    """
    Raw output from a subprocess run, before OrbitLogger interprets it.

    exit_code == 0   → script signalled success
    exit_code != 0   → failure (OrbitLogger maps this to status="failed")
    exit_code == -1  → infrastructure error or abort (no retries attempted)
    error_message    → set when an OSError prevents the process from launching
    timed_out        → True when the script exceeded timeout_minutes
    """

    exit_code: int
    stdout_lines: list[str] = field(default_factory=list)
    error_message: Optional[str] = None
    timed_out: bool = False


class BaseExecutor(ABC):
    """
    Abstract base for all Orbit360 script executors.

    The execute() method drives the full lifecycle including retry.
    Subclasses implement can_handle() and build_command() only.
    """

    # ------------------------------------------------------------------ #
    # Subclass contract                                                    #
    # ------------------------------------------------------------------ #

    @abstractmethod
    def can_handle(self, script_path: Path, engine_hint: Optional[str]) -> bool:
        """Return True if this executor should handle the given script."""
        ...

    @abstractmethod
    def build_command(self, ctx: ExecutionContext) -> list[str]:
        """Return the argv list used to launch the script subprocess."""
        ...

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def execute(self, ctx: ExecutionContext) -> ExecutionResult:
        """
        Run the script with retry policy.

        Retries on non-zero exit code up to ctx.max_retries times.
        Stops immediately on abort, infrastructure OSError, or timeout.
        Accumulated stdout from all attempts is merged into the result.
        """
        all_stdout: list[str] = []

        for attempt in range(ctx.max_retries + 1):
            if ctx.abort_flag():
                return ExecutionResult(exit_code=-1, stdout_lines=all_stdout)

            if attempt > 0:
                ctx.on_output(
                    f"  ↺ Retry {attempt}/{ctx.max_retries} "
                    f"— {ctx.script_name} (3s delay)"
                )
                time.sleep(3)

            result = self._run_once(ctx)
            all_stdout.extend(result.stdout_lines)

            # Stop: success, infra error, timeout, or retries exhausted
            if (
                result.exit_code == 0
                or result.error_message
                or result.timed_out
                or attempt >= ctx.max_retries
            ):
                return ExecutionResult(
                    exit_code=result.exit_code,
                    stdout_lines=all_stdout,
                    error_message=result.error_message,
                    timed_out=result.timed_out,
                )

        return ExecutionResult(exit_code=-1, stdout_lines=all_stdout)

    # ------------------------------------------------------------------ #
    # Shared subprocess runner                                             #
    # ------------------------------------------------------------------ #

    def _run_once(self, ctx: ExecutionContext) -> ExecutionResult:
        """
        Single subprocess attempt.

        Reads stdout one character at a time so we can detect input()
        prompts that don't end with a newline.  Parses the ORBIT wire
        protocol inline and delegates each event to the appropriate
        ctx callback.
        """
        try:
            cmd = self.build_command(ctx)
        except OSError as exc:
            return ExecutionResult(exit_code=-1, error_message=str(exc))

        stdout_lines: list[str] = []
        return_code = -1
        attempt_start = time.monotonic()
        deadline = (
            attempt_start + ctx.timeout_minutes * 60
            if ctx.timeout_minutes else None
        )

        try:
            with subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=ctx.env,
                cwd=str(ctx.cwd),
            ) as proc:
                ctx.register_proc(proc)
                timed_out = False

                try:
                    # One char at a time so input() prompts (no trailing \n)
                    # are detected within _STDIN_WAIT seconds.
                    char_queue: queue.Queue = queue.Queue()

                    def _read_chars(stdout_pipe, q: queue.Queue) -> None:
                        try:
                            while True:
                                ch = stdout_pipe.read(1)
                                if not ch:
                                    break
                                q.put(ch)
                        finally:
                            q.put(None)  # EOF sentinel

                    threading.Thread(
                        target=_read_chars,
                        args=(proc.stdout, char_queue),
                        daemon=True,
                    ).start()

                    _STDIN_WAIT = 2.0
                    buf = ""
                    prompted = False

                    while True:
                        try:
                            ch = char_queue.get(timeout=_STDIN_WAIT)
                        except queue.Empty:
                            if deadline and time.monotonic() > deadline:
                                ctx.on_output(
                                    f"  [TIMEOUT] Script exceeded "
                                    f"{ctx.timeout_minutes}m limit — "
                                    "terminating process"
                                )
                                proc.kill()
                                timed_out = True
                                break
                            if proc.poll() is None and buf.strip() and not prompted:
                                prompted = True
                                ctx.on_manual_input(buf.strip())
                            continue

                        if ch is None:  # EOF
                            if buf:
                                stripped = _ANSI_ESCAPE.sub("", buf.rstrip())
                                if stripped:
                                    stdout_lines.append(stripped)
                                    ctx.on_output(stripped)
                            break

                        prompted = False
                        buf += ch

                        if ch == "\n":
                            stripped = _ANSI_ESCAPE.sub("", buf.rstrip())
                            buf = ""
                            if not stripped:
                                continue

                            # ── ORBIT wire protocol ─────────────────────
                            if stripped.startswith("ORBIT_OUTPUT|"):
                                kv = stripped[len("ORBIT_OUTPUT|"):]
                                key, _, val = kv.partition("=")
                                if key:
                                    ctx.on_context_output(key.strip(), val.strip())
                                continue

                            if stripped.startswith("ORBIT_VALUE_REQUEST|"):
                                field_label = stripped[len("ORBIT_VALUE_REQUEST|"):]
                                prompted = True
                                ctx.on_value_requested(field_label)
                                continue

                            if stripped == "ORBIT_FAILURE_RECOVERY":
                                ctx.on_failure_recovery(stripped)
                                continue
                            # ── Normal output ────────────────────────────

                            stdout_lines.append(stripped)
                            ctx.on_output(stripped)
                            if "Press ENTER" in stripped:
                                ctx.on_manual_input(stripped)

                    proc.wait()
                    return_code = proc.returncode

                finally:
                    ctx.unregister_proc()

            if timed_out:
                return ExecutionResult(
                    exit_code=-1,
                    stdout_lines=stdout_lines,
                    timed_out=True,
                )
            return ExecutionResult(exit_code=return_code, stdout_lines=stdout_lines)

        except OSError as exc:
            return ExecutionResult(
                exit_code=-1,
                stdout_lines=stdout_lines,
                error_message=str(exc),
            )
