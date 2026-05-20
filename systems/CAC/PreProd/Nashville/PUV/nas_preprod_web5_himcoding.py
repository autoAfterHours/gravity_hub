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
ENVIRONMENT = "PreProd"
PILLAR      = "Nashville"
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
        pre_run_check("https://XRDCWTWEBCAC07B.HCA.CORPAD.NET/3M_360App")
        browser = playwright.chromium.launch(
            headless=False,
            args=["--start-maximized"]
            )
        context = browser.new_context(no_viewport=True)
        start_trace(context)
        page = context.new_page()

    # Navigate to CAC Dashboard Loaded
        section_break("CAC Dashboard")
        step("CAC Dashboard", "Opening CAC Dashboard")
        page.goto("https://XRDCWTWEBCAC07B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        screenshot(page, "cac_dashboard")
        logger.info("CAC Dashboard Successfully Loaded")
        end_step()

    # Navigate to HIM Coding Dashboard
        section_break("HIM Coding Dashboard")
        step("HIM Coding", "Navigating to HIM Coding Dashboard")
        page.wait_for_timeout(4000)
        page.wait_for_load_state("domcontentloaded")
        page.get_by_text("HIM Coding").click()
        page.wait_for_timeout(5000)
        page.wait_for_load_state("domcontentloaded")
        screenshot(page, "him_coding_db")
        logger.info("HIM Coding Dashboard Loaded Successfully.")
        end_step()

        # ED Worklist
        step("ED", "Navigating to ED Worklist")
        page.get_by_text("ED", exact=True).click()
        page.wait_for_timeout(4000)
        page.wait_for_load_state("domcontentloaded")
        screenshot(page, "him_coding_ed_wl_loaded")
        logger.info("ED Worklist Loaded Successfully.")
        end_step()

        # Ready Bucket
        step("Ready", "Navigating to Ready Bucket")
        page.get_by_text("Ready", exact=True).nth(3).click()
        page.wait_for_timeout(4000)
        page.wait_for_load_state("domcontentloaded")
        screenshot(page, "him_coding_ready_bucket")
        logger.info("Ready Bucket Loaded Successfully.")
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

    # Create & Send Query 
            section_break("Query Functionality Check")
            step("Check Query Form", "Opening Query Form")
            page1.get_by_role("button").filter(has_text="Create Query").click()
            logger.info("Query Form Loaded. Opening Provider Communication Dropdown")
            page1.wait_for_timeout(2500)
            page1.wait_for_load_state("domcontentloaded")
            screenshot(page1, "queryform")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            page1.get_by_text("Provider Communication").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            screenshot(page1, "provider_comms")
            logger.info("Confirmed Provider Communications")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            page1.get_by_role("button").filter(has_text="Cancel").click()
            logger.info("Closing Query Form")
            page1.wait_for_timeout(1000)
            end_step()

    # Select Pop-Out Button
            section_break("Pop-Out Functionality")
            step("Select Pop-Out Button","Opening Pop-Out")
            logger.info("Selecting Pop-Out Button")
            page1.get_by_role("button").filter(has_text="Pop-Out").click()
            with page1.expect_popup() as page2_info:
                page2 = page2_info.value
            page2.wait_for_timeout(2000)
            page2.wait_for_load_state("domcontentloaded")
            end_step()
            
    # Prompt to Allow Pop Up Blocker & Continue
            section_break("Pop Up Manual Prompt")    
            step("PopUp", "Allow Pop Up Blocker") 
            manual_prompt(
                message="Allow Pop Up Blocker",
                completion_note="Window Opening"
            )
            end_step()
            
    # Pop Back In to Account
            section_break("Pop Back In to Chart")
            step("PopIn", "Popping Back in to Chart")
            screenshot(page2, "pop_out_view")
            page2.wait_for_timeout(3000)
            page2.wait_for_load_state("domcontentloaded")
            logger.info("Popped Out View Open")
            page2.get_by_role("button").click()
            end_step()

    # Verify Account Opens Properly & Options Appear
            section_break("Closing Account")
            step("Close Account", "Closing Account")
            page1.wait_for_timeout(3000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Patient Successfully Loaded. Closing Account")
            page1.get_by_text("Close").click()
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