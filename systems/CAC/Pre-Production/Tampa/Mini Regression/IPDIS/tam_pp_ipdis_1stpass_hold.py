import os
import sys
import time
import re
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
# ==========================================================================================================================================
# Configuration
# ==========================================================================================================================================
SYSTEM      = "CAC"
ENVIRONMENT = "Pre-Production"
PILLAR      = "Tampa"
RUN_TYPE    = "Mini Regression"
TEST_SET    = "IPDIS"
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
)
from orbit360.utils.orbit_script_helpers import (
    init_helpers,
    WAIT_PROFILES, DEFAULT_TIMEOUT, RETRY_COUNT,
    wait_with_intervention, wait_for_data_load,
    safe_click, safe_fill, safe_screenshot, step_with_pause,
    pre_run_check,
)
from orbit360.utils.orbit_frames import CACFrames
# ==========================================================================================================================================
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
    page2   = None
    admit_date = acct_number = attending_md = admitting_md = ""
# ==========================================================================================================================================
# Patient Profile Values
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
        pre_run_check("https://XRDCWTWEBCAC06B.HCA.CORPAD.NET/3M_360App")
        browser = playwright.chromium.launch(headless=False, args=["--start-maximized"])
        context = browser.new_context(no_viewport=True)
        start_trace(context)
        page = context.new_page()
# ==========================================================================================================================================
# Navigate to CAC Dashsboard
# ==========================================================================================================================================
        section_break("CAC Dashboard")
        step("Tampa Pre-Production CAC Dashboard", "Launching Browser & Navigating to Dashboard")
        
        page.goto("https://XRDCWTWEBCAC06B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")
        wait_for_data_load(page, "CAC Dashboard", profile="popup")
        screenshot(page, "cac_dashboard")

        end_step()
# ==========================================================================================================================================
# Navigate to Conurrent Coding Dashboard
# ==========================================================================================================================================
        section_break("Concurrent Coding Dashboard")
        step("Check Concurrent Coding Dashboard Functionality", "Navigating to Concurrent Coding Dashboard")

        logger.info("Navigating to Concurrent Coding Dashboard")
        page.get_by_text("Concurrent Coding").click()
        wait_for_data_load(page, "Concurrent Coding Page", profile="popup")
        screenshot(page, "concurrent_coding_db")

        end_step()
# ==========================================================================================================================================
# Navigate to Discharged All Worklist
# ==========================================================================================================================================
        section_break("Discharged All Worklist")
        step("Open Discharged All Worklist", "Openging Discharged All Worklist")

        logger.info("Selecting Discharged All Worklist")
        page.get_by_text("Discharged All", exact=True).click()
        wait_for_data_load(page, "Discharged All Worklist", profile="popup")
        screenshot(page, "concurrent_coding_dashboard")
        
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
        page1.bring_to_front()
        frames = CACFrames(page1)
        screenshot(page1, "patient_record")

        end_step()
# ==========================================================================================================================================
# Patient Profile — Record Dates & Physicians
# ==========================================================================================================================================
        section_break("Patient Profile")
        step("Record Patient Profile Data", "Capturing admit date and attending physicians")

        page1.wait_for_timeout(1000)
        logger.info("Navigating to Patient Profile Tab")
        page1.get_by_text("Patient Profile").click()
        page1.wait_for_timeout(1000)
        logger.info("Prompt Patient Values")

        if not acct_number:
            acct_number = prompt_value("Enter Account Number")

        if not admit_date:
            admit_date = prompt_value("Enter Admit Date")

        if not attending_md:
            attending_md = prompt_value("Enter Attending Provider")

        if not admitting_md:
            admitting_md = prompt_value("Enter Admitting Provider")
            
        screenshot(page1, "patient_profile")
        logger.info("Values Saved")
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
# Pop Out Codefinder
# ==========================================================================================================================================
        section_break("Pop Out Codefinder")
        step("Pop Out Codefinder", "Popping Out Codefinder")

        logger.info("Selecting Pop Out Button")
        page1.wait_for_timeout(1000)
        page1.get_by_role("button", name=" Pop-out").click()
