"""
orbit_logger.py — Orbit360 v4.0
Structured logging layer: run directories, per-script result.json,
and run_summary.json. No UI logic. No Qt imports.

Run directory layout
--------------------
orbit_data/runs/<System>_<Level0>_<Level1>_<YYYY-MM-DD_HH-MM-SS>/
    run_summary.json
    <Script_Name>/
        result.json
        output.log
        screenshots/
"""

from __future__ import annotations

import json
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from orbit360.utils.paths import ORBIT_DATA_DIR, RUNS_DIR


def _utc_now() -> str:
    """Return current UTC time as ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _make_run_id() -> str:
    """Generate a human-readable run ID: YYYY-MM-DD_HH-MM-SS."""
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def _slug(name: str) -> str:
    """
    Sanitize a display name for use as a filesystem folder component.

    Replaces any run of non-alphanumeric characters with a single
    underscore, then strips leading/trailing underscores.

    Examples:
        'Codefinder (CRS)'  → 'Codefinder_CRS'
        'Full Regression'   → 'Full_Regression'
        'QA'                → 'QA'
    """
    s = re.sub(r'[^\w]+', '_', name)
    return s.strip('_')


@dataclass
class ScriptResult:
    """Immutable record of a single script's execution outcome."""
    script_name: str
    script_path: str
    return_code: int
    stdout: str
    stderr: str
    started_at: str          # ISO-8601 UTC
    finished_at: str         # ISO-8601 UTC
    duration_seconds: float
    log_dir: str             # Absolute path to script output folder
    screenshot_dir: str      # Absolute path to screenshots folder
    status: str              # "passed" | "failed" | "manual_complete" | "error"


