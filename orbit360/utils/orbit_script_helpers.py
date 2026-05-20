"""
orbit360/utils/orbit_script_helpers.py
Shared helper functions for all Orbit test scripts.

Usage in every script — replace the local helper block with:

    from orbit360.utils.orbit_script_helpers import (
        init_helpers,
        WAIT_PROFILES, DEFAULT_TIMEOUT, RETRY_COUNT,
        wait_with_intervention, wait_for_data_load,
        safe_click, safe_fill, safe_screenshot, step_with_pause,
    )

    ctx    = setup(SYSTEM, ENVIRONMENT, PILLAR, RUN_TYPE, TEST_SET)
    logger = ctx.logger
    init_helpers(ctx)          # bind once — all helpers are ready to use

Call signatures are identical to the old inline copies so no call-site
changes are needed.
"""

import time
from contextlib import contextmanager

from orbit360.backend.orbit_context import screenshot as _take_screenshot, manual_prompt, SkipStep
from orbit360.utils.orbit_retry import retry_call as _retry_call

# ------------------------------------------------------------------ #
# Configuration constants                                              #
# ------------------------------------------------------------------ #

WAIT_PROFILES: dict = {
    "dashboard": {"max_wait": 120_000, "check_interval": 0.5},
    "grid":      {"max_wait":  60_000, "check_interval": 0.5},
    "popup":     {"max_wait":  45_000, "check_interval": 0.5},
    "dropdown":  {"max_wait":  15_000, "check_interval": 0.3},
    "quick":     {"max_wait":  12_000, "check_interval": 0.2},
}

DEFAULT_TIMEOUT: int = 20_000
RETRY_COUNT:     int = 2

# ------------------------------------------------------------------ #
# Runtime binding                                                      #
# ------------------------------------------------------------------ #

_ctx    = None
_logger = None


def init_helpers(ctx) -> None:
    """Bind the shared context and logger.  Call once, right after setup()."""
    global _ctx, _logger
    _ctx    = ctx
    _logger = ctx.logger


def _require_init() -> None:
    if _ctx is None or _logger is None:
        raise RuntimeError(
            "orbit_script_helpers not initialised — call init_helpers(ctx) "
            "after setup() before using any helper function."
        )


# ------------------------------------------------------------------ #
# Helpers                                                              #
# ------------------------------------------------------------------ #

class _SkipSignal(Exception):
    """Internal: user chose 'S' in wait_with_intervention."""

class _RetrySignal(Exception):
    """Internal: user chose ENTER (retry) in wait_with_intervention."""


def wait_with_intervention(locator, name="element",
                           timeout=DEFAULT_TIMEOUT, retries=RETRY_COUNT):
    """Wait for a locator to become visible, prompting the user if retries fail.

    Uses orbit_retry for the inner retry loop; on exhaustion the user is
    given Q / S / Enter choices via ctx.prompt_value() so the call routes
    correctly whether running in Orbit GUI or a plain terminal.
    """
    _require_init()

    def _attempt():
        locator.wait_for(state="visible", timeout=timeout)
        return locator

    def _on_exhaust(_fn_name, _exc):
        _logger.error(f"'{name}' failed after all retries")
        choice = _ctx.prompt_value(
            f"[ACTION REQUIRED] '{name}' is not visible. "
            "Enter Q to quit, S to skip, or press ENTER to retry",
            default=""
        ).lower()
        if choice == "q":
            raise Exception(f"User terminated at '{name}'")
        elif choice == "s":
            _logger.warning(f"'{name}' skipped by user")
            raise _SkipSignal()
        else:
            _logger.info(f"Retrying '{name}' after user confirmation")
            raise _RetrySignal()

    try:
        return _retry_call(
            _attempt,
            attempts=retries + 1,
            delay=2.0,
            on_exhaust=_on_exhaust,
            logger=_logger,
        )
    except _SkipSignal:
        return None
    except _RetrySignal:
        return wait_with_intervention(locator, name, timeout, retries)


