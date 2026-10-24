import json
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

from app.extraction.ca_extractor import UnsupportedReport
from app.states import PIPELINES
from app.states.detect import detect_state

MOCK_URL = "http://localhost:8000/index.html"


def main() -> None:
    load_dotenv()

    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    no_fill = "--no-fill" in sys.argv
    if not args:
        raise SystemExit('Usage: python -m tools.manual_local_pdf "path\\to\\report.pdf" [--no-fill]')

    pdf_path = Path(args[0]).expanduser().resolve()
    if not pdf_path.is_file():
        raise SystemExit(f"File not found: {pdf_path}")

    model = os.getenv("OPENAI_MODEL", "gpt-6-luna")
    print(f"PDF: {pdf_path.name} | Model: {model}")

    start = time.perf_counter()
    found = detect_state(pdf_path, model)
    state = (found.state or "").upper()
    print(f"Detected: {state or '?'} | {found.form_name} | {found.agency} "
          f"({time.perf_counter() - start:.1f}s)")

    pipeline = PIPELINES.get(state)
    if pipeline is None:
        raise SystemExit(f"SKIPPED: {state or 'unknown state'} is not supported yet.")

    try:
        start = time.perf_counter()
        payload = pipeline.extract(pdf_path, model)
        print(f"Extraction: {time.perf_counter() - start:.1f}s")
    except UnsupportedReport as error:
        raise SystemExit(f"SKIPPED: {error}")

    print("\n===== KEYING PAYLOAD (printed only, not saved) =====")
    print(json.dumps(payload, indent=2, default=str))
    print(f"\nUnits: {len(payload['units'])}")

    if no_fill or not payload["units"]:
        return

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=100)
        page = browser.new_page()
        page.goto(MOCK_URL)
        pipeline.fill(page, payload)
        print("\nFilled the mock form. Check each unit tab against the PDF.")
        page.pause()


if __name__ == "__main__":
    main()

