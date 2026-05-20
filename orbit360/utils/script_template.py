import os
import sys
import time
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect

# =========================================================
# Configuration — update these 4 values for each new script
# =========================================================

SYSTEM      = "CAC"          # e.g. CAC, Cloverleaf
ENVIRONMENT = "QA"           # e.g. QA, PreProd, Prod
PILLAR      = "ENT"          # e.g. ENT, CER, MTX
RUN_TYPE    = "IP"           # e.g. CLI, IP, ED, IPDIS, OBS, eMD, RCR, REF, SDC, SLR

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
    prompt_value, claim_excel_row, release_excel_row,
    base_url,
)

ctx    = setup(SYSTEM, ENVIRONMENT, PILLAR, RUN_TYPE)
logger = ctx.logger

# =========================================================
# Data — one patient record claimed per run
# =========================================================
# The Excel file is declared in run_sequence.yaml:
#
#   test_data:
#     path: "test_data/CAC/PreProd/Houston/patients.xlsx"
#     run_flag_col: "Run"
#
# The GUI injects ORBIT_EXCEL_PATH automatically — nothing
# to set here.  Each run claims the next available row so
# two analysts running simultaneously never share a record.
#
# Excel column headers (row 1) become dict keys:
#   | PatientMRN | CPTCode | DXCode | Run |
#   |   12345    |  33249  |  I499  |  Y  |
#
# Access values in your steps with: patient.get("PatientMRN")

# =========================================================
# Main Run
# =========================================================

def run(playwright: Playwright) -> None:
    run_start_time = time.time()

    browser = None
    context = None
    page    = None
    page1   = None

    # ── Claim one patient record from the pool ───────────────────────────
    patient, row_idx = claim_excel_row()
    if row_idx == -1:
        logger.info("No patient records available — pool exhausted.")
        return
    patient_id = patient.get("PatientMRN") or "Unknown"
    logger.info(f"Patient record claimed: {patient_id} (row {row_idx + 1})")

    try:
        browser = playwright.chromium.launch(
            headless=False,
            args=["--start-maximized"],
        )
        context = browser.new_context(no_viewport=True)
        start_trace(context)
        page = context.new_page()

# =========================================================
# One-time setup
# =========================================================

# Navigate to Dashboard
        section_break("CAC Dashboard")
        step("Navigate to Dashboard", "Launching Browser & Navigating to Dashboard")
        page.goto(
            base_url() + "/3M_360App/dashboard",
            wait_until="domcontentloaded",
        )
        page.wait_for_timeout(4000)
        screenshot(page, "dashboard")
        logger.info("Dashboard Loaded")
        end_step()

# Navigate to Worklist
        section_break("Navigate to Worklist")
        step("Navigate to Worklist", "Navigating to Worklist")
        page.get_by_text("HIM Coding").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        # TODO: click the correct worklist type and bucket
        screenshot(page, "worklist")
        end_step()

# =========================================================
# Patient Record
# =========================================================

# Select Patient
        section_break("Select Record")
        step("Select Patient", "Select a Patient Record")
        manual_prompt(
            message=f"Select patient {patient_id} from the worklist",
            completion_note="Patient Selected",
        )
        end_step()

# Confirm Patient Loaded (Popup)
        section_break("Validate Record")
        step("Confirm Patient Loaded", "Patient Record Loaded")
        page1 = None
        with page.expect_popup() as page1_info:
            page1 = page1_info.value
            crs   = crs_frame(page1)      # remove if script doesn't use CRS iframe
            page1.bring_to_front()
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(2000)
            screenshot(page1, "record")
            manual_prompt(
                message="Validate Patient Opened Correctly",
                completion_note="Patient Record Validated",
            )
            end_step()

# =========================================================
# TODO: Add test steps here
#
# Inject Excel values directly into Playwright actions:
#   crs.get_by_role("textbox", name="Enter Keyword or Code:").fill(patient.get("DXCode", ""))
#   crs.get_by_role("textbox", name="Enter Keyword or Code:").fill(patient.get("CPTCode", ""))
#
# Step pattern:
#   section_break("Step Title")
#   step("Step Name", "Log message")
#   # ... playwright actions ...
#   screenshot(page1, "descriptive_label")
#   logger.info("Confirmation message")
#   end_step()
# =========================================================

# Complete Account
            section_break("Complete Account")
            step("Complete Account", "Completing Account")
            page1.wait_for_load_state("domcontentloaded")
            crs.get_by_role("button", name="Complete").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            screenshot(page1, "completed")
            logger.info("Account Completed")
            end_step()

# Submit Account
            section_break("Submit Account")
            step("Submit Account", "Submitting Account")
            page1.wait_for_load_state("domcontentloaded")
            page1.get_by_role("button").filter(has_text="Submit & Next").click()
            page1.wait_for_timeout(3000)
            logger.info("Account Submitted")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(1000)
            page1.get_by_text("Close").click()
            end_step()

# Confirm Landing Bucket
        section_break("Confirm Bucket")
        step("Confirm Account Bucket", "Confirming Account Landed Correctly")
        page.wait_for_load_state("domcontentloaded")
        page.bring_to_front()
        page.wait_for_timeout(2000)
        page.get_by_text("Coded Today").click()    # TODO: update bucket text
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        screenshot(page, "confirmed")
        logger.info("Account Confirmed in Bucket")
        end_step()

        release_excel_row(row_idx, "PASS")
        logger.info(f"Patient {patient_id} — PASS")

# ── Failure handling ──────────────────────────────────────────────────────────
    except Exception as e:
        release_excel_row(row_idx, "FAIL", notes=str(e))
        handle_failure(e, page1 or page)

    finally:
        if context:
            save_trace(context)
        if browser:
            browser.close()
        logger.info(f"Total Run Duration | {format_duration(time.time() - run_start_time)}")


with sync_playwright() as playwright:
    run(playwright)
