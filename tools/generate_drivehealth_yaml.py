"""
generate_drivehealth_yaml.py
----------------------------
Generates the full run_sequence.yaml hierarchy under
systems/Infra/DriveHealth/ from the canonical site/server maps.

Run once to create (or regenerate) all 36 YAML files:

    python tools/generate_drivehealth_yaml.py

Re-run any time a site is added, removed, or renamed.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
REPO_ROOT  = Path(__file__).resolve().parent.parent
DH_ROOT    = REPO_ROOT / "systems" / "Infra" / "DriveHealth"
PS1_FILE   = DH_ROOT / "DriveHealth_Final_All.ps1"

# ── Server inventory ──────────────────────────────────────────────────────────
QA_SITES: dict[str, list[str]] = {
    "CER_QA": ["XRDCWQAPPCAC10B","XRDCWQDBSCAC10B","XRDCWQINTCAC10B","XRDCWQRPTCAC10B","XRDCWQWEBCAC10B"],
    "ENT_QA": ["XRDCWQAPPCAC08B","XRDCWQDBSCAC08B","XRDCWQINTCAC08B","XRDCWQRPTCAC08B","XRDCWQWEBCAC08B"],
    "MTX_QA": ["XRDCWQAPPCAC20B","XRDCWQDBSCAC20B","XRDCWQINTCAC20B","XRDCWQRPTCAC20B","XRDCWQWEBCAC20B"],
}

SITE_SUFFIX_MAP: dict[str, str] = {
    "CER":"10B","CSA":"20B","CWT":"22B","DAL":"02B","EFD":"23B",
    "GCD":"24B","HOU":"03B","NAS":"07B","NFD":"21B","OPK":"04B",
    "RIC":"03B","SAN":"01B","TAM":"06B","TSD":"25B","TRN":"00B",
}
FWD_SITES = {"CWT","DAL","HOU","GCD","SAN"}

PREPROD_SITES = list(SITE_SUFFIX_MAP.keys())
PROD_SITES    = [s for s in SITE_SUFFIX_MAP if s != "TRN"]


# ── Helpers ───────────────────────────────────────────────────────────────────

def build_pp_servers(site: str, env_code: str) -> list[str]:
    """Return the 5 server names for a Pre-Prod / Prod site."""
    suffix = SITE_SUFFIX_MAP[site]
    prefix = ("FWDCW" if site in FWD_SITES else "XRDCW") + env_code
    return [
        f"{prefix}APPCAC{suffix}", f"{prefix}DBSCAC{suffix}",
        f"{prefix}INTCAC{suffix}", f"{prefix}RPTCAC{suffix}",
        f"{prefix}WEBCAC{suffix}",
    ]


_TYPE_RE = re.compile(r"(APP|DBS|INT|RPT|WEB)CAC", re.IGNORECASE)

def server_type_label(server: str) -> str:
    """Derive a short type label from a server name, e.g. APPCAC → APP."""
    m = _TYPE_RE.search(server)
    if not m:
        return "UNKNOWN"
    raw = m.group(1).upper()
    return {"DBS": "DB", "INT": "INTERFACE", "RPT": "REPORT"}.get(raw, raw)


def rel_ps1(yaml_dir: Path) -> str:
    """Relative path from a yaml directory back to the PS1 file."""
    return os.path.relpath(PS1_FILE, yaml_dir).replace("\\", "/")


def write_yaml(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    print(f"  wrote  {path.relative_to(REPO_ROOT)}")


def env_level_yaml(yaml_dir: Path, display: str, orbit_envs: str) -> str:
    """Single-entry YAML for an environment-level (or all-envs) run."""
    script = rel_ps1(yaml_dir)
    return (
        f"sequence:\n"
        f"  - script: {script}\n"
        f"    display: {display}\n"
        f"    env:\n"
        f"      ORBIT_DH_ENVS: \"{orbit_envs}\"\n"
    )


def site_level_yaml(yaml_dir: Path, orbit_envs: str, site: str, servers: list[str]) -> str:
    """Five-entry YAML for a site-level run (one entry per server)."""
    script = rel_ps1(yaml_dir)
    lines = ["sequence:\n"]
    for srv in servers:
        label = server_type_label(srv)
        lines.append(
            f"  - script: {script}\n"
            f"    display: \"{srv}  ({label})\"\n"
            f"    env:\n"
            f"      ORBIT_DH_ENVS: \"{orbit_envs}\"\n"
            f"      ORBIT_DH_SITE: \"{site}\"\n"
            f"      ORBIT_DH_SERVER: \"{srv}\"\n"
        )
    return "".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"Generating DriveHealth YAML hierarchy under:\n  {DH_ROOT}\n")
    count = 0

    # 1 ── All Environments ────────────────────────────────────────────────────
    p = DH_ROOT / "run_sequence.yaml"
    write_yaml(p, env_level_yaml(p.parent, "DriveHealth — All Environments", "QA,PreProd,Prod"))
    count += 1

    # 2 ── QA env level ────────────────────────────────────────────────────────
    qa_dir = DH_ROOT / "QA"
    p = qa_dir / "run_sequence.yaml"
    write_yaml(p, env_level_yaml(p.parent, "DriveHealth — QA", "QA"))
    count += 1

    # 3 ── QA site level ───────────────────────────────────────────────────────
    for site, servers in QA_SITES.items():
        site_dir = qa_dir / site
        p = site_dir / "run_sequence.yaml"
        write_yaml(p, site_level_yaml(p.parent, "QA", site, servers))
        count += 1

    # 4 ── Pre-Prod env level ──────────────────────────────────────────────────
    pp_dir = DH_ROOT / "PreProd"
    p = pp_dir / "run_sequence.yaml"
    write_yaml(p, env_level_yaml(p.parent, "DriveHealth — Pre-Prod", "PreProd"))
    count += 1

    # 5 ── Pre-Prod site level ─────────────────────────────────────────────────
    for site in PREPROD_SITES:
        servers = build_pp_servers(site, "WT")
        site_dir = pp_dir / site
        p = site_dir / "run_sequence.yaml"
        write_yaml(p, site_level_yaml(p.parent, "PreProd", site, servers))
        count += 1

    # 6 ── Prod env level ──────────────────────────────────────────────────────
    prod_dir = DH_ROOT / "Prod"
    p = prod_dir / "run_sequence.yaml"
    write_yaml(p, env_level_yaml(p.parent, "DriveHealth — Prod", "Prod"))
    count += 1

    # 7 ── Prod site level ─────────────────────────────────────────────────────
    for site in PROD_SITES:
        servers = build_pp_servers(site, "WP")
        site_dir = prod_dir / site
        p = site_dir / "run_sequence.yaml"
        write_yaml(p, site_level_yaml(p.parent, "Prod", site, servers))
        count += 1

    print(f"\nDone — {count} YAML files written.")


if __name__ == "__main__":
    main()
