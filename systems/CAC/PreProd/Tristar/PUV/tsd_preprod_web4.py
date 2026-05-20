import re
from playwright.sync_api import Playwright, sync_playwright, expect
from orbit360.backend.orbit_context import start_trace, save_trace
from orbit360.utils.orbit_script_helpers import pre_run_check

def run(playwright: Playwright) -> None:
    pre_run_check("https://xrdcwtwebcac25b.hca.corpad.net/sts/VersionInformation.aspx")
    browser = playwright.chromium.launch(
        headless=False,
        args=["--start-maximized"]
        )
    context = browser.new_context(no_viewport=True)
    start_trace(context)
    page = context.new_page()
    try:
        page.goto("https://xrdcwtwebcac25b.hca.corpad.net/sts/VersionInformation.aspx", wait_until="domcontentloaded")

# Validate Site Loads without Error
        page.wait_for_timeout(3000)

    finally:
        save_trace(context)
        browser.close()

with sync_playwright() as playwright:
    run(playwright)
