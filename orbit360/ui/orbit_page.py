"""
orbit_page.py — Orbit360
Smart Playwright page/frame wrapper.

Replaces scattered wait_for_timeout() calls with operations that wait for
actual DOM state, scroll into view, interact, log the outcome, and capture
a failure screenshot automatically — all in one call.

Usage:

    from orbit360.ui.orbit_page import OrbitPage
    from orbit360.backend.orbit_context import screenshot

    # Wrap a page or popup page
    op = OrbitPage(page, logger, screenshot_fn=screenshot)

    # Wrap a frame (pass the parent page for screenshots)
    op_frame = OrbitPage(codefinder_frame, logger, screenshot_fn=screenshot, page=page)

    # Interactions — all wait, scroll, act, log, screenshot on failure
    op.click("Submit button", frame.get_by_role("button", name="Submit"))
    op.fill("MRN field",      frame.get_by_role("textbox", name="MRN"), mrn_value)
    op.press("MRN field",     frame.get_by_role("textbox", name="MRN"), "Enter")
    op.select("Hold reason",  dropdown_locator, "3M-3M UPDATE ISSUE")
    op.check("Unspecified",   radio_locator)
    op.right_click("Code row", row_locator)

    # Waiting without interaction
    op.wait_visible("worklist rows", page.locator("table tr"))
    op.wait_hidden("spinner",        page.locator(".spinner"))
    op.wait_network_idle()
    op.wait_no_spinners()

    # Screenshots
    op.screenshot("step_name")

    # Switch to a popup page — inherits all settings
    with page.expect_popup() as popup_info:
        op.click("Pop-out button", pop_out_btn)
    op2 = op.with_page(popup_info.value)
    op2.click("OK", ok_btn)
"""
from __future__ import annotations

import logging
import time
from typing import Any, Callable, Optional


