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
PILLAR      = "Tampa"
RUN_TYPE    = "Mini Regression"
TEST_TYPE    = "ED"
# ==========================================================================================================================================
# Bootstrap — locate project root and import shared runtime
# ==========================================================================================================================================
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
# ==========================================================================================================================================
from orbit360.backend.orbit_context import (
    setup, step, end_step, section_break,
    screenshot, manual_prompt, handle_failure, format_duration,
    crs_frame, start_trace, save_trace,
    claim_excel_row, release_excel_row,
)
from orbit360.utils.orbit_script_helpers import (
    init_helpers,
    WAIT_PROFILES, DEFAULT_TIMEOUT, RETRY_COUNT,
    wait_with_intervention, wait_for_data_load,
    safe_click, safe_fill, safe_screenshot, step_with_pause,
    pre_run_check,
)
ctx    = setup(SYSTEM, ENVIRONMENT, PILLAR, RUN_TYPE, TEST_TYPE)
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
    acct_number = None
    admit_date = None
    attending_md = None
    admitting_md = None
    e       = None
    admit_date = acct_number = attending_md = admitting_md = ""
    row_idx = -1

    # ── Claim one account from the pool ──────────────────────────────────────
    patient, row_idx = claim_excel_row()
    if row_idx == -1:
        logger.info("No account records available — pool exhausted.")
        return
    acct_number = patient.get("AccountNumber", "")
    logger.info(f"Account claimed: {acct_number} (row {row_idx + 1})")
# ==========================================================================================================================================
    def _ctx(*fields):
        labels = {
            "admit":      ("Admit",      lambda: admit_date),
            "acct_number": ("Account",   lambda: acct_number),
            "attending":  ("Attending",  lambda: attending_md),
            "admitting":  ("Admitting",  lambda: admitting_md),
        }
        parts = [f"{labels[f][0]}: {labels[f][1]()}" for f in fields if labels[f][1]()]
        return f"  [{' | '.join(parts)}]" if parts else ""
    try:
        pre_run_check("https://XRDCWTWEBCAC06B.HCA.CORPAD.NET/3M_360App")
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
        step("Tampa Pre-Production CAC Dashboard", "Launching Browser & Navigating to Dashboard")

        page.goto("https://XRDCWTWEBCAC06B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")
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
# ==========================================================================================================================================
# Coded Today Bucket
# ==========================================================================================================================================
        section_break("Coded Today Bucket")
        step("Coded Today Bucket", "Navigating to Coded Today Bucket")
        logger.info("Selecting Coded Today Bucket")
        page.get_by_text("Coded Today").click()
        wait_for_data_load(page, "Coded Today Bucket", profile="popup")
        screenshot(page, "coded_today_bucket")
        end_step()
# ==========================================================================================================================================
# Search for Patient Account
# ========================================================================================================================================== 
        section_break("Patient Validation Check")
        step("Confirm Patient Loaded", "Searching for Patient")
        page.get_by_role("textbox", name="Type visit ID or patient name").click()
        page.wait_for_timeout(1000)
        page.get_by_role("textbox", name="Type visit ID or patient name").fill(acct_number)
        page.wait_for_timeout(2000)
        screenshot(page, "patient_search")
        logger.info("Opening Patient Record")
        with page.expect_popup() as page1_info:
            page.get_by_role("row", name=f"Visit ID: {acct_number}").locator("#visitid").click()
            page1 = page1_info.value
            page1.bring_to_front()
            logger.info("Patient Record Open")
            screenshot(page1, "patient_record")
            end_step()
# ==========================================================================================================================================
# Move Account from Coded to Ready
# ==========================================================================================================================================
        section_break("Move Account from Coded to Ready")
        step("Update Account from Coded to Ready", "Updating Account to Ready")
        page1.wait_for_timeout(1000)
        page1.get_by_role("button").filter(has_text="Coded").click()
        logger.info("Moving Account to Ready Status")
        page1.wait_for_timeout(1000)
        page1.get_by_role("menuitem", name="Ready").click()
        page1.wait_for_timeout(1000)
        screenshot(page1, "updated_account_status_ready")
        end_step()