# ==========================================================================================================================================
# Manual Prompt - Allow Pop Up
# ==========================================================================================================================================
        manual_prompt(
             message="Click Allow Popup", 
             completion_note="Pop Out Window Opening"
        )  
        with page1.expect_popup() as page2_info:
            page2 = page2_info.value
            frames2 = CACFrames.for_popout(page2)
            logger.info("Page Popped Out")
            screenshot(page2, "pop_out_codefinder")

            end_step()
# ==========================================================================================================================================
# Code Account (Inpatient Esophagitis with Bleeding)
# ==========================================================================================================================================
            section_break("Code Account (Inpatient Esophagitis with Bleeding)")
            step("Code Account", "Add Codes to Account")

# ==========================================================================================================================================
# Adding Diagnosis Reason - K2090
# ==========================================================================================================================================
            logger.info("Adding Diagnosis Reason - K2090")
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").fill("K2090")
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("button", name="OK").click()
            logger.info("Code (K2090) Added")
# ==========================================================================================================================================
# Adding Diagnosis Reason - K2091
# ==========================================================================================================================================
            logger.info("Adding Diagnosis Code - K2091")
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("button", name="Add Diagnosis").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").fill("K2091")
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("button", name="OK").click()
            logger.info("Code (K2091) Added")
# ==========================================================================================================================================
# Adding Diagnosis Reason - K2211
# ==========================================================================================================================================
            logger.info("Adding Diagnosis Code - K2211")
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("button", name="Add Diagnosis").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").fill("K2211")
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("button", name="OK").click()
            logger.info("Code (K2211) Added")
# ==========================================================================================================================================
# Adding CPT Code - 0DB58ZX
# ==========================================================================================================================================
            logger.info("Adding CPT Code - 0DB58ZX")
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("button", name="Add Procedure").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").fill("0DB58ZX")
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Enter Keyword or Code:").press("Enter")
            logger.info("CPT Code (0DB58ZX) Added")
# ==========================================================================================================================================
# Deleting Diagnosis Code - K2091
# ==========================================================================================================================================
            logger.info("Deleting Diagnosis Code - K2091")
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_text("PrincipalEsophagitis,").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_text("PrincipalEsophagitis,").click(button="right")
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_text("Delete Code(s)").click()
            page2.wait_for_timeout(1000)
            logger.info("Diagnosis Code (K2091) Deleted")
            screenshot(page2, "codeset_added")

            end_step()
# ==========================================================================================================================================
# Add Provider Episode to CPT Codes
# ==========================================================================================================================================
            section_break("Add Provider Procedure to CPT Code")
            step("Add Dr Episode to CPT Codes", "Adding Procedure Episode to CPT Codes")

            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_text("PrincipalExcision of").click()
            page2.wait_for_timeout(1000)            
            frames2.codefinder_popout.get_by_text("PrincipalExcision of").click(button="right")
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("menuitem", name="Add Date/Physician/Episode").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Start Date").click()
            
            safe_fill(frames2.codefinder_popout.get_by_role("textbox", name="Start Date"),
                      admit_date,
                      "Start Date"
            )
            
            page2.wait_for_timeout(1000)
            logger.info("Procedure Date Selected....Continuing Automation")
            frames2.codefinder_popout.get_by_role("textbox", name="Start Date").click()
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Start Date").press("Tab")
            page2.wait_for_timeout(1000)
            
            try:
                self_pay = frames2.crs_popout.get_by_label("Self Pay")
                if self_pay.is_visible():
                    frames2.crs_popout.get_by_label("Self Pay").press("Tab")
                else:
                    raise Exception()
            except:
                logger.info("Self Pay not available, moving to next step")
            
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("textbox", name="Physician").click()
            page2.wait_for_timeout(1000)
            
            safe_fill(frames2.codefinder_popout.get_by_role("textbox", name="Physician"),
                      attending_md,
                      "Attending Physician"
            )            
            
            page2.wait_for_timeout(1000)
            
            manual_prompt(message="Select Provider.",
                          completion_note="Provider Selected. Continuing Automation"
            )            
            
            page2.wait_for_timeout(1000)
            frames2.codefinder_popout.get_by_role("button", name="OK").click()
            page2.wait_for_timeout(1000)
            screenshot(page2, "codeset_with_providerep_added")
            logger.info("Provider Episode Successfully Added")

            end_step()
