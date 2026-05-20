import os
import sys
import time
import re
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
# =================================================================================================================================================
# Configuration
# =================================================================================================================================================
SYSTEM      = "CAC"
ENVIRONMENT = "Pre-Production"
PILLAR      = "North Florida"
RUN_TYPE    = "Mini Regression"
TEST_SET    = "ED"
# ==========================================================================================================================================        
# Bootstrap — locate project root and import shared runtime
# ==========================================================================================================================================        
_env_root = os.environ.get("ORBIT_ROOT")
if _env_root:
    sys.path.insert(0, _env_root)
else:
    _p = Path(__file__).resolve()
    while _p.name.lower() not in ("orbit360",):
        if _p.parent == _p:
            raise RuntimeError("Could not locate Orbit project root.")
        _p = _p.parent
    sys.path.insert(0, str(_p))
# ==========================================================================================================================================        
from orbit360.backend.orbit_context import (
    setup, step, end_step, section_break,
    screenshot, manual_prompt, handle_failure, format_duration,
    crs_frame, start_trace, save_trace,
)
from orbit360.utils.orbit_script_helpers import (
    init_helpers,
    WAIT_PROFILES, DEFAULT_TIMEOUT, RETRY_COUNT,
    wait_with_intervention, wait_for_data_load,
    safe_click, safe_fill, safe_screenshot, step_with_pause,
    pre_run_check,
)
ctx    = setup(SYSTEM, ENVIRONMENT, PILLAR, RUN_TYPE, TEST_SET)
logger = ctx.logger
init_helpers(ctx)
# ==========================================================================================================================================        
# Main Run
# ==========================================================================================================================================   
def run(playwright: Playwright) -> None:
    run_start_time = time.time()
    from orbit360.backend.orbit_context import prompt_value
    acct_number = None
    admit_date = None
    attending_md = None
    admitting_md = None
    browser = None
    context = None
    page    = None
    page1   = None
    e       = None
    admit_date = acct_number = attending_md = admitting_md = ""
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
# ==========================================================================================================================================        
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

        wait_for_data_load(page, "CAC Dashboard", profile="popup")
        screenshot(page,"cac_dashboard")

        end_step()
# ==========================================================================================================================================
# HIM Coding
# ==========================================================================================================================================
        section_break("HIM Coding Dashboard")
        step("Check HIM Coding Dashboard Functionality", "Navigating to HIM Coding")

        page.get_by_text("HIM Coding").click()
        wait_for_data_load(page, "HIM Coding Page", profile="popup")
        screenshot(page, "cac_dashboard")

        end_step()
# ==========================================================================================================================================
# ED Worklist
# ==========================================================================================================================================
        section_break("ED Worklist")
        step("ED Worklist", "Navigating to ED Worklist")

        logger.info("Selecting ED Worklist")
        page.get_by_text("ED", exact=True).click()
        wait_for_data_load(page, "ED Worklist", profile="popup")
        screenshot(page, "him_coding_dashboard")

        end_step()
# ==========================================================================================================================================
# Hold Bucket
# ==========================================================================================================================================
        section_break("ED Hold Bucket")
        step("Hold Bucket", "Navigating to Hold Bucket")

        logger.info("Selecting Hold Bucket")
        page.locator("span").filter(has_text=re.compile(r"^Hold$")).click()
        wait_for_data_load(page, "Hold Bucket", profile="popup")
        screenshot(page, "ed_hold_bucket")

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
            pass
        page1 = page1_info.value
        page1.wait_for_load_state("domcontentloaded")
        page1.bring_to_front()
        page1.wait_for_timeout(1000)
        page1.get_by_text("Patient Profile").click()
        
        if not acct_number:
            acct_number = prompt_value("Enter Account Number")

        if not admit_date:
            admit_date = prompt_value("Enter Admit Date")

        if not attending_md:
            attending_md = prompt_value("Enter Attending Provider")

        if not admitting_md:
            admitting_md = prompt_value("Enter Admitting Provider")

        screenshot(page1, "patient_profile")
        patient_anchor = page1.locator("#selDis-dropdownPanelTrigger")

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
# Move Account from Hold to Ready
# ==========================================================================================================================================  
        section_break("Move Account from Hold to Ready")
        step("Hold to Ready", "Move Account from Hold to Ready")

        logger.info("Selecting Hold Dropdown") 
        page1.wait_for_timeout(1000)
        page1.get_by_role("button").filter(has_text="Hold").click()
        logger.info("Moving Account to Ready") 
        page1.wait_for_timeout(1000)
        page1.get_by_role("menuitem", name="Ready").click()
        logger.info("Account Status Updated") 
