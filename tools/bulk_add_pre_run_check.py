#!/usr/bin/env python3
"""
bulk_add_pre_run_check.py
Adds pre_run_check(url) to every Orbit script under systems/ that does not
already have it.

Two cases are handled:
  A. Mini Regression scripts — already import from orbit_script_helpers.
     → Add 'pre_run_check' to the existing import list.
     → Insert `pre_run_check(url)` before `playwright.chromium.launch(`.

  B. PUV / all other scripts — only import from orbit_context.
     → Add `from orbit360.utils.orbit_script_helpers import pre_run_check` after the
       last orbit_context import line.
     → Insert `pre_run_check(url)` before `playwright.chromium.launch(`.

The first page.goto("https://...") inside run() is used as the URL.
"""

import re
import sys
from pathlib import Path

SYSTEMS_DIR = Path(__file__).resolve().parent.parent / "systems"


def extract_url(text: str) -> str | None:
    """Return the first https URL from page.goto() inside run()."""
    m = re.search(r'page\.goto\("\s*(https://[^"]+)"', text)
    if m:
        return m.group(1)
    return None


def patch_mini_regression(text: str, url: str) -> str:
    """
    Case A: already imports from orbit_script_helpers.
    1. Add pre_run_check to the helpers import block.
    2. Insert pre_run_check(url) call before playwright.chromium.launch.
    """
    # 1. Add to existing import if not present
    if "pre_run_check" not in text:
        # Find the helpers import block — it may span multiple lines
        # Pattern: from orbit360.utils.orbit_script_helpers import (
        def add_to_import(m):
            block = m.group(0)
            # Insert before closing paren or at end of inline import
            if ")" in block:
                # multi-line: insert before last )
                return block.rstrip().rstrip(")").rstrip() + ",\n    pre_run_check,\n)"
            else:
                # single-line: append
                return block.rstrip() + ", pre_run_check"

        text = re.sub(
            r"from core\.orbit_script_helpers import \([^)]+\)",
            add_to_import,
            text,
            flags=re.DOTALL,
        )

    # 2. Insert call before browser launch
    launch_pat = re.compile(r"( +)(browser = playwright\.chromium\.launch\()")
    def insert_call(m):
        indent = m.group(1)
        return f"{indent}pre_run_check(\"{url}\")\n{m.group(0)}"
    text = launch_pat.sub(insert_call, text, count=1)
    return text


def patch_puv(text: str, url: str) -> str:
    """
    Case B: no orbit_script_helpers import.
    1. Add import line after the last orbit_context import.
    2. Insert pre_run_check(url) call before playwright.chromium.launch.
    """
    # 1. Add import after orbit_context import block
    # Find end of the 'from orbit360.backend.orbit_context import (...)' block
    oc_import_re = re.compile(
        r"(from core\.orbit_context import \([^)]+\))",
        re.DOTALL,
    )
    m = oc_import_re.search(text)
    if m:
        insert_pos = m.end()
        new_import = "\nfrom orbit360.utils.orbit_script_helpers import pre_run_check"
        text = text[:insert_pos] + new_import + text[insert_pos:]
    else:
        # Fallback: add after last 'from core.' line
        lines = text.splitlines(keepends=True)
        last_core_idx = -1
        for i, line in enumerate(lines):
            if line.startswith("from core."):
                last_core_idx = i
        if last_core_idx >= 0:
            lines.insert(last_core_idx + 1, "from orbit360.utils.orbit_script_helpers import pre_run_check\n")
            text = "".join(lines)

    # 2. Insert call before browser launch
    launch_pat = re.compile(r"( +)(browser = playwright\.chromium\.launch\()")
    def insert_call(m):
        indent = m.group(1)
        return f"{indent}pre_run_check(\"{url}\")\n{m.group(0)}"
    text = launch_pat.sub(insert_call, text, count=1)
    return text


def process_file(path: Path) -> bool:
    """Return True if the file was modified."""
    text = path.read_text(encoding="utf-8")

    if "pre_run_check" in text:
        return False  # already patched

    url = extract_url(text)
    if not url:
        print(f"  SKIP (no URL found): {path.relative_to(SYSTEMS_DIR)}")
        return False

    if "playwright.chromium.launch" not in text:
        print(f"  SKIP (no launch): {path.relative_to(SYSTEMS_DIR)}")
        return False

    is_mini_regression = "orbit_script_helpers" in text

    if is_mini_regression:
        new_text = patch_mini_regression(text, url)
    else:
        new_text = patch_puv(text, url)

    if new_text == text:
        print(f"  WARN (no change made): {path.relative_to(SYSTEMS_DIR)}")
        return False

    path.write_text(new_text, encoding="utf-8")
    return True


def main():
    py_files = sorted(SYSTEMS_DIR.rglob("*.py"))
    py_files = [f for f in py_files if "__pycache__" not in f.parts]

    patched = []
    skipped = []

    for f in py_files:
        if process_file(f):
            patched.append(f)
            print(f"  OK: {f.relative_to(SYSTEMS_DIR)}")
        else:
            skipped.append(f)

    print(f"\nDone. Patched {len(patched)} files, skipped {len(skipped)} files.")


if __name__ == "__main__":
    main()