# ==========================================================================================================================================            
# Pop In Codefinder
# ==========================================================================================================================================            
            section_break("Pop In to Window")
            step("Pop In", "Popping Back Into Window")

            page2.wait_for_timeout(1000)
            page2.get_by_role("button", name=" Pop-In").click()
            logger.info("Page Popped in Successfully")
            screenshot(page1, "popped_in")

            end_step()  
# ==========================================================================================================================================            
# Resolve Critical Error
# ==========================================================================================================================================            
            section_break("Resolve Critical Error")
            step("Resolve Error", "Resolving Critical Error")

            page1.wait_for_timeout(1000)
            frames.codefinder_inline.get_by_role("button", name="Resolve").click()
            page1.wait_for_timeout(1000)
            frames.codefinder_inline.get_by_label("To resolve, you need to").select_option("\n13\n")
            page1.wait_for_timeout(1000)
            frames.codefinder_inline.get_by_role("textbox", name="Add additional note").click()
            page1.wait_for_timeout(1000)
            frames.codefinder_inline.get_by_role("textbox", name="Add additional note").fill("\nTEST")
            page1.wait_for_timeout(1000)
            frames.codefinder_inline.get_by_role("button", name="OK").click()
            logger.info("Critical Error Resolved")               
            screenshot(page1, "resolved_error")

            end_step()
# ==========================================================================================================================================            
# Add Consulting Provider within Abstract Tab
# ==========================================================================================================================================            
            section_break("Add Consulting Provider")
            step("Add Consult Provider", "Adding Consulting Providers")

            logger.info("Selecting Abstract Tab")
            page1.wait_for_timeout(1000)
            page1.get_by_text("Abstract").click() # Select Abstract Tab 
            screenshot(page1, "abstract_tab")
            logger.info("Adding 1st Consulting Provider")    
            page1.wait_for_timeout(1000)
            
            try:
                frames.abstract.get_by_role("button").filter(has_text="Add Consulting Provider").click() 
                logger.info("Selecting Add Consulting Provider Option")
            except Exception as e:
                    logger.error(f"Did Not Find Add Consulting Provider Option | {str(e)}")
                    manual_prompt(message="Did Not Find Add Consulting Provider Option. Click Add Consulting Provider Option, and then hit Continue to pick back up.",
                                  completion_note="Continuning Run"
                    )
            
            page1.wait_for_timeout(1000)
            frames.abstract.locator("c-dropdown div").first.click()
            page1.wait_for_timeout(1000)
            frames.abstract.locator("input[name=\"search\"]").click()                                
            page1.wait_for_timeout(1000)
            
            safe_fill(frames.abstract.locator("input[name=\"search\"]"),
                      attending_md,
                      "Attending Physician"
            )                                  
            
            page1.wait_for_timeout(1000)
            frames.abstract.locator("input[name=\"search\"]").press("Enter")                                
            page1.wait_for_timeout(1000)
            
            manual_prompt(message="Select Provider.",
                          completion_note="Provider Selected. Continuing Automation")            
            
            page1.wait_for_timeout(1000)
            screenshot(page1, "1st_consult_provider")
            frames.abstract.get_by_role("button").filter(has_text="OK").click()
            page1.wait_for_timeout(1000)
