import os
import sys
import time
import re
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
# ==========================================================================================================================================
# Configuration
# ==========================================================================================================================================
SYSTEM      = "CAC"
ENVIRONMENT = "Pre-Production"
PILLAR      = "Nashville"
RUN_TYPE    = "Mini Regression"
TEST_SET    = "ED"
# ==========================================================================================================================================
# Bootstrap — locate project root and import shared runtime
# ==========================================================================================================================================
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
from orbit360.utils.orbit_script_helpers import (
    init_helpers,
    WAIT_PROFILES, DEFAULT_TIMEOUT, RETRY_COUNT,
    wait_with_intervention, wait_for_data_load,
    safe_click, safe_fill, safe_screenshot, step_with_pause,
    pre_run_check,
)
ctx    = setup(SYSTEM, ENVIRONMENT, PILLAR, RUN_TYPE, TEST_SET)
logger = ctx.logger
init_helpers(ctx)
# ==========================================================================================================================================
# Main Run
# ==========================================================================================================================================
def run(playwright: Playwright) -> None:
    run_start_time = time.time()
    browser = None
    context = None
    page    = None
    page1   = None
    try:
        pre_run_check("https://XRDCWTWEBCAC07B.HCA.CORPAD.NET/3M_360App")
        browser = playwright.chromium.launch(
            headless=False,
            args=["--start-maximized"]
            )
        context = browser.new_context(no_viewport=True)
        start_trace(context)
        page = context.new_page()
# ==========================================================================================================================================
# Navigate to CAC Dashsboard
# ==========================================================================================================================================
        section_break("CAC Dashboard")
        step("Nashville Pre-Production CAC Dashboard", "Launching Browser & Navigating to Dashboard")

        page.goto("https://XRDCWTWEBCAC07B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")

        wait_for_data_load(page, "CAC Dashboard", profile="popup")
        screenshot(page,"cac_dashboard")

        end_step()
# ==========================================================================================================================================
# HIM Coding
# ==========================================================================================================================================
        section_break("HIM Coding Dashboard")
        step("Check HIM Coding Dashboard Functionality", "Navigating to HIM Coding")

        page.get_by_text("HIM Coding").click()
        wait_for_data_load(page, "HIM Coding Page", profile="popup")
        screenshot(page, "cac_dashboard")

        end_step()
# ==========================================================================================================================================
# ED Worklist
# ==========================================================================================================================================
        section_break("ED Worklist")
        step("ED Worklist", "Navigating to ED Worklist")

        logger.info("Selecting ED Worklist")
        page.get_by_text("ED", exact=True).click()
        wait_for_data_load(page, "ED Worklist", profile="popup")
        screenshot(page, "him_coding_dashboard")

        end_step()
# =========================================================================================================================================
# Ready Bucket
# ==========================================================================================================================================  
        section_break("Ready Bucket")
        step("Ready Bucket", "Navigating to Ready Bucket")

        logger.info("Selecting Ready Bucket")
        page.get_by_text("Ready", exact=True).nth(3).click()
        wait_for_data_load(page, "Ready Bucket", profile="popup")
        screenshot(page, "ed_ready_bucket")

        end_step()
# ==========================================================================================================================================
# Manual Patient Selection
# ==========================================================================================================================================  
        section_break("Select Patient Record")
        step("Select Patient", "Select a Patient Record")

        manual_prompt(
            message="Select a patient record",
            completion_note="Patient Selected"
        )

        end_step()
# ==========================================================================================================================================
# Patient Account
# ==========================================================================================================================================  
        section_break("Patient Validation Check")
        step("Confirm Patient Loaded", "Patient Record Loaded")

        with page.expect_popup() as page1_info:
            pass
        page1 = page1_info.value
        page1.wait_for_load_state("domcontentloaded")
        page1.bring_to_front()
        screenshot(page1, "patient_profile")
        patient_anchor = page1.locator("#selDis-dropdownPanelTrigger")
        screenshot(page1, "patient_record")

        end_step()