# ==========================================================================================================================================
# Enter Diagnosis Reason (L89324)
# ==========================================================================================================================================
        logger.info("Adding Diagnosis Reason (L89324)") 
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("L89324")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
        logger.info("Diagnosis Code (L89324) Added")
# ==========================================================================================================================================
# Enter Diagnosis Code (L89324)
# ==========================================================================================================================================
        logger.info("Adding Diagnosis Code (L89324)") 
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Diagnosis").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("L89324")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
        logger.info("Diagnosis Code (L89324) Added")
# ==========================================================================================================================================
# Enter Diagnosis Code (I96)
# ==========================================================================================================================================
        logger.info("Adding Diagnosis Code (I96)") 
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("I96").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Gangrene, not elsewhere").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Gangrene, not elsewhere").click(button="right")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("Move to Principal Position").click()
        logger.info("Diagnosis Code (I96) Added")
# ==========================================================================================================================================
# Add CPT Code (11042)
# ==========================================================================================================================================
        logger.info("Adding CPT Code (11042)") 
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Add Procedure").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("11042")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
        page1.wait_for_timeout(1000)
        logger.info("CPT Code Added")
        screenshot(page1, "codeset")
        
        end_step()
# ==========================================================================================================================================
# Show Evidence 
# ==========================================================================================================================================
        section_break("Evidence")
        step("Evidence", "Selecting Show Evidence")

        manual_prompt(
            message="Select Show Evidence Button",
            completion_note="Button Selected"
        )
        
        screenshot(page1, "show_evidence")
        
        end_step()
# ==========================================================================================================================================
# Accept ASDRG
# ==========================================================================================================================================  
        section_break("AS-DRG")
        step("Auto-Suggested DRG", "Selecting ASDRG")

        page1.wait_for_timeout(1000)
        page1.locator("m-cac iframe").content_frame.get_by_role("button", name="Accept Code", exact=True).click()
        page1.wait_for_load_state("domcontentloaded")
        page1.wait_for_timeout(1000)
        screenshot(page1, "as_drg")
        
        end_step()
# ==========================================================================================================================================
# Launch WSS
# ========================================================================================================================================== 
        section_break("Worksheet Services")
        step("WSS", "Selecting WSS")

        page1.wait_for_timeout(1000)
        page1.locator("m-cac iframe").content_frame.get_by_role("button", name="Launch Worksheet Services").click()
        page1.wait_for_timeout(2000)
        screenshot(page1, "wss")
        
        end_step()
# ==========================================================================================================================================
# WSS - E/M 
# ==========================================================================================================================================
        section_break("E&M")
        step("E&M", "Opening E&M Screen")

        try:
            btn = page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Clear")
            if btn.is_visible():
                safe_click(btn, "Clear Button")
            else:
                raise Exception()
        except:
            logger.info("Clear not available, moving to next step")

        page1.wait_for_timeout(1000)
        page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#item-4000185417-checkbox-box").click()
        page1.wait_for_timeout(1000)
        page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Calculate").click()
        logger.info("E&M Codes Added")
        
        end_step()
