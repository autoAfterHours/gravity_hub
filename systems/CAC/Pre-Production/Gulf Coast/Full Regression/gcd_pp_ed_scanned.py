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
PILLAR      = "Gulf Coast"
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
        pre_run_check("https://FWDCWTWEBCAC24B.HCA.CORPAD.NET/3M_360App")
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
        step("Gulf Coast Pre-Production CAC Dashboard", "Launching Browser & Navigating to Dashboard")
        page.goto("https://FWDCWTWEBCAC24B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")
        page.wait_for_timeout(15000)
        screenshot(page,"cac_dashboard")
        end_step()
# ==========================================================================================================================================
# HIM Coding
# ==========================================================================================================================================
        section_break("HIM Coding Dashboard")
        step("Check HIM Coding Dashboard Functionality", "Navigating to HIM Coding")
        page.get_by_text("HIM Coding").click()
        page.wait_for_timeout(15000)
        screenshot(page, "cac_dashboard")
        end_step()
# ==========================================================================================================================================
# ED Worklist
# ==========================================================================================================================================
        section_break("ED Worklist")
        step("ED Worklist", "Navigating to ED Worklist")
        logger.info("Selecting ED Worklist")
        page.get_by_text("ED", exact=True).click()
        page.wait_for_timeout(15000)
        screenshot(page, "him_coding_dashboard")
        end_step()
# =========================================================================================================================================
# Not Ready Bucket
# ==========================================================================================================================================  
        section_break("Not Ready Bucket")
        step("Not Ready Bucket", "Navigating to Not Ready Bucket")
        logger.info("Selecting Not Ready Bucket")
        page.locator("span").filter(has_text=re.compile(r"^Not Ready$")).click() 
        page.wait_for_timeout(30000)
        screenshot(page, "ed_ready_bucket")
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
# Navigating to Documents and Codes Tab
# ==========================================================================================================================================
        section_break("Navigate to Document and Codes Tab")
        step("Doc and Codes Tab", "Navigating to Document and Codes Tab")
        page.wait_for_timeout(10000)
        page1.get_by_text("Documents and Codes").click()
        page1.wait_for_timeout(2000)
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
        page1.locator("#holdReasonLabel-filterInput").fill("ER-MISSING ER REPORT/T- SHEET")
        page1.wait_for_timeout(1000)
        logger.info("Clicking Hold Reason Option")
        page1.get_by_role("listitem", name="ER-MISSING ER REPORT/T- SHEET").locator("div").nth(1).click()
        logger.info("Hold Reason Selected")
        screenshot(page1, "hold_selected")
        logger.info("Selecting Hold Button")
        page1.locator("#holdReasonForm").get_by_role("button").filter(has_text="Hold").click() # Click Hold Button
        end_step()
# ========================================================================================
        section_break("Add Diagnois Code (I10)")
        step("Add I10", "Adding Diagnosis Code (I10)")

        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("I10")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Essential (primary)").click(button="right")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Copy Code as Primary").click()
        page1.wait_for_timeout(1000)
        logger.info("Primary DX Code Copied Successfully")

        end_step()
# ==========================================================================================================================================
# Launch WSS
# ========================================================================================================================================== 
        section_break("Worksheet Services")
        step("WSS", "Selecting WSS")
        page1.wait_for_timeout(1000)
        page1.locator("m-cac iframe").content_frame.get_by_role("button", name="Launch Worksheet Services").click()
        page1.wait_for_timeout(2000)
        screenshot(page1, "wss")
        end_step()
# ==========================================================================================================================================
# WSS - E/M 
# ==========================================================================================================================================
        section_break("E&M")
        step("E&M", "Opening E&M Screen")
        try:
            btn = page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Clear")
            if btn.is_visible():
                safe_click(btn, "Clear Button")
            else:
                raise Exception()
        except:
            logger.info("Clear not available, moving to next step")
        page1.wait_for_timeout(1000)
        page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#item-4000185417-checkbox-box").click()
        page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Calculate").click()
        logger.info("E&M Codes Added")
        end_step()

# ==========================================================================================================================================
# WSS - Infusion & Injections
# ==========================================================================================================================================
        section_break("Infusion & Injections")
        step("I&I", "Opening Infusions & Injections Screen")
        page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("tab", name="Infusion & Injection").click()
        try:
            calculate_btn = page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Calculate")
            if calculate_btn.is_visible():
                calculate_btn = page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Calculate").click()
            else:
                raise Exception()
        except:
            logger.info("Calculate not available, moving to next step")

        manual_prompt(
            message="Update & Calculate Any Remaining Codes. This will also require the Select All button be selected, and any new codes marked as Do Not Charge",
            completion_note="Final Scan Completed"
        )
        page1.wait_for_timeout(1000)
        page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Process").click()
        page1.wait_for_timeout(1000)
        logger.info("I&I Code Added. Processing")
        end_step()
# ==========================================================================================================================================
# Close Account
# ==========================================================================================================================================
        section_break("Move to Next Account & Close")
        step("Next Account", "Closing Account")
        page1.wait_for_load_state("domcontentloaded")
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
        page1.wait_for_timeout(2000)
        page1.get_by_role("button").filter(has_text="Submit").click()    
        page1.pause()    
        page1.wait_for_timeout(2000)
        try:
            next_btn = page1.get_by_role("button").filter(has_text=re.compile(r"^Next$"))
            if next_btn.is_visible():
                page1.get_by_role("button").filter(has_text=re.compile(r"^Next$")).click()
                page1.wait_for_timeout(3000)
                page1.get_by_text("Close").click()
            else:
                raise Exception()
        except:
            logger.info("Next Button not available, Closing Account.")
            page1.get_by_text("Close").click()
        logger.info("Account Closed")
        end_step()
# ==========================================================================================================================================
# Hold Bucket
# ==========================================================================================================================================
        section_break("Check Hold Bucket")
        step("Verify Account on Hold", "Verify Account Lands on Hold Bucket")
        logger.info("Moving to Hold Bucket")
        page.wait_for_timeout(30000)
        page.locator("span").filter(has_text=re.compile(r"^Hold$")).click()
        page.wait_for_timeout(15000)
        screenshot(page, "hold_bucket")
        logger.info("Test Run Successfully")
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