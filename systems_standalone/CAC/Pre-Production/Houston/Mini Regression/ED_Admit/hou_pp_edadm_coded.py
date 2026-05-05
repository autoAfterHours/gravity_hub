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
PILLAR      = "Houston"
RUN_TYPE    = "Mini Regression"
TEST_TYPE    = "ED_Admit"
# ==========================================================================================================================================
# Bootstrap — locate project root and import shared runtime
# ==========================================================================================================================================
# ==========================================================================================================================================
# ==========================================================================================================================================
# Main Run
# ==========================================================================================================================================
def run(playwright: Playwright) -> None:
    run_start_time = time.time()
    acct_number = None
    admit_date = None
    browser = None
    context = None
    page    = None
    page1   = None
    admit_date = acct_number = attending_md = iv_start_time = iv_stop_time = ""
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
            "iv_start_time": ("IV Start", lambda: iv_start_time),
            "iv_stop_time": ("IV Stop", lambda: iv_stop_time),
            "acct_number": ("Account",   lambda: acct_number),
            "attending_md": ("Attending Provider", lambda: attending_md),
        }
        parts = [f"{labels[f][0]}: {labels[f][1]()}" for f in fields if labels[f][1]()]
        return f"  [{' | '.join(parts)}]" if parts else ""
    page2   = None
    crs_frame = None
    try:
        pre_run_check("https://FWDCWTWEBCAC03B.HCA.CORPAD.NET/3M_360App")
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
        step("Houston Pre-Production CAC Dashboard", "Launching Browser & Navigating to Dashboard")
        page.goto("https://FWDCWTWEBCAC03B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")
        wait_for_data_load(page, "CAC Dashboard", profile="popup")
        screenshot(page,"cac_dashboard")
        end_step()
# ==========================================================================================================================================
# HIM Charger
# ==========================================================================================================================================
        section_break("HIM Charger Dashboard")
        step("Check HIM Charger Dashboard Functionality", "Navigating to HIM Charger")
        logger.info("Navigating to HIM Charger Dashboard")
        page.get_by_text("HIM Charger").click()
        wait_for_data_load(page, "HIM Charger Page", profile="popup")
        screenshot(page, "him_charger_dashboard")
        end_step()
# ==========================================================================================================================================
# ED Admit Worklist
# ==========================================================================================================================================
        section_break("ED Admit Worklist")
        step("ED Admit Worklist", "Navigating to ED Admit Worklist")
        logger.info("Selecting ED Admit Worklist")
        page.get_by_text("ED Admits", exact=True).click()
        wait_for_data_load(page, "ED Admit Worklist", profile="popup")
        screenshot(page, "edadmit_wl")
        end_step()
# ==========================================================================================================================================
# Ready Bucket
# ==========================================================================================================================================   
        section_break("Ready Bucket")
        step("Ready Bucket", "Navigating to Ready Bucket")
        logger.info("Selecting Ready Bucket")
        page.get_by_text("Ready", exact=True).nth(3).click()
        wait_for_data_load(page, "Ready Bucket", profile="popup")
        screenshot(page, "edadmit_ready_bucket")
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
# Direct Code (99285)
# ==========================================================================================================================================
        section_break("Direct Code Account")
        step("Direct Code Account", "Adding Codeset") 
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Procedure").click()
        logger.info("Entering Code(99285)")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("99285")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        logger.info("Code Entered")
# ==========================================================================================================================================
# Direct Code (90471)
# ==========================================================================================================================================
        logger.info("Entering Code(90471)")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Procedure").click()        
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("90471")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        logger.info("Code Entered")
# ==========================================================================================================================================
# Direct Code (32665)
# ==========================================================================================================================================
        logger.info("Entering Code(32665)")   
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Procedure").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("32665")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        logger.info("Code Entered")
        logger.info("All Codes Entered Successfully")
        end_step()         
# ==========================================================================================================================================
# Add Procedure Date to CPT Codes
# ==========================================================================================================================================
        section_break("Add Provider Episode to CPT Codes")
        step("Add Provider Episode", "Adding Provider Episode to CPT Codes")
        page1.wait_for_timeout(1000)
# ==================================================================
# Add Provider Episode Navigation (Right Click Code)
        try:
            add_dr = page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Thoracoscopy, surgical; with")
            if add_dr.is_visible():
                page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Thoracoscopy, surgical; with").click(button="right")
            else:
                raise Exception()
        except:
            logger.info("Code not available, moving to next step")
