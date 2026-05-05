import os
import sys
import time
import re
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
# =========================================================
# Configuration
# =========================================================
SYSTEM      = "CAC"
ENVIRONMENT = "Pre-Production"
PILLAR      = "Orange Park"
RUN_TYPE    = "Interface Test"
TEST_TYPE   = "OBS"
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
        pre_run_check("https://XRDCWTWEBCAC04B.HCA.CORPAD.NET/3M_360App")
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
        step("Orange Park Pre-Production CAC Dashboard", "Launching Browser & Navigating to Dashboard")
        page.goto("https://XRDCWTWEBCAC04B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")
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
        section_break("OBS Worklist")
        step("OBS Worklist", "Navigating to OBS Worklist")
        logger.info("Selecting OBS Worklist")
        page.get_by_text("OBV").click()
        wait_for_data_load(page, "OBS Worklist", profile="quick")
        screenshot(page, "him_coding_dashboard")
        end_step()
# =========================================================================================================================================
# Ready Bucket
# ==========================================================================================================================================  
        section_break("Ready Bucket")
        step("Ready Bucket", "Navigating to Ready Bucket")
        logger.info("Selecting Ready Bucket")
        page.get_by_text("Ready", exact=True).nth(3).click()
        wait_for_data_load(page, "Ready Bucket", profile="quick")
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
        with page.expect_popup() as page1_info:
            page.get_by_role("row", name=f"Visit ID: {acct_number}").locator("#visitid").click()
            page1 = page1_info.value
            page1.bring_to_front()
            logger.info("Patient Record Open")
            end_step()
# ==========================================================================================================================================
# Navigating to Documents and Codes Tab
# ==========================================================================================================================================
            section_break("Navigate to Documents and Codes & Confirm Patient Status")
            step("Confirm Patient Loaded", "Confirm Patient Status")      
            page1.wait_for_timeout(4000)
            page1.get_by_text("Documents and Codes").click()      
            page1.wait_for_timeout(4000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Patient Status Confirmed")              
            screenshot(page1, "patient_status")        
            end_step()
# ==========================================================================================================================================
# Close Account
# ==========================================================================================================================================
        section_break("Close Account")
        step("Close Account", "Closing Account")
        page1.wait_for_load_state("domcontentloaded")
        page1.wait_for_timeout(3000)
        page1.get_by_text("Close").click()
        page.wait_for_timeout(3000)
        logger.info("Test Run Completed Successfully!")
        page.close()
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