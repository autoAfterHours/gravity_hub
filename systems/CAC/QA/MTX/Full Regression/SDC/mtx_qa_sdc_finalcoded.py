import os
import sys
import time
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
# =========================================================
# Configuration
# =========================================================
SYSTEM      = "CAC"
ENVIRONMENT = "QA"
PILLAR      = "MTX"
RUN_TYPE    = "Full Regression"
TEST_TYPE    = "SDC"
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
        pre_run_check("https://XRDCWQWEBCAC20B.HCA.CORPAD.NET/3M_360App")
        browser = playwright.chromium.launch(
            headless=False,
            args=["--start-maximized"]
            )
        context = browser.new_context(no_viewport=True)
        start_trace(context)
        page = context.new_page()
# ==========================================================================================================================================
        section_break("Navigate to CAC Dashsboard")
        step("MTX QA CAC Dashboard", "Launching Browser & Navigating to Dashboard")
        page.goto("https://XRDCWQWEBCAC20B.HCA.CORPAD.NET/3M_360App")
        wait_for_data_load(page, "CAC Dashboard", profile="quick")
        screenshot(page,"cac_dashboard")
        end_step()
# Navigate to HIM Coding Dashboard > SDC Ready Worklist
        page.wait_for_timeout(2000)
        page.get_by_text("HIM Coding").click()
        page.wait_for_timeout(2000)
        page.get_by_text("SDC Ready", exact=True).click()
        page.wait_for_timeout(2000)
        page.get_by_text("Coded Today").click()
        page.wait_for_timeout(2000)

# ==========================================================================================================================================
# Search for Patient Account
# ========================================================================================================================================== 
        section_break("Patient Validation Check")
        step("Confirm Patient Loaded", "Searching for Patient")
        page.get_by_role("textbox", name="Type visit ID or patient name").click()
        page.wait_for_timeout(1000)
        page.get_by_role("textbox", name="Type visit ID or patient name").fill(acct_number)
        page.wait_for_timeout(1000)
        screenshot(page, "patient_search")
        logger.info("Opening Patient Record")
        page1 = None
        with page.expect_popup() as page1_info:
            page.get_by_role("row", name=f"Visit ID: {acct_number}").locator("#visitid").click()
            page1 = page1_info.value
            crs = crs_frame(page1)
            page1.bring_to_front()
            logger.info("Patient Record Open")
            screenshot(page1, "patient_record")
            end_step()

# Move Account from Coded to Ready Status
        page1.wait_for_timeout(2000)
        page1.get_by_role("button").filter(has_text="Coded").click()
        page1.wait_for_timeout(1000)
        page1.get_by_role("menuitem", name="Ready").click()

# Manual Prompt & Delete the Primary DX (I2510)
        print("\n---------------------------------------------")
        print(" MANUAL STEP REQUIRED - Select the I2510 Diagnosis Code & Right Click the Code to Open Menu")
        print("---------------------------------------------")
        print("Select the I2510 Diagnosis Code & Right Click the Code to Open Menu")
        print("Press ENTER when you are ready to continue.\n")
        input("Ready to Continue?")
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Delete Code(s)").click()

# Direct Code Primary DX (I2510)
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Diagnosis").click()
        page1.wait_for_timeout(500)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("I2510")
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()

# Manual Prompt & Move DX Code I2510 to Principal Position
        print("\n---------------------------------------------")
        print(" MANUAL STEP REQUIRED - Select the I2510 Diagnosis Code & Right Click the Code to Open Menu")
        print("---------------------------------------------")
        print("Select the I2510 Diagnosis Code & Right Click the Code to Open Menu")
        print("Press ENTER when you are ready to continue.\n")
        input("Ready to Continue?")
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Move to Principal Position").click()

# Complete & Confirm Results
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
        page1.pause()

# Submit Account (Final Coded)
        page1.wait_for_timeout(2000)
        page1.get_by_role("button").filter(has_text="Submit & Next").click()

# Close Next Account        
        page1.wait_for_timeout(2000)
        page1.get_by_text("Close").click()

# Navigate to Coded Today Bucket & Confirm Account Landed Correctly
        page.wait_for_timeout(3000)
        page.get_by_text("Coded Today").click()
        page.wait_for_timeout(3000)

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