# ==================================================================
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="Add Date/Physician/Episode").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Start Date").click()
        safe_fill(page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Start Date"),
                  admit_date,
                  "Start Date")
        page1.wait_for_timeout(1000)
        logger.info("Procedure Date Selected....Continuing Automation")
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Start Date").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Start Date").press("Tab")
        page1.wait_for_timeout(1000)
        try:
            self_pay = page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_label("Self Pay")
            if self_pay.is_visible():
                self_pay = page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_label("Self Pay").press("Tab")
            else:
                raise Exception()
        except:
            logger.error(f"Self Pay Not Available. Moving to Next Step")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Physician").click()
        page1.wait_for_timeout(1000)
        safe_fill(page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Physician"),
                    attending_md,
                    "Attending Physician")    
        page1.wait_for_timeout(1000)
        manual_prompt("Select Provider.",completion_note="Provider Selected. Continuing Automation")            
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
        screenshot(page1, "codeset_with_providerep_added")
        logger.info("Provider Episode Successfully Added") 
        end_step()  
# ==========================================================================================================================================
# Complete Account (1st Try)
# ==========================================================================================================================================
        section_break("Complete Account")
        step("Complete Account", "Completing Account")
        page1.wait_for_timeout(1000)
        try:
            complete = page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete")
            if complete.is_visible():
                complete = page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
            else:
                raise Exception()
        except:
            manual_prompt(
            message="Complete button not working. Review Account and Clear Blocker. Once Complete hit Continue in Orbit to pick up next step.",
            completion_note="Issue corrected. Moving to next step.")  
        page1.wait_for_timeout(1000)
        screenshot(page1, "account_completed")
        logger.info("Account has been completed")
        end_step()
# ==========================================================================================================================================
# Click Charge Codes Tab
# ==========================================================================================================================================
        section_break("Charge Codes Tab")
        step("Check Charge Codes Tab", "Navigating to Charge Codes Tab")
        page1.get_by_role("tab", name=re.compile(r"Charge Codes")).locator("a").click()
        logger.info("Charge Code Tab Selected")
        screenshot(page1, "charge_codes_tab_1st_try")
        end_step()
# ==========================================================================================================================================
# Submit Account & Validate Error (1st Try)
# ==========================================================================================================================================
        section_break("Submit & Validate Error")
        step("Submit and Validate", "Submit Account & Validate Error")
        page1.wait_for_timeout(1000)
        page1.get_by_role("button").filter(has_text="Submit & Next").click()
        logger.info("Submit & Next Selected...Validating Error")
        screenshot(page1, "validation_error_1st_try")
        end_step()
# ==========================================================================================================================================
# Navigating Back to Documents and Codes Tab
# ==========================================================================================================================================
        section_break("Navigate Back to Documents and Codes Tab")
        step("Documents and Codes", "Navigating Back to Documents and Codes Tab")
        page1.wait_for_timeout(1000)
        page1.get_by_role("tab", name="Documents and Codes").locator("a").click()
        end_step()
# ==========================================================================================================================================
# Select & Delete Codes
# ============================================================================================================================================================================================
        section_break("Delete Codes - 99285 & 90471")
        step("Delete Codes", "Deleting Codes 99285 & 90471")
        logger.info("Clicking Code 99285")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Emergency department visit").click()
        logger.info("Code Selected")
        logger.info("Clicking Code 90471")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Immunization administration;").click(modifiers=["ControlOrMeta"])
        logger.info("Code Selected")
        logger.info("Right Clicking Codes")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Immunization administration;").click(button="right")
        logger.info("Menu Opened")
        logger.info("Deleting Codes")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Delete Code(s)").click()
        logger.info("Codes Deleted Successfully")
        end_step()
# ==========================================================================================================================================
# Complete Account (1st Try)
# ==========================================================================================================================================
        section_break("Complete Account")
        step("Complete Account", "Completing Account")
        page1.wait_for_timeout(1000)
        try:
            complete = page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete")
            if complete.is_visible():
                complete = page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
            else:
                raise Exception()
        except:
            manual_prompt(
            message="Complete button not working. Review Account and Clear Blocker. Once Complete hit Continue in Orbit to pick up next step.",
            completion_note="Issue corrected. Moving to next step.")  
        page1.wait_for_timeout(1000)
        screenshot(page1, "account_completed")
        logger.info("Account has been completed")
        end_step()
