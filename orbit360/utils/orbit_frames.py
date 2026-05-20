"""
orbit_frames.py — Orbit360
Named frame registry for CAC (3M 360App) and other multi-iframe applications.

The 3M 360App nests its content inside several layers of iframes.  Writing
the full locator chain in every script is both verbose and brittle — a single
class name change in 3M's HTML breaks every script that references it.

This module centralises every frame locator chain in one place so that when
3M updates their DOM, only this file needs to change.

Usage:

    from orbit360.utils.orbit_frames import CACFrames

    # Patient record window (page1)
    frames = CACFrames(page1)
    frames.codefinder.get_by_role("button", name="OK").click()
    frames.cac.get_by_label("Self Pay").press("Tab")
    frames.abstract.get_by_role("button").filter(has_text="Save").click()
    frames.hold_dialog.locator("textarea").fill("TEST")

    # After pop-out — pass the popup page
    frames2 = CACFrames(page2)
    frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword").fill("K2090")
    frames2.crs_popout.get_by_role("button", name="OK").click()

    # Original window after pop-out (uses different CSS selector)
    frames.codefinder_inline.get_by_role("button", name="Resolve").click()

    # Rebind to a different page (e.g. after pop-in)
    frames = frames.rebind(page1)

Frame layout reference
======================

Patient record window (page1):
    page1
    ├── .c_position_relative > div > .c_full_height > iframe   → codefinder (initial)
    │       └── <body> content_frame                           → codefinder
    ├── #cac_frame                                             → cac
    ├── #atframe                                               → abstract
    ├── #aiframehold                                           → hold_dialog
    ├── #qframe                                                → query
    ├── #crsOuterIframe → <body> content_frame                 → crs_inline
    ├── m-cac iframe                                           → m_cac
    ├── #findingframe                                          → finding
    └── iframe[name="emw_frame_name"]                          → em_wizard

Patient record window after pop-out (page1):
    page1
    └── .c_position_relative > div > .c_full_height > .c_html_content_iframe
            └── <body> content_frame                           → codefinder_inline

Pop-out window (page2):
    page2
    ├── #container iframe
    │       └── <body> content_frame                           → codefinder_popout
    └── #crsOuterIframe
            └── <body> content_frame                           → crs_popout

Main dashboard page (page / main window):
    page
    ├── #CRSConfigFrame1                                       → crs_config
    └── iframe[title="Container"]                              → container
"""
from __future__ import annotations


