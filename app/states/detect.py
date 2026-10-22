import base64
import re

import pymupdf
from pydantic import BaseModel

from app.ai.runtime import get_ai_client


class ReportID(BaseModel):
    state: str | None
    form_name: str | None
    agency: str | None


# Known forms: (state, form name, any of these phrases on page 1)
FORM_SIGNATURES = [
    ("CA", "CHP 555", ("CHP 555", "CALIFORNIA HIGHWAY PATROL")),
    ("TX", "CR-3", ("TEXAS PEACE OFFICER", "CR-3 ")),
]

STATE_NAMES = {
    "ALABAMA": "AL", "ALASKA": "AK", "ARIZONA": "AZ", "ARKANSAS": "AR",
    "CALIFORNIA": "CA", "COLORADO": "CO", "CONNECTICUT": "CT", "DELAWARE": "DE",
    "FLORIDA": "FL", "GEORGIA": "GA", "HAWAII": "HI", "IDAHO": "ID",
    "ILLINOIS": "IL", "INDIANA": "IN", "IOWA": "IA", "KANSAS": "KS",
    "KENTUCKY": "KY", "LOUISIANA": "LA", "MAINE": "ME", "MARYLAND": "MD",
    "MASSACHUSETTS": "MA", "MICHIGAN": "MI", "MINNESOTA": "MN", "MISSISSIPPI": "MS",
    "MISSOURI": "MO", "MONTANA": "MT", "NEBRASKA": "NE", "NEVADA": "NV",
    "NEW HAMPSHIRE": "NH", "NEW JERSEY": "NJ", "NEW MEXICO": "NM", "NEW YORK": "NY",
    "NORTH CAROLINA": "NC", "NORTH DAKOTA": "ND", "OHIO": "OH", "OKLAHOMA": "OK",
    "OREGON": "OR", "PENNSYLVANIA": "PA", "RHODE ISLAND": "RI", "SOUTH CAROLINA": "SC",
    "SOUTH DAKOTA": "SD", "TENNESSEE": "TN", "TEXAS": "TX", "UTAH": "UT",
    "VERMONT": "VT", "VIRGINIA": "VA", "WASHINGTON": "WA", "WEST VIRGINIA": "WV",
    "WISCONSIN": "WI", "WYOMING": "WY",
}


def detect_from_text(page) -> ReportID | None:
    """Free and instant: read the PDF's own text layer, if it has one."""
    text = " ".join(page.get_text().upper().split())
    if len(text) < 50:
        return None  # scanned image with no text layer

    for state, form, phrases in FORM_SIGNATURES:
        if any(phrase in text for phrase in phrases):
            return ReportID(state=state, form_name=form, agency=None)

    match = re.search(r"STATE OF ([A-Z]+(?: [A-Z]+)?)", text)
    if match:
        for name in (match.group(1), match.group(1).split()[0]):
            if name in STATE_NAMES:
                return ReportID(state=STATE_NAMES[name], form_name=None, agency=None)
    return None


def detect_from_image(page, model: str) -> ReportID:
    """Fallback for image-only PDFs: read only the header, at readable resolution."""
    header = pymupdf.Rect(0, 0, page.rect.width, page.rect.height * 0.2)
    pix = page.get_pixmap(dpi=200, clip=header, colorspace=pymupdf.csGRAY, alpha=False)
    image = "data:image/jpeg;base64," + base64.b64encode(
        pix.tobytes("jpeg", jpg_quality=85)
    ).decode()

    return get_ai_client().parse(
        model=model,
        instructions=(
            "This is the top of a police crash report. Read the printed "
            "header text only. Return the state exactly as printed "
            "(e.g. 'STATE OF CALIFORNIA' -> CA), the form name or number "
            "exactly as printed, and the agency. If the header does not "
            "print a state, return null. Never guess from layout."
        ),
        content=[{"type": "input_image", "image_url": image, "detail": "high"}],
        schema=ReportID,
        reasoning_effort="none",
    )


def detect_state(pdf_path, model: str) -> ReportID:
    with pymupdf.open(pdf_path) as doc:
        page = doc.load_page(0)
        found = detect_from_text(page)
        if found:
            print("(state read from PDF text, no API call)")
            return found
        print("(no text layer, reading header image)")
        return detect_from_image(page, model)
