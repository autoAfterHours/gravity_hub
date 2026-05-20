import re
from playwright.sync_api import Playwright, sync_playwright, expect
from orbit360.backend.orbit_context import start_trace, save_trace
from orbit360.utils.orbit_script_helpers import pre_run_check

def run(playwright: Playwright) -> None:
    pre_run_check("https://xrdcwtappcac25b.hca.corpad.net/launchCRS.html")
    browser = playwright.chromium.launch(
        headless=False,
        args=["--start-maximized"]
        )
    context = browser.new_context(no_viewport=True)
    start_trace(context)
    page = context.new_page()
    try:
        page.goto("https://xrdcwtappcac25b.hca.corpad.net/launchCRS.html", wait_until="domcontentloaded")

# Select Help Button - Select About
## Screenshot | CRS_MainMenu
        page.wait_for_timeout(2000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_text("Help").click()
        page.wait_for_timeout(2000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_text("About").click()
## Screenshot | SystemVersionDetails
        page.wait_for_timeout(2000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="OK").click()

# Enter Age of Admission
        page.wait_for_timeout(2000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("textbox", name="Age at Admission:").click()
        page.wait_for_timeout(500)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("textbox", name="Age at Admission:").fill("22")
## Screenshot | CodefinderUpdated
        page.wait_for_timeout(2000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Continue").click()

# Select Patient Disposition
## Screenshot | PatientDisposition
        page.wait_for_timeout(2000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("radio", name="Home, Self Care (UB-01)").click()

# Walk Through Coding Process (Example: "BACK")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").click()
        page.wait_for_timeout(500)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("textbox", name="Enter Keyword or Code:").fill("BACK")
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Continue").click()
## Screenshot | CodeProcess
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Back").click()
        page.wait_for_timeout(1000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Back").click()

# Exit Session & Close Page
        page.wait_for_timeout(2000)
        page.locator("iframe[title=\"Container\"]").content_frame.get_by_role("button", name="Yes").click()

    finally:
        save_trace(context)
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
