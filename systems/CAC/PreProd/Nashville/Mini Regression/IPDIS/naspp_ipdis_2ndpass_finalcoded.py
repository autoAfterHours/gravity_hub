import os
import sys
import time
import re
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
# ============================================================================================================================================================
# Configuration
# ============================================================================================================================================================
SYSTEM      = "CAC"
ENVIRONMENT = "Pre-Production"
PILLAR      = "Nashville"
RUN_TYPE    = "Mini Regression"
TEST_SET    = "IPDIS"
# ============================================================================================================================================================
# Bootstrap — locate project root and import shared runtime
# ============================================================================================================================================================
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
# ============================================================================================================================================================
from orbit360.backend.orbit_context import (
    setup, step, end_step, section_break,
    screenshot, manual_prompt, handle_failure, format_duration,
    crs_frame, start_trace, save_trace,
    )
from orbit360.utils.orbit_frames import CACFrames
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
# ============================================================================================================================================================
# Main Run
# ============================================================================================================================================================
def run(playwright: Playwright) -> None:
    run_start_time = time.time()
    browser = None
    context = None
    page    = None
    page1   = None
    page2   = None
    try:
        pre_run_check("https://XRDCWTWEBCAC07B.HCA.CORPAD.NET/3M_360App")
        browser = playwright.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(no_viewport=True)
        start_trace(context)
        page = context.new_page()
# ============================================================================================================================================================
# Navigate to CAC Dashsboard
# ============================================================================================================================================================
        section_break("CAC Dashboard")
        step("Nashville Pre-Production CAC Dashboard", "Launching Browser & Navigating to Dashboard")
        
        page.goto("https://XRDCWTWEBCAC07B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")
        wait_for_data_load(page, "CAC Dashboard", profile="popup")
        screenshot(page, "cac_dashboard")

        end_step()
# ==========================================================================================================================================
# Navigate to Conurrent Coding Dashboard
# ==========================================================================================================================================
        section_break("Concurrent Coding Dashboard")
        step("Check Concurrent Coding Dashboard Functionality", "Navigating to Concurrent Coding Dashboard")

        logger.info("Navigating to Concurrent Coding Dashboard")
        page.get_by_text("Concurrent Coding").click()
        wait_for_data_load(page, "Concurrent Coding Page", profile="popup")
        screenshot(page, "concurrent_coding_db")

        end_step()
# ==========================================================================================================================================
# Navigate to Discharged All Worklist
# ==========================================================================================================================================
        section_break("Discharged All Worklist")
        step("Open Discharged All Worklist", "Openging Discharged All Worklist")

        logger.info("Selecting Discharged All Worklist")
        page.get_by_text("Discharged All", exact=True).click()
        wait_for_data_load(page, "Discharged All Worklist", profile="popup")
        screenshot(page, "concurrent_coding_dashboard")
        
        end_step()
# ============================================================================================================================================================
# Manual Patient Selection
# ============================================================================================================================================================  
        section_break("Select Patient Record")
        step("Select Patient", "Select a Patient Record")

        manual_prompt(
            message="Select a patient record",
            completion_note="Patient Selected"
        )

        end_step()
# ============================================================================================================================================================
# Patient Account
# ============================================================================================================================================================  
        section_break("Patient Validation Check")
        step("Confirm Patient Loaded", "Patient Record Loaded")

        with page.expect_popup() as page1_info:
            pass
        page1 = page1_info.value
        page1.bring_to_front()
        frames = CACFrames(page1)
        screenshot(page1, "patient_record")

        end_step()
# ============================================================================================================================================================
# Navigate to Documents and Codes
# ============================================================================================================================================================
        section_break("Documents and Codes")
        step("Documents and Codes", "Navigating to Documents and Codes")

        page1.wait_for_timeout(1000)
        page1.get_by_text("Documents and Codes").click()
        page1.wait_for_timeout(1000)
        logger.info("Documents and Codes Tab Selected")
        screenshot(page1, "doc_codes_tab")

        end_step()
# ============================================================================================================================================================
# Move Account from Hold to Ready
# ============================================================================================================================================================
        section_break("Move Account from Hold to Ready")
        step("Update Patient Status", "Update Patient Status to Ready")

        logger.info("Moving Account from Hold to Ready")
        page1.get_by_text("Hold").nth(1).click()
        page1.wait_for_timeout(1000)
        logger.info("Dropdown Selected. Selecting Ready")
        page1.wait_for_timeout(1000)

        page1.get_by_text("Ready").click()
        page1.wait_for_timeout(1000)
        logger.info("Account Moved to Ready")
        screenshot(page1, "account_updated")

        end_step()
# ============================================================================================================================================================
# Open Codefinder
# ============================================================================================================================================================
        section_break("Open Codefinder")
        step("Open Codefinder", "Opening Codefinder")

        logger.info("Open Codefinder")
        page1.get_by_role("button", name=" Codefinder").click()
        page1.wait_for_timeout(1000)
        logger.info("Codefinder Opened")
        screenshot(page1, "codefinder_opened")

        end_step()
