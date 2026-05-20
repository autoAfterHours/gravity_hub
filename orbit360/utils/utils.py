from __future__ import annotations

import os

import json
from pathlib import Path
from typing import Optional

import yaml



def load_dotenv(start: "Path | None" = None) -> None:
    """
    Read a .env file from the project root and inject missing env vars into
    the current process.  Already-set shell vars are never overwritten.

    Called once at GUI startup (orbit360_gui.py) AND once inside each script
    subprocess (orbit_wrapper.py) so that every process — main GUI thread and
    worker subprocesses alike — sees the same environment.

    Supported syntax:
        KEY=value        KEY="value"       KEY='value'
        # comment line   (blank lines ignored)
    Inline comments are not supported.
    """
    import sys as _sys
    from pathlib import Path as _Path
    if start:
        root = _Path(start)
    elif getattr(_sys, "frozen", False):
        # Frozen exe: look for .env next to the executable, not inside the bundle.
        root = _Path(_sys.executable).parent
    else:
        root = _Path(__file__).resolve().parent.parent.parent
    dotenv = root / ".env"
    if not dotenv.is_file():
        return
    for raw in dotenv.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key   = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

def find_uirobot() -> str:
    """
    Locate UiRobot.exe, checking in priority order:

      1. ORBIT_UIROBOT_PATH env var   — explicit override (works for any layout)
      2. PATH lookup                  — if UiPath is on the system PATH
      3. %LOCALAPPDATA%\\UiPath\\app-*  — user-local versioned Studio installs
      4. Per-machine Studio installs  — Program Files (x64 then x86)
      5. Robot-only install           — Program Files\\UiPath\\Robot
      6. Fallback "UiRobot.exe"       — let the OS try at launch time

    No configuration needed for standard UiPath installations.
    """
    import glob
    import shutil

    explicit = os.environ.get("ORBIT_UIROBOT_PATH", "").strip()
    if explicit and Path(explicit).is_file():
        return explicit

    in_path = shutil.which("UiRobot.exe") or shutil.which("UiRobot")
    if in_path:
        return in_path

    candidates: list[str] = []

    local = os.environ.get("LOCALAPPDATA", "")
    if local:
        versioned = sorted(
            glob.glob(os.path.join(local, "UiPath", "app-*", "UiRobot.exe")),
            reverse=True,   # newest version first
        )
        candidates.extend(versioned)

    candidates += [
        r"C:\Program Files\UiPath\Studio\UiRobot.exe",
        r"C:\Program Files (x86)\UiPath\Studio\UiRobot.exe",
        r"C:\Program Files\UiPath\Robot\UiRobot.exe",
    ]

    for path in candidates:
        if Path(path).is_file():
            return path

    return "UiRobot.exe"   # last resort — OS PATH at subprocess launch time


def scan_subdirectories(parent: Path) -> list[str]:
    """
    Return sorted list of immediate subdirectory names under `parent`.
    Skips hidden directories (names beginning with '.') and non-directories.
    Returns an empty list if `parent` does not exist or is not a directory.
    """
    if not parent.is_dir():
        return []
    return sorted(
        entry.name
        for entry in parent.iterdir()
        if entry.is_dir()
        and not entry.name.startswith(".")
        and not (entry.name.startswith("__") and entry.name.endswith("__"))
    )


def _xaml_display_name(stem: str) -> str:
    """Convert a XAML filename stem to a readable display name."""
    return stem.replace("_", " ").replace("-", " ").title()


def _discover_xaml_entries(directory: Path) -> list[dict]:
    """
    Auto-discover UiPath workflows from a workflows/ subdirectory.

    Called when a run_sequence.yaml has type:uipath but no explicit sequence,
    or when the yaml is absent entirely and a workflows/ folder exists.
    Returns entries sorted by filename so the order is predictable.
    """
    workflows_dir = directory / "workflows"
    if not workflows_dir.is_dir():
        return []
    xamls = sorted(workflows_dir.glob("*.xaml"))
    return [
        {
            "name": _xaml_display_name(p.stem),
            "path": f"workflows/{p.name}",
            "tags": [],
            "env":  {},
            "type": "uipath",
        }
        for p in xamls
    ]


