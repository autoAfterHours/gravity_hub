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
        page.get_by_text("Ready", exact=True).nth(3).click()
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

# Code Patient (Outpatient Atherosclerosis with Stent Placement)
# Add Admit DX (I2582)
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("I2582")
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()

# Add Diagnosis Code (I2510)
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Diagnosis").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("I2510")
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()

# Add Diagnosis Code (I2582)
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Diagnosis").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("I2582")
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()

# Add Procedure Code (92928)
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Procedure").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("92928")
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")

# Add Procedure Code (C9600)
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Procedure").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("C9600")
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")

# Add Procedure Code (C9601)
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Procedure").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("C9601")
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")

# Add Procedure Code (93451)
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Procedure").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("93451")
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")

# Add LD Modifiers to C9600)
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Perc drug-el cor stent sing").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Perc drug-el cor stent sing").click(button="right")
        page1.wait_for_timeout(500)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="Add/Delete Modifiers").click()

# Manual Prompt - Select -LD Modifier
        print("\n---------------------------------------------")
        print(" MANUAL STEP REQUIRED - Select Option -LD")
        print("---------------------------------------------")
        print("Please Select Option -LD from the Modifier Options.")
        print("Press ENTER when you are ready to continue.\n")
        input("Ready to Continue?")
        
        page1.wait_for_timeout(500)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add >").click()
        page1.wait_for_timeout(500)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
       
# Add LM Modifiers to 92928 & C9601)
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("PERQ TCAT PLMT NTRAC ST 1 LES").click()
        page1.wait_for_timeout(500)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Perc drug-el cor stent bran").click(modifiers=["ControlOrMeta"])
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Perc drug-el cor stent bran").click(button="right")
        page1.wait_for_timeout(500)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="Add Modifiers").click()
        
        print("\n---------------------------------------------")
        print(" MANUAL STEP REQUIRED - Select Option -LM")
        print("---------------------------------------------")
        print("Please Select Option -LM from the Modifier Options.")
        print("Press ENTER when you are ready to continue.\n")
        input("Ready to Continue?")

        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add >").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()

# Add Provider Procedure Episode
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("RIGHT HEART CATH O2").click(modifiers=["ControlOrMeta"])
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Perc drug-el cor stent sing").click(modifiers=["ControlOrMeta"])
        page1.wait_for_timeout(500)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Perc drug-el cor stent sing").click(button="right")
        page1.wait_for_timeout(500)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="Add Date/Physician/Episode").click()

# Manual Prompt - Enter Procedure Date
        print("\n---------------------------------------------")
        print(" MANUAL STEP REQUIRED - Enter Procedure Date ")
        print("---------------------------------------------")
        print("Please Enter the Date of the Procedure | Date Format: MM/DD/YYYY | *Hint: Reference Patient Admit/Discharge Date for Applicable Date Time Frame.")
        print("Press ENTER when you are ready to continue.\n")
        input("Ready to Continue?")

# Fill Out Remainder of Provider Episode
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Start Date").click()
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Start Date").press("Enter")
        page1.wait_for_timeout(500)
        crs.get_by_label("Self Pay").press("Tab")
        page1.wait_for_timeout(500)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Physician").fill("DANNER")
        page1.wait_for_timeout(500)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("cell", name="DANNER, CECE").click()
        page1.wait_for_timeout(500)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()

# Complete & Confirm Results
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()

# Add Consulting Provider
        page1.wait_for_timeout(2000)
        page1.get_by_role("tab", name="Abstract").locator("a").click()
        page1.wait_for_timeout(1000)
        page1.get_by_role("button").filter(has_text="Add Consulting Provider").click()
        page1.wait_for_timeout(500)
        page1.get_by_role("dialog").locator("c-dropdown div").first.click()
        page1.locator("input[name=\"search\"]").click()
        page1.locator("input[name=\"search\"]").fill("DANNER")
        page1.locator("input[name=\"search\"]").click()
        page1.locator("input[name=\"search\"]").press("Enter")
        page1.wait_for_timeout(500)
        page1.get_by_role("dialog").get_by_text("DANNER, CECE").click()
        page1.wait_for_timeout(500)
        page1.get_by_role("button").filter(has_text="OK").click()

