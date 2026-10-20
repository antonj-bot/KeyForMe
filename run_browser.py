from __future__ import annotations

import msvcrt
import os
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from dotenv import load_dotenv
from playwright.sync_api import Page, sync_playwright

from app.browser.pdf_downloader import download_report_pdf_temporarily
from app.browser.playwright_filler import fill_keying_form
from app.extraction.openai_extractor import extract_chp555
from app.extraction.pdf_pages import render_field_pages
from app.keying.ca_mapper import map_ca_keying
from app.validation.rules import validate


KEYING_URL = "https://azkeying.ecrash.lexisnexisrisk.com/ecrash/"
DOWNLOAD_PDF_SELECTOR = "#download"  # TODO: replace with real selector


def wait_for_enter(context, message: str) -> None:
    """Wait for Enter while keeping Playwright alive.

    input() freezes Playwright, which leaves new popups stuck at about:blank.
    """
    print(message, end="", flush=True)
    while True:
        open_pages = [p for p in context.pages if not p.is_closed()]
        if open_pages:
            open_pages[0].wait_for_timeout(200)
        else:
            time.sleep(0.2)
        if msvcrt.kbhit() and msvcrt.getwch() in ("\r", "\n"):
            print()
            return


def find_form_page(context) -> Page:
    for page in reversed(context.pages):
        if page.is_closed() or page.url in ("", "about:blank"):
            continue
        field = page.frame_locator("#formIframe").locator("#Incident_CaseIdentifier")
        try:
            if field.count() and field.is_visible():
                return page
        except Exception:
            pass
    raise RuntimeError("Could not find the open CA keying form.")


def find_work_page(context) -> Page:
    for page in reversed(context.pages):
        if not page.is_closed() and page.url not in ("", "about:blank"):
            return page
    raise RuntimeError("No loaded work page found.")


def extract_report_in_memory(pdf_path: Path) -> dict:
    model = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    with TemporaryDirectory(prefix="KeyForMe_Pages_") as page_dir:
        pages = render_field_pages(pdf_path, Path(page_dir), dpi=180)
        print(f"Extracting with {model}...")
        result = extract_chp555(pages, model)
        warnings = validate(result)
        print(f"Parties found: {len(result.parties)} | Warnings: {len(warnings)}")
        for warning in warnings:
            print(f"  - {warning}")
        return map_ca_keying(result)

def debug_selector(context, selector: str) -> None:
    print(f"\nSearching for: {selector}")
    for page in context.pages:
        if page.is_closed():
            continue
        print(f"\nTAB: {page.url}")
        for frame in page.frames:
            try:
                count = frame.locator(selector).count()
            except Exception as error:
                count = f"error: {error}"
            print(f"  frame: {frame.url[:100]}  matches: {count}")
            for embed in frame.locator("embed, object, iframe").all():
                src = embed.get_attribute("src") or embed.get_attribute("data")
                if src:
                    print(f"    embedded: {src[:120]}")
                    
                    
def main() -> None:
    load_dotenv()
    print("RUNNING NEW run_browser.py (no input() version)")

    with sync_playwright() as playwright, TemporaryDirectory(
        prefix="KeyForMe_Chrome_",
        ignore_cleanup_errors=True,
    ) as profile_dir:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            channel="chrome",
            headless=False,
            chromium_sandbox=True,
            accept_downloads=True,
            no_viewport=True,
        )

        page = context.pages[0] if context.pages else context.new_page()
        page.goto(KEYING_URL)

        wait_for_enter(
            context,
            "Log in, open the work item, then press Enter when the PDF button is visible...",
        )
        

        with download_report_pdf_temporarily(
            context, DOWNLOAD_PDF_SELECTOR
        ) as pdf_path:
            payload = extract_report_in_memory(pdf_path)

        print("Temporary PDF deleted.")

        wait_for_enter(context, "Open the blank CA form, then press Enter...")

        fill_keying_form(find_form_page(context), payload)

        print("Done. Review the form. Nothing was saved or submitted.")
        wait_for_enter(context, "Press Enter to close the browser...")
        context.close()


if __name__ == "__main__":
    main()