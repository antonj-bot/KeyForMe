from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Iterator


def find_download_button(context, selector: str):
    """Search every tab and every iframe for the download button."""
    for page in reversed(context.pages):
        if page.is_closed():
            continue
        for frame in page.frames:
            try:
                button = frame.locator(selector).first
                if button.count() and button.is_visible():
                    print(f"Found download button in frame: {frame.url}")
                    return page, button
            except Exception:
                continue
    raise RuntimeError(f"Download button not found: {selector}")


@contextmanager
def download_report_pdf_temporarily(
    context,
    selector: str,
    timeout_ms: int = 30_000,
):
    page, button = find_download_button(context, selector)

    with TemporaryDirectory(
        prefix="KeyForMe_PDF_",
        ignore_cleanup_errors=True,
    ) as temp_dir:
        print("Clicking download button...")
        with page.expect_download(timeout=timeout_ms) as download_info:
            button.click()

        download = download_info.value
        name = download.suggested_filename or "report.pdf"
        if not name.lower().endswith(".pdf"):
            name += ".pdf"

        pdf_path = Path(temp_dir) / name
        download.save_as(pdf_path)

        if pdf_path.stat().st_size == 0:
            raise RuntimeError("Downloaded PDF is empty.")

        print(f"Temporary PDF ready: {name}")
        yield pdf_path