# ==========================================================================================================================================
# WSS - Infusion & Injections
# ==========================================================================================================================================
        section_break("Infusion & Injections")
        step("I&I", "Opening Infusions & Injections Screen")

        try:
            i_i = page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("tab", name="Infusion & Injection")
            if i_i.is_visible():
                safe_click(i_i, "Infusions & Injections Button")
                page1.wait_for_timeout(1000)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_text_injection_0_drug_0").click()
                page1.wait_for_timeout(1000)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_text_injection_0_drug_0").fill("1")
                page1.wait_for_timeout(1000)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_text_injection_0_drug_0").press("Tab")
                page1.wait_for_timeout(1000)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_number_injection_0_quantity_0").fill("1")
                page1.wait_for_timeout(1000)
                page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.locator("#input_number_injection_0_quantity_0").press("Tab")
                manual_prompt(message="Enter Injection Date/Time",completion_note="Data Entered")
                page1.wait_for_timeout(1000)
            else:
                raise Exception()
        except:
            logger.info("I&I not available, moving to next step")

        try:
            calculate_btn = page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Calculate")
            if calculate_btn.is_visible():
                safe_click(calculate_btn, "Calculate Button")
            else:
                raise Exception()
        except:
            logger.info("Calculate not available, moving to next step")

        manual_prompt(
            message="Update & Calculate Any Remaining Codes. This will also require the Select All button be selected, and any new codes marked as Do Not Charge",
            completion_note="Final Scan Completed"
        )

        page1.wait_for_timeout(1000)
        page1.locator("iframe[name=\"emw_frame_name\"]").content_frame.get_by_role("button", name="Process").click()
        page1.wait_for_timeout(1000)
        logger.info("I&I Code Added. Processing")

        end_step()
# ==========================================================================================================================================
# Add Provider Episode
# ==========================================================================================================================================
        section_break("Add Provider Episode")  
        step("Add Provider Episode", "Adding Provider Episode")

        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("DEBRIDEMENT SUBCUTANEOUS").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("DEBRIDEMENT SUBCUTANEOUS").click(button="right")
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="Add Date/Physician/Episode").click()
        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Start Date").click()

        safe_fill(page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Start Date"),
                  admit_date,
                  "Start Date"
        )

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
                logger.info("Navigating to Physician")
            else:
                raise Exception()
        except:
                logger.error(f"Did Not Correctly Bypass Self Pay Option | {str(e)}")
                manual_prompt(
                    message="Unable to bypass Self Pay. Hit Continue in Orbit and Automation will pick up at Physician properly.",
                    completion_note="Continuning Run")

        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Physician").click()
        page1.wait_for_timeout(1000)
        
        safe_fill(page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("textbox", name="Physician"),
                    attending_md,
                    "Attending Physician"
        )            

        page1.wait_for_timeout(1000)
        manual_prompt(
            message="Select Provider.",
            completion_note="Provider Selected. Continuing Automation"
        )           

        page1.wait_for_timeout(1000)
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
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
        page1.locator("#crsOuterIframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="Complete").click()
        page1.wait_for_timeout(1000)
        screenshot(page1, "account_completed")
        logger.info("Account has been completed")
        
        end_step()
# ==========================================================================================================================================
# Submit Account
# ==========================================================================================================================================
        section_break("Submit Account")
        step("Submit Account", "Submitting Account to Coded Status")

        page1.get_by_role("button").filter(has_text="Submit & Next").click()
        logger.info("Account Submitted")
        logger.info("Closing Next Account")
        page1.get_by_text("Close").click()

        end_step()
# ==========================================================================================================================================
# Navigate to Coded Today Bucket
# ==========================================================================================================================================
        section_break("Wrap Up & Confirm Account Lands on Coded Today Bucket")
        step("Navigate to Coded Today Bucket", "Navigating to Coded Today Bucket")

        page.bring_to_front()
        page.get_by_text("Coded Today").click()
        wait_for_data_load(page, "Coded Today", profile="popup")
        screenshot(page, "coded_account")
        page.close()
        logger.info("Test Run Completed Successfully!")

        end_step()
# ==========================================================================================================================================
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