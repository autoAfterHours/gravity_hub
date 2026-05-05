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
PILLAR      = "Richmond"
RUN_TYPE    = "Mini Regression"
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
        pre_run_check("https://XRDCWTWEBCAC03B.HCA.CORPAD.NET/3M_360App")
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
        step("Richmond Pre-Production CAC Dashboard", "Launching Browser & Navigating to Dashboard")
        page.goto("https://XRDCWTWEBCAC03B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")
        page.wait_for_timeout(15000)
        screenshot(page,"cac_dashboard")
        end_step()
# ==========================================================================================================================================
# HIM Coding
# ==========================================================================================================================================
        section_break("HIM Coding Dashboard")
        step("Check HIM Coding Dashboard Functionality", "Navigating to HIM Coding")
        page.get_by_text("HIM Coding").click()
        page.wait_for_timeout(15000)
        screenshot(page, "cac_dashboard")
        end_step()
# ==========================================================================================================================================
# ED Worklist
# ==========================================================================================================================================
        section_break("ED Worklist")
        step("ED Worklist", "Navigating to ED Worklist")
        logger.info("Selecting ED Worklist")
        page.get_by_text("ED", exact=True).click()
        page.wait_for_timeout(15000)
        screenshot(page, "him_coding_dashboard")
        end_step()
# =========================================================================================================================================
# Ready Bucket
# ==========================================================================================================================================  
        section_break("Ready Bucket")
        step("Ready Bucket", "Navigating to Ready Bucket")
        logger.info("Selecting Ready Bucket")
        page.get_by_text("Ready", exact=True).nth(3).click()
        page.wait_for_timeout(30000)
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
        page.wait_for_timeout(2000)
        screenshot(page, "patient_search")
        logger.info("Opening Patient Record")
        with page.expect_popup() as page1_info:
            page.get_by_role("row", name=f"Visit ID: {acct_number}").locator("#visitid").click()
            page1 = page1_info.value
            page1.bring_to_front()
            logger.info("Patient Record Open")
            screenshot(page1, "patient_record")
            end_step()
# ==========================================================================================================================================
# Navigating to Documents and Codes Tab
# ==========================================================================================================================================
        section_break("Navigate to Document and Codes Tab")
        step("Doc and Codes Tab", "Navigating to Document and Codes Tab")
        page.wait_for_timeout(10000)
        page1.get_by_text("Documents and Codes").click()
        page1.wait_for_timeout(2000)
        end_step()
# ==========================================================================================================================================
# Update Discharge Disposition
# ==========================================================================================================================================  
        section_break("Update Discharge Disposition")
        step("Updating Discharge Disposition", "Updating Discharge Disposition")
        page1.wait_for_load_state("domcontentloaded")
        page1.wait_for_timeout(1000)
        logger.info("Selecting Discharge Disposition Dropdown")
        page1.locator("#selDis-dropdownPanelTrigger").click()
        page1.wait_for_timeout(1000)
        page1.locator("#selDis-filterInput").click()
        page1.wait_for_timeout(1000)
        page1.locator("#selDis-filterInput").fill("AMA - 07 - Left against medical advice")
        page1.get_by_text("AMA - 07 - Left against medical advice").click()
        logger.info("Discharge Disposition Updated to AMA - 07 - Left against medical advice")
        end_step()
# ==========================================================================================================================================
# Place on Hold
# ==========================================================================================================================================
        section_break("Place Account on Hold")
        step("Place Account on Hold", "Placing Account on Hold")
        page1.wait_for_timeout(1000)
        page1.get_by_role("button").filter(has_text="Ready").click()
        page1.wait_for_timeout(1000)
        page1.get_by_role("menuitem", name="Hold").click()
        page1.wait_for_timeout(1000)
        logger.info("Hold Menu Opening")
        screenshot(page1, "hold_menu")
        page1.wait_for_timeout(1000)        
        page1.locator("#holdReasonLabel-dropdownPanelTrigger span").click() # Filter Search for H&P
        logger.info("Filtering Options and Selecting Hold Reason")
        page1.wait_for_timeout(1000)
        page1.locator("#holdReasonLabel-filterInput").click()
        screenshot(page1, "hold_reason")
        logger.info("Typing Hold Reason")
        page1.wait_for_timeout(1000)
        page1.locator("#holdReasonLabel-filterInput").fill("3M-3M UPDATE ISSUE")
        page1.wait_for_timeout(1000)
        logger.info("Clicking Hold Reason Option")
        page1.get_by_role("listitem", name="3M-3M UPDATE ISSUE").locator("div").nth(1).click()
        logger.info("Hold Reason Selected")
        screenshot(page1, "hold_selected")
        logger.info("Selecting Hold Button")
        page1.locator("#holdReasonForm").get_by_role("button").filter(has_text="Hold").click() # Click Hold Button
        end_step()
# ==========================================================================================================================================
# Close Account
# ==========================================================================================================================================
        section_break("Move to Next Account & Close")
        step("Next Account", "Closing Account")
        page1.wait_for_load_state("domcontentloaded")
        page1.wait_for_timeout(2000)
        try:
            next_btn = page1.get_by_role("button").filter(has_text=re.compile(r"^Next$"))
            if next_btn.is_visible():
                page1.get_by_role("button").filter(has_text=re.compile(r"^Next$")).click()
                page1.wait_for_timeout(3000)
                page1.get_by_text("Close").click()
            else:
                raise Exception()
        except:
            logger.info("Next Button not available, Closing Account.")
            page1.get_by_text("Close").click()
        logger.info("Account Closed")
        end_step()
# ==========================================================================================================================================
# Hold Bucket
# ==========================================================================================================================================
        section_break("Check Hold Bucket")
        step("Verify Account on Hold", "Verify Account Lands on Hold Bucket")
        logger.info("Moving to Hold Bucket")
        page.wait_for_timeout(30000)
        page.locator("span").filter(has_text=re.compile(r"^Hold$")).click()
        page.wait_for_timeout(15000)
        screenshot(page, "hold_bucket")
        logger.info("Test Run Successfully")
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