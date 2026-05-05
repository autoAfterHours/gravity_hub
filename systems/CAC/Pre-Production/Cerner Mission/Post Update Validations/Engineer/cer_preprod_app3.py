import os
import sys
import time
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect

# =========================================================
# Configuration
# =========================================================

SYSTEM      = "CAC"
ENVIRONMENT = "Pre-Production"
PILLAR      = "Cerner Mission"
RUN_TYPE    = "Post Update Validations"
TEST_SET    = "Engineer"

# =========================================================
# Bootstrap — locate project root and import shared runtime
# =========================================================

_env_root = os.environ.get("ORBIT_ROOT")
if _env_root:
    sys.path.insert(0, _env_root)
else:
    _p = Path(__file__).resolve().parent
    while not (_p / "orbit360").is_dir():
        if _p.parent == _p:
            raise RuntimeError("Could not locate Orbit project root.")
        _p = _p.parent
    sys.path.insert(0, str(_p))

from orbit360.backend.orbit_context import (
    setup, step, end_step, section_break,
    screenshot, manual_prompt, handle_failure, format_duration,
    crs_frame, start_trace, save_trace,
)

ctx    = setup(SYSTEM, ENVIRONMENT, PILLAR, RUN_TYPE, TEST_SET)
logger = ctx.logger

# Main Run
def run(playwright: Playwright) -> None:
    run_start_time = time.time()
    browser = None
    context = None
    page    = None
    try:
        browser = playwright.chromium.launch(
            headless=False,
            args=["--start-maximized"]
            )
        context = browser.new_context(no_viewport=True)
        start_trace(context)
        page = context.new_page()

    # Navigate to Codefinder Page
        section_break("Codefinder(CRS)")
        step("Codefinder(CRS)", "Launching Codefinder (CRS)")
        page.goto("https://xrdcwtappcac10b.hca.corpad.net/launchCRS.html", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        screenshot(page, "codefinder_crs")
        logger.info("Codefinder (CRS) Successfully Loaded")
        end_step()
    
    # Select Help Button - Select About
        section_break("Help Button")
        step("Help Button", "Open Help Menu & Confirm Version")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        screenshot(page, "codefinder_menu")
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_text("Help").click()
        logger.info("Help Button Selected")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_text("About").click()
        logger.info("About Option Selected")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        screenshot(page, "system_version_details")
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="OK").click()
        end_step()
    
    # Enter Age of Admission
        section_break("Enter Age of Admission")
        step("Age of Admission", "Enter Age of Admission")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("textbox", name="Age at Admission:").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("textbox", name="Age at Admission:").fill("22")
        logger.info("Age Entered")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        screenshot(page, "codefinder_updated")
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Continue").click()
        end_step()

    # Select Patient Disposition
        section_break("Patient Disposition")
        step("Patient Disposition", "Select Patient Disposition")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        screenshot(page, "patient_disposition")
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("radio", name="Home, Self Care (UB-01)").click()
        logger.info("Patient Disposition Updated")
        end_step()

    # Walk Through Coding Process (Example: "BACK")
        section_break("Coding Process")
        step("Coding Process", "Walk Through Coding Process")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page.wait_for_timeout(500)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("BACK")
        screenshot(page, "coding_details")
        logger.info("Coding Pathway Entered")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Continue").click()
        logger.info("Continuing")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        screenshot(page, "codeset_added")
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Back").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Back").click()
        logger.info("Backed Out of Coding Process")
        end_step()

    # Exit Session & Close Page
        section_break("Close Session")
        step("Close Session", "Closing Session")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        screenshot(page, "end_session_button")
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Yes").click()
        logger.info("Session Closed")
        end_step()
        logger.info("Codefinder Test Passed!")

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