def load_tests_yaml(tests_yaml_path: Path) -> list[dict]:
    """
    Parse a test definition file and return a normalized list of script entries
    as ``[{"name": str, "path": str, "type": str, ...}, ...]``.

    Supports three formats:

    tests.yaml (legacy):
        scripts:
          - name: <display name>
            path: <path relative to file's parent>

    run_sequence.yaml — explicit sequence:
        sequence:
          - script: <filename>
            display: <display name>     # optional
            type: uipath                # optional; default "playwright"
            env:                        # optional per-entry env overrides
              KEY: value

    run_sequence.yaml — UiPath auto-discover (no sequence needed):
        type: uipath
        # All *.xaml files in workflows/ are loaded alphabetically.
        # Drop a new .xaml in the folder; it appears automatically.

    Returns empty list if file is missing, unreadable, or malformed.
    """
    if not tests_yaml_path.is_file():
        return []
    try:
        with tests_yaml_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            return []

        # tests.yaml format
        if "scripts" in data:
            scripts = data["scripts"]
            return [
                s for s in scripts
                if isinstance(s, dict) and "name" in s and "path" in s
            ]

        # Explicit run_sequence.yaml format
        if "sequence" in data:
            display_map = load_display_names(tests_yaml_path.parent / "display_names.json")
            result = []
            for entry in data.get("sequence", []):
                if not isinstance(entry, dict) or "script" not in entry:
                    continue
                script_file = entry["script"]
                display_name = entry.get(
                    "display",
                    display_map.get(script_file, Path(script_file).stem),
                )
                raw_tags = entry.get("tags") or []
                tags = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else ([str(raw_tags)] if raw_tags else [])
                raw_env = entry.get("env") or {}
                entry_env = {str(k): str(v) for k, v in raw_env.items()} if isinstance(raw_env, dict) else {}
                raw_repeat = entry.get("repeat", 1)
                repeat = raw_repeat if isinstance(raw_repeat, int) and raw_repeat >= 1 else 1
                result.append({"name": display_name, "path": script_file, "tags": tags, "env": entry_env, "type": entry.get("type", "playwright"), "repeat": repeat})
            return result

        # UiPath auto-discover: type:uipath with no sequence → scan workflows/
        if data.get("type") == "uipath":
            return _discover_xaml_entries(tests_yaml_path.parent)

        return []
    except Exception:
        return []


def load_test_data_config(tests_yaml_path: Path) -> dict | None:
    """
    Return the ``test_data:`` block from a run_sequence.yaml, or None if absent.

    Expected shape in YAML:
        test_data:
          path: "test_data/CAC/PreProd/Houston/patients.xlsx"
          sheet: 0           # optional — sheet index or name, default 0
          run_flag_col: "Run" # optional — only import rows where this col == "Y"

    ``path`` is resolved relative to ORBIT_DATA_DIR / test_data/ when not absolute.
    """
    if tests_yaml_path is None or not tests_yaml_path.is_file():
        return None
    try:
        with tests_yaml_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict):
            return None
        cfg = data.get("test_data")
        return cfg if isinstance(cfg, dict) else None
    except Exception:
        return None


def load_display_names(display_names_path: Path) -> dict[str, str]:
    """
    Load an optional display_names.json mapping raw filesystem names to
    human-readable labels shown in the GUI.

    JSON shape:
        { "HL7_ADT": "HL7 ADT Feed", "Smoke_Tests": "Smoke Tests" }

    Returns empty dict if file is absent or malformed.
    """
    if not display_names_path.is_file():
        return {}
    try:
        with display_names_path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def resolve_display_name(raw_name: str, display_map: dict[str, str]) -> str:
    """
    Return the human-readable label for `raw_name` if present in
    `display_map`, otherwise return `raw_name` unchanged.
    """
    return display_map.get(raw_name, raw_name)


def format_duration(seconds: float) -> str:
    """
    Convert a floating-point second count into a human-readable string.

    Examples:
        0.4   -> "0.4s"
        75.0  -> "1m 15s"
        3661  -> "1h 1m 1s"
    """
    seconds = max(0.0, seconds)
    if seconds < 60:
        return f"{seconds:.1f}s"
    minutes, secs = divmod(int(seconds), 60)
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours, mins = divmod(minutes, 60)
    return f"{hours}h {mins}m {secs}s"


if __name__ == "__main__":
    from orbit360.utils.paths import SYSTEMS_DIR

    print(f"Systems found: {scan_subdirectories(SYSTEMS_DIR)}")
    print(f"format_duration(0.4)   = {format_duration(0.4)}")
    print(f"format_duration(75)    = {format_duration(75)}")
    print(f"format_duration(3661)  = {format_duration(3661)}")