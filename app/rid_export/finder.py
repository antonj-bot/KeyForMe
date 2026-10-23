"""Find the Report ID element in every open tab, popup and iframe."""
from __future__ import annotations


def find_text_in_all_pages(context, selector, timeout_ms=1000, skip_page=None):
    """Return (text, page) for the first visible match, else raise LookupError."""
    pages = []
    for page in list(context.pages):
        try:
            if not page.is_closed():
                pages.append(page)
        except Exception:
            continue
    if not pages:
        raise LookupError("No open browser pages")

    for page in pages:
        if skip_page is not None and skip_page(page):
            continue
        try:
            frames = list(page.frames)  # main frame + every iframe
        except Exception:
            continue
        for frame in frames:
            try:
                locator = frame.locator(selector)
                if locator.count() > 0:
                    locator.first.wait_for(timeout=timeout_ms)
                    return locator.first.inner_text().strip(), page
            except Exception:
                continue
    raise LookupError("Report ID selector not found in any open page")
