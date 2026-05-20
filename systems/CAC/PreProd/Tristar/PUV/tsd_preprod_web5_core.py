import re
from playwright.sync_api import Playwright, sync_playwright, TimeoutError as PWTimeout
from orbit360.backend.orbit_context import start_trace, save_trace
from orbit360.utils.orbit_script_helpers import pre_run_check

def run(playwright: Playwright) -> None:
    pre_run_check("https://XRDCWTWEBCAC25B.HCA.CORPAD.NET/3M_360App")
    browser = playwright.chromium.launch(
        headless=False,
        slow_mo=150,
        args=["--start-maximized"]
        )
    context = browser.new_context(no_viewport=True)
    start_trace(context)
    page = context.new_page()
    try:
        page.goto("https://XRDCWTWEBCAC25B.HCA.CORPAD.NET/3M_360App", wait_until="domcontentloaded")

# Click About & Validate Version
        page.locator("#container").get_by_text("About").click()
        page.wait_for_timeout(1000)
        page.get_by_role("button", name="Close", exact=True).click()

# Click Help & Open What's New
        with page.expect_popup() as page1_info:
            page.locator("#container").get_by_text("Help").click()
        page1 = page1_info.value
        page1.get_by_role("link", name=" What's New in 360 Encompass").click()
        page1.goto("https://apps.3mhis.com/download/3M_Docs_Secured/360_Encompass/360_P2_library/en/whats_new_360r2.html")
        page1.close()

# Click Codefinder & Validate Functionality
        with page.expect_popup() as page2_info:
            page.get_by_role("button", name="Codefinder").click()
            page2 = page2_info.value
            page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("menuitem", name="Help").click()
            page2.wait_for_timeout(2000)
            page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_text("About").click()
            page2.wait_for_timeout(2000)
            page2.locator("#container iframe").content_frame.get_by_text("</body> </html>").content_frame.get_by_role("button", name="OK").click()
            page2.close()

# Select Patient Search & Check Functionality
        page.get_by_text("Patient Search", exact=True).click()
        page.wait_for_timeout(2000)
        page.locator("#container input[type=\"text\"]").nth(2).click()
        page.locator("#container input[type=\"text\"]").nth(2).fill("Test")
        page.locator("#container input[type=\"text\"]").nth(2).press("Enter")
        page.wait_for_timeout(2000)
        page.get_by_role("button", name=" Back to Dashboard").click()

# Navigate to Reports Tab
        page.wait_for_timeout(3000)
        page.locator("span").filter(has_text="Reports").click()

# Select Legacy System Administration Reports
        print("\n---------------------------------------------")
        print(" MANUAL STEP REQUIRED - Select Legacy System Administration Reports")
        print("---------------------------------------------")
        print("Please Select Select Legacy System Administration Reports")
        print("Press ENTER when you are ready to continue.\n")
        input("Ready to Continue?")
        print("Continuing Automation Run.")

# Select Interface010 Inbound Interface Listing
        print("\n---------------------------------------------")
        print(" MANUAL STEP REQUIRED - Select Interface010 Inbound Interface Listing")
        print("---------------------------------------------")
        print("Please Select Interface010 Inbound Interface Listing Report Type")
        print("Press ENTER when you are ready to continue.\n")
        input("Ready to Continue?")
        print("Continuing Automation Run.")

# Run Interface010 Inbound Interface Listing Report
        print("\n---------------------------------------------")
        print(" MANUAL STEP REQUIRED - Run Interface010 Inbound Interface Listing Report")
        print("---------------------------------------------")
        print("Please Select the Run Report Button")
        print("Press ENTER when you are ready to continue.\n")
        input("Ready to Continue?")
        print("Continuing Automation Run.")

    finally:
        save_trace(context)
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
