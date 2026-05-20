import os
import sys
import time
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect

# =========================================================
# Configuration
# =========================================================

SYSTEM      = "CAC"
ENVIRONMENT = "Prod"
PILLAR      = "Orange Park"
RUN_TYPE    = "PUV"

# =========================================================
# Bootstrap — locate project root and import shared runtime
# =========================================================

_env_root = os.environ.get("ORBIT_ROOT")
if _env_root:
    sys.path.insert(0, _env_root)
else:
    _p = Path(__file__).resolve()
    while _p.name.lower() not in ("orbit360_v3.0", "orbit_hub"):
        if _p.parent == _p:
            raise RuntimeError("Could not locate Orbit project root.")
        _p = _p.parent
    sys.path.insert(0, str(_p))

from orbit360.backend.orbit_context import (
    setup, step, end_step, section_break,
    screenshot, manual_prompt, handle_failure, format_duration,
    crs_frame, start_trace, save_trace,
)
from orbit360.utils.orbit_script_helpers import pre_run_check

ctx    = setup(SYSTEM, ENVIRONMENT, PILLAR, RUN_TYPE)
logger = ctx.logger

# Main Run
def run(playwright: Playwright) -> None:
    run_start_time = time.time()
    browser = None
    context = None
    page    = None
    try:
        pre_run_check("https://xrdcwpappcac04b.hca.corpad.net/CRSConfigPlatform.html")
        browser = playwright.chromium.launch(
            headless=False,
            args=["--start-maximized"]
            )
        context = browser.new_context(no_viewport=True)
        start_trace(context)
        page = context.new_page()

    # Navigate to CRS Config Utility Page
        section_break("CRS Config Utility Page)")
        step("CRS Config Utility Page", "Launching CRS Config Utility Page")
        page.goto("https://xrdcwpappcac04b.hca.corpad.net/CRSConfigPlatform.html", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        screenshot(page, "crs_config_utility")
        logger.info("Codefinder (CRS) Successfully Loaded")
        end_step()

    # Click Custom Edits Tab
        section_break("Navigate Custom Edits Tab")
        step("CRS Config Utility", "Navigating to Custom Edits Tab")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        logger.info("Clicking Custom Edits Tab")
        page.get_by_role("button", name="Custom Edits").click()
        page.wait_for_load_state("domcontentloaded") 
        page.wait_for_timeout(2000) 
        screenshot(page, "custom_edits")
        page.locator("#CRSConfigFrame1").content_frame.get_by_role("textbox", name="Filter Edits By Text..").click()
        page.locator("#CRSConfigFrame1").content_frame.get_by_role("textbox", name="Filter Edits By Text..").fill("1181")
        screenshot(page, "custom_edit_1181")
        logger.info("Searching for Custom Edit 1181")
        page.wait_for_load_state("domcontentloaded") 
        page.wait_for_timeout(2000)
        page.locator("#CRSConfigFrame1").content_frame.get_by_role("cell", name="SLR - Procedure Unrelated to").click()
        screenshot(page, "edit_details")
        end_step()
        logger.info("Test Successfully Passed!")
        
    except Exception as e:
        handle_failure(e, page)

    finally:
        if context:
            save_trace(context)
        if browser:
            browser.close()
        total_duration = time.time() - run_start_time
        logger.info(f"Total Run Duration | {format_duration(total_duration)}")

with sync_playwright() as playwright:
    run(playwright)
