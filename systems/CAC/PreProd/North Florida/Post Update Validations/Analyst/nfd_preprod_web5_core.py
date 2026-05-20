import re
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
PILLAR      = "North Florida"
RUN_TYPE    = "Post Update Validations"
TEST_SET    = "Analyst"

# =========================================================
# Bootstrap — locate project root and import shared runtime
# =========================================================

_env_root = os.environ.get("ORBIT_ROOT")
if _env_root:
    sys.path.insert(0, _env_root)
else:
    _p = Path(__file__).resolve()
    while _p.name.lower() not in ("orbit360",):
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

    # Navigate to CAC Dashboard 
        section_break("CAC Dashboard")
        step("CAC Dashboard", "Opening CAC Dashboard")
        page.goto("https://XRDCWTWEBCAC21B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        screenshot(page, "cac_dashboard")
        logger.info("CAC Dashboard Successfully Loaded")
        end_step()

    # Click About & Validate Version
        section_break("Checking About")
        step("About", "Checking About Functionality")
        page.wait_for_timeout(1000)
        page.wait_for_load_state("domcontentloaded")
        page.locator("#container").get_by_text("About").click()
        page.wait_for_timeout(1000)
        page.wait_for_load_state("domcontentloaded")
        logger.info("About Opened Succesfully. Capturing Screenshot of Details.")
        screenshot(page, "about")
        page.get_by_role("button", name="Close", exact=True).click()
        page.wait_for_timeout(1000)
        page.wait_for_load_state("domcontentloaded")
    
    # Click Help & Open What's New
        section_break("Help")
        step("Help", "Checking Help Functionality")
        logger.info("Clicking Help Button")
        with page.expect_popup() as page1_info:
            page.locator("#container").get_by_text("Help").click()
        page1 = page1_info.value
        logger.info("Help Menu Loaded Successfully")
        screenshot(page1,"help_menu")
        logger.info("Opening System Admin Library Option")
        page1.get_by_role("link", name=" What's New in 360 Encompass").click()
        page1.goto("https://apps.3mhis.com/download/3M_Docs_Secured/360_Encompass/360_P2_library/en/whats_new_360r2.html")
        logger.info("System Admin Library Successfully Loaded")
        logger.info("Closing Window")
        page1.close()
        end_step()

    # Click Codefinder & Validate Functionality
        section_break("Codefinder")
        step("Codefinder","Opening Codefinder")
        with page.expect_popup() as page2_info:
            page.get_by_role("button", name="Codefinder").click()
            page2 = page2_info.value
            page2.wait_for_timeout(1000)
            page2.wait_for_load_state("domcontentloaded")
            page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="Help").click()
            logger.info("Codefinder Opened Successfully")
            screenshot(page2, "codefinder_mainmenu")
            page2.wait_for_timeout(1000)
            page2.wait_for_load_state("domcontentloaded")
            logger.info("Opening About Option")
            page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("About").click()
            page2.wait_for_timeout(2000)
            screenshot(page2, "version")
            logger.info("Version Validated")
            logger.info("Closing Window")
            page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
            logger.info("Menu Closed. Closing Codefinder")
            page2.close()
            end_step()

    # Select Patient Search & Check Functionality
        section_break("Patient Search")
        step("Patient Search", "Opening Patient Search and Testing Functionality")
        page.wait_for_timeout(1000)
        page.wait_for_load_state("domcontentloaded")
        page.get_by_text("Patient Search", exact=True).click()
        page.wait_for_timeout(2000)
        page.wait_for_load_state("domcontentloaded")
        screenshot(page, "patient_search")
        logger.info("Patient Search Loaded Successfully.")
        logger.info("Searching for Patient")
        page.locator("#container input[type=\"text\"]").nth(2).click()
        page.wait_for_timeout(500)
        page.locator("#container input[type=\"text\"]").nth(2).fill("Smith")
        page.wait_for_timeout(500)
        logger.info("Patient Name Entered")
        screenshot(page, "patient_name_entered")
        page.locator("#container input[type=\"text\"]").nth(2).press("Enter")
        page.wait_for_timeout(2000)
        page.wait_for_load_state("domcontentloaded")
        screenshot(page, "patient_searched")
        logger.info("Navigating Back to Dashboard")
        page.get_by_role("button", name=" Back to Dashboard").click()

    # Navigate to Reports Tab
        section_break("Reports")
        step("Reports", "Navigating to Reports Tab")
        page.wait_for_timeout(3000)
        page.wait_for_load_state("domcontentloaded")
        page.locator("span").filter(has_text="Reports").click()
        page.wait_for_load_state("domcontentloaded")
        screenshot(page, "reports")
        logger.info("Reports Tab Selected")
        end_step()
        
    # Prompt to Select Report Type & Run Report
        step("Interface010 Inbound Interface Listing Report", "Selecting Interface010 Inbound Interface Listing")        
        manual_prompt(
            message="Select Interface010 Inbound Interface Listing & Run Report",
            completion_note="Report Ran Successfully"
        )
        end_step()
        page.wait_for_timeout(2000)
        page.wait_for_load_state("domcontentloaded")
        screenshot(page, "interface010_report_loaded")
        logger.info("Report Successfully Genreated Results")
        logger.info("Test Passed Successfully! Closing Session.")

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