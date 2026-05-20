# gravity_hub

Pre-change baseline snapshot of Orbit360 (orbit_hub). This repository preserves the
source state before the QML fixes, ORBIT_BASE_URL, connectivity preflight, and Nexus
additions introduced in the active development branch.

## Contents

Full Orbit360 project layout extracted from the original `orbit_hub` upload:

- `orbit360/` — Python package (backend, executors, models, UI, utils)
- `qml/` — QML UI files (pre-fix baseline)
- `tests/` — test suite (SQL executor, UiPath executor)
- `systems/` — automation scripts and `run_sequence.yaml` configs (MTX, CAC, Infra)
- `tools/` — utilities (patient generator, script migration helper, DriveHealth generator)
- `core/` — legacy module stubs

## Related repositories

- **orbit_hub** — active development branch with all fixes and new features
- **orbit_beacon** — standalone PyQt6 system metrics utility
