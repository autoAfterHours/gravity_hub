"""
paths.py — Orbit360
Single source of truth for all directory constants.
Every other module imports from here; nothing is computed elsewhere.

Frozen-mode support (PyInstaller):
  - _IS_FROZEN = True when running as a packaged .exe
  - _RESOURCE_BASE: where bundled read-only files live (qml/, systems/, etc.)
      → sys._MEIPASS  (the extracted bundle directory)
  - BASE_DIR: where writable user data lives (orbit_data/, .env)
      → directory containing the .exe itself
  In development mode both roots are the project root derived from __file__.
"""

import sys
from pathlib import Path

# ── Frozen vs. dev mode ────────────────────────────────────────────────────────
_IS_FROZEN: bool = getattr(sys, "frozen", False)

if _IS_FROZEN:
    # Running as a PyInstaller bundle.
    # sys._MEIPASS  → extracted bundle (_internal/ for --onedir, temp dir for --onefile)
    # sys.executable → the actual .exe file
    _RESOURCE_BASE: Path = Path(sys._MEIPASS)          # bundled read-only assets
    BASE_DIR: Path = Path(sys.executable).parent        # writable root next to .exe
else:
    # Development: derive everything from this file's location.
    # orbit360/utils/paths.py → go up two levels to reach the project root.
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    _RESOURCE_BASE: Path = BASE_DIR

# ── Directory constants ────────────────────────────────────────────────────────

# Where system directories live (CAC/, Meditech_Expanse/, etc.)
# In frozen mode, prefer a sidecar systems/ directory placed next to the exe
# over the read-only bundled copy inside _internal/.  This lets the script
# library be updated (e.g. via git pull) without rebuilding the exe.
if _IS_FROZEN:
    _sidecar_systems = BASE_DIR / "systems"
    SYSTEMS_DIR: Path = _sidecar_systems if _sidecar_systems.exists() else _RESOURCE_BASE / "systems"
else:
    SYSTEMS_DIR: Path = _RESOURCE_BASE / "systems"

# Runtime data root — always next to the exe / project root.
# orbit_data/ is intentionally excluded from the repo so each install starts fresh.
ORBIT_DATA_DIR: Path = BASE_DIR / "orbit_data"

# Unified run output tree:
#   orbit_data/runs/<system>/<...hierarchy...>/<run_id>/
#       run_summary.json
#       <script_name>/
#           result.json
#           logs/
#           screenshots/
RUNS_DIR: Path = ORBIT_DATA_DIR / "runs"

# Default root for Excel test data files (user-managed, not in repo).
# run_sequence.yaml paths like "test_data/CAC/PreProd/Houston/patients.xlsx"
# are resolved relative to this directory.
TEST_DATA_DIR: Path = ORBIT_DATA_DIR / "test_data"

# Patient-generator templates the user drops in to drive the Genesis generator.
# Lives under orbit_data/ so users can add new templates in frozen mode without
# rebuilding the .exe.
PATIENT_TEMPLATES_DIR: Path = ORBIT_DATA_DIR / "patient_templates"

# Where the patient generator writes its batch outputs. Each batch goes under
# its own RUN_ID subdirectory, and each source sheet becomes its own .xlsx
# pool file so the existing single-sheet pool model in excel_data_manager
# picks it up automatically via the TEST_DATA_DIR rglob discovery.
GENERATED_PATIENTS_DIR: Path = TEST_DATA_DIR / "generated"

# .env file used by load_dotenv() and the Settings panel
ENV_FILE: Path = BASE_DIR / ".env"

# ── Python interpreter for subprocess script execution ─────────────────────────
if _IS_FROZEN:
    # The exe itself handles wrapper-mode execution via the --orbit-wrapper flag.
    # workers.py detects _IS_FROZEN and builds the command accordingly.
    PYTHON_EXECUTABLE: str = sys.executable
else:
    # Prefer a co-located venv so deployed dev installations are self-contained;
    # falls back to sys.executable so the app works without a venv.
    _venv_python = BASE_DIR / "venv" / "bin" / "python"
    PYTHON_EXECUTABLE: str = str(_venv_python) if _venv_python.exists() else sys.executable


if __name__ == "__main__":
    print(f"_IS_FROZEN:        {_IS_FROZEN}")
    print(f"BASE_DIR:          {BASE_DIR}")
    print(f"_RESOURCE_BASE:    {_RESOURCE_BASE}")
    print(f"SYSTEMS_DIR:       {SYSTEMS_DIR}")
    print(f"ORBIT_DATA_DIR:    {ORBIT_DATA_DIR}")
    print(f"RUNS_DIR:          {RUNS_DIR}")
    print(f"PYTHON_EXECUTABLE: {PYTHON_EXECUTABLE}")
