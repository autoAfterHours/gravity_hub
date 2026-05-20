import re
from playwright.sync_api import Playwright, sync_playwright, expect
from orbit360.backend.orbit_context import start_trace, save_trace
from orbit360.utils.orbit_script_helpers import pre_run_check

def run(playwright: Playwright) -> None:
    pre_run_check("https://xrdcwtappcac25b.hca.corpad.net/CRSConfigPlatform.html")
    browser = playwright.chromium.launch(
        headless=False,
        args=["--start-maximized"]
        )
    context = browser.new_context(no_viewport=True)
    start_trace(context)
    page = context.new_page()
    try:
        page.goto("https://xrdcwtappcac25b.hca.corpad.net/CRSConfigPlatform.html", wait_until="domcontentloaded")

# Click Custom Edits Tab
        page.wait_for_timeout(3000)
        page.get_by_role("button", name="Custom Edits").click()

# Search for Custom Edit (Example: 1181)
        page.wait_for_timeout(2000)
        page.locator("#CRSConfigFrame1").content_frame.get_by_role("textbox", name="Filter Edits By Text..").click()
        page.locator("#CRSConfigFrame1").content_frame.get_by_role("textbox", name="Filter Edits By Text..").fill("1181")

# Click Custom Edit & View Details
        page.wait_for_timeout(2000)
        page.locator("#CRSConfigFrame1").content_frame.get_by_role("cell", name="SLR - Procedure Unrelated to").click()
        page.wait_for_timeout(2000)

    finally:
        save_trace(context)
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