# ============================================================================================================================================================
# Complete Account (1st Try)
# ============================================================================================================================================================
        section_break("Complete Account - 1st Try")
        step("Complete Account", "Completing Account")

        logger.info("Completing Account")
        frames.codefinder.get_by_role("button", name="Complete").click()
        page1.wait_for_timeout(1000)
        logger.info("Account Completed")
        screenshot(page1, "complete_acct_1sttry")

        end_step()
# ============================================================================================================================================================
# Add DX I10 to Account
# ============================================================================================================================================================
        section_break("Add Diagnosis Code (I10)")
        step("Add DX Code", "Adding DX Code")

        try:
            frames.codefinder.get_by_role("button", name="Add Diagnosis").click()
        except:
            manual_prompt(
                message="Check and Ensure Add Diagnosis Button is Visible.",
                completion_note="Add Diagnois Button Now Available."
            )
        logger.info("Add Diagnosis Button Selected. Adding Codes.")
        frames.codefinder.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        frames.codefinder.get_by_role("textbox", name="Enter Keyword or Code:").fill("I10")
        page1.wait_for_timeout(1000)
        screenshot(page1, "i10_typed")
        frames.codefinder.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        frames.codefinder.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        page1.wait_for_timeout(1000)
        frames.codefinder.get_by_role("button", name="OK").click()
        page1.wait_for_timeout(1000)
        logger.info("I10 Added to Account")
        screenshot(page1, "i10_added")

        end_step()
# ============================================================================================================================================================
# Complete Account (2nd Try)
# ============================================================================================================================================================
        section_break("Complete Account - 2nd Try")
        step("Complete Account", "Completing Account")

        frames.codefinder.get_by_role("button", name="Complete").click()
        page1.wait_for_timeout(1000)
        logger.info("Account Completed")
        screenshot(page1, "complete_acct_2ndtry")

        end_step()
# ============================================================================================================================================================
# Present on Admission
# ============================================================================================================================================================
        section_break("Present on Admission")
        step("POA", "Present on Admission")

        screenshot(page1, "poa_prompt")
        page1.wait_for_timeout(1000)
        logger.info("Present On Admission Prompt")
        page1.wait_for_timeout(1000)

        frames.codefinder.get_by_role("button", name="Yes").click()
        page1.wait_for_timeout(1000)
        logger.info("Yes Selected on POA Pop Up")

        manual_prompt(
            message="Select Y, and Ok",
            completion_note="Option Selected"
        )            

        page1.wait_for_timeout(1000)
        logger.info("POA Added Successfully")
        screenshot(page1, "poa_added")

        end_step()
# ============================================================================================================================================================
# Complete Account (3rd Try)
# ============================================================================================================================================================
        section_break("Complete Account - 3rd Try")
        step("Complete Account", "Completing Account")

        logger.info("Completing Account")
        frames.codefinder.get_by_role("button", name="Complete").click()
        page1.wait_for_timeout(3000)
        logger.info("Account Completed")
        screenshot(page1, "account_completed_3rdtry")

        end_step()
# ============================================================================================================================================================
# Submit Account
# ============================================================================================================================================================
        section_break("Submit Account")
        step("Submit Account", "Submitting Account")

        page1.get_by_role("button", name="Submit").click()
        page1.wait_for_timeout(3000)
        logger.info("Account Submitted")
        screenshot(page1, "account_submitted")

        end_step()        
# ============================================================================================================================================================
# Indicators Tab
# ============================================================================================================================================================
        section_break("Indicators Tab")
        step("Indicators Tab", "Navigating to Indicators Tab")

        page1.wait_for_timeout(2000)
        page1.get_by_text("Indicators").click()
        page1.wait_for_timeout(3000)
        logger.info("Indicators Tab Opened")
        screenshot(page1, "indicators_tab")

        end_step()        
# ============================================================================================================================================================
# Impact/ROI Tab
# ============================================================================================================================================================
        section_break("Impact/ROI Tab")
        step("Impact/ROI Tab", "Navigating to Impact/ROI Tab")

        page1.wait_for_timeout(1000)
        page1.get_by_text("Impact/ROI").click()
        page1.wait_for_timeout(3000)
        logger.info("Impact/ROI Tab Opened")
        screenshot(page1, "impact_roi")

        end_step()        
# ============================================================================================================================================================
# Close Account
# ============================================================================================================================================================
        section_break("Close Account")
        step("Close Account", "Closing Account")

        page1.wait_for_timeout(1000)
        page1.get_by_role("button", name="Close").click()
        page.wait_for_timeout(4000)
        logger.info("Account Closed")

        end_step()        
# ============================================================================================================================================================
# Wrap Up Test
# ============================================================================================================================================================        
        section_break("Wrap Up Test")
        step("Wrap Up Test", "Finishing Test")

        page.wait_for_timeout(4000)
        logger.info("Closing Session")
        page.close()
        logger.info("Test Passed Successfully!")

        end_step()
# ============================================================================================================================================================
    except Exception as e:
        handle_failure(e, page2, page1 or page)

    finally:
        if context:
            save_trace(context)
        if browser:
            browser.close()
        total_duration = time.time() - run_start_time
        logger.info(f"Total Run Duration | {format_duration(total_duration)}")

with sync_playwright() as playwright:
    run(playwright)