def wait_for_data_load(page, name="data load", profile="quick",
                       allow_partial=True) -> None:
    """Poll for spinner/row state using a JS snippet; degrade gracefully."""
    _require_init()
    config     = WAIT_PROFILES.get(profile, WAIT_PROFILES["quick"])
    max_wait   = config["max_wait"]
    interval   = config["check_interval"]
    start_time = time.time()
    _logger.info(f"Waiting for {name} [{profile}]")

    while True:
        try:
            ready = page.evaluate("""
            () => {
                const spinners = document.querySelectorAll(
                    '[class*="spinner"], [class*="loading"]'
                );
                const rows = document.querySelectorAll('table tr, [role="row"]');
                return spinners.length === 0 && rows.length > 0;
            }
            """)
            if ready:
                _logger.info(f"{name} ready")
                return
        except Exception:
            pass

        elapsed = (time.time() - start_time) * 1000
        if elapsed > max_wait:
            _logger.warning(f"{name} exceeded expected load time [{profile}]")
            if allow_partial:
                return
            manual_prompt(
                message=f"{name} may not be fully loaded. Continue?",
                completion_note="User confirmed",
            )
            return

        seconds = int(elapsed / 1000)
        if seconds in (10, 30, 60, 90):
            _logger.info(f"{name} still loading... ({seconds}s elapsed)")

        time.sleep(interval)


def safe_click(locator, name="element") -> None:
    """Wait for visibility, scroll into view, then click."""
    result = wait_with_intervention(locator, name)
    if result is None:
        return
    locator.scroll_into_view_if_needed()
    locator.click()
    _logger.info(f"Clicked {name}")


def safe_fill(locator, value: str, name="input") -> None:
    """Wait for visibility, scroll into view, then fill the field with value."""
    result = wait_with_intervention(locator, name)
    if result is None:
        return
    locator.scroll_into_view_if_needed()
    locator.fill(value)
    _logger.info(f"Filled {name} with {value!r}")


def safe_screenshot(page, anchor_locator, name: str) -> None:
    """Wait for an anchor element, then capture a screenshot."""
    wait_with_intervention(anchor_locator, f"{name} anchor")
    page.wait_for_timeout(500)
    _take_screenshot(page, name)
    _logger.info(f"Screenshot captured: {name}")


def pre_run_check(url: str) -> None:
    """Verify the target URL is reachable before launching the browser.

    Raises RuntimeError immediately if the site is down so the script fails
    fast with a clear message instead of hanging inside Playwright.
    Call this once near the top of run(), before playwright.chromium.launch().

    Works with or without init_helpers() — safe to call from PUV scripts that
    only import from orbit_context and do not call init_helpers().
    """
    import logging
    log = _logger if _logger is not None else logging.getLogger(__name__)
    from orbit360.utils.orbit_health import check_url
    result = check_url(url, timeout=10.0)
    if result.reachable:
        log.info(
            f"Pre-run health check passed | {url} | {result.latency_ms:.0f} ms"
        )
    else:
        msg = result.error or f"HTTP {result.status_code}"
        log.error(f"Pre-run health check FAILED | {url} | {msg}")
        raise RuntimeError(
            f"Target URL is not reachable — aborting run.\n"
            f"  URL   : {url}\n"
            f"  Reason: {msg}\n"
            "Check VPN, network, and whether the 3M server is up."
        )


@contextmanager
def step_guard():
    """Context manager that catches a SkipStep signal from handle_failure().

    When an analyst clicks "Skip Step" during failure recovery, handle_failure()
    raises SkipStep(BaseException).  The script's outer ``except Exception``
    block does NOT catch BaseException, so SkipStep propagates up until it
    hits a ``step_guard()`` wrapper, which logs the skip and lets execution
    continue at the next step.

    Usage::

        with step_guard():
            section_break("Submit Account")
            step("Submit Account", "Submitting...")
            page1.get_by_role("button").filter(has_text="Submit & Next").click()
            end_step()
    """
    _require_init()
    try:
        yield
    except SkipStep as e:
        _logger.warning(f"[STEP SKIPPED] {e} — continuing automation")


def step_with_pause(step_name: str, action, verify) -> None:
    """Run action(); on failure prompt user to fix manually, then re-verify."""
    _require_init()
    try:
        action()
        _logger.info(f"{step_name} | SUCCESS")
    except Exception as e:
        _logger.error(f"{step_name} | FAILED | {e}")
        _logger.info(f"{step_name} | Waiting for user to fix via Orbit...")
        manual_prompt(
            message=(
                f"Paused at '{step_name}' — fix the issue in the app, "
                "then click Continue in Orbit to resume"
            ),
            completion_note="Resuming after manual fix",
        )
        try:
            verify()
            _logger.info(f"{step_name} | VERIFIED after manual fix")
        except Exception as e2:
            _logger.error(f"{step_name} | STILL FAILED after resume | {e2}")
            raise