# ==============================================================================================            
# Add 1st Consult Date
# ==============================================================================================    
            manual_prompt(message="Select Date for 1st Consulting Provider",
                          completion_note="Date Entered"
                          )                               
            page1.wait_for_timeout(1000)
            frames.abstract.get_by_role("button").filter(has_text="Save").click()
            page1.wait_for_timeout(1000)
            logger.info("1st Consulting Provider Added")                                
            screenshot(page1, "1st_consult_dr_added")
            logger.info("Adding 2nd Consulting Provider")
            
            try:
                frames.abstract.get_by_role("button").filter(has_text="Add Consulting Provider").click() 
                logger.info("Selecting Add Consulting Provider Option")
            except Exception as e:
                    logger.error(f"Did Not Find Add Consulting Provider Option | {str(e)}")
                    manual_prompt(message="Did Not Find Add Consulting Provider Option.Click Add Consulting Provider Option, and then hit Continue to pick back up.",
                                completion_note="Continuning Run"
                    )
            
            page1.wait_for_timeout(1000)
            frames.abstract.locator("c-dropdown div").first.click()
            page1.wait_for_timeout(1000)
            frames.abstract.locator("input[name=\"search\"]").click()                                
            page1.wait_for_timeout(1000)            
            
            safe_fill(frames.abstract.locator("input[name=\"search\"]"),
                      admitting_md,
                      "Admitting Physician"
            )                                  
            
            page1.wait_for_timeout(1000)
            frames.abstract.locator("input[name=\"search\"]").press("Enter")                                
            page1.wait_for_timeout(1000)
            
            manual_prompt(message="Select Provider.",
                          completion_note="Provider Selected. Continuing Automation"
            )   
            
            page1.wait_for_timeout(1000)
            screenshot(page1, "2nd_consult_provider")
            frames.abstract.get_by_role("button").filter(has_text="OK").click() # Add Second Provider Outside of Date Range & Validate Error
# ============================================================================================================================================================            
# Manual Prompt - Enter Date
# ============================================================================================================================================================            
            manual_prompt(
                 message="Select Date for 2nd Consulting Provider use a date OUTSIDE the admit range to trigger the validation error)",
                 completion_note="Date Entered"
            )                                
            
            page1.wait_for_timeout(1000)
            frames.abstract.get_by_role("button").filter(has_text="Save").click()
            logger.info("2nd Consulting Provider Added")
            screenshot(page1, "2nd_consult_dr_added")                                
            logger.info("Checking Validation Tab")
            page1.wait_for_timeout(1000)
            page1.get_by_text("Validation").click() # Select Validation Tab and Validate Error is Present 
            screenshot(page1, "2nd_validation_tab_check")
            logger.info("Moving Back to Abstract Tab")
            page1.wait_for_timeout(1000)
            page1.get_by_text("Abstract").click() # Select Abstract Tab                                
            logger.info("Update 2nd Provider Entry to Correct Date")
            page1.wait_for_timeout(1000)
            frames.abstract.get_by_role("button").nth(2).click() # Update 2nd Provider Entry
# ============================================================================================================================================================
# Manual Prompt - Correct Date
# ============================================================================================================================================================
            manual_prompt(
                 message="Update 2nd Consulting Provider date to a VALID date within the admit range",
                 completion_note="Date Updated"
            )
            
            page1.wait_for_timeout(1000)
            frames.abstract.get_by_role("button").filter(has_text="Save").click()
            logger.info("2nd Consulting Provider Updated")                                
            screenshot(page1, "2nd_consult_dr_updated")
            logger.info("Checking Validation Tab")
            page1.wait_for_timeout(1000)
            page1.get_by_text("Validation").click() # Select Validation Tab and Validate Error is No Longer Present               
            screenshot(page1, "final_validation_check")
            logger.info("Navigating Back to Documents and Codes Tab")
            page1.wait_for_timeout(1000)
            page1.get_by_text("Documents and Codes").click() # Select Document and Codes Tab                                
            logger.info("Consulting Provider Logic Tested")

            end_step()
# ============================================================================================================================================================
# Complete Account (1st Try)
# ============================================================================================================================================================
            section_break("Complete Account - 1st Try")
            step("Complete Account - 1st Attempt", "Completing Account")

            page1.wait_for_timeout(1000)
            frames.codefinder_inline.get_by_role("button", name="Complete").click()

            end_step()
