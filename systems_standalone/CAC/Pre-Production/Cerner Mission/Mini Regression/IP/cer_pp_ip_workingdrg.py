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
# ==========================================================================================================================================
# Configuration
# ==========================================================================================================================================
SYSTEM      = "CAC"
ENVIRONMENT = "Pre-Production"
PILLAR      = "Cerner Mission"
RUN_TYPE    = "Mini Regression"
TEST_SET    = "IP"
# ==========================================================================================================================================
# Bootstrap — locate project root and import shared runtime
# ==========================================================================================================================================
# ==========================================================================================================================================
# ==========================================================================================================================================
# Main Run
# ==========================================================================================================================================
def run(playwright: Playwright) -> None:
    run_start_time = time.time()
    browser = None
    context = None
    page    = None
    page1   = None
    admit_date = acct_number = ""
    def _ctx(*fields):
        labels = {
            "admit":      ("Admit",      lambda: admit_date),
            "acct_number": ("Account",   lambda: acct_number),
        }
        parts = [f"{labels[f][0]}: {labels[f][1]()}" for f in fields if labels[f][1]()]
        return f"  [{' | '.join(parts)}]" if parts else ""
    page2   = None
    crs_frame = None
    try:
        pre_run_check("https://XRDCWTWEBCAC10B.HCA.CORPAD.NET/3M_360App")
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
        step("Cerner Mission Pre-Production CAC Dashboard", "Launching Browser & Navigating to Dashboard")

        page.goto("https://XRDCWTWEBCAC10B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")

        wait_for_data_load(page, "CAC Dashboard", profile="popup")
        screenshot(page,"cac_dashboard")

        end_step()
# ===========================================================================
        section_break("Navigate to Concurrent Coding Dashboard")
        step("Check Concurrent Coding Dashboard Functionality", 
        "Navigating to Concurrent Coding Dashboard")
        
        # Click Concurrent Coding
        page.get_by_text("Concurrent Coding").click()
        wait_for_data_load(page, "Concurrent Coding Page", profile="quick")
        screenshot(page, "concurrent_coding_db")

        end_step()
# ===========================================================================
        section_break("Navigate to Conurrent Priority Worklist")
        step("Concurrent Priority WL", "Navigating to Concurrent Priority Worklist")
        
        # Click Concurrent Priority
        page.get_by_role("cell", name="Concurrent Priority").click()
        wait_for_data_load(page, "Concurrent Priority Worklist",profile="quick")  
        screenshot(page, "concurrent_priority_wl")

        end_step()
# ===========================================================================
        section_break("Select Patient Record")
        step("Select Patient", "Select a Patient Record")
        
        # Manual Prompt 
        manual_prompt(
        message="Select a patient record"
        "Once you have selected the patient click the Continue button in Orbit360.",
        completion_note="Patient Selected.Beginning Validation")
        
        end_step()
# ===========================================================================
        section_break("Confirm Patient Loaded Successfully")
        step("Confirm Patient Loaded", "Patient Record Loaded")
        
        with page.expect_popup() as page1_info:
            page1 = page1_info.value
            page1.bring_to_front()
            frames = CACFrames(page1)

        end_step()
# ===========================================================================
        section_break(
        "Navigate to Patient Profile & Gather Account Values")
        step("Record Patient Profile Data","Capturing Admit Date & Attending Physicians")
        
        # Navigate to Patient Profile Tab
        page1.wait_for_timeout(1000)
        page1.get_by_text("Patient Profile").click()
        page1.wait_for_timeout(1000)
        logger.info("Navigating to Patient Profile Tab.")
        screenshot(page1, "patient_profile")
        page1.wait_for_timeout(1000)

        # Remaining Steps 
        admit_date = ctx.input("Admit Date (as shown on Patient Profile)")
        acct_number = ctx.input("Account Number")

        logger.info(f"Admit: {admit_date} | Account: {acct_number}")

        screenshot(page1, "patient_profile")

        end_step()