class CACFrames:
    """
    Lazy frame accessors for the 3M 360App CAC window.

    Each property re-resolves the locator chain on every access so the
    reference remains live across navigations and page reloads.  Never cache
    the returned frame locator — always access it via the property.
    """

    def __init__(self, page) -> None:
        """
        Args:
            page: The Playwright Page object for this window.
                  Pass page1 for the patient record window,
                  page2 for the pop-out codefinder window.
        """
        self._page = page

    # ------------------------------------------------------------------ #
    # Patient record window frames                                         #
    # ------------------------------------------------------------------ #

    @property
    def codefinder(self):
        """
        CodeFinder iframe — main coding interface (initial state, before pop-out).
        Contains: keyword/code search box, Dx/CPT code lists, Add/Delete buttons.
        """
        return (
            self._page
            .locator(".c_position_relative > div > .c_full_height > iframe")
            .first
            .content_frame
            .get_by_text("</body> </html>")
            .content_frame
        )

    @property
    def cac(self):
        """
        CAC / CRS iframe — version info dialogs, POA prompts, status OK buttons.
        Selector: #cac_frame
        """
        return self._page.locator("#cac_frame").content_frame

    @property
    def abstract(self):
        """
        Abstract tab iframe — consulting providers, attending physician,
        hold-reason entry, Save/OK buttons within the Abstract tab.
        Selector: #atframe
        """
        return self._page.locator("#atframe").content_frame

    @property
    def hold_dialog(self):
        """
        Hold dialog iframe — hold-reason dropdown, notes textarea, Hold button.
        Appears when moving an account to Hold status.
        Selector: #aiframehold
        """
        return self._page.locator("#aiframehold").content_frame

    @property
    def codefinder_inline(self):
        """
        CodeFinder iframe after the pop-out window has been used and popped
        back in.  3M renders this with a different CSS class than the initial
        codefinder frame — use this property instead of .codefinder once the
        pop-out/pop-in cycle has occurred.
        Selector: .c_html_content_iframe (vs .c_full_height > iframe initially)
        """
        return (
            self._page
            .locator(
                ".c_position_relative > div > .c_full_height > .c_html_content_iframe"
            )
            .first
            .content_frame
            .get_by_text("</body> </html>")
            .content_frame
        )

    # ------------------------------------------------------------------ #
    # Pop-out codefinder window frames (page2)                            #
    # ------------------------------------------------------------------ #

    @property
    def codefinder_popout(self):
        """
        CodeFinder frame inside the detached pop-out window (page2).
        Contains the same coding interface as .codefinder but rendered
        in a separate browser window.
        Selector: #container iframe → content_frame
        """
        return (
            self._page
            .locator("#container iframe")
            .content_frame
            .get_by_text("</body> </html>")
            .content_frame
        )

    @property
    def crs_popout(self):
        """
        CRS (Coding & Reimbursement System) iframe inside the pop-out window.
        Contains provider episode fields, date pickers, physician lookup.
        Selector: #crsOuterIframe → content_frame
        """
        return (
            self._page
            .locator("#crsOuterIframe")
            .content_frame
            .get_by_text("</body> </html>")
            .content_frame
        )

    # ------------------------------------------------------------------ #
    # Additional patient record window frames                              #
    # ------------------------------------------------------------------ #

    @property
    def query(self):
        """
        CDI Query / Provider Communication iframe (page1).
        Contains query text, response status, and Send/Save buttons.
        Selector: #qframe
        """
        return self._page.locator("#qframe").content_frame

    @property
    def crs_inline(self):
        """
        CRS iframe embedded in the patient record window (page1).
        Used during ED Admit / outpatient direct coding workflows.
        Differs from crs_popout — this lives in page1, not the pop-out.
        Selector: #crsOuterIframe → content_frame (double-nested)
        """
        return (
            self._page
            .locator("#crsOuterIframe")
            .content_frame
            .get_by_text("</body> </html>")
            .content_frame
        )

    @property
    def m_cac(self):
        """
        AS DRG / WSS module iframe (page1) — Tristar and similar sites.
        Contains working DRG assignment buttons and WSS score display.
        Selector: m-cac iframe (tag + child iframe)
        """
        return self._page.locator("m-cac iframe").content_frame

    @property
    def finding(self):
        """
        Working DRG Findings panel iframe (page1).
        Displays DRG findings, HACs, and quality indicator alerts.
        Selector: #findingframe
        """
        return self._page.locator("#findingframe").content_frame

    @property
    def em_wizard(self):
        """
        E&M Wizard iframe (page1).
        Contains E&M level selection, complexity scoring, and documentation
        requirement guidance for outpatient / professional fee coding.
        Selector: iframe[name="emw_frame_name"]
        """
        return self._page.locator('iframe[name="emw_frame_name"]').content_frame

    # ------------------------------------------------------------------ #
    # Main dashboard / app-shell frames (main page, not patient popup)    #
    # ------------------------------------------------------------------ #

    @property
    def crs_config(self):
        """
        CRS Configuration iframe on the main dashboard page.
        Used for custom edits filter setup and CRS rule configuration.
        Selector: #CRSConfigFrame1
        Note: bind this to the *main* page object, not the patient popup.
        """
        return self._page.locator("#CRSConfigFrame1").content_frame

    @property
    def container(self):
        """
        Container iframe on the main dashboard page.
        Used by QA and ENT outpatient application views.
        Selector: iframe[title="Container"]
        Note: bind this to the *main* page object, not the patient popup.
        """
        return self._page.locator('iframe[title="Container"]').content_frame

    # ------------------------------------------------------------------ #
    # Helpers                                                              #
    # ------------------------------------------------------------------ #

    def rebind(self, page) -> "CACFrames":
        """
        Return a new CACFrames instance bound to a different page object.
        Useful when the same script works with both page1 and page2.

        Usage:
            frames1 = CACFrames(page1)
            frames2 = frames1.rebind(page2)
        """
        return CACFrames(page)

    @classmethod
    def for_popout(cls, popout_page) -> "CACFrames":
        """
        Convenience constructor for the pop-out window.
        Equivalent to CACFrames(popout_page) but more readable at the call site.

        Usage:
            with page1.expect_popup() as p2_info:
                pop_out_btn.click()
            page2 = p2_info.value
            frames2 = CACFrames.for_popout(page2)
        """
        return cls(popout_page)
