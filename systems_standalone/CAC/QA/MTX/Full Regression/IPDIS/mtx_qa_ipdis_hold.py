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
TEST_TYPE    = "IPDIS"
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

    # Navigate to Concurrent Coding Dashboard > Discharged All Worklist
        section_break("Concurrent Coding Dashboard")
        step("Check Concurrent Coding Dashboard Functionality", "Navigating to Concurrent Coding Dashboard")
        page.get_by_text("Concurrent Coding").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        screenshot(page, "concurrent_coding_dashboard")
        logger.info("Selecting Discharged All Worklist")
        page.get_by_text("Discharged All", exact=True).click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        screenshot(page, "discharged_all_worklist")
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

        # Check Help > About > Coding & Reimbursement
            section_break("About - Coding & Reimbursement")
            step("About - Coding & Reimbursement", "Checking Help - About - Coding & Reimbursement")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Selecting Help Option")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="Help").click()
            logger.info("Help Menu Open")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Selecting About")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="About ➧").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Selecting Coding & Reimbursement")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitemcheckbox", name="Coding & Reimbursement System").click()
            logger.info("Details Opened")
            screenshot(page1, "crs_version_details")
            page1.wait_for_timeout(2000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Closing CRS Version Window")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
            logger.info("Checking About - Computer Assisted Coding")
            end_step()

        # Check Help > About > Computer Assisted Coding
            section_break("About - Computer Assisted Coding")
            step("About - Computer Assisted Coding", "Checking Help - About - Computer Assisted Coding")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Selecting Help Option")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="Help").click()
            logger.info("Help Menu Open")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Selecting About")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="About ➧").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Selecting Computer Assisted Coding")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Computer Assisted Coding").click()
            logger.info("Details Opened")
            screenshot(page1, "crs_version_details")
            page1.wait_for_timeout(2000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Closing CRS Version Window")
            page1.locator("#cac_frame").content_frame.get_by_role("button", name="OK").click()
            logger.info("Moving to Next Steps of Test")
            end_step()
            
        # Add Custom Actionable Edit (D630)
            section_break("Add Custom Actionable Edit - D630")
            step("Actionable Edit", "Add Custom Actionable Edit - D630")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Adding Diagnosis Code - D630")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("D630")
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Code Added")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Anemia in neoplastic disease").click(button="right")
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Copy Code as Primary").click() # Copy D630 Dx Code as Primary
            logger.info("Copied Admit Dx as Primary Diagnosis")
            screenshot(page1, "copied_admit_dx")

            manual_prompt(
                message="Select Neoplasm", # Prompt to Select Neoplasm
                completion_note="Neoplasm Selected"
                )     
            
        # Work Through Remaining D630 Prompts (D499)
            logger.info("Neoplasm Selected")
            logger.info("Working Through Remaining Prompts")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("radio", name="Unspecified").check()
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("radio", name="Unspecified").check()
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Continue").click()
            logger.info(" Diagnosis Code (D499) Added Successfully")
            screenshot(page1, "custom_edit_added")
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Working Through Deleting Added Codes")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("PrincipalNeoplasm of").click()
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("PrincipalNeoplasm of").click(button="right")
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Delete Code(s)").click() # Delete Diagnosis Code (D499)
            logger.info("Diagnosis Code (D499) Deleted Successfully")
            page1.wait_for_timeout(1000)
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("PrincipalAnemia in neoplastic").click()
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("PrincipalAnemia in neoplastic").click(button="right")
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Delete Code(s)").click() # Delete Diagnosis Code (D630)
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Code (D630) Deleted Successfully")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Anemia in neoplastic disease").click()
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Anemia in neoplastic disease").click(button="right")
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator(".c_position_relative > div > .c_full_height > iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Delete Code(s)").click() # Delete Admit DX Code (D630)
            logger.info("All Codes Successfully Deleted")
            screenshot(page1, "codes_removed")
            end_step()

        # Pop Out Codefinder
            section_break("Pop Out Codefinder")
            step("Pop Out Codefinder", "Popping Out Codefinder")
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Selecting Pop Out Button")
            page1.get_by_role("button", name=" Pop-out").click()
            page1.wait_for_timeout(500)
            page1.wait_for_load_state("domcontentloaded")

        # Prompt to Allow Pop Up
            manual_prompt(
                message="Click Allow Popup",
                completion_note="Pop Out Window Opening"
                )  
            
        page2 = None
        with page1.expect_popup() as page2_info:
                page2 = page2_info.value
                page2.wait_for_load_state("domcontentloaded")
                logger.info("Page Popped Out")
                screenshot(page2, "pop_out_codefinder")
                end_step()

        # Code Account
                section_break("Code Account (Inpatient Esophagitis with Bleeding)")
                step("Code Account", "Add Codes to Account")
                page2.wait_for_timeout(1000)
                page2.wait_for_load_state("domcontentloaded")
                logger.info("Adding Diagnosis Reason - K2090")
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
                page2.wait_for_timeout(500)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("K2090")
                page2.wait_for_timeout(500)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
                page2.wait_for_timeout(500)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter") # Add Admit DX Code (K2090)
                page2.wait_for_timeout(1000)
                page2.wait_for_load_state("domcontentloaded")
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
                logger.info("Code (K2090) Added")
                page2.wait_for_timeout(1000)
                page2.wait_for_load_state("domcontentloaded")
                logger.info("Adding Diagnosis Code - K2091")
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Diagnosis").click()
                page2.wait_for_timeout(1000)
                page2.wait_for_load_state("domcontentloaded")
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
                page2.wait_for_timeout(500)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("K2091")
                page2.wait_for_timeout(500)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
                page2.wait_for_timeout(500)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter") # Add Diagnosis Code (K2091)
                logger.info("Code (K2091) Added")
                page2.wait_for_timeout(1000)
                page2.wait_for_load_state("domcontentloaded")
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
                page2.wait_for_timeout(1000)
                page2.wait_for_load_state("domcontentloaded")
                logger.info("Adding Diagnosis Code - K2211")
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Diagnosis").click()
                page2.wait_for_timeout(1000)
                page2.wait_for_load_state("domcontentloaded")
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
                page2.wait_for_timeout(500)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("K2211")
                page2.wait_for_timeout(500)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
                page2.wait_for_timeout(500)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter") # Add Diagnosis Code (K2211)
                logger.info("Code (K2211) Added")
                page2.wait_for_timeout(1000)
                page2.wait_for_load_state("domcontentloaded")
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
                page2.wait_for_timeout(1000)
                page2.wait_for_load_state("domcontentloaded")
                logger.info("Adding CPT Code - 0DB58ZX")
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Procedure").click()
                page2.wait_for_timeout(1000)
                page2.wait_for_load_state("domcontentloaded")
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
                page2.wait_for_timeout(1000)
                page2.wait_for_load_state("domcontentloaded")
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("0DB58ZX")
                page2.wait_for_timeout(500)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
                page2.wait_for_timeout(500)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter") # Add CPT Code (0DB58ZX)
                logger.info("CPT Code (0DB58ZX) Added")
                page2.wait_for_timeout(1000)
                page2.wait_for_load_state("domcontentloaded")
                logger.info("Deleting Diagnosis Code - K2091")
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("PrincipalEsophagitis,").click()
                page2.wait_for_timeout(2000)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("PrincipalEsophagitis,").click(button="right")
                page2.wait_for_timeout(2000)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Delete Code(s)").click() # Delete Diagnosis Code (K2091)
                logger.info("Diagnosis Code (K2091) Deleted")
                screenshot(page2, "codeset_added")
                end_step()

        # Add Provider Episode to CPT Codes
                section_break("Add Provider Procedure to CPT Code")
                step("Add Dr Episode to CPT Codes", "Adding Procedure Episode to CPT Codes")
                page2.wait_for_timeout(1000)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("PrincipalExcision of").click()
                page2.wait_for_timeout(500)
                page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("PrincipalExcision of").click(button="right")
                page2.wait_for_timeout(500)
                crs.get_by_role("menuitem", name="Add Date/Physician/Episode").click() # Add Provider Procedure Episode to CPT Code (0DB58ZX)
                page2.wait_for_timeout(1000)
                crs.get_by_role("textbox", name="Start Date").click()
                page2.wait_for_load_state("domcontentloaded")

        # Manual Prompt
                manual_prompt(
                    message="Select Date for Provider Episode",
                    completion_note="Provider Episode Date Entered"
                )

    # Remaining Procedure Date Prompts
                logger.info("Procedure Date Selected....Continuing Automation")
                page2.wait_for_load_state("domcontentloaded")
                crs.get_by_role("textbox", name="Start Date").press("Enter")
                page2.wait_for_timeout(1000)
                crs.get_by_role("textbox", name="Physician").fill("Hansen, Todd H")
                page2.wait_for_timeout(1000)
                crs.get_by_role("cell", name="Hansen, Todd H").click()
                page2.wait_for_timeout(1000)
                crs.get_by_role("button", name="OK").click()
                page2.wait_for_timeout(1000)
                screenshot(page2, "codeset_with_providerep_added")
                logger.info("Provider Episode Successfully Added")
                page2.wait_for_load_state("domcontentloaded")
                end_step()

        # Pop In Codefinder
                section_break("Pop In to Window")
                step("Pop In", "Popping Back Into Window")
                page2.wait_for_load_state("domcontentloaded")
                page2.wait_for_timeout(2000)
                page2.get_by_role("button", name=" Pop-In").click()
                logger.info("Page Popped in Successfully")
                screenshot(page1, "popped_in")
                end_step()

        # Resolve Critical Error
                section_break("Resolve Critical Error")
                step("Resolve Error", "Resolving Critical Error")
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator(".c_position_relative > div > .c_full_height > .c_html_content_iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Resolve").click()
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator(".c_position_relative > div > .c_full_height > .c_html_content_iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_label("To resolve, you need to").select_option("\n13\n")
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator(".c_position_relative > div > .c_full_height > .c_html_content_iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Add additional note").click()
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator(".c_position_relative > div > .c_full_height > .c_html_content_iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Add additional note").fill("\nTEST")
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator(".c_position_relative > div > .c_full_height > .c_html_content_iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
                logger.info("Critical Error Resolved")
                page1.wait_for_load_state("domcontentloaded")
                page1.wait_for_timeout(1000)
                screenshot(page1, "resolved_error")
                end_step()

        # Add Consulting Provider within Abstract Tab
                page1.wait_for_timeout(1000)
                page1.get_by_text("Abstract").click()
                page1.wait_for_timeout(1000)

                # Add Consulting Provider within Abstract Tab
                section_break("Add Consulting Provider")
                step("Add Consult Provider", "Adding Consulting Providers")
                page1.wait_for_timeout(1000)
                logger.info("Selecting Abstract Tab")
                page1.get_by_text("Abstract").click() # Select Abstract Tab
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                screenshot(page1, "abstract_tab")
                logger.info("Adding 1st Consulting Provider")    
                page1.locator("#atframe").content_frame.get_by_role("button").click()
                page1.wait_for_timeout(500)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.locator("c-dropdown div").first.click()
                page1.wait_for_timeout(500)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.locator("input[name=\"search\"]").click()
                page1.wait_for_timeout(500)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.locator("input[name=\"search\"]").fill("Hansen, Todd H")
                page1.wait_for_timeout(500)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.locator("input[name=\"search\"]").press("Enter")
                page1.wait_for_timeout(500)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.get_by_text("Hansen, Todd H").click()
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.get_by_role("button").filter(has_text="OK").click() # Add 1st Consulting Provider

        # Manual Prompt - Enter Date
                manual_prompt(
                    message="Select Date for Consulting Provider Date",
                    completion_note="Date Entered"
                )

                page1.wait_for_timeout(500)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.get_by_role("button").filter(has_text="Save").click()
                logger.info("1st Consulting Provider Added")
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                screenshot(page1, "1st_consult_dr_added")
                logger.info("Adding 2nd Consulting Provider")
                page1.locator("#atframe").content_frame.get_by_role("button").filter(has_text="Add Consulting Provider").click()
                page1.wait_for_timeout(500)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.locator("c-dropdown div").first.click()
                page1.wait_for_timeout(500)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.locator("input[name=\"search\"]").click()
                page1.wait_for_timeout(500)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.locator("input[name=\"search\"]").fill("TEST")
                page1.wait_for_timeout(500)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.locator("input[name=\"search\"]").press("Enter")
                page1.wait_for_timeout(500)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.get_by_text("TEST, ONE").click()
                page1.wait_for_timeout(500)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.get_by_role("button").filter(has_text="OK").click() # Add Second Provider Outside of Date Range & Validate Error

        # Manual Prompt - Enter Date
                manual_prompt(
                    message="Select Date for Consulting Provider Date",
                    completion_note="Date Entered"
                )
                page1.wait_for_timeout(500)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator("#atframe").content_frame.get_by_role("button").filter(has_text="Save").click()
                logger.info("2nd Consulting Provider Added")
                screenshot(page1, "2nd_consult_dr_added")
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                logger.info("Checking Validation Tab")
                page1.get_by_text("Validation").click() # Select Validation Tab and Validate Error is Present
                page1.wait_for_timeout(3000)
                page1.wait_for_load_state("domcontentloaded")
                screenshot(page1, "2nd_validation_tab_check")
                logger.info("Moving Back to Abstract Tab")
                page1.get_by_text("Abstract").click() # Select Abstract Tab
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                logger.info("Update 2nd Provider Entry to Correct Date")
                page1.locator("#atframe").content_frame.get_by_role("button").nth(2).click() # Update 2nd Provider Entry

        # Manual Prompt - Correct Date
                manual_prompt(
                    message="Update Date",
                    completion_note="Date Updated"
                )
                page1.locator("#atframe").content_frame.get_by_role("button").filter(has_text="Save").click()
                logger.info("2nd Consulting Provider Updated")
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                screenshot(page1, "2nd_consult_dr_updated")
                logger.info("Checking Validation Tab")
                page1.get_by_text("Validation").click() # Select Validation Tab and Validate Error is No Longer Present
                page1.wait_for_timeout(3000)
                page1.wait_for_load_state("domcontentloaded")
                screenshot(page1, "final_validation_check")
                logger.info("Navigating Back to Documents and Codes Tab")
                page1.get_by_text("Documents and Codes").click() # Select Document and Codes Tab
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                logger.info("Consulting Provider Logic Tested")
                end_step()

         # Complete Account
                section_break("Complete Account - 1st Try")
                step("Complete Account - 1st Attempt", "Completing Account")
                page1.wait_for_load_state("domcontentloaded")
                page1.wait_for_timeout(1000)
                crs.get_by_role("button", name="Complete").click()
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                screenshot(page1, "poa_prompt")
                page1.locator(".c_position_relative > div > .c_full_height > .c_html_content_iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Yes").click()
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                page1.locator(".c_position_relative > div > .c_full_height > .c_html_content_iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("radio", name="choice Y.").click()
                page1.wait_for_timeout(1000)
                page1.locator(".c_position_relative > div > .c_full_height > .c_html_content_iframe").first.content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()                
                logger.info("POA Added Successfully")
                screenshot(page1, "poa_added")
                logger.info("Attempting to Complete Once More.")
                page1.wait_for_load_state("domcontentloaded")
                page1.wait_for_timeout(1000)
                crs.get_by_role("button", name="Complete").click()
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                logger.info("Account has been completed")
                end_step()

        # Place Account on Hold
                section_break("Place Account on Hold")
                step("Place Account on Hold", "Placing Account on Hold")
                page1.wait_for_load_state("domcontentloaded")
                page1.wait_for_timeout(1000)
                logger.info("Moving Account from Ready to Hold")
                page1.get_by_text("Ready").first.click()
                page1.wait_for_load_state("domcontentloaded")
                page1.wait_for_timeout(1000)
                page1.get_by_text("Hold", exact=True).click()
                page1.wait_for_load_state("domcontentloaded")
                page1.wait_for_timeout(1000)
                page1.locator("#aiframehold").content_frame.locator("#holdReasonLabel-inputFieldContainer").click()
                page1.wait_for_load_state("domcontentloaded")
                page1.wait_for_timeout(1000)
                page1.locator("#aiframehold").content_frame.locator("#holdReasonLabel-filterInput").click()
                page1.wait_for_load_state("domcontentloaded")
                page1.wait_for_timeout(1000)
                page1.locator("#aiframehold").content_frame.locator("#holdReasonLabel-filterInput").fill("3M-3M UPDATE ISSUE")
                page1.wait_for_load_state("domcontentloaded")
                page1.wait_for_timeout(1000)
                page1.locator("#aiframehold").content_frame.get_by_role("listitem", name="3M-3M UPDATE ISSUE").locator("div").nth(1).click()
                page1.wait_for_load_state("domcontentloaded")
                page1.wait_for_timeout(1000)
                page1.locator("#aiframehold").content_frame.locator("textarea").click()
                page1.wait_for_load_state("domcontentloaded")
                page1.wait_for_timeout(1000)
                page1.locator("#aiframehold").content_frame.locator("textarea").fill("TEST")
                page1.wait_for_load_state("domcontentloaded")
                page1.wait_for_timeout(1000)
                page1.locator("#aiframehold").content_frame.get_by_role("button").filter(has_text="Hold").click()
                page1.wait_for_load_state("domcontentloaded")
                page1.wait_for_timeout(1000)
                logger.info("Account Moved to Hold Status")
                screenshot(page1, "hold_status_update")
                end_step()

        # Submit Account
                section_break("Submit Account")
                step("Submit Account", "Submitting Account to Coded Status")
                page1.wait_for_load_state("domcontentloaded")
                page1.get_by_role("button", name="Submit").click()
                page1.wait_for_timeout(1000)
                page1.wait_for_load_state("domcontentloaded")
                logger.info("Account Submitted")
                end_step()

        # Close Account
                section_break("Close Account")
                step("Close Account", "Closing Account")
                page1.wait_for_timeout(4000)
                page1.wait_for_load_state("domcontentloaded")
                page1.get_by_text("Close").click()
                logger.info("Account Closed")
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