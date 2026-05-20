"""
migrate_scripts_to_orbit360.py
================================
One-shot migration tool: updates systems/ scripts written against the
old `core.*` package layout to the new `orbit360.*` package layout.

Run from the project root:
    python tools/migrate_scripts_to_orbit360.py

What it fixes
-------------
1. Import paths:
       from core.orbit_context        → from orbit360.backend.orbit_context
       from core.orbit_script_helpers → from orbit360.utils.orbit_script_helpers
       from core.orbit_frames         → from orbit360.utils.orbit_frames
       (and all other core.* → orbit360.* mappings)

2. Old bootstrap sentinel walk:
       while _p.name.lower() not in ("orbit360", ...):
           _p = _p.parent
   → containment check that correctly finds the project root:
       _p = Path(__file__).resolve().parent
       while not (_p / "orbit360").is_dir():
           _p = _p.parent

Safe to re-run — files are only written when changes are detected.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# ── Project root ──────────────────────────────────────────────────────────────
_ROOT = Path(__file__).resolve().parent.parent
_SYSTEMS = _ROOT / "systems"

if not _SYSTEMS.exists():
    sys.exit(f"ERROR: systems/ directory not found at {_SYSTEMS}")

# ── Import mapping ────────────────────────────────────────────────────────────
IMPORT_MAP = {
    "core.orbit_context":          "orbit360.backend.orbit_context",
    "core.orbit_script_helpers":   "orbit360.utils.orbit_script_helpers",
    "core.orbit_frames":           "orbit360.utils.orbit_frames",
    "core.orbit_logger":           "orbit360.orbit_logger",
    "core.orbit_runtime":          "orbit360.backend.orbit_runtime",
    "core.orbit_report":           "orbit360.utils.orbit_report",
    "core.orbit_health":           "orbit360.utils.orbit_health",
    "core.orbit_retry":            "orbit360.utils.orbit_retry",
    "core.paths":                  "orbit360.utils.paths",
    "core.utils":                  "orbit360.utils.utils",
    "core.executors.base":         "orbit360.executors.base",
    "core.executors.registry":     "orbit360.executors.registry",
}

# ── Old sentinel patterns to replace ─────────────────────────────────────────
# Matches the old while-loop that searched for a directory BY NAME.
# Captures optional tuple of names like ("orbit360",) or ("orbit360_v3.0", "orbit_hub")
_SENTINEL_RE = re.compile(
    r'(_p\s*=\s*Path\(__file__\)\.resolve\(\)\n)'
    r'(\s*)while\s+_p\.name\.lower\(\)\s+not\s+in\s+\(.*?\):\s*\n'
    r'(\s*if\s+_p\.parent\s*==\s*_p:\s*\n'
    r'\s+raise\s+RuntimeError\([^\n]+\)\n)'
    r'(\s*_p\s*=\s*_p\.parent\n)',
    re.MULTILINE,
)

_SENTINEL_REPLACEMENT = (
    r'_p = Path(__file__).resolve().parent\n'
    r'\2while not (_p / "orbit360").is_dir():\n'
    r'\3'
    r'\4'
)


def _fix_file(path: Path) -> bool:
    """Apply all fixes to one file. Returns True if file was changed."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"  SKIP  {path.relative_to(_ROOT)} — read error: {exc}")
        return False

    original = text

    # 1. Fix import paths (longest-match first to avoid partial replacements)
    for old, new in sorted(IMPORT_MAP.items(), key=lambda x: -len(x[0])):
        text = text.replace(old, new)

    # 2. Fix old bootstrap sentinel walk
    text = _SENTINEL_RE.sub(_SENTINEL_REPLACEMENT, text)

    if text == original:
        return False

    path.write_text(text, encoding="utf-8")
    return True


def main() -> None:
    py_files = sorted(_SYSTEMS.rglob("*.py"))
    if not py_files:
        print("No .py files found under systems/ — nothing to do.")
        return

    changed: list[Path] = []
    skipped: list[Path] = []

    for path in py_files:
        if _fix_file(path):
            changed.append(path)
        else:
            skipped.append(path)

    print(f"\nMigration complete.")
    print(f"  Updated : {len(changed)} file(s)")
    print(f"  No-op   : {len(skipped)} file(s)")

    if changed:
        print("\nUpdated files:")
        for p in changed:
            print(f"  {p.relative_to(_ROOT)}")


if __name__ == "__main__":
    main()