class OrbitPage:
    """
    Thin wrapper around a Playwright Page or FrameLocator that adds:

      - Smart waiting  (wait_for visible before every interaction)
      - Auto scroll-into-view
      - Structured logging  (INFO on success with elapsed ms, ERROR on failure)
      - Auto-screenshot on failure (label = "fail_<name>")
      - Optional post-interaction settle pause (wait_after_ms)

    All methods raise the underlying Playwright exception on failure after
    capturing the screenshot — so existing try/except and handle_failure()
    wrappers in scripts continue to work unchanged.
    """

    DEFAULT_TIMEOUT: int = 20_000  # milliseconds

    def __init__(
        self,
        page_or_frame,
        logger: logging.Logger,
        screenshot_fn: Optional[Callable] = None,
        timeout: int = DEFAULT_TIMEOUT,
        page=None,
    ) -> None:
        """
        Args:
            page_or_frame:  Playwright Page *or* a content_frame FrameLocator.
                            All locator operations run against this object.
            logger:         OrbitLogger or standard logging.Logger instance.
            screenshot_fn:  Called as screenshot_fn(page, label) on failure.
                            Import `screenshot` from orbit360.backend.orbit_context and
                            pass it here.
            timeout:        Default element-wait timeout in milliseconds.
            page:           The top-level Page object used for screenshots
                            when page_or_frame is a frame.  If omitted and
                            page_or_frame is a Page, it is used directly.
        """
        self._target = page_or_frame          # locators are resolved against this
        self._page = page or page_or_frame    # screenshots always need a Page
        self._logger = logger
        self._screenshot_fn = screenshot_fn
        self._timeout = timeout

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _safe_screenshot(self, label: str) -> None:
        if not self._screenshot_fn:
            return
        try:
            self._screenshot_fn(self._page, label)
        except Exception:
            pass  # never let screenshot capture crash a test

    def _on_failure(self, name: str, exc: Exception) -> None:
        self._logger.error(f"FAILED | {name} | {exc}")
        safe_label = "fail_" + name.lower().replace(" ", "_")[:50]
        self._safe_screenshot(safe_label)
        raise exc

    def _run(self, name: str, fn: Callable[[], Any]) -> Any:
        """Execute fn(), log timing on success, screenshot + raise on failure."""
        t0 = time.monotonic()
        try:
            result = fn()
            elapsed = (time.monotonic() - t0) * 1000
            self._logger.info(f"OK  | {name}  [{elapsed:.0f}ms]")
            return result
        except Exception as exc:
            self._on_failure(name, exc)

    # ------------------------------------------------------------------ #
    # Interaction API                                                      #
    # ------------------------------------------------------------------ #

    def click(
        self,
        name: str,
        locator,
        timeout: Optional[int] = None,
        wait_after_ms: int = 0,
    ) -> None:
        """
        Wait for *locator* to be visible, scroll into view, then click.

        Args:
            name:          Human-readable label used in logs and screenshot names.
            locator:       Any Playwright Locator object.
            timeout:       Override the instance default (ms).
            wait_after_ms: Hard settle pause after click.  Use only when the
                           target page has no detectable loading indicator.
        """
        t = timeout if timeout is not None else self._timeout

        def _do():
            locator.wait_for(state="visible", timeout=t)
            locator.scroll_into_view_if_needed()
            locator.click()
            if wait_after_ms:
                self._page.wait_for_timeout(wait_after_ms)

        self._run(name, _do)

    def right_click(
        self,
        name: str,
        locator,
        timeout: Optional[int] = None,
    ) -> None:
        """Right-click *locator* (for context menus)."""
        t = timeout if timeout is not None else self._timeout

        def _do():
            locator.wait_for(state="visible", timeout=t)
            locator.scroll_into_view_if_needed()
            locator.click(button="right")

        self._run(f"right-click: {name}", _do)

    def fill(
        self,
        name: str,
        locator,
        value: str,
        timeout: Optional[int] = None,
        clear_first: bool = True,
    ) -> None:
        """
        Wait for *locator*, optionally clear it, then type *value*.

        Args:
            clear_first: Set False if the field should not be cleared before
                         typing (e.g. append mode).
        """
        t = timeout if timeout is not None else self._timeout

        def _do():
            locator.wait_for(state="visible", timeout=t)
            locator.scroll_into_view_if_needed()
            if clear_first:
                locator.clear()
            locator.fill(value)

        self._run(f"fill: {name}", _do)

    def press(
        self,
        name: str,
        locator,
        key: str,
        timeout: Optional[int] = None,
    ) -> None:
        """
        Wait for *locator* then send *key* (e.g. ``"Enter"``, ``"Tab"``).
        """
        t = timeout if timeout is not None else self._timeout

        def _do():
            locator.wait_for(state="visible", timeout=t)
            locator.press(key)

        self._run(f"press {key}: {name}", _do)

    def select_option(
        self,
        name: str,
        locator,
        value: str,
        timeout: Optional[int] = None,
    ) -> None:
        """Wait for a ``<select>`` element and choose *value*."""
        t = timeout if timeout is not None else self._timeout

        def _do():
            locator.wait_for(state="visible", timeout=t)
            locator.select_option(value)

        self._run(f"select: {name}", _do)

    def check(
        self,
        name: str,
        locator,
        timeout: Optional[int] = None,
    ) -> None:
        """Wait for a checkbox or radio button and check it."""
        t = timeout if timeout is not None else self._timeout

        def _do():
            locator.wait_for(state="visible", timeout=t)
            locator.check()

        self._run(f"check: {name}", _do)

    # ------------------------------------------------------------------ #
    # Wait-only operations                                                 #
    # ------------------------------------------------------------------ #

    def wait_visible(
        self,
        name: str,
        locator,
        timeout: Optional[int] = None,
    ) -> None:
        """Block until *locator* is visible.  No interaction."""
        t = timeout if timeout is not None else self._timeout
        self._run(
            f"wait visible: {name}",
            lambda: locator.wait_for(state="visible", timeout=t),
        )

    def wait_hidden(
        self,
        name: str,
        locator,
        timeout: Optional[int] = None,
    ) -> None:
        """Block until *locator* is hidden or detached from the DOM."""
        t = timeout if timeout is not None else self._timeout
        self._run(
            f"wait hidden: {name}",
            lambda: locator.wait_for(state="hidden", timeout=t),
        )

    def wait_network_idle(self, timeout: int = 30_000) -> None:
        """
        Wait for all in-flight network requests to settle.
        Use after navigations or actions that trigger XHR/fetch calls.
        """
        self._run(
            "network idle",
            lambda: self._page.wait_for_load_state("networkidle", timeout=timeout),
        )

    def wait_no_spinners(
        self,
        timeout_ms: int = 60_000,
        poll_interval: float = 0.4,
        name: str = "page ready",
    ) -> None:
        """
        Poll until no spinner or loading elements are present in the DOM.

        Complements wait_network_idle() for apps (like 3M CAC) that continue
        rendering after the network has quieted.  Checks for elements whose
        CSS class contains 'spinner', 'loading', or 'busy'.
        """
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            try:
                clear = self._page.evaluate(
                    "() => document.querySelectorAll("
                    "  '[class*=\"spinner\"],[class*=\"loading\"],[class*=\"busy\"]'"
                    ").length === 0"
                )
                if clear:
                    self._logger.info(f"OK  | {name} — no spinners")
                    return
            except Exception:
                pass
            time.sleep(poll_interval)
        self._logger.warning(f"wait_no_spinners timed out after {timeout_ms}ms — continuing")

    # ------------------------------------------------------------------ #
    # Screenshot                                                           #
    # ------------------------------------------------------------------ #

    def screenshot(self, label: str) -> None:
        """Capture a screenshot via the registered screenshot_fn."""
        if not self._screenshot_fn:
            self._logger.warning(f"No screenshot_fn registered — skipped: {label}")
            return
        try:
            self._screenshot_fn(self._page, label)
            self._logger.info(f"Screenshot: {label}")
        except Exception as exc:
            self._logger.warning(f"Screenshot failed: {label} | {exc}")

    # ------------------------------------------------------------------ #
    # Page switching                                                       #
    # ------------------------------------------------------------------ #

    def with_page(self, new_page) -> "OrbitPage":
        """
        Return a new OrbitPage bound to a different page (e.g. a popup).
        Inherits logger, screenshot_fn, and timeout from the current instance.

        Usage:
            with page.expect_popup() as popup_info:
                op.click("Pop-out button", pop_out_btn)
            op2 = op.with_page(popup_info.value)
            op2.click("OK in popup", ok_btn)
        """
        return OrbitPage(
            page_or_frame=new_page,
            logger=self._logger,
            screenshot_fn=self._screenshot_fn,
            timeout=self._timeout,
        )

    def with_frame(self, frame) -> "OrbitPage":
        """
        Return a new OrbitPage that runs locator operations against *frame*
        but still uses the current page for screenshots.

        Usage:
            op_cf = op.with_frame(frames.codefinder)
            op_cf.click("Submit", submit_btn)
        """
        return OrbitPage(
            page_or_frame=frame,
            logger=self._logger,
            screenshot_fn=self._screenshot_fn,
            timeout=self._timeout,
            page=self._page,
        )
