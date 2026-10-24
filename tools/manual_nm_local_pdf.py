import functools
import http.server
import os
import threading
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from app.states.nm import extract
from app.browser.engine import fill_form


ROOT = Path(__file__).resolve().parent.parent

PDF_PATH = (
    ROOT
    / "pdfs"
    / "States"
    / "NM"
    / "report-9000000003.pdf"
)

MOCK_DIR = ROOT / "mock" / "nm"


def start_server():
    handler = functools.partial(
        http.server.SimpleHTTPRequestHandler,
        directory=str(MOCK_DIR),
    )

    server = http.server.ThreadingHTTPServer(
        ("127.0.0.1", 0),
        handler,
    )

    threading.Thread(
        target=server.serve_forever,
        daemon=True,
    ).start()

    return server


def main():
    load_dotenv(dotenv_path=ROOT / ".env")

    if not PDF_PATH.exists():
        raise FileNotFoundError(PDF_PATH)

    if not (MOCK_DIR / "index.html").exists():
        raise FileNotFoundError(
            "NM mock not found."
        )

    model = os.getenv(
        "OPENAI_MODEL",
        "gpt-6-luna",
    )

    print("\n===== NM LOCAL PDF TEST =====")

    start = time.perf_counter()

    print("Extracting NM report...")

    payload = extract(
        PDF_PATH,
        model,
    )

    print(
        f"Extraction: "
        f"{time.perf_counter() - start:.2f}s"
    )

    print(
        f"Units detected: {len(payload['units'])}"
    )

    if len(payload["units"]) != 2:
        raise RuntimeError(
            "Expected 2 units. Filling cancelled."
        )

    if payload.get("notes"):
        print("\nExtraction warnings:")
        for warning in payload["notes"]:
            print("-", warning)

        raise RuntimeError(
            "Extraction has unresolved warnings. "
            "Review before filling."
        )

    server = start_server()

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                channel="chrome",
                headless=False,
                slow_mo=100,
            )

            page = browser.new_page(
                no_viewport=True,
            )

            url = (
                f"http://127.0.0.1:"
                f"{server.server_address[1]}/index.html"
            )

            page.goto(url)

            print("\nNM mock opened.")
            print("Filling Units 1 and 2...")

            start = time.perf_counter()
            
            print(
                "Intersection value sent to filler:",
                repr(payload.get("incident", {}).get("intersection_type")),
            )
            
            warnings = fill_form(page, payload, state="NM", log=print)

            print(
                f"Form filling: "
                f"{time.perf_counter() - start:.2f}s"
            )

            if warnings:
                print("\n===== FILLING WARNINGS =====")
                for warning in warnings:
                    print("-", warning)

            print("\nReview the NM mock form.")
            print("Nothing was saved or submitted.")

            page.pause()

            browser.close()

    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
