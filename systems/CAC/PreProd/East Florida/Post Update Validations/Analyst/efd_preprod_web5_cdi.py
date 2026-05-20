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
PILLAR      = "East Florida"
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
        page.goto("https://XRDCWTWEBCAC23B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        screenshot(page, "cac_dashboard")
        logger.info("CAC Dashboard Successfully Loaded")
        end_step()

    # Navigate to CDI Dashboard
        section_break("CDI Dashboard")
        step("CDI", "Open CDI Prioirty ALL Worklist")
        logger.info("Selecting CDI Worklist")
        page.wait_for_timeout(2000)
        page.wait_for_load_state("domcontentloaded")
        logger.info("Accessing CDI Worklist")
        page.locator(".c_graphic_hover_rect").first.click()
        page.wait_for_timeout(2000)
        page.wait_for_load_state("domcontentloaded")
        screenshot(page, "cdi_dashboard")
        logger.info("CDI Worklist Loaded")
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
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(2500)
            screenshot(page1, "queryform")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(1000)
            page1.locator("#qframe").content_frame.get_by_text("Provider Communication").click()
            screenshot(page1, "provider_comms")
            logger.info("Confirmed Provider Communications")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(500)
            page1.locator("#qframe").content_frame.get_by_role("button").filter(has_text="Cancel").click()
            logger.info("Closing Query Form")
            page1.wait_for_timeout(1000)
            end_step()

    # Codefinder - Help - Coding & Reimbursement System  
            section_break("Help Button - Coding & Reimbursement System")  
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(1000)
            logger.info("Clicking Help Button")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="Help").click()
            page1.wait_for_timeout(500)
            logger.info("Clicking About Button")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="About ➧").click()
            page1.wait_for_timeout(1000)
            logger.info("Selecting Coding & Reimbursement System")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Coding & Reimbursement System").click()
            page1.wait_for_timeout(3000)
            logger.info("Closing Menu")
            screenshot(page1, "crs_menu")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
            logger.info("Version Validated")

    # Codefinder - Help - Computer Assisted Coding
            section_break("Help Button - Computer Assisted Coding") 
            logger.info("Clicking Help Button")    
            page1.wait_for_timeout(1000)
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="Help").click()
            page1.wait_for_timeout(500)
            logger.info("Clicking About Button")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="About ➧").click()
            page1.wait_for_timeout(1000)
            logger.info("Selecting Computer Assisted Coding")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Computer Assisted Coding").click()
            page1.wait_for_timeout(3000)
            logger.info("Closing Menu")
            screenshot(page1, "cac_menu")
            page1.locator("#cac_frame").content_frame.get_by_role("button", name="OK").click()
            logger.info("Version Validated")
            page1.wait_for_timeout(2000)
            logger.info("Closing Account")
            page1.get_by_role("button", name="Close").click()
            logger.info("Test Passed!")
        
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