# ==========================================================================================================================================
# Navigating to Documents and Codes Tab
# ==========================================================================================================================================
        section_break("Navigate to Document and Codes Tab")
        step("Doc and Codes Tab", "Navigating to Document and Codes Tab")

        page1.wait_for_timeout(1000)  
        page1.get_by_text("Documents and Codes").click()
        page1.wait_for_timeout(1000)

        end_step()
# ==========================================================================================================================================
# Update Discharge Disposition
# ==========================================================================================================================================  
        section_break("Update Discharge Disposition")
        step("Updating Discharge Disposition", "Updating Discharge Disposition")

        page1.wait_for_load_state("domcontentloaded")
        page1.wait_for_timeout(1000)
        logger.info("Selecting Discharge Disposition Dropdown")
        page1.locator("#selDis-dropdownPanelTrigger").click()

        page1.wait_for_timeout(1000)
        page1.locator("#selDis-filterInput").click()

        page1.wait_for_timeout(1000)
        page1.locator("#selDis-filterInput").fill("AMA - 07 - AMA - Against Medical Advice")

        page1.get_by_text("AMA - 07 - AMA - Against Medical Advice").click()
        logger.info("Discharge Disposition Updated to AMA")

        end_step()
# ==========================================================================================================================================
# Place on Hold
# ==========================================================================================================================================
        section_break("Place Account on Hold")
        step("Place Account on Hold", "Placing Account on Hold")

        page1.wait_for_timeout(1000)
        page1.get_by_role("button").filter(has_text="Ready").click()

        page1.wait_for_timeout(1000)
        page1.get_by_role("menuitem", name="Hold").click()
        page1.wait_for_timeout(1000)
        logger.info("Hold Menu Opening")
        screenshot(page1, "hold_menu")

        page1.wait_for_timeout(1000)        
        page1.locator("#holdReasonLabel-dropdownPanelTrigger span").click() # Filter Search for H&P
        logger.info("Filtering Options and Selecting Hold Reason")

        page1.wait_for_timeout(1000)
        page1.locator("#holdReasonLabel-filterInput").click()
        screenshot(page1, "hold_reason")
        logger.info("Typing Hold Reason")

        page1.wait_for_timeout(1000)
        page1.locator("#holdReasonLabel-filterInput").fill("3M-3M UPDATE ISSUE")

        page1.wait_for_timeout(1000)
        logger.info("Clicking Hold Reason Option")
        page1.get_by_role("listitem", name="3M-3M UPDATE ISSUE").locator("div").nth(1).click()
        logger.info("Hold Reason Selected")
        screenshot(page1, "hold_selected")

        logger.info("Selecting Hold Button")
        page1.locator("#holdReasonForm").get_by_role("button").filter(has_text="Hold").click() # Click Hold Button

        end_step()
# ==========================================================================================================================================
# Close Account
# ==========================================================================================================================================
        section_break("Move to Next Account & Close")
        step("Next Account", "Closing Account")

        page1.wait_for_load_state("domcontentloaded")
        page1.wait_for_timeout(1000)
        page1.get_by_role("button").filter(has_text=re.compile(r"^Next$")).click()
        page1.get_by_text("Close").click()
        logger.info("Account Closed")

        end_step()
# ==========================================================================================================================================
# Hold Bucket
# ==========================================================================================================================================
        section_break("Check Hold Bucket")
        step("Verify Account on Hold", "Verify Account Lands on Hold Bucket")

        logger.info("Moving to Hold Bucket")
        page.locator("span").filter(has_text=re.compile(r"^Hold$")).click()
        wait_for_data_load(page, "Hold Bucket", profile="popup")
        screenshot(page, "hold_bucket")
        logger.info("Test Run Successfully")

        end_step()
# ==========================================================================================================================================    
    except Exception as e:
        handle_failure(e, page1 or page)

    finally:
        if context:
            save_trace(context)
        if browser:
            browser.close()

        total_duration = time.time() - run_start_time
        logger.info(f"Total Run Duration | {format_duration(total_duration)}")

with sync_playwright() as playwright:
    run(playwright)