# ==================================================================
        section_break("Add Finding")
        step("Add Finding", "Adding Finding")
        
        # Click Add Finding
        page1.get_by_role("button", name="Add Finding...").click()
        page1.wait_for_timeout(1000)
        logger.info("Add Finding Button Selected")
        screenshot(page1, "add_finding_box")
        # Add Comment
        page1.locator("#findingframe").content_frame.locator("#findingsComments").click()
        page1.wait_for_timeout(1000)
        logger.info("Comment Box Clicked. Typing Text Entry")
        page1.locator("#findingframe").content_frame.locator("#findingsComments").fill("TEST")
        page1.wait_for_timeout(1000) 
        logger.info("Comment Added")
        screenshot(page1, "comment_added")
        # Click Add Button
        page1.locator("#findingframe").content_frame.locator("#id_finding_add-button").click()
        logger.info("Added Finding to Account")
        page1.wait_for_timeout(1000)
        screenshot(page1, "finding_acknowledged")

        end_step()
# ========================================================================================
        section_break("Navigate to Document and Codes Tab")
        step("Doc and Codes Tab", 
        "Navigating to Document and Codes Tab")
        
        page1.get_by_text("Documents and Codes").click()
        page1.wait_for_timeout(1000)
        logger.info("Documents and Codes Tab Selected")
        screenshot(page1, "doc_codes_tab")
        
        end_step()
# ========================================================================================
        section_break("Add Diagnois Code (I10)")
        step("Add I10", "Adding Diagnosis Code (I10)")

        # Diagnosis Text Box (Click)
        frames.codefinder.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        logger.info("Clicked in Codefinder to Add Diagnosis Code to Account.")
        # Fill I10
        frames.codefinder.get_by_role("textbox", name="Enter Keyword or Code:").fill("I10")
        page1.wait_for_timeout(1000)
        logger.info("Clicked in Codefinder to Add Diagnosis Code to Account.")
        screenshot(page1, "i10_added")
        # Diagnosis Text Box (Click)
        frames.codefinder.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        # Enter I10
        frames.codefinder.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        page1.wait_for_timeout(1000)
        logger.info("Prompt for I10. Selecting Ok.")
        screenshot(page1, "i10_entered")            
        # Click Ok
        frames.codefinder.get_by_role("button", name="OK").click()
        page1.wait_for_timeout(1000)
        logger.info("Confirming I10 Showing in Codefinder.")
        screenshot(page1, "i10_confirmed")

        end_step()
# ========================================================================================
        section_break("Copy Code as Primary")
        step("Copy DX as Primary","Copying Diagnosis Code I10 as Primary")

        # Right Click Code
        frames.codefinder.get_by_text("Essential (primary)").click(button="right")
        page1.wait_for_timeout(1000)
        # Click Copy Code as Primary
        frames.codefinder.get_by_text("Copy Code as Primary").click()
        page1.wait_for_timeout(1000)
        logger.info("Selecting Copy Code as Primary Option.")
        screenshot(page1, "copied_code")

        end_step()
# ========================================================================================
        section_break("Complete Account")
        step("Complete Account", "Completing Account")

        # Complete Account    
        frames.codefinder.get_by_role("button", name="Complete").click()
        page1.wait_for_timeout(1000)
        logger.info("Account has been completed")
        screenshot(page1, "account_completed_1sttry")

        end_step()
# ========================================================================================
        section_break("Present on Admission")
        step("POA", "POA Prompt")

        # Present on Admission
        frames.codefinder.get_by_role("button", name="Yes").click()
        page1.wait_for_timeout(1000)
        logger.info("Present on Admission Prompt")
        screenshot(page1, "poa_prompt")

        # Manual Prompt
        manual_prompt(
        message="Select Y for I10, and Select Ok Button",
        completion_note="Y Selected for I10")

        end_step()
# ==============================================================================================        
        section_break("Complete Account")
        step("Complete Account", "Completing Account")

        # Complete Account    
        frames.codefinder.get_by_role("button", name="Complete").click()
        page1.wait_for_timeout(1000)
        logger.info("Account has been completed")
        screenshot(page1, "account_completed_2ndtry")

        end_step()
# ==========================================================================================================================================
        section_break("Close Account")
        step("Close Account", "Closing Account")

        # Close Account
        page1.get_by_role("button", name="Close").click()
        page.wait_for_timeout(1000)
        logger.info("Closing Account")

        # Close Session 
        page.wait_for_timeout(1000)
        logger.info("Closing Session")       
        page.close()
        logger.info("Test Run Completed Successfully!")
        end_step()
# ==========================================================================================================================================
    except Exception as e:
        handle_failure(e or page)

    finally:
        if context:
            save_trace(context)
        if browser:
            browser.close()
        total_duration = time.time() - run_start_time
        logger.info(f"Total Run Duration | {format_duration(total_duration)}")

with sync_playwright() as playwright:
    run(playwright)