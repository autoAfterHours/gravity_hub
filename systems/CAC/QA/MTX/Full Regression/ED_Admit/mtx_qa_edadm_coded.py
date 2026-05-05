import os
import sys
import time
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
# =========================================================
# Configuration
# =========================================================
SYSTEM      = "CAC"
ENVIRONMENT = "QA"
PILLAR      = "MTX"
RUN_TYPE    = "Full Regression"
TEST_TYPE    = "ED_Admit"
# ==========================================================================================================================================
# Bootstrap — locate project root and import shared runtime
# ==========================================================================================================================================
_env_root = os.environ.get("ORBIT_ROOT")
if _env_root:
    sys.path.insert(0, _env_root)
else:
    _p = Path(__file__).resolve().parent
    while not (_p / "orbit360").is_dir():
        if _p.parent == _p:
            raise RuntimeError("Could not locate Orbit project root.")
        _p = _p.parent
    sys.path.insert(0, str(_p))
# ==========================================================================================================================================
from orbit360.backend.orbit_context import (
    setup, step, end_step, section_break,
    screenshot, manual_prompt, handle_failure, format_duration,
    crs_frame, start_trace, save_trace,
    claim_excel_row, release_excel_row,
)
from orbit360.utils.orbit_script_helpers import (
    init_helpers,
    WAIT_PROFILES, DEFAULT_TIMEOUT, RETRY_COUNT,
    wait_with_intervention, wait_for_data_load,
    safe_click, safe_fill, safe_screenshot, step_with_pause,
    pre_run_check,
)
ctx    = setup(SYSTEM, ENVIRONMENT, PILLAR, RUN_TYPE, TEST_TYPE)
logger = ctx.logger
init_helpers(ctx)
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
        browser = playwright.chromium.launch(
            headless=False,
            args=["--start-maximized"]
            )
        context = browser.new_context(no_viewport=True)
        start_trace(context)
        page = context.new_page()

    # Navigate to CAC Dashsboard
        section_break("CAC Dashboard")
        step("CER QA CAC Dashboard", "Launching Browser & Navigating to CER QA CAC Dashboard")
        page.goto("https://XRDCWQWEBCAC10B.HCAQA.CORPADQA.NET/3M_360App",wait_until="domcontentloaded")
        page.wait_for_timeout(4000)
        screenshot(page, "cac_dashboard")
        logger.info("CAC Dashboard Loaded & Screenshot Captured")
        end_step()

    # Navigate to HIM Charger Dashboard > ED Admits Worklist
        section_break("HIM Charger Dashboard")
        step("Check HIM Charger Dashboard Functionality", "Navigating to HIM Charger Dashboard")
        page.get_by_text("HIM Charger").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        screenshot(page, "him_charger_dashboard")
        logger.info("Selecting ED Admits Worklist")
        page.get_by_text("ED Admits").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        screenshot(page, "edadmit_worklist")
        logger.info("Selecting Ready Bucket")
        page.get_by_text("Ready", exact=True).nth(3).click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
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
        # Direct Code (99285)
            section_break("Direct Code Account")
            step("Direct Code Account", "Adding Codeset")    
            page1.wait_for_timeout(2000)
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Procedure").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Entering Code(99285)")
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("99285")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
            page1.wait_for_timeout(2000)
            logger.info("Code Entered")

        # Direct Code (90471)
            logger.info("Entering Code(90471)")
            page1.wait_for_timeout(2000)
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Procedure").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")            
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page1.wait_for_timeout(1000)
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("90471")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
            page1.wait_for_timeout(2000)
            logger.info("Code Entered")
            
        # Direct Code (32665)
            logger.info("Entering Code(32665)")   
            page1.wait_for_timeout(2000)     
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Procedure").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page1.wait_for_timeout(1000)
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("32665")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded") 
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded") 
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
            page1.wait_for_timeout(2000)
            logger.info("Code Entered")
            logger.info("All Codes Entered Successfully")
            end_step()         

    # Add Procedure Date to CPT Codes
            section_break("Add Provider Episode to CPT Codes")
            step("Add Provider Episode", "Adding Provider Episode to CPT Codes")
            page1.wait_for_load_state("domcontentloaded")
            page1.wait_for_timeout(500)
            page1.pause()
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("EMERGENCY DEPARTMENT VISIT MODERATE MDM").click(button="right")
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

        # Complete Account (1st Try)
            section_break("Completing Account")
            step("Complete Account", "Completing Account")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded") 
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
            logger.info("Clicked Complete")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded") 
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded") 
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
            logger.info("Completed Changes")
            screenshot(page1, "completed_account_1st_try")
            end_step()

        # Click Charge Codes Tab
            section_break("Charge Codes Tab")
            step("Check Charge Codes Tab", "Navigating to Charge Codes Tab")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded") 
            page1.get_by_role("tab", name="Charge Codes (2)").locator("a").click()
            logger.info("Charge Code Tab Selected")
            screenshot(page1, "charge_codes_tab_1st_try")
            end_step()

        # Submit Account & Validate Error (1st Try)
            section_break("Submit & Validate Error")
            step("Submit and Validate", "Submit Account & Validate Error")
            page1.wait_for_timeout(2000)
            page1.wait_for_load_state("domcontentloaded") 
            page1.get_by_role("button").filter(has_text="Submit & Next").click()
            logger.info("Submit & Next Selected...Validating Error")
            screenshot(page1, "validation_error_1st_try")
            page1.wait_for_timeout(3000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Navigating Back to Documents and Codes Tab") 
            page1.get_by_role("tab", name="Documents and Codes").locator("a").click()
            end_step()

        # Select & Delete Codes
            section_break("Delete Codes - 99285 & 90471")
            step("Delete Codes", "Deleting Codes 99285 & 90471")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Clicking Code 99285")
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Emergency department visit").click()
            logger.info("Code Selected")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Clicking Code 90471")
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Immunization administration;").click(modifiers=["ControlOrMeta"])
            logger.info("Code Selected")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Right Clicking Codes")
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Immunization administration;").click(button="right")
            logger.info("Menu Opened")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Deleting Codes")
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Delete Code(s)").click()
            logger.info("Codes Deleted Successfully")
            end_step()

        # Complete Account (1st Try)
            section_break("Completing Account")
            step("Complete Account", "Completing Account")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded") 
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
            logger.info("Clicked Complete")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded") 
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded") 
            page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
            logger.info("Completed Changes")
            screenshot(page1, "completed_account_2nd_try")
            end_step()

        # Click Charge Codes Tab
            section_break("Charge Codes Tab")
            step("Check Charge Codes Tab", "Navigating to Charge Codes Tab")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded") 
            page1.get_by_role("tab", name="Charge Codes (2)").locator("a").click()
            screenshot(page1, "charge_codes_tab_2nd_try")
            logger.info("Charge Code Tab Selected")
            end_step

        # Submit Account & Validate Error (2nd Try)
            section_break("Submit & Validate Error")
            step("Submit and Validate", "Submit Account & Validate Error")
            page1.wait_for_timeout(2000)
            page1.wait_for_load_state("domcontentloaded") 
            page1.get_by_role("button").filter(has_text="Submit & Next").click()
            logger.info("Submit & Next Selected...Validating Error")
            screenshot(page1, "validation_error_1st_try")
            page1.wait_for_timeout(3000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Navigating Back to Documents and Codes Tab") 
            page1.get_by_role("tab", name="Documents and Codes").locator("a").click()
            end_step()

    ### WSS
    ## Facility - E&M Tab
            section_break("Worksheet Services - E&M Tab")
            step("WSS E&M", "Add E&M WSS Codes")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Opening Worksheet Services")
            page1.locator("m-cac iframe").content_frame.get_by_role("button", name="Launch Worksheet Services").click()
            page1.wait_for_timeout(5000)
            logger.info("Worksheet Services Opened")
            screenshot(page1, "WSS")
            logger.info("Selecting Level 2 Option")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#item-4000185378-checkbox-box").click() # Level 2
            logger.info("Option Selected")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Selecting Level 3 Option")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#item-4000185417-checkbox-box").click() # Level 3
            logger.info("Option Selected")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Selecting Level 4 Option")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#item-4000185426-checkbox-box").click() # Level 4
            logger.info("Option Selected")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Selecting Level 5 Option")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#item-4000185381-checkbox-box").click() # Level 5
            logger.info("Option Selected")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Calculating Changes")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Calculate").click()
            logger.info("Codes Calculated")
            page1.wait_for_load_state("domcontentloaded")
            screenshot(page1, "calulated_em")
            end_step()
            
    ### WSS
    ## Facility - I&I Tab
            section_break("Worksheet Services - I&I Tab")
            step("WSS I&I", "Add I&I WSS Codes")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Navigating to I&I Tab")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("tab", name="Infusion & Injection").click()
            logger.info("I&I Tab Open")
            page1.wait_for_timeout(2000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Entering Data into Site")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input-text-Infusion-site-1").click() # IV Infusions (Site 1)
            page1.wait_for_timeout(500)
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input-text-Infusion-site-1").fill("1") # IV Infusions (Site 1)
            logger.info("1 Entered for Site")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Entering Data into Drug")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_text_infusion_0_drug_0").click() # IV Infusions (Drug)
            page1.wait_for_timeout(500)
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_text_infusion_0_drug_0").fill("3") # IV Infusions (Drug)
            logger.info("3 Entered for Drug")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Selecting IV Type")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#infusion_0_row_0").get_by_role("button").click() # IV Infusions (IV Type)
            page1.wait_for_timeout(500)
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_text("Infusion > 15 min to 1 hr").click() # IV Infusions (IV Type)
            logger.info("IV Type Selected")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded")
            logger.info("Enter Data for Quanity")
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_number_infusion_0_quantity_0").click() # IV Infusions (Quanity)
            page1.wait_for_timeout(500)
            page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_number_infusion_0_quantity_0").fill("1") # IV Infusions (Quanity)
            logger.info("1 Entered for Quantity")
            screenshot(page1, "i_i_uncalculated")
            end_step()

        # Prompt to Enter Start & Stop Date/Time      
            manual_prompt(
                message="Enter Start & Stop Date/Time",
                completion_note="Entering Date Information"
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
            screenshot(page1, "charge_codes_added_via_wss")
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
            end_step()

        # Click Charge Codes Tab
            section_break("Charge Codes Tab")
            step("Check Charge Codes Tab", "Navigating to Charge Codes Tab")
            page1.wait_for_timeout(1000)
            page1.wait_for_load_state("domcontentloaded") 
            page1.get_by_role("tab", name="Charge Codes (2)").locator("a").click()
            logger.info("Charge Code Tab Selected")
            screenshot(page1, "charge_codes_tab_1st_try")
            end_step

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
        section_break("Wrap Up & Confirm Account Lands on Charged Today Bucket")
        step("Navigate to Charged Today Bucket", "Navigating to Charged Today Bucket")
        page.wait_for_load_state("domcontentloaded")
        page.bring_to_front()
        page.wait_for_timeout(2000)
        page.get_by_text("Charged Today").click()
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(2000)
        screenshot(page, "charged_account_finalpass")
        logger.info("Charged Account Confirmed")
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