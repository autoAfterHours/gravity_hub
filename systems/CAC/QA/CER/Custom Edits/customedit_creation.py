import os
import sys
import time
import re
from pathlib import Path
from playwright.sync_api import Playwright, sync_playwright, expect
# ==========================================================================================================================================
# Main Run
# ==========================================================================================================================================
def run(playwright: Playwright) -> None:
    run_start_time = time.time()
    browser = None
    context = None
    page    = None
    page1   = None
# ==========================================================================================================================================
    browser = playwright.chromium.launch(
        headless=False,
        args=["--start-maximized"]
        )
    context = browser.new_context(no_viewport=True)
    page = context.new_page()
    page.goto("https://xrdcwqappcac08b.hcaqa.corpadqa.net/CRSConfigPlatform.html", wait_until="domcontentloaded")

    page.get_by_role("button", name="Custom Edits").click()
    page.wait_for_timeout(2000)
    page.locator("#CRSConfigFrame1").content_frame.get_by_role("cell", name="✚").click()
    page.wait_for_timeout(2000)
    page.locator("#CRSConfigFrame1").content_frame.locator("#UDEDefText").click()
    page.wait_for_timeout(2000)
    page.locator("#CRSConfigFrame1").content_frame.locator("#UDEDefText").fill("Future Straddle Account")
    page.wait_for_timeout(2000)
    # page.locator("#CRSConfigFrame1").content_frame.get_by_role("button", name="💾").click()

    page.pause()

with sync_playwright() as playwright:
    run(playwright)