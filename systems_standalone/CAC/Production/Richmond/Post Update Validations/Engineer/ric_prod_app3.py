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
ENVIRONMENT = "Production"
PILLAR      = "Richmond"
RUN_TYPE    = "Post Update Validations"
TEST_SET    = "Engineer"

# =========================================================
# Bootstrap — locate project root and import shared runtime
# =========================================================


# Main Run
def run(playwright: Playwright) -> None:
    run_start_time = time.time()
    browser = None
    context = None
    page    = None
    try:
        browser = playwright.chromium.launch(
            headless=False,
            args=["--start-maximized"]
            )
        context = browser.new_context(no_viewport=True)
        start_trace(context)
        page = context.new_page()

    # Navigate to Codefinder Page
        section_break("Codefinder(CRS)")
        step("Codefinder(CRS)", "Launching Codefinder (CRS)")
        page.goto("https://xrdcwpappcac03b.hca.corpad.net/launchCRS.html", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        screenshot(page, "codefinder_crs")
        logger.info("Codefinder (CRS) Successfully Loaded")
        end_step()
    
    # Select Help Button - Select About
        section_break("Help Button")
        step("Help Button", "Open Help Menu & Confirm Version")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        screenshot(page, "codefinder_menu")
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_text("Help").click()
        logger.info("Help Button Selected")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_text("About").click()
        logger.info("About Option Selected")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        screenshot(page, "system_version_details")
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="OK").click()
        end_step()
    
    # Enter Age of Admission
        section_break("Enter Age of Admission")
        step("Age of Admission", "Enter Age of Admission")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("textbox", name="Age at Admission:").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("textbox", name="Age at Admission:").fill("22")
        logger.info("Age Entered")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        screenshot(page, "codefinder_updated")
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Continue").click()
        end_step()

    # Select Patient Disposition
        section_break("Patient Disposition")
        step("Patient Disposition", "Select Patient Disposition")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        screenshot(page, "patient_disposition")
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("radio", name="Home, Self Care (UB-01)").click()
        logger.info("Patient Disposition Updated")
        end_step()

    # Walk Through Coding Process (Example: "BACK")
        section_break("Coding Process")
        step("Coding Process", "Walk Through Coding Process")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page.wait_for_timeout(500)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("BACK")
        screenshot(page, "coding_details")
        logger.info("Coding Pathway Entered")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Continue").click()
        logger.info("Continuing")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        screenshot(page, "codeset_added")
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Back").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Back").click()
        logger.info("Backed Out of Coding Process")
        end_step()

    # Exit Session & Close Page
        section_break("Close Session")
        step("Close Session", "Closing Session")
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)
        screenshot(page, "end_session_button")
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Yes").click()
        logger.info("Session Closed")
        end_step()
        logger.info("Codefinder Test Passed!")

    except Exception as e:
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