"""
orbit_toolkit.py — Orbit360 v4.0

Lightweight helper module for test scripts.

Provides thin wrappers around the ORBIT_* environment variables injected by
the Orbit360 runner so scripts don't need to parse os.environ manually.

Typical usage:
    from orbit_toolkit import base_url, screenshot_dir, save_screenshot

    def test_homepage(page):
        page.goto(base_url())
        save_screenshot(page, "homepage")
"""

from __future__ import annotations

import os
from pathlib import Path


# ── Environment accessors ─────────────────────────────────────────────────────

def base_url(default: str = "http://localhost") -> str:
    """Return ORBIT_BASE_URL, or `default` when not set."""
    return os.environ.get("ORBIT_BASE_URL", default)


def run_id() -> str:
    """Return the unique ID for the current run (ORBIT_RUN_ID)."""
    return os.environ.get("ORBIT_RUN_ID", "")


def script_name() -> str:
    """Return the name of the currently executing script (ORBIT_SCRIPT_NAME)."""
    return os.environ.get("ORBIT_SCRIPT_NAME", "")


def is_headless() -> bool:
    """Return True when the runner is configured for headless browser mode."""
    return os.environ.get("ORBIT_HEADLESS", "0") == "1"


def is_parallel() -> bool:
    """Return True when more than one script is running concurrently."""
    return int(os.environ.get("ORBIT_PARALLEL", "1")) > 1


def env(key: str, default: str = "") -> str:
    """Read any environment variable with an optional fallback."""
    return os.environ.get(key, default)


# ── Directory helpers ─────────────────────────────────────────────────────────

def screenshot_dir() -> Path:
    """
    Return the directory where screenshots should be saved for this run.
    Creates the directory if it does not exist.
    """
    d = Path(os.environ.get("ORBIT_SCREENSHOT_DIR", "."))
    d.mkdir(parents=True, exist_ok=True)
    return d


def log_dir() -> Path:
    """
    Return the log output directory for this run.
    Creates the directory if it does not exist.
    """
    d = Path(os.environ.get("ORBIT_LOG_DIR", "."))
    d.mkdir(parents=True, exist_ok=True)
    return d


# ── Playwright convenience ────────────────────────────────────────────────────

def save_screenshot(page, name: str) -> Path:
    """
    Save a Playwright page screenshot to the run's screenshot directory.

    Args:
        page: A Playwright ``Page`` object.
        name: Base filename (no extension).  A ``.png`` suffix is added.

    Returns:
        The ``Path`` of the saved file.

    Example::

        from orbit_toolkit import save_screenshot
        save_screenshot(page, "checkout_success")
    """
    path = screenshot_dir() / f"{name}.png"
    page.screenshot(path=str(path))
    return path