# ==========================================================================================================================================
# Click Charge Codes Tab
# ==========================================================================================================================================
        section_break("Charge Codes Tab")
        step("Check Charge Codes Tab", "Navigating to Charge Codes Tab")
        page1.get_by_role("tab", name=re.compile(r"Charge Codes")).locator("a").click()
        screenshot(page1, "charge_codes_tab_2nd_try")
        logger.info("Charge Code Tab Selected")
        end_step()
# ==========================================================================================================================================
# Submit Account & Validate Error (2nd Try)
# ==========================================================================================================================================
        section_break("Submit & Validate Error")
        step("Submit and Validate", "Submit Account & Validate Error") 
        page1.get_by_role("button").filter(has_text="Submit & Next").click()
        logger.info("Submit & Next Selected...Validating Error")
        screenshot(page1, "validation_error_1st_try")
        logger.info("Navigating Back to Documents and Codes Tab") 
        page1.get_by_role("tab", name="Documents and Codes").locator("a").click() 
        end_step()
# ==========================================================================================================================================
# WSS - Facility - E&M Tab
# ==========================================================================================================================================
        section_break("Worksheet Services - E&M Tab")
        step("WSS E&M", "Add E&M WSS Codes")
        logger.info("Opening Worksheet Services")
        page1.wait_for_timeout(1000)
        page1.locator("m-cac iframe").content_frame.get_by_role("button", name="Launch Worksheet Services").click()
        logger.info("Worksheet Services Opened")
        screenshot(page1, "WSS")
        logger.info("Clearing Selected Options")
        page1.wait_for_timeout(1000) 
        try:
            clear_btn = page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Clear")
            if clear_btn.is_visible():
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Clear").click()
            else:
                raise Exception()
        except:
            logger.info("Clear Button not available, moving to next step")
        logger.info("Selecting Level 2 Option")
        page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#item-4000185378-checkbox-box").click() # Level 2
        logger.info("Option Selected")
        logger.info("Selecting Level 3 Option")
        page1.wait_for_timeout(1000)
        page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#item-4000185417-checkbox-box").click() # Level 3
        logger.info("Option Selected")
        logger.info("Selecting Level 4 Option")
        page1.wait_for_timeout(1000)
        page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#item-4000185426-checkbox-box").click() # Level 4
        logger.info("Option Selected")
        logger.info("Selecting Level 5 Option")
        page1.wait_for_timeout(1000)
        page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#item-4000185381-checkbox-box").click() # Level 5
        logger.info("Option Selected")
        logger.info("Calculating Changes")
        page1.wait_for_timeout(1000)
        page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Calculate").click()
        logger.info("Codes Calculated")
        screenshot(page1, "calulated_em")
        end_step()
# ==========================================================================================================================================
# WSS - Facility - I&I Tab
# ==========================================================================================================================================     
        section_break("Worksheet Services - I&I Tab")
        step("WSS I&I", "Add I&I WSS Codes")

        logger.info("Navigating to I&I Tab")
        try:
            i_i = page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("tab", name="Infusion & Injection")
            if i_i.is_visible():
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("tab", name="Infusion & Injection").click()
                page1.wait_for_timeout(1000)
                logger.info("I&I Tab Open")
                logger.info("Entering Data into Site")
                page1.wait_for_timeout(1000)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input-text-Infusion-site-1").click() # IV Infusions (Site 1)
                page1.wait_for_timeout(1000)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input-text-Infusion-site-1").fill("1") # IV Infusions (Site 1)
                logger.info("1 Entered for Site")
                logger.info("Entering Data into Drug")
                page1.wait_for_timeout(1000)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_text_infusion_0_drug_0").click() # IV Infusions (Drug)
                page1.wait_for_timeout(1000)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_text_infusion_0_drug_0").fill("3") # IV Infusions (Drug)
                logger.info("3 Entered for Drug")
                logger.info("Selecting IV Type")
                page1.wait_for_timeout(1000)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#infusion_0_row_0").get_by_role("button").click() # IV Infusions (IV Type)
                page1.wait_for_timeout(1000)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_text("Infusion > 15 min to 1 hr").click() # IV Infusions (IV Type)
                logger.info("IV Type Selected")
                logger.info("Enter Data for Quanity")
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_number_infusion_0_quantity_0").click() # IV Infusions (Quanity)
                page1.wait_for_timeout(1000)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_number_infusion_0_quantity_0").fill("1") # IV Infusions (Quanity)
                logger.info("1 Entered for Quantity")
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_number_infusion_0_quantity_0").press("Tab") # IV Infusions (Quanity)
                safe_fill(page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_date_infusion_0_start_datetime_0"),
                  iv_start_time,
                  "IV Start Time")
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_date_infusion_0_start_datetime_0").press("Tab")
                safe_fill(page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_date_infusion_0_stop_datetime_0"),
                  iv_stop_time,
                  "IV Stop Time")                
                screenshot(page1, "i_i_uncalculated")
                page1.wait_for_timeout(1000)
            else:
                raise Exception()
        except:
            logger.info("I&I not available, moving to next step")
        try:
            calculate_btn = page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Calculate")
            if calculate_btn.is_visible():
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Calculate").click()
            else:
                raise Exception()
        except:
            logger.info("Calculate not available, moving to next step")
        try:
            process = page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Process")
            if process.is_visible():
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Process").click()
            else:
                raise Exception()
        except:
            manual_prompt(
            message="Update & Calculate Any Remaining Codes. This will also require the Select All button be selected, and any new codes marked as Do Not Charge",
            completion_note="Final Scan Completed")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Process").click()
        page1.wait_for_timeout(1000)
        logger.info("WSS Codes Added")
        end_step()
