import re
from playwright.sync_api import Playwright, sync_playwright, TimeoutError as PWTimeout
from orbit360.backend.orbit_context import start_trace, save_trace
from orbit360.utils.orbit_frames import CACFrames
from orbit360.utils.orbit_script_helpers import pre_run_check

def run(playwright: Playwright) -> None:
    pre_run_check("https://XRDCWTWEBCAC25B.HCA.CORPAD.NET/3M_360App")
    browser = playwright.chromium.launch(
        headless=False,
        args=["--start-maximized"]
        )
    context = browser.new_context(no_viewport=True)
    start_trace(context)
    page = context.new_page()
    try:
        page.goto("https://XRDCWTWEBCAC25B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")

# Navigate to CDI Dashboard
        page.locator(".c_graphic_hover_rect").click()

# Prompt to Select Patient & Continue
        print("\n---------------------------------------------")
        print(" MANUAL STEP REQUIRED - Select a Patient ")
        print("---------------------------------------------")
        print("Please Select a Recent Patient Record from the worklist")
        print("Press ENTER when you are ready to continue.\n")
        input("Ready to Continue?")
        print("Continuing Automation Run.")

        with page.expect_popup() as page1_info:
            page1 = page1_info.value
            frames = CACFrames(page1)
            page1.get_by_text("Documents and Codes").click()

# Create & Send Query
            page1.get_by_role("button", name="Create Query...").click()
            page1.wait_for_timeout(1000)
            page1.locator("#qframe").content_frame.locator("select[name=\"sel_query_template\"]").select_option("1: Object")
            page1.locator("#qframe").content_frame.get_by_role("row", name="*Provider Response Recipient").get_by_role("textbox").first.click()
            page1.locator("#qframe").content_frame.get_by_role("radio", name="All Providers").check()
            page1.locator("#qframe").content_frame.get_by_role("cell", name="Search", exact=True).get_by_role("textbox").click()
            page1.locator("#qframe").content_frame.get_by_role("cell", name="Search", exact=True).get_by_role("textbox").fill("FAKE")
            page1.locator("#qframe").content_frame.get_by_role("cell", name="Search   FAKE", exact=True).get_by_role("textbox").click()
            page1.locator("#qframe").content_frame.get_by_role("cell", name="Search   FAKE", exact=True).get_by_role("textbox").press("Enter")
            page1.locator("#qframe").content_frame.get_by_role("button").filter(has_text="OK").click()
            page1.locator("#qframe").content_frame.locator("textarea[name=\"ta_clinical_indicators\"]").click()
            page1.locator("#qframe").content_frame.locator("textarea[name=\"ta_clinical_indicators\"]").fill("TEST")
            page1.wait_for_timeout(2000)
            page1.locator("#qframe").content_frame.get_by_role("button").filter(has_text="Send").click()

# Codefinder | About | Coding & Reimbursement
            page1.get_by_role("button", name=" Codefinder").click()
            page1.wait_for_timeout(2000)
            frames.codefinder.get_by_role("menuitem", name="Help").click()
            page1.wait_for_timeout(1000)
            frames.codefinder.get_by_role("menuitem", name="About ➧").click()
            page1.wait_for_timeout(1000)
            frames.codefinder.get_by_text("Coding & Reimbursement System").click()
            page1.wait_for_timeout(1000)
            frames.codefinder.get_by_role("button", name="OK").click()

# Codefinder | About | Computer Assisted Coding
            page1.wait_for_timeout(1000)
            frames.codefinder.get_by_role("menuitem", name="Help").click()
            page1.wait_for_timeout(1000)
            frames.codefinder.get_by_role("menuitem", name="About ➧").click()
            page1.wait_for_timeout(1000)
            frames.codefinder.get_by_text("Computer Assisted Coding").click()
            page1.wait_for_timeout(1000)
            frames.cac.get_by_role("button", name="OK").click()

    finally:
        save_trace(context)
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
