"""
Interactive CLI wrapper around orbit360.utils.patient_generator.

Kept for headless / scripted use. The Genesis panel in the GUI calls the same
underlying function (``orbit360.utils.patient_generator.generate_patients``)
so output is identical regardless of entry point.

Usage:
    python tools/generate_patients.py
"""
from __future__ import annotations

import sys
from pathlib import Path

# Allow running this file directly from a clone without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orbit360.utils.patient_generator import (
    GENERATED_PATIENTS_DIR,
    detect_system,
    generate_patients,
    list_templates,
)


def _prompt_release() -> str:
    while True:
        value = input("Enter release (e.g., APRGR1.26): ").strip().upper()
        if value:
            return value


def _prompt_count() -> int:
    while True:
        try:
            value = int(input("How many patients per sheet? (e.g., 500): "))
            if value > 0:
                return value
        except ValueError:
            pass
        print("  Enter a positive integer.")


def _prompt_template() -> Path:
    templates = list_templates()
    if templates:
        print("\nAvailable templates:")
        for i, p in enumerate(templates, 1):
            print(f"  [{i}] {p.name}  ({detect_system(p)})")
        raw = input("Pick a number, or paste a path: ").strip()
        if raw.isdigit():
            idx = int(raw) - 1
            if 0 <= idx < len(templates):
                return templates[idx]
        return Path(raw)
    return Path(input("Enter input Excel filename: ").strip())


def main() -> None:
    template = _prompt_template()
    if not template.is_file():
        print(f"Template not found: {template}")
        sys.exit(1)

    release = _prompt_release()
    count   = _prompt_count()

    print("\n--- RUN SUMMARY ---")
    print(f"Template:  {template}")
    print(f"System:    {detect_system(template)}")
    print(f"Release:   {release}")
    print(f"Per sheet: {count}")
    print(f"Output:    {GENERATED_PATIENTS_DIR}")
    print("-------------------")

    if input("Proceed? (Y/N): ").strip().lower() != "y":
        print("Run cancelled.")
        return

    def _progress(sheet: str, done: int, total: int) -> None:
        if done == total:
            print(f"  done {sheet}: {done}/{total}")

    result = generate_patients(template, release, count, progress=_progress)
    print(f"\nGenerated {result.total_patients} patient(s) across {result.sheet_count} sheet(s)")
    print(f"Output:    {result.output_dir}")
    print(f"Log:       {result.log_file}")


if __name__ == "__main__":
    main()