# ==========================================================================================================================================
# Complete Account
# ==========================================================================================================================================
        section_break("Complete Account")
        step("Complete Account", "Completing Account")
        page1.wait_for_timeout(1000)
        try:
            complete_button = page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete")
            if complete_button.is_visible():
                page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
            else:
                raise Exception()
        except:
            manual_prompt(
            message="Complete button not working. Review Account and Clear Blocker. Once Complete hit Continue in Orbit to pick up next step.",
            completion_note="Issue corrected. Moving to next step.")  
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
        page1.wait_for_timeout(1000)
        screenshot(page1, "account_completed")
        logger.info("Account has been completed")
        end_step()
# ==========================================================================================================================================
# Click Charge Codes Tab
# ==========================================================================================================================================
        section_break("Charge Codes Tab")
        step("Check Charge Codes Tab", "Navigating to Charge Codes Tab")
        page1.get_by_role("tab", name=re.compile(r"Charge Codes")).locator("a").click()
        logger.info("Charge Code Tab Selected")
        screenshot(page1, "charge_codes_tab_1st_try")
        end_step()
# ==========================================================================================================================================
# Submit Account
# ==========================================================================================================================================
        section_break("Submit Account")
        step("Submit Account", "Submitting Account to Coded Status")
        page1.wait_for_timeout(1000)
        try:
            submit_button = page1.get_by_role("button").filter(has_text="Submit & Next")
            if submit_button.is_visible():
                page1.get_by_role("button").filter(has_text="Submit & Next").click()
            else:
                raise Exception()
        except:
            manual_prompt(
            message="Submit & Next button not working. Review Account and Clear Blocker. Once Complete hit Continue in Orbit to pick up next step.",
            completion_note="Issue corrected. Moving to next step."
        )  
            page1.get_by_role("button").filter(has_text="Submit & Next").click()
        logger.info("Account Submitted")
        end_step()
# ==========================================================================================================================================
# Close Account
# ==========================================================================================================================================
        section_break("Close Account")
        step("Close Account", "Closing Account")
        page1.wait_for_timeout(1000)
        try:
            close_acct = page1.get_by_text("Close")
            if close_acct.is_visible():
                close_acct = page1.get_by_text("Close").click()
            else:
                raise Exception()
        except:
            manual_prompt(
            message="Close Account button not working. Review Account and Clear Blocker. Once Complete hit Continue in Orbit to pick up next step.",
            completion_note="Issue corrected. Moving to next step.")  
            page1.get_by_text("Close").click()
        logger.info("Account Closed")
        end_step()
# ==========================================================================================================================================
# Navigate to Charged Today Bucket
# ==========================================================================================================================================
        section_break("Wrap Up & Confirm Account Lands on Charged Today Bucket")
        step("Navigate to Charged Today Bucket", "Navigating to Charged Today Bucket")
        page.bring_to_front()
        page.wait_for_load_state("domcontentloaded")
        page.get_by_text("Charged Today").click()
        wait_for_data_load(page, "Charged Today", profile="popup")
        screenshot(page, "charged_account")
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