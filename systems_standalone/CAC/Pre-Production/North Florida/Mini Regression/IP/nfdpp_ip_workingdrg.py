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
PILLAR      = "North Florida"
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
    admit_date = acct_number = attending_md = ""
    page2   = None
    crs_frame = None
# ==========================================================================================================================================
    def _ctx(*fields):
        labels = {
            "admit":      ("Admit",      lambda: admit_date),
            "acct_number": ("Account",   lambda: acct_number),
            "attending_md": ("Account", lambda: attending_md),
        }
        parts = [f"{labels[f][0]}: {labels[f][1]()}" for f in fields if labels[f][1]()]
        return f"  [{' | '.join(parts)}]" if parts else ""
    try:
        pre_run_check("https://XRDCWTWEBCAC21B.HCA.CORPAD.NET/3M_360App")
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
        step("North Florida Pre-Production CAC Dashboard", "Launching Browser & Navigating to Dashboard")

        page.goto("https://XRDCWTWEBCAC21B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")

        wait_for_data_load(page, "CAC Dashboard", profile="quick")
        screenshot(page,"cac_dashboard")

        end_step()
# ==========================================================================================================================================
# Navigate to Conurrent Coding Dashboard
# ==========================================================================================================================================
        section_break("Concurrent Coding Dashboard")
        step("Check Concurrent Coding Dashboard Functionality", "Navigating to Concurrent Coding Dashboard")

        logger.info("Navigating to Concurrent Coding Dashboard")
        page.get_by_text("Concurrent Coding").click()
        wait_for_data_load(page, "Concurrent Coding Page", profile="quick")
        screenshot(page, "concurrent_coding_db")

        end_step()
# ==========================================================================================================================================
# Navigate to Conurrent Priority Worklist
# ==========================================================================================================================================
        section_break("Conurrent Priority Worklist")
        step("Concurrent Priority WL", "Navigating to Concurrent Priority Worklist")

        logger.info("Navigating to Concurrent Priority Worklist")
        page.get_by_role("cell", name="Concurrent Priority").click()
        wait_for_data_load(page, "Concurrent Priority Worklist", profile="quick")
        screenshot(page, "concurrent_priority_wl")

        end_step()
# ==========================================================================================================================================
# Manual Patient Selection
# ==========================================================================================================================================  
        section_break("Select Patient Record")
        step("Select Patient", "Select a Patient Record")

        manual_prompt(
            message="Select a patient record",
            completion_note="Patient Selected"
        )

        end_step()
# ==========================================================================================================================================
# Patient Account
# ==========================================================================================================================================  
        section_break("Patient Validation Check")
        step("Confirm Patient Loaded", "Patient Record Loaded")

        with page.expect_popup() as page1_info:
            page1 = page1_info.value
            page1.bring_to_front()
            screenshot(page1, "patient_account")

        end_step()
# ==========================================================================================================================================
# Patient Profile — Record Dates & Physicians
# ==============================================================================================
        section_break("Patient Profile")
        step("Record Patient Profile Data", "Navigating to Patient Profile Tab")

        page1.wait_for_timeout(1000)
        page1.get_by_text("Patient Profile").click()
        page1.wait_for_timeout(1000)

        admit_date      = ctx.input("Document Admit Date (as shown on Patient Profile)")
        acct_number     = ctx.input("Document Account Number")
        attending_md    = ctx.input("Document Attending Provider")
        logger.info(f"Admit Date: {admit_date} | Account: {acct_number} | Attending Provider: {attending_md}")

        screenshot(page1, "patient_profile")
        frames = CACFrames(page1)
        patient_anchor = page1.get_by_role("button", name="Add Finding...")

        end_step() 
# ==========================================================================================================================================
# Navigating to Documents and Codes Tab
# ==========================================================================================================================================
        section_break("Navigate to Document and Codes Tab")
        step("Doc and Codes Tab", "Navigating to Document and Codes Tab")

        page1.wait_for_timeout(1000)  
        page1.get_by_text("Documents and Codes").click()
        page1.wait_for_timeout(1000)

        end_step()
# ==========================================================================================================================================
# Add Finding
# ========================================================================================================================================== 
        section_break("Add Finding")
        step("Add Finding", "Adding Finding")

        page1.wait_for_timeout(1000)
        page1.get_by_role("button", name="Add Finding...").click()
        page1.wait_for_timeout(1000)        
        page1.locator("#findingframe").content_frame.locator("#findingsComments").click()
        page1.wait_for_timeout(1000)
        page1.locator("#findingframe").content_frame.locator("#findingsComments").fill("TEST")
        page1.wait_for_timeout(1000)
        page1.locator("#findingframe").content_frame.locator("#id_finding_add-button").click()

        end_step()
