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
PILLAR      = "North Florida"
RUN_TYPE    = "Mini Regression"
TEST_SET    = "IP"
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
from orbit360.utils.orbit_frames import CACFrames
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

        admit_date      = ctx.prompt_value("Document Admit Date (as shown on Patient Profile)")
        acct_number     = ctx.prompt_value("Document Account Number")
        attending_md    = ctx.prompt_value("Document Attending Provider")
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