class OrbitLogger:
    """
    Manages directory structure and log files for a single test run.

    The run folder is a single flat directory whose name encodes the
    system, hierarchy selections, and timestamp — easy to browse without
    navigating deep nesting.

    Lifecycle:
        logger = OrbitLogger("CAC", ["QA", "ENT", "PUV"])
        logger.begin_run()
        log_dir, ss_dir = logger.prepare_script_dirs("Codefinder (CRS)")
        result = logger.record_script(...)
        summary_path = logger.finalize_run([result, ...])
    """

    def __init__(self, system_name: str, hierarchy: list[str] | None = None) -> None:
        self.system_name = system_name
        self.hierarchy: list[str] = hierarchy or []
        self._run_id: Optional[str] = None
        self._run_root: Optional[Path] = None
        self._run_start_time: Optional[float] = None
        self._run_started_at: Optional[str] = None
        self._context_data: Optional[dict] = None
        self._context_lock = threading.Lock()

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def begin_run(self) -> str:
        """
        Generate a timestamped run_id, create the flat run root directory,
        and record the wall-clock start time.

        Run root:
            RUNS_DIR / "<System>_<Level0>_<Level1>_<YYYY-MM-DD_HH-MM-SS>"

        Example:
            orbit_data/runs/CAC_QA_ENT_PUV_2026-02-28_14-43-00/

        Returns:
            The run_id string (e.g. "2026-02-28_14-43-00").
        """
        self._run_id = _make_run_id()

        # Build a single flat folder name from system + hierarchy + timestamp
        name_parts = [_slug(self.system_name)] + [_slug(h) for h in self.hierarchy]
        folder_name = "_".join(name_parts) + "_" + self._run_id

        self._run_root = RUNS_DIR / folder_name
        self._run_root.mkdir(parents=True, exist_ok=True)
        if os.environ.get("ORBIT_PRUNE_OLD_RUNS", "").strip().lower() in ("1", "true", "yes", "on"):
            self._prune_old_runs()
        self._run_start_time = time.monotonic()
        self._run_started_at = _utc_now()
        return self._run_id

    def prepare_script_dirs(self, script_name: str) -> tuple[Path, Path]:
        """
        Create and return the output directory and screenshots subfolder
        for one script.

        Layout:
            <run_root>/<Script_Name>/              ← log_dir (output.log + result.json)
            <run_root>/<Script_Name>/screenshots/  ← screenshot_dir

        Returns:
            (log_dir, screenshot_dir) as Path objects.

        Raises:
            RuntimeError: If begin_run() has not been called.
        """
        self._require_run()
        script_dir = self._run_root / _slug(script_name)
        screenshot_dir = script_dir / "screenshots"
        script_dir.mkdir(parents=True, exist_ok=True)
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        return script_dir, screenshot_dir

    def record_script(
        self,
        script_name: str,
        script_path: str,
        return_code: int,
        stdout: str,
        stderr: str,
        start_time: float,
        end_time: float,
        log_dir: Path,
        screenshot_dir: Path,
        started_at: Optional[str] = None,
    ) -> ScriptResult:
        """
        Build a ScriptResult and write result.json + output.log to log_dir.

        Status mapping:
            return_code == 0  -> "passed"
            return_code == 2  -> "manual_complete"  (analyst finished steps manually)
            return_code != 0  -> "failed"

        started_at: ISO-8601 UTC wall-clock time captured before the subprocess
            launched. If not provided, the current time is used as a fallback
            (which would be the finish time — callers should always supply this).
        """
        duration = end_time - start_time
        if return_code == 0:
            status = "passed"
        elif return_code == 2:
            status = "manual_complete"
        else:
            status = "failed"
        script_started_at = started_at or _utc_now()
        now_wall = _utc_now()

        result = ScriptResult(
            script_name=script_name,
            script_path=script_path,
            return_code=return_code,
            stdout=stdout,
            stderr=stderr,
            started_at=script_started_at,
            finished_at=now_wall,
            duration_seconds=round(duration, 3),
            log_dir=str(log_dir),
            screenshot_dir=str(screenshot_dir),
            status=status,
        )
        self._write_result_json(log_dir, result)
        self._write_log_file(log_dir, result)
        return result

    def record_failure(
        self,
        script_name: str,
        script_path: str,
        error_message: str,
        log_dir: Path,
        screenshot_dir: Path,
        started_at: Optional[str] = None,
    ) -> ScriptResult:
        """
        Record a script that failed to launch at all (e.g. FileNotFoundError).
        Writes result.json + output.log with status "error" and return_code -1.
        """
        now = _utc_now()
        result = ScriptResult(
            script_name=script_name,
            script_path=script_path,
            return_code=-1,
            stdout="",
            stderr=error_message,
            started_at=started_at or now,
            finished_at=now,
            duration_seconds=0.0,
            log_dir=str(log_dir),
            screenshot_dir=str(screenshot_dir),
            status="error",
        )
        self._write_result_json(log_dir, result)
        self._write_log_file(log_dir, result)
        return result

    def finalize_run(self, results: list[ScriptResult], aborted: bool = False) -> Path:
        """
        Write an aggregate run_summary.json to the run root directory
        and place a copy inside each script's folder.

        aborted: True when the user clicked Stop before all scripts completed.
            Recorded in run_summary.json so post-run tooling can distinguish
            a stopped run from a naturally completed one.

        Returns:
            Path to the written run_summary.json file.

        Raises:
            RuntimeError: If begin_run() has not been called.
        """
        self._require_run()
        elapsed = time.monotonic() - self._run_start_time
        finished_at = _utc_now()

        passed           = sum(1 for r in results if r.status == "passed")
        failed           = sum(1 for r in results if r.status == "failed")
        manual_complete  = sum(1 for r in results if r.status == "manual_complete")
        errored          = sum(1 for r in results if r.status == "error")

        summary = {
            "run_id":                 self._run_id,
            "system":                 self.system_name,
            "hierarchy":              self.hierarchy,
            "started_at":             self._run_started_at,
            "finished_at":            finished_at,
            "total_duration_seconds": round(elapsed, 3),
            "aborted":                aborted,
            "total_scripts":          len(results),
            "passed":                 passed,
            "failed":                 failed,
            "manual_complete":        manual_complete,
            "errored":                errored,
            "scripts": [
                {
                    "script_name":       r.script_name,
                    "status":            r.status,
                    "duration_seconds":  r.duration_seconds,
                    "return_code":       r.return_code,
                }
                for r in results
            ],
        }

        summary_content = json.dumps(summary, indent=2)

        summary_path = self._run_root / "run_summary.json"
        summary_path.write_text(summary_content, encoding="utf-8")
        self._update_run_history(summary_path, summary)
        self._write_html_report(summary, results)

        # Copy into each script folder so it's accessible alongside result.json
        for r in results:
            script_dir = self._run_root / _slug(r.script_name)
            if script_dir.is_dir():
                (script_dir / "run_summary.json").write_text(
                    summary_content, encoding="utf-8"
                )

        return summary_path

    def write_run_csvs(
        self,
        results: list[ScriptResult],
        script_entries: list[dict],
    ) -> None:
        """
        Write report_steps.csv and report_phases.csv to the run root.

        script_entries: list from load_tests_yaml — dicts with at least
        {"name": str, "type": str} — used to label each script as CAC or MTX.
        """
        if self._run_root is None or not results:
            return

        import csv
        import io

        type_map = {s["name"]: s.get("type", "playwright") for s in script_entries}

        # ── report_steps.csv ──────────────────────────────────────────────────
        steps_buf = io.StringIO()
        steps_writer = csv.DictWriter(steps_buf, fieldnames=[
            "script_name", "system", "status",
            "duration_seconds", "started_at", "finished_at", "return_code",
        ])
        steps_writer.writeheader()
        for r in results:
            system_label = "MTX" if type_map.get(r.script_name) == "uipath" else "CAC"
            steps_writer.writerow({
                "script_name":      r.script_name,
                "system":           system_label,
                "status":           r.status,
                "duration_seconds": r.duration_seconds,
                "started_at":       r.started_at,
                "finished_at":      r.finished_at,
                "return_code":      r.return_code,
            })
        (self._run_root / "report_steps.csv").write_text(
            steps_buf.getvalue(), encoding="utf-8"
        )

        # ── report_phases.csv — aggregate by system (CAC / MTX) ──────────────
        phase_totals: dict[str, dict] = {}
        for r in results:
            label = "MTX" if type_map.get(r.script_name) == "uipath" else "CAC"
            if label not in phase_totals:
                phase_totals[label] = {
                    "total_duration_seconds": 0.0,
                    "step_count":  0,
                    "pass_count":  0,
                    "fail_count":  0,
                }
            pt = phase_totals[label]
            pt["total_duration_seconds"] = round(
                pt["total_duration_seconds"] + (r.duration_seconds or 0.0), 3
            )
            pt["step_count"] += 1
            if r.status in ("passed", "manual_complete"):
                pt["pass_count"] += 1
            else:
                pt["fail_count"] += 1

            # Merge per-script phase timings from orbit_context begin_phase/end_phase
            phases_file = Path(r.log_dir) / "phases.json"
            if phases_file.is_file():
                try:
                    sub = json.loads(phases_file.read_text(encoding="utf-8"))
                    for phase_name, dur in sub.items():
                        sub_key = f"{label}.{phase_name}"
                        if sub_key not in phase_totals:
                            phase_totals[sub_key] = {
                                "total_duration_seconds": 0.0,
                                "step_count": 0,
                                "pass_count": 0,
                                "fail_count": 0,
                            }
                        phase_totals[sub_key]["total_duration_seconds"] = round(
                            phase_totals[sub_key]["total_duration_seconds"] + dur, 3
                        )
                        phase_totals[sub_key]["step_count"] += 1
                except Exception:
                    pass

        if phase_totals:
            phases_buf = io.StringIO()
            phases_writer = csv.DictWriter(phases_buf, fieldnames=[
                "phase", "total_duration_seconds", "step_count", "pass_count", "fail_count",
            ])
            phases_writer.writeheader()
            for phase_label, data in phase_totals.items():
                phases_writer.writerow({"phase": phase_label, **data})
            (self._run_root / "report_phases.csv").write_text(
                phases_buf.getvalue(), encoding="utf-8"
            )

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #

    @property
    def run_id(self) -> Optional[str]:
        return self._run_id

    @property
    def run_root(self) -> Optional[Path]:
        return self._run_root

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #


    def _prune_old_runs(self, keep: int = 25) -> None:
        """
        Delete the oldest run folders under RUNS_DIR when the total exceeds
        *keep*.  Uses mtime for ordering so the most recently created runs
        are always preserved.  Errors are silently ignored so a cleanup
        failure never aborts a run.
        """
        try:
            folders = sorted(
                (d for d in RUNS_DIR.iterdir() if d.is_dir()),
                key=lambda d: d.stat().st_mtime,
            )
            for old in folders[:max(0, len(folders) - keep)]:
                try:
                    shutil.rmtree(old)
                except OSError as exc:
                    import logging as _log
                    _log.getLogger(__name__).warning(
                        "Could not delete old run folder %s: %s", old.name, exc
                    )
        except Exception:
            pass

    def _update_run_history(
        self, summary_path: Path, summary: dict, keep: int = 20
    ) -> None:
        """
        Append a structured entry for this run to orbit_data/run_history.json,
        keeping only the *keep* most recent.  Each entry carries enough
        metadata for a quick overview without reading the full summary file:

            {
                "run_id":       "20260306_142301",
                "system":       "CAC",
                "hierarchy":    ["QA", "ENT"],
                "started_at":   "2026-03-06T14:23:01Z",
                "total_scripts": 12,
                "passed":       11,
                "failed":        1,
                "errored":       0,
                "aborted":      false,
                "summary_path": "/abs/path/to/run_summary.json"
            }

        Old plain-string entries from previous versions are migrated to
        {"summary_path": <value>} objects so the file stays consistent.
        Errors are silently ignored so a history write never aborts a run.
        """
        history_file = ORBIT_DATA_DIR / "run_history.json"
        try:
            if history_file.is_file():
                raw = json.loads(history_file.read_text(encoding="utf-8"))
                # Migrate any legacy plain-string entries
                history: list[dict] = [
                    e if isinstance(e, dict) else {"summary_path": e}
                    for e in raw
                ]
            else:
                history = []

            history.append(
                {
                    "run_id":         summary.get("run_id", ""),
                    "system":         summary.get("system", ""),
                    "hierarchy":      summary.get("hierarchy", []),
                    "started_at":     summary.get("started_at", ""),
                    "total_scripts":  summary.get("total_scripts", 0),
                    "passed":         summary.get("passed", 0),
                    "failed":         summary.get("failed", 0),
                    "errored":        summary.get("errored", 0),
                    "aborted":        summary.get("aborted", False),
                    "summary_path":   str(summary_path),
                }
            )
            history = history[-keep:]
            history_file.write_text(json.dumps(history, indent=2), encoding="utf-8")
        except Exception:
            pass


    def _write_html_report(self, summary: dict, results: list) -> None:
        """
        Write a self-contained HTML run report alongside run_summary.json.

        run_report.html has no external dependencies (all CSS is inline) so it
        opens correctly from any filesystem path.  Sections:
          • Header: system, hierarchy, run ID, timestamps, total duration
          • Pass-rate progress bar
          • Summary badges (passed / failed / errored)
          • Per-script <details> panels with coloured stdout and screenshots
        """
        import html as _html

        try:
            run_root = self._run_root
            if run_root is None:
                return

            def _dur(seconds) -> str:
                if seconds is None:
                    return "—"
                m, s = divmod(int(seconds), 60)
                return f"{m}:{s:02d}" if m else f"0:{s:02d}"

            def _line_color(line: str) -> str:
                """Replicate the GUI's _log_line_color() for HTML rendering."""
                parts    = line.split("|", 1)
                level    = parts[0].strip().upper()
                msg_part = parts[1].strip() if len(parts) > 1 else ""
                if msg_part.startswith("─"):
                    return "#89b4fa"
                if "Total Run Duration" in msg_part or msg_part == "Run Started":
                    return "#89b4fa"
                if level in ("ERROR", "CRITICAL") or "SCRIPT FAILED" in line:
                    return "#f38ba8"
                if level == "WARNING" or "MANUAL STEP" in line:
                    return "#fab387"
                if level == "INFO":
                    return "#a6e3a1"
                if level == "DEBUG":
                    return "#6c7086"
                return "#a6adc8"

            STATUS_ICON  = {"passed": "✓", "failed": "✗", "error": "⚠"}
            STATUS_COLOR = {"passed": "#a6e3a1", "failed": "#f38ba8", "error": "#fab387"}
            STATUS_BG    = {"passed": "#1e3a2a", "failed": "#3a1e1e", "error": "#3a2a1e"}

            hier        = " → ".join(summary.get("hierarchy", [])) or "(root)"
            total_dur   = _dur(summary.get("total_duration_seconds"))
            passed      = summary.get("passed",  0)
            failed      = summary.get("failed",  0)
            errored     = summary.get("errored", 0)
            total       = passed + failed + errored
            aborted     = summary.get("aborted", False)
            pass_pct    = round(passed  / total * 100) if total else 0
            fail_pct    = round((failed + errored) / total * 100) if total else 0

            # ── Per-script detail panels ───────────────────────────────────
            script_panels = ""
            for r in results:
                status  = getattr(r, "status", "error")
                scolor  = STATUS_COLOR.get(status, "#cdd6f4")
                sbg     = STATUS_BG.get(status, "#1e1e2e")
                icon    = STATUS_ICON.get(status, "?")
                dur_str = _dur(getattr(r, "duration_seconds", None))

                # Colour each stdout line
                stdout_raw   = getattr(r, "stdout", "") or ""
                coloured_log = ""
                for line in stdout_raw.splitlines():
                    col  = _line_color(line)
                    safe = _html.escape(line)
                    coloured_log += (
                        f'<span style="color:{col}">{safe}</span>\n'
                    )

                # Screenshots (relative paths from run_root)
                screenshots_html = ""
                script_dir = run_root / _slug(r.script_name)
                ss_dir     = script_dir / "screenshots"
                if ss_dir.is_dir():
                    pngs = sorted(ss_dir.glob("*.png"))
                    if pngs:
                        thumbs = ""
                        for png in pngs:
                            rel = png.relative_to(run_root)
                            thumbs += (
                                f'<a href="{rel}" target="_blank" title="{png.name}">'
                                f'<img src="{rel}" alt="{_html.escape(png.name)}" '
                                f'style="height:90px;border-radius:4px;'
                                f'border:1px solid #313244;object-fit:contain;'
                                f'background:#181825;cursor:pointer">'
                                f'</a>'
                            )
                        screenshots_html = (
                            f'<div style="display:flex;flex-wrap:wrap;gap:6px;'
                            f'margin-top:10px;padding:8px;background:#181825;'
                            f'border-radius:6px">{thumbs}</div>'
                        )

                open_attr = ' open' if status != "passed" else ''
                script_panels += f"""
<details{open_attr} style="margin-bottom:8px;border-radius:6px;overflow:hidden">
  <summary style="display:flex;align-items:center;gap:10px;padding:10px 14px;
                  background:{sbg};cursor:pointer;user-select:none;list-style:none">
    <span style="color:{scolor};font-size:1.1rem;font-weight:700">{icon}</span>
    <span style="font-weight:600;color:#cdd6f4;flex:1">{_html.escape(r.script_name)}</span>
    <span style="color:{scolor};font-size:.85rem;font-weight:600">{status.upper()}</span>
    <span style="color:#6c7086;font-size:.8rem;margin-left:12px">{dur_str}</span>
  </summary>
  <div style="padding:12px 14px;background:#1e1e2e">
    <pre style="margin:0;font-family:'Fira Code',monospace;font-size:.8rem;
                line-height:1.5;white-space:pre-wrap;word-break:break-all">{coloured_log.rstrip()}</pre>
    {screenshots_html}
  </div>
</details>"""

            # ── Full HTML ─────────────────────────────────────────────────
            aborted_banner = (
                '<div style="background:#3a2a1e;color:#fab387;padding:8px 14px;'
                'border-radius:6px;margin-bottom:12px;font-weight:600">'
                '⚠ Run was aborted before all scripts completed.</div>'
            ) if aborted else ""

            report_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Orbit360 — {_html.escape(summary.get('run_id', 'Run Report'))}</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box }}
  body   {{ font-family: system-ui, sans-serif; background: #11111b;
            color: #cdd6f4; margin: 0; padding: 1.5rem 2rem }}
  h1     {{ font-size: 1.25rem; margin: 0 0 .25rem; color: #89b4fa; font-weight: 700 }}
  .run-id{{ font-size: .75rem; color: #6c7086; margin-bottom: 1.25rem }}
  .meta  {{ display: grid; grid-template-columns: max-content 1fr;
            gap: .2rem 1rem; font-size: .8rem; margin-bottom: 1.25rem }}
  .meta .k {{ color: #6c7086 }}
  .pbar-wrap{{ background: #313244; border-radius: 99px; height: 8px;
               margin-bottom: 1rem; overflow: hidden }}
  .pbar-pass{{ background: #a6e3a1; height: 100%; float: left;
               border-radius: 99px 0 0 99px; width: {pass_pct}% }}
  .pbar-fail{{ background: #f38ba8; height: 100%; float: left;
               width: {fail_pct}% }}
  .badges{{ display: flex; gap: .75rem; margin-bottom: 1.25rem; flex-wrap: wrap }}
  .badge {{ padding: .3rem .9rem; border-radius: .4rem; font-weight: 700;
            font-size: .9rem }}
  .b-pass{{ background: #1e3a2a; color: #a6e3a1 }}
  .b-fail{{ background: #3a1e1e; color: #f38ba8 }}
  .b-err {{ background: #3a2a1e; color: #fab387 }}
  details summary::-webkit-details-marker {{ display: none }}
  details[open] summary {{ border-bottom: 1px solid #313244 }}
</style>
</head>
<body>
<h1>Orbit360 Run Report</h1>
<div class="run-id">{_html.escape(summary.get('run_id', ''))}</div>

<div class="meta">
  <span class="k">System</span>    <span>{_html.escape(summary.get('system',''))}</span>
  <span class="k">Hierarchy</span> <span>{_html.escape(hier)}</span>
  <span class="k">Started</span>   <span>{summary.get('started_at','')}</span>
  <span class="k">Finished</span>  <span>{summary.get('finished_at','')}</span>
  <span class="k">Duration</span>  <span>{total_dur}</span>
</div>

<div class="pbar-wrap"><div class="pbar-pass"></div><div class="pbar-fail"></div></div>

<div class="badges">
  <span class="badge b-pass">✓ {passed} Passed</span>
  <span class="badge b-fail">✗ {failed} Failed</span>
  <span class="badge b-err">⚠ {errored} Errored</span>
</div>

{aborted_banner}
{script_panels}
</body>
</html>"""

            (run_root / "run_report.html").write_text(report_html, encoding="utf-8")
        except Exception:
            pass

    # ── context.json ──────────────────────────────────────────────────────────

    @property
    def context_path(self) -> Optional[Path]:
        return (self._run_root / "context.json") if self._run_root else None

    def write_context_json(
        self,
        all_scripts: list[dict],
        excel_path: str = "",
        status: str = "running",
    ) -> None:
        """Write initial context.json at the start of a run (called from main thread)."""
        if self._run_root is None:
            return
        self._context_data = {
            "run_id":      self._run_id,
            "started_at":  self._run_started_at,
            "finished_at": None,
            "status":      status,
            "system":      self.system_name,
            "hierarchy":   self.hierarchy,
            "excel_path":  excel_path,
            "scripts": [
                {
                    "name":             s["name"],
                    "path":             s["path"],
                    "status":           "pending",
                    "started_at":       None,
                    "finished_at":      None,
                    "duration_seconds": None,
                    "return_code":      None,
                }
                for s in all_scripts
            ],
            "outputs": {},
        }
        self._flush_context()

    def update_context_script(self, script_name: str, result: "ScriptResult") -> None:
        """Update one script's entry after it completes (thread-safe)."""
        if self._context_data is None:
            return
        with self._context_lock:
            for entry in self._context_data["scripts"]:
                if entry["name"] == script_name:
                    entry["status"]           = result.status
                    entry["started_at"]       = result.started_at
                    entry["finished_at"]      = result.finished_at
                    entry["duration_seconds"] = result.duration_seconds
                    entry["return_code"]      = result.return_code
                    break
            self._flush_context()

    def set_context_output(self, key: str, value: str) -> None:
        """Store a cross-job output value and flush immediately (thread-safe)."""
        if self._context_data is None:
            return
        with self._context_lock:
            self._context_data["outputs"][key] = value
            self._flush_context()

    def finalize_context(self, status: str) -> None:
        """Set final run status and timestamp (called from main thread after all scripts)."""
        if self._context_data is None:
            return
        self._context_data["status"]      = status
        self._context_data["finished_at"] = _utc_now()
        self._flush_context()

    def _flush_context(self) -> None:
        """Write _context_data to context.json. Caller must hold _context_lock if threaded."""
        if self._run_root is None or self._context_data is None:
            return
        try:
            (self._run_root / "context.json").write_text(
                json.dumps(self._context_data, indent=2), encoding="utf-8"
            )
        except Exception:
            pass

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _require_run(self) -> None:
        if self._run_id is None:
            raise RuntimeError("begin_run() must be called before this method.")

    @staticmethod
    def _write_result_json(script_dir: Path, result: ScriptResult) -> None:
        (script_dir / "result.json").write_text(
            json.dumps(asdict(result), indent=2), encoding="utf-8"
        )

    @staticmethod
    def _write_log_file(script_dir: Path, result: ScriptResult) -> None:
        """Write a human-readable output.log directly into the script folder."""
        header = "\n".join([
            f"Script:   {result.script_name}",
            f"Path:     {result.script_path}",
            f"Started:  {result.started_at}",
            f"Finished: {result.finished_at}",
            f"Status:   {result.status.upper()}",
            f"Duration: {result.duration_seconds}s",
            f"Exit:     {result.return_code}",
            "-" * 60,
            "",
        ])
        body = result.stdout or ""
        if result.stderr:
            body += f"\n\nSTDERR:\n{result.stderr}"
        (script_dir / "output.log").write_text(header + body, encoding="utf-8")


if __name__ == "__main__":
    import time as _time

    logger = OrbitLogger("CAC", ["QA", "ENT", "PUV"])
    run_id = logger.begin_run()
    print(f"Run ID:   {run_id}")
    print(f"Run root: {logger.run_root}")

    log_dir, ss_dir = logger.prepare_script_dirs("Codefinder (CRS)")
    print(f"Log dir:        {log_dir}")
    print(f"Screenshot dir: {ss_dir}")

    t0 = _time.monotonic()
    _time.sleep(0.05)
    t1 = _time.monotonic()

    result = logger.record_script(
        script_name="Codefinder (CRS)",
        script_path="entqa_app3.py",
        return_code=0,
        stdout="All steps passed",
        stderr="",
        start_time=t0,
        end_time=t1,
        log_dir=log_dir,
        screenshot_dir=ss_dir,
    )
    print(f"Script status: {result.status}")

    summary = logger.finalize_run([result])
    print(f"Summary: {summary}")
    print("Logger test passed.")