# ==========================================================================================================================================
# Launching Worksheet Services
# ==========================================================================================================================================
        section_break("Launching Worksheet Services")
        step("WSS Code", "Launching Worksheet Services")
        logger.info("Status Updated to Ready. Launching WSS Icon")
        page1.wait_for_timeout(1000)
        page1.locator("m-cac iframe").content_frame.get_by_role("button", name="Launch Worksheet Services").click()
        page1.wait_for_timeout(1000)        
        end_step()
# ==========================================================================================================================================
# Infusion & Injections
# ==========================================================================================================================================
        section_break("Infusion & Injections")
        step("I&I", "Opening Infusions & Injections Screen")
        try:
            i_i = page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("tab", name="Infusion & Injection")
            if i_i.is_visible():
                safe_click(i_i, "Infusions & Injections Button")
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Add Injection").click()
                page1.wait_for_timeout(500)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_text_injection_0_drug_1").click()
                page1.wait_for_timeout(500)
                logger.info("Adding 2 for Drug")
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_text_injection_0_drug_1").fill("2")
                page1.wait_for_timeout(500)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_text_injection_0_drug_1").press("Tab")
                page1.wait_for_timeout(500)
                logger.info("Adding 1 for Quanity")
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_number_injection_0_quantity_1").fill("1")
                page1.wait_for_timeout(500)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_number_injection_0_quantity_1").press("Tab")
                page1.wait_for_timeout(500)
                manual_prompt(
                    message="Enter Injection Date/Time",
                    completion_note="Data Entered")
                page1.wait_for_timeout(1000)
            else:
                raise Exception()
        except:
            logger.info("I&I not available, moving to next step")
        try:
            calculate_btn = page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Calculate")
            if calculate_btn.is_visible():
                safe_click(calculate_btn, "Calculate Button")
            else:
                raise Exception()
        except:
            logger.info("Calculate not available, moving to next step")        
        manual_prompt(
            message="Update & Calculate Any Remaining Codes. This will also require the Select All button be selected, and any new codes marked as Do Not Charge",
            completion_note="Final Scan Completed")
        page1.wait_for_timeout(1000)
        page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Process").click()
        page1.wait_for_timeout(1000)
        logger.info("I&I Code Added. Processing")       
        end_step()
# ==========================================================================================================================================
# Complete Account
# ==========================================================================================================================================        
        section_break("Complete Account")
        step("Complete Account", "Completing Account")
        page1.wait_for_timeout(1000)
        try:
            complete = page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete")
            if complete.is_visible():
                complete = page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
            else:
                raise Exception()
        except:
            manual_prompt(
            message="Complete button not working. Review Account and Clear Blocker. Once Complete hit Continue in Orbit to pick up next step.",
            completion_note="Issue corrected. Moving to next step.")  
        page1.wait_for_timeout(1000)
        screenshot(page1, "account_completed")
        logger.info("Account has been completed")        
        end_step()
# ==========================================================================================================================================
# Submit Account
# ==========================================================================================================================================
        section_break("Submit Account")
        step("Submit Account", "Submitting Account to Coded Status")
        page1.get_by_role("button").filter(has_text="Submit & Next").click()
        page1.wait_for_timeout(1000)
        logger.info("Account Submitted")
        end_step()
# ==========================================================================================================================================
# Close Account
# ==========================================================================================================================================
        section_break("Close Account")
        step("Close Account", "Closing Account")
        page1.wait_for_timeout(1000)
        logger.info("Closing Next Account")
        page1.get_by_text("Close").click()
        end_step()
# ==========================================================================================================================================
# Navigate to Coded Today Bucket
# ==========================================================================================================================================
        section_break("Wrap Up & Confirm Account Remains on Coded Today Bucket")
        step("Navigate to Coded Today Bucket", "Navigating to Coded Today Bucket")
        page.bring_to_front()
        logger.info("Navigating to Coded Today")
        page.get_by_text("Coded Today").click()
        wait_for_data_load(page, "Coded Today", profile="popup")
        screenshot(page,"coded_account")
        page.close()
        logger.info("Test Run Completed Successfully!")
        end_step()
# ==========================================================================================================================================
        release_excel_row(row_idx, "PASS")
        logger.info(f"Account {acct_number} — PASS")

    except Exception as e:
        if row_idx != -1:
            release_excel_row(row_idx, "FAIL", notes=str(e))
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