# Manual Prompt - Enter Consult Date
        print("\n---------------------------------------------")
        print(" MANUAL STEP REQUIRED - Enter Consult Start Date ")
        print("---------------------------------------------")
        print("Please Enter the Date of the Consult | Date Format: MM/DD/YYYY | *Hint: Reference Patient Admit/Discharge Date for Applicable Date Time Frame.")
        print("Press ENTER when you are ready to continue.\n")
        input("Ready to Continue?")
        page1.wait_for_timeout(500)
        page1.get_by_role("button").filter(has_text="Save").click()
        page1.wait_for_timeout(1000)

# Add Consulting Provider 2nd Run
        page1.wait_for_timeout(2000)
        page1.get_by_role("button").filter(has_text="Add Consulting Provider").click()
        page1.wait_for_timeout(500)
        page1.get_by_role("dialog").locator("c-dropdown div").first.click()
        page1.locator("input[name=\"search\"]").click()
        page1.locator("input[name=\"search\"]").fill("DANNER")
        page1.locator("input[name=\"search\"]").click()
        page1.locator("input[name=\"search\"]").press("Enter")
        page1.wait_for_timeout(500)
        page1.get_by_role("dialog").get_by_text("DANNER, CECE").click()
        page1.wait_for_timeout(500)
        page1.get_by_role("button").filter(has_text="OK").click()

# Manual Prompt - Enter Consult Date
        print("\n---------------------------------------------")
        print(" MANUAL STEP REQUIRED - Enter Consult Start Date ")
        print("---------------------------------------------")
        print("Please Enter the Date of the Consult | Date Format: MM/DD/YYYY | *Hint: Reference Patient Admit/Discharge Date for Applicable Date Time Frame.")
        print("Press ENTER when you are ready to continue.\n")
        input("Ready to Continue?")
        page1.wait_for_timeout(500)
        page1.get_by_role("button").filter(has_text="Save").click()
        page1.wait_for_timeout(1000)

# Cancel 2nd Provider Entry 
        page1.wait_for_timeout(3000)
        page1.get_by_role("button").filter(has_text="Cancel").click()

# Add A Different Consulting Provider
        page1.wait_for_timeout(2000)
        page1.get_by_role("button").filter(has_text="Add Consulting Provider").click()
        page1.wait_for_timeout(1000)
        page1.get_by_role("dialog").locator("c-dropdown div").first.click()
        page1.wait_for_timeout(1000)
        page1.locator("input[name=\"search\"]").click()
        page1.locator("input[name=\"search\"]").fill("TEST")
        page1.locator("input[name=\"search\"]").click()
        page1.locator("input[name=\"search\"]").press("Enter")
        page1.wait_for_timeout(500)
        page1.get_by_text("TEST, ONE").click()
        page1.wait_for_timeout(1000)
        page1.get_by_role("button").filter(has_text="OK").click()

# Manual Prompt - Enter Consult Date
        print("\n---------------------------------------------")
        print(" MANUAL STEP REQUIRED - Enter Consult Start Date ")
        print("---------------------------------------------")
        print("Please Enter the Date of the Consult | Date Format: MM/DD/YYYY | *Hint: Reference Patient Admit/Discharge Date for Applicable Date Time Frame.")
        print("Press ENTER when you are ready to continue.\n")
        input("Ready to Continue?")
        page1.wait_for_timeout(500)
        page1.get_by_role("button").filter(has_text="Save").click()
        page1.wait_for_timeout(2000)

# Submit Account (Final Coded)
        page1.wait_for_timeout(2000)
        page1.get_by_role("tab", name="Documents and Codes").locator("a").click()
        page1.wait_for_timeout(2000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
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