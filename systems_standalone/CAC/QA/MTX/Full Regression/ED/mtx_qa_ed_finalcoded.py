import os
import sys
import time
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
# =========================================================
# Configuration
# =========================================================
SYSTEM      = "CAC"
ENVIRONMENT = "QA"
PILLAR      = "MTX"
RUN_TYPE    = "Full Regression"
TEST_TYPE    = "ED"
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
# ==========================================================================================================================================
# Hold Bucket Worklist
# ==========================================================================================================================================
        logger.info("Selecting Hold Bucket")
        page.get_by_text("Hold", exact=True).click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        screenshot(page, "ed_hold_bucket")
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
# ==========================================================================================================================================
# Move Account From Hold to Ready
# ========================================================================================================================================== 
            section_break("Move Account from Hold to Ready")
            step("Move to Ready", "Moving Account from Hold to Ready")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(2000)
            page1.get_by_role("button").filter(has_text="Hold").click()
            logger.info("Hold Dropdown Selected")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(2000)
            page1.get_by_role("menuitem", name="Ready").click()
            logger.info("Ready Option Selected")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(2000)
            screenshot(page1, "hold_to_ready_final")
            end_step()
# ==========================================================================================================================================
# WSS - Part 2 (Facility I/I Tab)
# ========================================================================================================================================== 
            section_break("Worksheet Services - I/I Tab")
            step("WSS I/I", "Add I/I WSS Codes")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Opening Worksheet Services")
            page1.locator("m-cac iframe").content_frame.get_by_role("button", name="Launch Worksheet Services").click()
            logger.info("Worksheet Services Opened")
            page1.wait_for_timeout(2000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Opening Injection & Infusion (I/I) Tab")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("tab", name="Infusion & Injection").click()
            logger.info("Injection & Infusion (I/I) Tab Opened")
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Entering Data for Drug")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_text_injection_0_drug_0").click()
            page1.wait_for_timeout(500)
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_text_injection_0_drug_0").fill("1")
            page1.wait_for_timeout(500)
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_text_injection_0_drug_0").press("Tab")
            logger.info("1 was Entered for Drug....Moving to Next Category")
            page1.wait_for_timeout(500)
            logger.info("Entering Data for Quantity")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_number_injection_0_quantity_0").fill("1")
            logger.info("1 was Entered for Quantity....Moving to Next Category")
            page1.wait_for_timeout(500)
            logger.info("Moving to Injection Date/Time Prompt")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_number_injection_0_quantity_0").press("Tab")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_date_injection_0_injection_datetime_0").click()
               
    # Prompt for Injection Start Date/Time
            manual_prompt(
                    message="Enter Injection Start Date and Time",
                    completion_note="Injection Information Entered"
            )
    # Calculate & Process Charges
            section_break("Calculate & Process WSS Charge Code")
            step("Calculate and Process", "Calculating and Processing WSS Charge Codes")
            screenshot(page1, "i_i_codes_added")
            logger.info("Calculating Changes")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Calculate").click()
            logger.info("Codes Calculated")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            screenshot(page1, "charges_calculated_iandi")
            logger.info("Processing Changes")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Process").click()
            logger.info("Charge Codes Processed and Present in Codefinder")
            end_step()

    # Add Procedure Date to CPT Codes
            section_break("Add Provider Episode to CPT Codes")
            step("Add Provider Episode", "Adding Provider Episode to CPT Codes")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(500)
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("THERAPEUTIC PROPHYLACTIC/DX").click(button="right")
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
            page1.wait_for_timeout(2000)
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
            logger.info("Account has been completed")
            screenshot(page1, "account_completed")
            end_step()

    # Submit Account
            section_break("Submit Account")
            step("Submit Account", "Submitting Account to Coded Status")
            page1.wait_for_load_state("domcontentloaded")
            page1.get_by_role("button").filter(has_text="Submit & Next").click()
            page1.wait_for_timeout(3000)
            logger.info("Account Submitted")
            end_step()

    # Close Account
            section_break("Close Account")
            step("Close Account", "Closing Account")
            page1.wait_for_timeout(5000)
            page1.wait_for_load_state("domcontentloaded")
            page1.get_by_text("Close").click()
            logger.info("Account Closed")
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
            screenshot(page, "coded_account_finalpass")
            logger.info("Coded Account Confirmed")
            page.close()
            logger.info("Test Run Completed Successfully!")
            end_step()
            
    except Exception as e:
        handle_failure(e, page1 or page)

    finally:
        if context:
            save_trace(context)
        if browser:
            browser.close()
        total_duration = time.time() - run_start_time
        logger.info(f"Total Run Duration | {format_duration(total_duration)}")

with sync_playwright() as playwright:
    run(playwright)
