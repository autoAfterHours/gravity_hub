import os
import sys
import time
import re
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect

# ─── Standalone Runtime ──────────────────────────────────────────────────────
import logging
import argparse
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = Path("screenshots")
SCREENSHOTS_DIR.mkdir(exist_ok=True)

WAIT_PROFILES   = {"quick": 5_000, "popup": 15_000, "slow": 30_000}
DEFAULT_TIMEOUT = 30_000
RETRY_COUNT     = 3


def step(title, desc=""):
    logger.info("\u25b6 " + title + ("  —  " + desc if desc else ""))


def end_step():
    pass


def section_break(name):
    logger.info("\n" + "─" * 60 + "\n  " + name + "\n" + "─" * 60)


def screenshot(page, label):
    try:
        page.screenshot(path=str(SCREENSHOTS_DIR / f"{label}.png"))
    except Exception:
        pass


def safe_screenshot(page, label):
    screenshot(page, label)


def safe_click(element, label=""):
    element.click()


def safe_fill(element, value, label=""):
    element.fill(value)


def step_with_pause(step_name="", pause_duration=0):
    if pause_duration:
        time.sleep(pause_duration)


def wait_for_data_load(page, name="page", profile="quick", **_kw):
    timeout = WAIT_PROFILES.get(profile, 5_000)
    try:
        page.wait_for_load_state("networkidle", timeout=timeout)
    except Exception:
        pass


def wait_with_intervention(page, name="page", **_kw):
    wait_for_data_load(page, name)


def manual_prompt(message="", completion_note=""):
    input(f"\n{message}\n  ({completion_note})\nPress Enter when done...")


def handle_failure(e, page):
    logger.error(f"Test failed: {e}")
    try:
        if page:
            page.screenshot(path="failure.png")
    except Exception:
        pass
    raise e


def format_duration(seconds):
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s}s" if m else f"{s}s"


def start_trace(context):
    context.tracing.start(screenshots=True, snapshots=True)


def save_trace(context):
    context.tracing.stop(path="trace.zip")


def crs_frame(page):
    frames = page.frames
    return frames[1] if len(frames) > 1 else page.main_frame


def claim_excel_row():
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--account",      default=os.environ.get("ACCOUNT_NUMBER", ""))
    ap.add_argument("--admit-date",   default=os.environ.get("ADMIT_DATE",     ""))
    ap.add_argument("--attending-md", default=os.environ.get("ATTENDING_MD",   ""))
    ap.add_argument("--admitting-md", default=os.environ.get("ADMITTING_MD",   ""))
    args, _ = ap.parse_known_args()
    patient = {
        "AccountNumber": args.account,
        "AdmitDate":     args.admit_date,
        "AttendingMD":   args.attending_md,
        "AdmittingMD":   args.admitting_md,
    }
    if not patient["AccountNumber"]:
        logger.warning("No --account supplied; set ACCOUNT_NUMBER env var or pass --account <id>")
        return patient, -1
    return patient, 0


def release_excel_row(row_idx, status, notes=""):
    logger.info(f"Result: {status}" + (f"  |  {notes}" if notes else ""))


def pre_run_check(url):
    pass  # health-check removed in standalone mode


def init_helpers(_ctx=None):
    pass


class CACFrames:
    def __init__(self, page):
        self._page = page

    @classmethod
    def for_popout(cls, page):
        return cls(page)

    @property
    def abstract(self):
        return self._page.frame_locator("iframe").first

    @property
    def codefinder(self):
        return self._page.frame_locator("iframe").nth(1)

    @property
    def codefinder_popout(self):
        return self._page.frame_locator("iframe").last
# ────────────────────────────────────────────────────────────────────────────
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
# ============================================================================================================================================================
    setup, step, end_step, section_break,
    screenshot, manual_prompt, handle_failure, format_duration,
    crs_frame, start_trace, save_trace,
    )
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