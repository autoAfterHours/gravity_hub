import os
import sys
import time
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
# ==========================================================================================================================================
# Configuration
# ==========================================================================================================================================
SYSTEM      = "CAC"
ENVIRONMENT = "QA"
PILLAR      = "MTX"
RUN_TYPE    = "Full Regression"
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
        pre_run_check("https://xrdcwqwebcac20b.hcaqa.corpadqa.net/3M_360App/dashboard")
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
        step("MTX QA CAC Dashboard", "Launching Browser & Navigating to CER QA CAC Dashboard")
        page.goto("https://xrdcwqwebcac20b.hcaqa.corpadqa.net/3M_360App/dashboard", wait_until="domcontentloaded")
        wait_for_data_load(page, "CAC Dashboard", profile="quick")
        screenshot(page,"cac_dashboard")
        end_step()
# ==========================================================================================================================================
# HIM Coding
# ==========================================================================================================================================
        section_break("HIM Coding Dashboard")
        step("Check HIM Coding Dashboard Functionality", "Navigating to HIM Coding")
        page.get_by_text("HIM Coding").click()
        wait_for_data_load(page, "HIM Coding Page", profile="quick")
        screenshot(page, "cac_dashboard")
        end_step()
# ==========================================================================================================================================
# ED Worklist
# ==========================================================================================================================================
        section_break("ED Worklist")
        step("ED Worklist", "Navigating to ED Worklist")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        page.get_by_text("ED", exact=True).click()
        wait_for_data_load(page, "ED Worklist", profile="quick")
        screenshot(page, "ed_worklist")
        end_step()

    # Navigate to HIM Coding Dashboard > ED Ready Worklist
        section_break("HIM Coding Dashboard")
        step("Check HIM Coding Dashboard Functionality", "Navigating to HIM Coding Dashboard")
        page.get_by_text("HIM Coding").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        screenshot(page, "him_coding_dashboard")
        logger.info("Selecting ED Worklist")
        page.get_by_text("ED", exact=True).click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        screenshot(page, "ed_worklist")
        logger.info("Selecting Ready Bucket")
        page.get_by_text("Ready", exact=True).nth(3).click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
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
    # Open Show Evidence Button
            section_break("Show Evidence Button")
            step("Show Evidence", "Checking Show Evidence Button Functionality")
            page1.locator("m-cac iframe").content_frame.get_by_role("listitem", name="Code E039, Hypothyroidism,").get_by_label("Show Evidence (1 source) Use").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            screenshot(page1, "show_evidence")
            end_step()

    # Accept AS DRG & Confirm Icon (Reviewed) Appears)
            section_break("Accept ASDRG Code")
            step("Accept ASDRG", "Accepting ASDRG Code E039")
            page1.locator("m-cac iframe").content_frame.get_by_role("button", name="Accept Code", exact=True).click()
            logger.info("Auto Suggested DRG Accepted")
            screenshot(page1, "asdrg_added")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Adding Secondary DX Code")
            page1.locator("m-cac iframe").content_frame.get_by_label("Code, E039. Description, Diagnosis: Hypothyroidism, unspecified. Status,").get_by_role("button", name="Accept Code").click()
            logger.info("Secondary Diagnosis Code Accepted")
            screenshot(page1, "secondary_dx_added")
            end_step()

    ### WSS - Part 1
    ## Facility E/M Tab
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("m-cac iframe").content_frame.get_by_role("button", name="Launch Worksheet Services").click()
            page1.wait_for_timeout(2000)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#item-4000185426-checkbox-box").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Calculate").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Process").click()

    # Add Procedure Date to CPT Codes
            section_break("Add Provider Episode to CPT Codes")
            step("Add Provider Episode", "Adding Provider Episode to CPT Codes")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(500)
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("EMERGENCY DEPARTMENT VISIT MODERATE MDM").click(button="right")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(500)
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="Add Date/Physician/Episode").click()
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(500)
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Start Date").click()
            page1.wait_for_load_state("domcontentloaded")

            manual_prompt(
                    message="Select Date for Provider Episode",
                    completion_note="Provider Episode Date Entered"
            )

    # Remaining Procedure Date Prompts
            logger.info("Procedure Date Selected....Continuing Automation")
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Start Date").press("Enter")
            page1.wait_for_timeout(1000)
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Physician").fill("Hansen, Todd H")
            page1.wait_for_timeout(1000)
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("cell", name="Hansen, Todd H").click()
            page1.wait_for_timeout(1000)
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
            page1.wait_for_timeout(1000)
            screenshot(page1, "codeset_with_providerep_added")
            logger.info("Provider Episode Successfully Added")
            page1.wait_for_load_state("domcontentloaded")
            end_step()

     # Complete Account
            section_break("Complete Account")
            step("Complete Account", "Completing Account")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(1000)
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            screenshot(page1, "account_completed")
            logger.info("Account has been completed")
            end_step()

    # Update Discharge Disposition to AMA
            section_break("Update Discharge Disposition")
            step("Update Discharge Disposition", "Updating Discharge Disposition to AMA")
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("#selDis-dropdownPanelTrigger").click()
            page1.wait_for_timeout(500)
            page1.locator("#selDis-filterInput").click()
            page1.wait_for_timeout(500)
            page1.locator("#selDis-filterInput").fill("AMA")
            page1.wait_for_timeout(500)
            page1.get_by_text("AMA - 07 - AMA - Against").click()
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(2000)
            screenshot(page1, "updated_discharge_dispo")
            logger.info("Discharge Disposition Updated to AMA")
            end_step()

    # Complete Account
            section_break("Complete Account")
            step("Complete Account", "Completing Account")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(1000)
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            screenshot(page1, "account_completed")
            logger.info("Account has been completed")
            end_step()

    # Submit Account
            section_break("Submit Account")
            step("Submit Account", "Submitting Account to Coded Status")
            page1.wait_for_load_state("domcontentloaded")
            page1.get_by_role("button").filter(has_text="Submit").click()
            page1.wait_for_timeout(3000)
            logger.info("Account Submitted")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(1000)
            logger.info("Closing Next Account")
            page1.get_by_text("Close").click()
            end_step()

    # Navigate to Coded Today Bucket
            section_break("Wrap Up & Confirm Account Lands on Coded Today Bucket")
            step("Navigate to Coded Today Bucket", "Navigating to Coded Today Bucket")
            page.wait_for_load_state("domcontentloaded")
            page.bring_to_front()
            page.wait_for_timeout(2000)
            page.get_by_text("Coded Today").click()
            page.wait_for_load_state("domcontentloaded")
            page.wait_for_timeout(2000)
            screenshot(page, "coded_account_1stpass")
            logger.info("Coded Account Confirmed")
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