# ==========================================================================================================================================
# Present on Admission
# ==========================================================================================================================================
            section_break("Present on Admission")
            step("POA", "Present on Admission")

            screenshot(page1, "poa_prompt")
            page1.wait_for_timeout(1000)
            logger.info("Present On Admission Prompt")
            page1.wait_for_timeout(1000)          
            frames.codefinder.get_by_role("button", name="Yes").click()
            manual_prompt(
                 message="Select Y, and Ok",
                 completion_note="Option Selected"
            )            
            logger.info("POA Added Successfully")
            screenshot(page1, "poa_added")

            end_step()
# ============================================================================================================================================================
# Complete Account (1st Try)
# ============================================================================================================================================================
            section_break("Complete Account - 1st Try")
            step("Complete Account - 1st Attempt", "Completing Account")

            logger.info("Attempting to Complete Once More.")                                
            page1.wait_for_timeout(1000)
            frames.codefinder_inline.get_by_role("button", name="Complete").click()
            logger.info("Account has been completed")

            end_step()
# ============================================================================================================================================================
# Place Account on Hold
# ============================================================================================================================================================
            section_break("Place Account on Hold")
            step("Place Account on Hold", "Placing Account on Hold")

            logger.info("Moving Account from Ready to Hold")
            page1.wait_for_timeout(1000)
            page1.get_by_text("Ready").first.click()                                
            page1.wait_for_timeout(1000)
            page1.get_by_text("Hold", exact=True).click()                                
            page1.wait_for_timeout(1000)
            frames.hold_dialog.locator("#holdReasonLabel-inputFieldContainer").click()
            page1.wait_for_timeout(1000)
            frames.hold_dialog.locator("#holdReasonLabel-filterInput").click()                                
            page1.wait_for_timeout(1000)
            frames.hold_dialog.locator("#holdReasonLabel-filterInput").fill("3M-3M UPDATE ISSUE")                                
            page1.wait_for_timeout(1000)
            frames.hold_dialog.get_by_role("listitem", name="3M-3M UPDATE ISSUE").locator("div").nth(1).click()                                
            page1.wait_for_timeout(1000)
            frames.hold_dialog.locator("textarea").click()                                
            page1.wait_for_timeout(1000)
            frames.hold_dialog.locator("textarea").fill("TEST")                                
            page1.wait_for_timeout(1000)
            frames.hold_dialog.get_by_role("button").filter(has_text="Hold").click()                                
            logger.info("Account Moved to Hold Status")
            screenshot(page1, "hold_status_update")

            end_step()
# ============================================================================================================================================================
# Submit Account (Hold Status)
# ============================================================================================================================================================
            section_break("Submit Account")
            step("Submit Account", "Submitting Account to Coded Status")

            page1.wait_for_timeout(1000)
            page1.get_by_role("button", name="Submit").click()
            logger.info("Account Submitted to Hold")
            page1.wait_for_timeout(1000)

            end_step()
# ==============================================================================================================
# Close Account
# ==============================================================================================================
            section_break("Close Account")
            step("Close Account", "Closing Account")    

            page1.wait_for_timeout(1000)
            page1.get_by_role("button", name="Close").click()
            logger.info("Account Closed")

            end_step()
# ==============================================================================================================
# Wrap Up Test Set
# ==============================================================================================================
            section_break("Wrap Up Test")
            step("Wrap Up Test", "Closing Session")

            logger.info("Wrapping UP Test")
            page.wait_for_timeout(3000)
            logger.info("Test Passed Successfully!")
            page.close()

            end_step()
# ==============================================================================================================
    except Exception as e:
        handle_failure(e, page2, page1 or page)

    finally:
        if context:
            save_trace(context)
        if browser:
            browser.close()
        total_duration = time.time() - run_start_time
        logger.info(f"Total Run Duration | {format_duration(total_duration)}")

with sync_playwright() as playwright:
    run(playwright)