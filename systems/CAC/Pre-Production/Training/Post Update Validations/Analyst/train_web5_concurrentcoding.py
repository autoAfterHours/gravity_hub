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
PILLAR      = "Training"
RUN_TYPE    = "Post Update Validations"
TEST_SET    = "Analyst"

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

    # Navigate to CAC Dashboard
        section_break("CAC Dashboard")
        step("CAC Dashboard", "Opening CAC Dashboard")
        page.goto("https://XRDCWTWEBCAC00B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        screenshot(page, "cac_dashboard")
        logger.info("CAC Dashboard Successfully Loaded")
        end_step()

    # Navigate to Concurrent Coding Dashboard
        section_break("Concurrent Coding Dashboard")
        step("Concurrent Coding Dashboard", "Navigating to Concurrent Coding Dashboard")
        page.wait_for_timeout(2000)
        page.wait_for_load_state("domcontentloaded")
        page.get_by_text("Concurrent Coding").click()
        page.wait_for_timeout(2000)
        page.wait_for_load_state("domcontentloaded")
        screenshot(page, "concurrent_coding_dashboard")
        logger.info("Concurrnt Coding Dashboard Opened Successfully.")
        logger.info("Navigating to Discharged All Worklist")
        page.get_by_role("cell", name="Discharged All").click()
        page.wait_for_timeout(2000)
        page.wait_for_load_state("domcontentloaded")
        screenshot(page, "discharged_all_worklist")
        end_step()

    # Prompt to Select Patient & Continue
        section_break("Select Patient Record")
        step("Select Patient", "Select a Patient Record")        
        manual_prompt(
            message="Select a patient record",
            completion_note="Patient Selected"
            )
        end_step()

    # Acknowledge Patient Record Loaded
        section_break("Patient Validation Check")
        step("Confirm Patient Loaded", "Patient Record Loaded")
        page1 = None
        with page.expect_popup() as page1_info:
            page1 = page1_info.value
            crs = crs_frame(page1)
            page1.bring_to_front()
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(2000)
            screenshot(page1, "patient_record")
            end_step()  

    # Navigate to Document and Codes Tab
            section_break("Documents and Codes Tab")
            step("Documents and Codes Tab", "Navigating to Documents and Codes Tab")
            page1.wait_for_timeout(2000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Navigating to Documents and Codes Tab")
            page1.get_by_text("Documents and Codes").click()
            page1.wait_for_timeout(2000)
            page1.wait_for_load_state("domcontentloaded")
            screenshot(page1, "docsandcodes_tab")
            end_step()

    # Create & Send Query 
            section_break("Query Functionality Check")
            step("Check Query Form", "Opening Query Form")
            page1.get_by_role("button", name="Create Query...").click()
            logger.info("Query Form Loaded. Opening Provider Communication Dropdown")
            page1.wait_for_timeout(2500)
            page1.wait_for_load_state("domcontentloaded")
            screenshot(page1, "queryform")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("#qframe").content_frame.get_by_text("Provider Communication").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            screenshot(page1, "provider_comms")
            logger.info("Confirmed Provider Communications")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("#qframe").content_frame.get_by_role("button").filter(has_text="Cancel").click()
            logger.info("Closing Query Form")
            page1.wait_for_timeout(1000)
            end_step()

    # Verify Account Opens Properly & Options Appear
            section_break("Closing Account")
            step("Close Account", "Closing Account")
            page1.wait_for_timeout(3000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Patient Successfully Loaded. Closing Account")
            page1.get_by_role("button", name="Close").click()
            end_step() 

# Move Back to Dashboard
        section_break("Closing Session")
        step("Close Session", "Navigating Back to Dashboard")
        page.wait_for_timeout(2000) 
        page.wait_for_load_state("domcontentloaded")
        page.get_by_role("button", name=" Back to Dashboard").click()
        page.wait_for_timeout(2000)
        page.wait_for_load_state("domcontentloaded")
        logger.info("Test Passed Successfully!")
        end_step()

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