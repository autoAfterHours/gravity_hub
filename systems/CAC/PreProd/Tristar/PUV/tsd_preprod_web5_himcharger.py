import re
from playwright.sync_api import Playwright, sync_playwright, TimeoutError as PWTimeout
from orbit360.backend.orbit_context import start_trace, save_trace
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

# Move to HIM Charger Dashboard & Open ED Admits Worklist
        page.get_by_text("HIM Charger").click()
        page.get_by_text("ED Admits").click()

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
        page1.get_by_text("Close").click()

    finally:
        save_trace(context)
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