# ==========================================================================================================================================
# Add Diagnosis Reason (I10)
# ==========================================================================================================================================
        section_break("Add Diagnois Code (I10)")
        step("Add I10", "Adding Diagnosis Code (I10)")

        frames.codefinder.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)        
        frames.codefinder.get_by_role("textbox", name="Enter Keyword or Code:").fill("I10")
        page1.wait_for_timeout(1000)
        frames.codefinder.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        frames.codefinder.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        page1.wait_for_timeout(1000)
        frames.codefinder.get_by_role("button", name="OK").click()

        end_step()
# ==========================================================================================================================================
# Copy Code as Primary
# ==========================================================================================================================================
        section_break("Copy Code as Primary")
        step("Copy DX as Primary", "Copying Diagnosis Code I10 as Primary")

        page1.wait_for_timeout(1000)
        frames.codefinder.get_by_text("Essential (primary)").click(button="right")
        page1.wait_for_timeout(1000)        
        frames.codefinder.get_by_text("Copy Code as Primary").click()

        end_step()
# ==========================================================================================================================================
# Add CPT Code (11042)
# ==========================================================================================================================================
        logger.info("Adding CPT Code (0DB58ZX)") 
        page1.wait_for_timeout(1000)
        page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Procedure").click()
        page1.wait_for_timeout(1000)
        page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("0DB58ZX")
        page1.wait_for_timeout(1000)
        page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        page1.wait_for_timeout(1000)
        logger.info("CPT Code Added")
        screenshot(page1, "codeset")
        
        end_step()
# ==========================================================================================================================================
# Add Provider Episode
# ==========================================================================================================================================
        section_break("Add Provider Episode")  
        step("Add Provider Episode", "Adding Provider Episode")

        page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("PrincipalExcision of").click()
        page1.wait_for_timeout(1000)
        page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("PrincipalExcision of").click(button="right")
        page1.wait_for_timeout(1000)
        page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="Add Date/Physician/Episode").click()
        page1.wait_for_timeout(1000)
        page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Start Date").click()
        page1.wait_for_timeout(1000)
        safe_fill(page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Start Date"),
                  admit_date,
                  "Start Date"
        )
        logger.info("Procedure Date Selected....Continuing Automation")
        page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Start Date").press("Tab")
        page1.wait_for_timeout(1000)
        try:
            self_pay = page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_label("Self Pay")
            if self_pay.is_visible():
                self_pay = page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_label("Self Pay").press("Tab")
                logger.info("Navigating to Physician")
            else:
                raise Exception()
        except:
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Physician").click()

        page1.wait_for_timeout(1000)
        safe_fill(page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Physician"),
                    attending_md,
                    "Attending Physician")            
        page1.wait_for_timeout(1000)
        manual_prompt(
            message="Select Provider. Then select Continue in Orbit360.",
            completion_note="Provider Selected. Continuing Automation")           
        page1.wait_for_timeout(1000)
        page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
        screenshot(page1, "codeset_with_providerep_added")
        logger.info("Provider Episode Successfully Added")
        screenshot(page1, "provider_episode_added")
        logger.info("Provider Episode Added!")
        
        end_step()
# ==========================================================================================================================================
# Complete Account
# ==========================================================================================================================================        
        section_break("Complete Account")
        step("Complete Account", "Completing Account")

        page1.wait_for_timeout(1000)
        frames.codefinder.get_by_role("button", name="Complete").click()        
        page1.wait_for_timeout(1000)
        screenshot(page1, "account_completed")

        end_step()
# ==========================================================================================================================================
# Present on Admission
# ==========================================================================================================================================
        section_break("Present on Admission")
        step("Present on Admission Prompt", "Present on Admission Prompt")

        page1.wait_for_timeout(1000)          
        screenshot(page1, "poa_prompt")
        frames.codefinder.get_by_role("button", name="Yes").click()
        logger.info("Yes Button Selected on Prompt")
        manual_prompt(
            message="Select Y for I10 DX code, and click Ok"
            "Once that is complete select the Continue button in Orbit360 to pick back up.",
            completion_note="Option Selected"
        )

        end_step()
# ==============================================================================================
# Complete Account (2nd Try)
# ==============================================================================================        
        section_break("Complete Account")
        step("Complete Account", "Completing Account")

        frames.codefinder.get_by_role("button", name="Complete").click()        
        page1.wait_for_timeout(1000)
        screenshot(page1, "account_completed_2ndtry")
        logger.info("Account has been completed")

        end_step()
# ==========================================================================================================================================
# Close Account
# ==========================================================================================================================================
        section_break("Close Account")
        step("Close Account", "Closing Account")

        page1.get_by_role("button", name="Close").click()
        page.wait_for_timeout(3000)
        logger.info("Test Run Completed Successfully!")
        page.close()

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