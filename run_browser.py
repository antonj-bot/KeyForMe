from __future__ import annotations

import functools
import http.server
import msvcrt
import os
import sys
import threading
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from dotenv import load_dotenv
from playwright.sync_api import Page, sync_playwright

from app.browser.pdf_downloader import download_report_pdf_temporarily
from app.extraction.openai_extractor import UnsupportedReport
from app.states import PIPELINES
from app.states.detect import detect_state

KEYING_URL = "https://keying-uat.green.usgov-ecrash-prod.azuregov.lnrsg.io/ecrash/"
DOWNLOAD_PDF_SELECTOR = "#download"
MOCK_DIR = Path(__file__).resolve().parent / "mock"


def wait_for_enter(context, message: str) -> str:
    """Wait for Enter or Q without freezing Playwright."""
    print(message, end="", flush=True)
    while True:
        open_pages = [p for p in context.pages if not p.is_closed()]
        if not open_pages:
            print()
            return "quit"
        open_pages[0].wait_for_timeout(200)
        if msvcrt.kbhit():
            key = msvcrt.getwch()
            if key in ("\r", "\n"):
                print()
                return "enter"
            if key.lower() == "q":
                print()
                return "quit"


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
    raise RuntimeError("Could not find the open keying form.")


def extract_payload(pdf_path, model: str):
    """Detect state and extract. Returns (state, pipeline, payload) or None if skipped."""
    found = detect_state(pdf_path, model)
    state = (found.state or "").upper()
    print(f"Detected: {state or '?'} | {found.form_name} | {found.agency}")

    pipeline = PIPELINES.get(state)
    if pipeline is None:
        print(f"SKIPPED: {state or 'unknown state'} is not supported yet. Key manually.")
        return None

    start = time.perf_counter()
    payload = pipeline.extract(pdf_path, model)
    print(f"Extraction: {time.perf_counter() - start:.1f}s")

    if not payload["units"]:
        print("SKIPPED: no vehicles extracted. Key manually.")
        return None
    return state, pipeline, payload


# ---------------- real eCrash site ----------------

def main() -> None:
    load_dotenv()
    model = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    print(f"KeyForMe | model: {model} | supported states: {', '.join(PIPELINES)}")

    with sync_playwright() as playwright, TemporaryDirectory(
        prefix="KeyForMe_Chrome_", ignore_cleanup_errors=True
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

        while True:
            if wait_for_enter(
                context, "\nOpen a work item, then press Enter (Q to quit)... "
            ) == "quit":
                break
            try:
                with download_report_pdf_temporarily(
                    context, DOWNLOAD_PDF_SELECTOR
                ) as pdf_path:
                    result = extract_payload(pdf_path, model)
                if result is None:
                    continue
                state, pipeline, payload = result

                if wait_for_enter(
                    context, f"Open the blank {state} form, then press Enter... "
                ) == "quit":
                    break
                pipeline.fill(find_form_page(context), payload)
                print("Filled. Review it. Nothing was saved or submitted.")
            except UnsupportedReport as error:
                print(f"SKIPPED: {error} Key manually.")
            except Exception as error:
                print(f"ERROR on this report: {error}")
                print("The session is still running. Key this report manually.")

        context.close()


# ---------------- mock mode ----------------

def start_mock_server() -> str:
    """Serve the mock folder in the background on a free port."""
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler, directory=str(MOCK_DIR)
    )
    handler.log_message = lambda *args: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{server.server_address[1]}/index.html"


def run_mock(pdf_paths) -> None:
    """Same flow, but local PDFs and the local mock form. No eCrash, no login."""
    load_dotenv()
    model = os.getenv("OPENAI_MODEL", "gpt-6-luna")

    for path in pdf_paths:
        if not path.is_file():
            raise SystemExit(f"File not found: {path}")
    if not (MOCK_DIR / "index.html").exists():
        raise SystemExit("mock\\index.html missing. Run capture_form.py and make_index first.")

    url = start_mock_server()
    print(f"KeyForMe MOCK MODE | model: {model} | {len(pdf_paths)} PDF(s)")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=False, slow_mo=60)
        context = browser.new_context(no_viewport=True)
        page = context.new_page()

        for pdf_path in pdf_paths:
            page.goto(url)  # fresh blank mock form for each report
            if wait_for_enter(
                context, f"\nMock form ready. Press Enter to key '{pdf_path.name}' (Q to quit)... "
            ) == "quit":
                break
            try:
                result = extract_payload(pdf_path, model)
                if result is None:
                    continue
                _, pipeline, payload = result
                print("Keying into the mock form...")
                pipeline.fill(find_form_page(context), payload)
                print("Filled. Compare the mock form with the PDF.")
            except UnsupportedReport as error:
                print(f"SKIPPED: {error}")
            except Exception as error:
                print(f"ERROR on this report: {error}")

        wait_for_enter(context, "\nAll done. Press Enter to close the browser... ")
        browser.close()


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--mock":
        run_mock([Path(a).expanduser().resolve() for a in sys.argv[2:]])
    else:
        main()