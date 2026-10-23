"""Free page triage for NJ reports: drop blank pages and exact duplicate pages.

Both checks only skip pages that carry no new information, so a miss costs one extra
API call and never changes the keyed data. Duplicates are EXACT (same embedded image
bytes, or the same rendered pixels); similar-looking different pages are never merged.
"""
from __future__ import annotations

import hashlib

import pymupdf

BLANK_INK_RATIO = 0.002      # share of clearly dark pixels (after cropping the scan edges)
DARK_PIXEL = 140


def is_effectively_blank(page) -> bool:
    w, h = page.rect.width, page.rect.height
    clip = pymupdf.Rect(w * 0.05, h * 0.05, w * 0.95, h * 0.95)     # ignore scanner shadows at the edges
    pix = page.get_pixmap(dpi=50, clip=clip, colorspace=pymupdf.csGRAY, alpha=False)
    samples = pix.samples
    if not samples:
        return True
    return sum(1 for s in samples if s < DARK_PIXEL) / len(samples) < BLANK_INK_RATIO


def page_digest(doc, index: int) -> str:
    page = doc.load_page(index)
    images = page.get_images(full=True)
    if len(images) == 1:
        try:
            return "img:" + hashlib.md5(doc.extract_image(images[0][0])["image"]).hexdigest()
        except Exception:
            pass
    pix = page.get_pixmap(dpi=60, colorspace=pymupdf.csGRAY, alpha=False)
    return "pix:" + hashlib.md5(pix.samples).hexdigest()


def usable_pages(doc) -> tuple[list[int], dict[int, str]]:
    """(kept page indexes in order, {dropped index: reason})."""
    kept, dropped, seen = [], {}, {}
    for index in range(len(doc)):
        page = doc.load_page(index)
        if is_effectively_blank(page):
            dropped[index] = "blank"
            continue
        digest = page_digest(doc, index)
        if digest in seen:
            dropped[index] = f"duplicate of page {seen[digest] + 1}"
            continue
        seen[digest] = index
        kept.append(index)
    return kept, dropped
