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
# ==========================================================================================================================================
# Configuration
# ==========================================================================================================================================
SYSTEM      = "CAC"
ENVIRONMENT = "QA"
PILLAR      = "MTX"
RUN_TYPE    = "Full Regression"
TEST_TYPE    = "Coding References"
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
    # ---- DASHBOARD ---- 
        section_break("CAC Dashboard")
        step("MTX QA CAC Dashboard", "Launching Browser & Navigating to CER QA CAC Dashboard")
        page.goto("https://xrdcwqwebcac20b.hcaqa.corpadqa.net/3M_360App/dashboard", wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        screenshot(page, "cac_dashboard")
        logger.info("CAC Dashboard Loaded & Screenshot Captured")
        end_step()
    # Select Codefinder Button
        section_break("Codefinder")
        step("Codefinder", "Opening Codefinder")
        with page.expect_popup() as page1_info:
            page.get_by_role("button", name="Codefinder").click()
        page1 = page1_info.value
        page1.bring_to_front()
        page1.wait_for_load_state("domcontentloaded")
        page1.wait_for_timeout(4000)
        screenshot(page1, "codefinder")
        logger.info("Codefinder Loaded & Screenshot Captured")
        end_step()
# Select Coding References
        section_break("Coding References Page")
        step("Coding References", "Opening Coding References Page")
        with page1.expect_popup() as page2_info:
            page1.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Reference (CTRL + R)").click()
        page2 = page2_info.value
        page2.bring_to_front()
        page2.wait_for_load_state("domcontentloaded")
        page2.wait_for_timeout(2000)
        screenshot(page2, "coding_refs")
        logger.info("Coding References Page Loaded & Screenshot Captured")
        end_step()
# ICD-9-CM Integrated Codebook
        section_break("ICD-9-CM Integrated Codebook")
        step("ICD-9-CM Integrated Codebook", "Opening ICD-9-CM Integrated Codebook")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="ICD-9-CM Integrated Codebook").click()
        with page2.expect_popup() as page3_info:
            page3 = page3_info.value
        page3.bring_to_front()
        page3.wait_for_load_state("domcontentloaded")
        page3.wait_for_timeout(2000)
        screenshot(page3, "icd_9_cm_integrated_codebook")
        logger.info("ICD-9-CM Integrated Codebook Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page3.get_by_role("button", name="References (Alt+R)").click()
        end_step()
# ICD-10-CM/PCS Integrated
        section_break("ICD-10-CM/PCS Integrated")
        step("ICD-10-CM/PCS Integrated", "Opening ICD-10-CM/PCS Integrated")
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="ICD-10-CM/PCS Integrated").click()
        page3.bring_to_front()
        page3.get_by_role("heading", name="Drugs").click()
        page3.wait_for_timeout(2000)
        screenshot(page3, "icd_10_cm_pcs_integrated")
        logger.info("ICD-10-CM/PCS Integrated Codebook Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page3.get_by_role("button", name="References (Alt+R)").click()
        end_step()
# Current Procedural Terminology
        section_break("Current Procedural Terminology")
        step("Current Procedural Terminologyk", "Opening Current Procedural Terminology")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Current Procedural Terminology").click()
        page2.bring_to_front()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Appendix A - Modifiers").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.wait_for_timeout(2000)
        screenshot(page2, "current_proc_term_appendix_a")
        logger.info("Current Procedural Terminology Loaded & Screenshot Captured")
        page2.wait_for_load_state("domcontentloaded")
        logger.info("Navigating Back to References Page")
        page2.get_by_role("button", name="References").click()
        end_step()
# AHA Coding Clinic for ICD-9
        section_break("AHA Coding Clinic for ICD-9")
        step("AHA Coding Clinic for ICD-9", "Opening AHA Coding Clinic for ICD-9")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="AHA Coding Clinic for ICD-9-").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.wait_for_timeout(1000)
        screenshot(page2, "aha_coding_clinic_icd_9")
        logger.info("AHA Coding Clinic for ICD-9 Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page2.get_by_role("button", name="References").click()
        end_step()
# Dorland's Medical Dictionary
        section_break("Dorland's Medical Dictionary")
        step("Dorland's Medical Dictionary", "Opening Dorland's Medical Dictionary")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Dorland's Medical Dictionary").click()
        with page2.expect_popup() as page4_info:
            page4 = page4_info.value
        page4.wait_for_load_state("domcontentloaded")
        page4.get_by_role("button", name="Accept all cookies").click()
        page4.wait_for_load_state("domcontentloaded")
        page4.get_by_role("link", name="A-Ad").click()
        page4.wait_for_load_state("domcontentloaded")
        page4.get_by_role("link", name="adenylyl", exact=True).click()
        page4.bring_to_front()
        page4.wait_for_load_state("domcontentloaded")
        screenshot(page4, "dorlands_dictionary")
        logger.info("Dorland's Medical Dictionary Loaded & Screenshot Captured")
        logger.info("Closing Page & Navigating Back to References Page")
        page4.close()
        end_step()
    # AMA CPT Assistant
        section_break("AMA CPT Assistant")
        step("AMA CPT Assistant", "Opening AMA CPT Assistant")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="AMA CPT® Assistant").click()
        page2.bring_to_front()
        page2.wait_for_timeout(2000)
        page2.wait_for_load_state("domcontentloaded")
        screenshot(page2, "ama_cpt_assist")
        logger.info("AMA CPT Assistant Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page2.get_by_role("button", name="References").click()
        end_step()
    # Anatomy Appendices
        section_break("Anatomy Appendices")
        step("Anatomy Appendices", "Opening Anatomy Appendices")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Anatomy Appendices").click()
        with page2.expect_popup() as page5_info:
            page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_text("Arteries").click()
        page5 = page5_info.value
        page5.bring_to_front()
        page5.wait_for_load_state("domcontentloaded")
        page5.wait_for_timeout(5000)
        screenshot(page5, "anatomy_appendices")
        logger.info("Anatomy Appendices Loaded & Screenshot Captured")
        logger.info("Closing Page & Navigating Back to References Page")
        page5.close()
        end_step()
    # Clinical Pharmacology
        section_break("Clinical Pharmacology")
        step("Clinical Pharmacology", "Opening Clinical Pharmacology")
        page2.get_by_role("button", name="References").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.wait_for_timeout(500)
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Clinical Pharmacology powered").click()
        with page2.expect_popup() as page6_info:
            page6 = page6_info.value
        page6.bring_to_front()
        page6.wait_for_load_state("domcontentloaded")
        page6.get_by_role("button", name="Continue").click()
        page6.wait_for_load_state("domcontentloaded")
        page6.get_by_text("Abacavir", exact=True).click()
        page6.wait_for_load_state("domcontentloaded")
        page6.get_by_text("×The Future of Clinical").click()
        page6.wait_for_load_state("domcontentloaded")
        page6.wait_for_timeout(3000)
        screenshot(page6, "clinical_pharmacology")
        logger.info("Clinical Pharmacology Loaded & Screenshot Captured")
        logger.info("Closing Page & Navigating Back to References Page")
        page6.close()
        end_step()
    # Elsevier's Anatomy Plates
        section_break("Elsevier's Anatomy Plates")
        step("Elsevier's Anatomy Plates", "Opening Elsevier's Anatomy Plates")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Elsevier's Anatomy Plates").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Circulatory System").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Aortic balloon valvuloplasty").click()
        page2.bring_to_front()
        page2.wait_for_load_state("domcontentloaded")
        screenshot(page2, "elseviers_anatomy_plate")
        logger.info("Elsevier's Anatomy Plates Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page2.get_by_role("button", name="References").click()
        end_step()
    # AHA Coding Clinic for HCPCS
        section_break("AHA Coding Clinic for HCPCS")
        step("AHA Coding Clinic for HCPCS", "Opening AHA Coding Clinic for HCPCS")
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="AHA Coding Clinic for HCPCS").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.wait_for_timeout(2000)
        screenshot(page2, "aha_coding_clinic_hcpcs")
        logger.info("AHA Coding Clinic for HCPCS Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page2.get_by_role("button", name="References").click()
        end_step()
    # Coders' Desk Reference for Procedures by Optum
        section_break("Coders' Desk References")
        step("Coders' Desk References", "Opening Coders' Desk References")
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Coders' Desk Reference for Procedures by Optum").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Introduction").click()
        page2.wait_for_load_state("domcontentloaded")
        screenshot(page2, "coders_desk_ref")
        logger.info("Coders' Desk Reference Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page2.get_by_role("button", name="References").click()
        end_step()
    # Shortcut to CPT Lay
        section_break("Shortcut to CPT Lay")
        step("Shortcut to CPT Lay", "Opening Shortcut to CPT Lay")
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Shortcut to CPT® Lay").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="- 49906").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="40500").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.wait_for_timeout(2000)
        screenshot(page2, "shortcut_cpt_lay")
        logger.info("Shortcut to CPT Lay Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page2.get_by_role("button", name="References").click()
        end_step()
    # Anesthesia Crosswalk
        section_break("Anesthesia Crosswalk")
        step("Anesthesia Crosswalk", "Opening Anesthesia Crosswalk")
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Anesthesia Crosswalk").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="- 10021").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="- 29999").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.wait_for_timeout(2000)
        screenshot(page2, "anesthesia_crosswalk")
        logger.info("Anesthesia Crosswalk Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page2.get_by_role("button", name="References").click()
        end_step()
    # Faye Brown's ICD-9-CM Coding
        section_break("Faye Brown's ICD-9-CM Coding")
        step("Faye Brown's ICD-9-CM Coding", "Opening Faye Brown's ICD-9-CM Coding")
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Faye Brown's ICD-9-CM Coding").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="1.   Introduction to the ICD-").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="CHAPTER OVERVIEW").click()
        page2.wait_for_load_state("domcontentloaded")
        screenshot(page2, "faye_browns")
        logger.info("Faye Brown's ICD-9-CM Coding Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page2.get_by_role("button", name="References").click()
        end_step()
# ICD-10-CM and ICD-10-PCS
        section_break("ICD-10-CM and ICD-10-PCS")
        step("ICD-10-CM and ICD-10-PCS", "Opening ICD-10-CM and ICD-10-PCS")
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="ICD-10-CM and ICD-10-PCS").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="1 Introduction to the ICD-10-").click()
        page2.wait_for_load_state("domcontentloaded")
        screenshot(page2, "icd_10_cm_pcs")
        logger.info("ICD-10-CM and ICD-10-PCS Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page2.get_by_role("button", name="References").click()
        end_step()
    # Mosby's Manual of Diagnostic
        section_break("Mosby's Manual of Diagnostic")
        step("Mosby's Manual of Diagnostic", "Opening Mosby's Manual of Diagnostic")
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Mosby's Manual of Diagnostic").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Quick Tips for Using this").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Common Reference Ranges").click()
        page2.wait_for_load_state("domcontentloaded")
        screenshot(page2, "mosbys_manual")
        logger.info("Mosby's Manual of Diagnostic Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page2.get_by_role("button", name="References").click()
        end_step()
    # Dorland's Dictionary of
        section_break("Dorland's Dictionary")
        step("Dorland's Dictionary", "Opening Dorland's Dictionary")
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Dorland's Dictionary of").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Preface").click()
        page2.wait_for_load_state("domcontentloaded")
        screenshot(page2, "dorlands_abbreviations")
        logger.info("Dorland's Dictionary Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page2.get_by_role("button", name="References").click()
        end_step()
    # ICD-9 MS-DRGs Definitions
        section_break("ICD-9 MS-DRGs Definitions")
        step("ICD-9 MS-DRGs Definitions", "Opening ICD-9 MS-DRGs Definitions")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="ICD-9 MS-DRGs Definitions").click()
        with page2.expect_popup() as page7_info:
            page7 = page7_info.value
        page7.bring_to_front()
        page7.wait_for_load_state("domcontentloaded")
        page7.wait_for_timeout(4000)
        screenshot(page7, "icd_9_ms_drgs_definitions")
        logger.info("ICD-9 MS-DRGs Definitions Loaded & Screenshot Captured")
        logger.info("Closing Page & Navigating Back to References Page")
        page7.close()
        end_step()
    # ICD-10 MS-DRGs Definitions
        section_break("ICD-10 MS-DRGs Definitions")
        step("ICD-10 MS-DRGs Definitions", "Opening ICD-10 MS-DRGs Definitions")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="ICD-10 MS-DRGs Definitions").click()
        with page2.expect_popup() as page8_info:
            page8 = page8_info.value
        page8.get_by_role("link", name="Index by MS-DRG").click()
        page8.wait_for_load_state("domcontentloaded")
        page8.get_by_role("link", name="DRG 001   Heart Transplant or").click()
        page8.bring_to_front()
        page8.wait_for_load_state("domcontentloaded")
        screenshot(page8, "icd_10_ms_drgs_definitions")
        logger.info("ICD-10 MS-DRGs Definitions Loaded & Screenshot Captured")
        logger.info("Closing Page & Navigating Back to References Page")
        page8.close()
        end_step()
    # The Merck Manual
        section_break("The Merck Manual")
        step("The Merck Manual", "Opening The Merck Manual")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="The Merck Manual").click()
        with page2.expect_popup() as page9_info:
            page9 = page9_info.value
        page9.bring_to_front()
        page9.wait_for_load_state("domcontentloaded")
        page9.get_by_role("button", name="Accept Optional Cookies").click()
        page9.wait_for_timeout(4000)
        screenshot(page9, "merck_manual")
        logger.info("The Merck Manual Loaded & Screenshot Captured")
        logger.info("Closing Page & Navigating Back to References Page")
        page9.close()
        end_step()
    # Dr. Z's Interventional
        section_break("Dr. Z's Interventional")
        step("Dr. Z's Interventional", "Opening Dr. Z's Interventional")
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Dr. Z's Interventional").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Introduction").click()
        page2.wait_for_load_state("domcontentloaded")
        screenshot(page2, "dr_z_interventional")
        logger.info("Dr. Z's Interventional Loaded & Screenshot Captured")
        logger.info("Navigating Back to References Page")
        page2.get_by_role("button", name="References").click()
        end_step()
    # Clinical Documentation
        section_break("Clinical Documentation")
        step("Clinical Documentation", "Opening Clinical Documentation")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Clinical Documentation").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="APR DRG").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Diseases and Disorders of the Nervous System").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.locator("iframe[name=\"contentframe\"]").content_frame.get_by_role("button", name="Seizure alternatives").click()
        page2.wait_for_load_state("domcontentloaded")
        page2.wait_for_timeout(2000)
        screenshot(page2, "clinical_documentation")
        logger.info("Clinical Documentation Loaded & Screenshot Captured")
        page2.get_by_role("button", name="References").click()
        end_step()
# =========================================================
# Wrapping Up
# =========================================================
        section_break("Wrapping Up Validation")
        step("Closing Browser", "All Coding References Validated. Closing Browser")
        page2.wait_for_timeout(1000)
        page2.close()
        end_step()

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