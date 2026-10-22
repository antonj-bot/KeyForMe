from app.ai.runtime import get_ai_client
import base64
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import re

import pymupdf


from app.models import (
    CaliforniaCHP555,
    InjuryPage,
    MovementColumns,
    Page1,
    Page2,
    PageKindResult,
    Party,
    PartyColumns,
)

RULES = (
    "KEY WHAT YOU SEE. Transcribe exactly as printed, including "
    "misspellings, abbreviations, capitalization, punctuation, "
    "periods, ellipses, and leading zeros. "
    "Never correct, normalize, guess, or invent source values. "
    "Read each field from its printed label and physical location. "
    "Never copy information between parties. "
    "For checkboxes, use only visibly marked selections. "
    "Return null for blank or unreadable fields. "
    "Report uncertain values in warnings. "
    "Dates: MM/DD/YYYY. Times: HH:MM."
)

CLASSIFY_PROMPT = (
    "Classify this single page from a California police-report PDF. "
    "Return exactly one kind. "
    "PARTY = TRAFFIC CRASH REPORT or TRAFFIC COLLISION REPORT, CHP 555 Page 1. "
    "CODING = TRAFFIC CRASH CODING or TRAFFIC COLLISION CODING, CHP 555 Page 2. "
    "INJURED_WITNESS = INJURED / WITNESS / PASSENGER or PASSENGERS, CHP 555 Page 3. "
    "SKETCH = SKETCH or SKETCH DIAGRAM, CHP 555 Page 4. "
    "NARRATIVE = NARRATIVE/SUPPLEMENTAL or CHP 556. "
    "OTHER = blank separator pages, photographs, attachments, or anything else. "
    "Use only the printed page title. Never infer the page type from layout."
)

PAGE1_PROMPT = (
    "Extract the California CHP 555 party page. "
    "Identify parties using their printed PARTY numbers. "
    "Include only populated party blocks. "

    "Extract incident information and each party's driver, "
    "owner, vehicle, insurance, and identification fields. "

    "Read CITY, STATE, and ZIP separately. "
    "Do not combine them or copy values from another party. "
    "Reporting District and Beat are separate fields. "

    "Read HOME PHONE and SAFETY EQUIP. from their labeled boxes. "

    "For owner information, distinguish SAME AS DRIVER "
    "from a separately named owner. "
    "Preserve owner names and addresses exactly. "

    "Read VIN character by character. "
    "Never correct VIN characters or force 17 characters. "

    "Preserve insurance carrier spelling exactly. "
    "Read the marked vehicle damage description exactly. "

    "If this is not a California CHP 555 party page, "
    "set is_california_chp555 to false. "

    + RULES
)

PAGE2_PROMPT = (
    "Extract the California CHP 555 coding page. "

    "For PRIMARY COLLISION FACTOR, extract the marked "
    "factor letter, party-at-fault number, violation, "
    "and Cited YES/NO selection. "

    "Extract incident-level codes for weather, lighting, "
    "roadway surface, roadway conditions, traffic control "
    "devices, collision type, and motor vehicle involved with. "

    "Return marked code letters, not descriptions. "

    "For party-specific coding, use the printed party "
    "column numbers. Never assign a mark to another party. "

    "Preserve all marked selections where multiple "
    "selections are allowed. "

    + RULES
)

PARTY_COLUMNS_PROMPT = (
    "Extract party-specific codes from this cropped "
    "California CHP 555 coding page. "

    "The printed column headers identify party numbers. "
    "Read each marked X by its exact row and column. "

    "Extract SOBRIETY - DRUG - PHYSICAL, "
    "OTHER ASSOCIATED FACTORS, and SPECIAL INFORMATION. "

    "Read every row, including N - NONE APPARENT. "

    "Return only marked code letters. "
    "Preserve multiple marked codes. "

    "Do not confuse marks with adjacent sections "
    "or vehicle automation fields. "

    + RULES
)

INJURY_PROMPT = (
    "Extract every populated person row from the "
    "California CHP 555 INJURED / WITNESS / PASSENGER page. "

    "Read each row independently. "
    "Do not transfer values between rows. "

    "Identify witness-only, passenger-only, "
    "and injured-person classifications. "

    "Extract the marked EXTENT OF INJURY description "
    "exactly as printed. "

    "Older forms may use FATAL INJURY, SEVERE INJURY, "
    "OTHER VISIBLE INJURY, or COMPLAINT OF PAIN. "

    "Newer forms may use SUSPECTED SERIOUS INJURY, "
    "SUSPECTED MINOR INJURY, or POSSIBLE INJURY. "

    "Never substitute one injury description for another. "

    "Extract person name, DOB, address, telephone, "
    "party number, seat position, airbag, safety equipment, "
    "ejected, transported by, and taken to. "

    "Preserve hospital names exactly, including ellipses. "

    "For addresses, preserve street, apartment or unit, "
    "city, state, ZIP, and any printed country marker. "

    "Include only populated rows. "

    + RULES
)




class UnsupportedReport(Exception):
    pass



def _jpeg(pix) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(
        pix.tobytes("jpeg", jpg_quality=85)
    ).decode()


def page_image(doc, index: int, dpi: int = 150) -> str:
    pix = doc.load_page(index).get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    return _jpeg(pix)


def header_image(doc, index: int) -> str:
    page = doc.load_page(index)

    # Use the top 25% because skewed/scanned titles may sit lower than expected.
    clip = pymupdf.Rect(
        0,
        0,
        page.rect.width,
        page.rect.height * 0.25,
    )

    pix = page.get_pixmap(
        dpi=160,
        clip=clip,
        colorspace=pymupdf.csGRAY,
        alpha=False,
    )

    return _jpeg(pix)


def party_columns_image(doc, index: int) -> str:
    page = doc.load_page(index)
    w, h = page.rect.width, page.rect.height
    clip = pymupdf.Rect(w * 0.36, h * 0.28, w * 0.97, h * 0.91)
    return _jpeg(page.get_pixmap(dpi=200, clip=clip, colorspace=pymupdf.csGRAY, alpha=False))

MOVEMENT_PROMPT = (
    "Read ONLY the MOVEMENT PRECEDING COLLISION section. "

    "The printed column headers identify party numbers. "
    "For each party, identify the row containing its X. "

    "Return the party number and marked row letter. "

    "Do not confuse movement marks with adjacent "
    "vehicle automation columns. "

    "Return null when a selection is unclear. "

    + RULES
)

def movement_image(doc, index: int) -> str:
    page = doc.load_page(index)
    w, h = page.rect.width, page.rect.height
    clip = pymupdf.Rect(w * 0.735, h * 0.285, w * 0.975, h * 0.515)
    return _jpeg(page.get_pixmap(dpi=220, clip=clip, colorspace=pymupdf.csGRAY, alpha=False))

def _call(prompt: str, images, schema, model: str):
    if isinstance(images, str):
        images = [images]
    start = time.perf_counter()
    result = get_ai_client().parse(
        model=model,
        instructions=prompt,
        content=[{"type": "input_image", "image_url": url, "detail": "high"} for url in images],
        schema=schema,
        reasoning_effort="none",
    )
    print(f"  {schema.__name__}: {time.perf_counter() - start:.1f}s")
    return result


TEXT_TITLES = (
    ("INJURED / WITNESS", "INJURED_WITNESS"),
    ("TRAFFIC CRASH CODING", "CODING"),
    ("TRAFFIC CRASH REPORT", "PARTY"),
    ("SKETCH DIAGRAM", "SKETCH"),
    ("NARRATIVE", "NARRATIVE"),
)

def is_effectively_blank(page) -> bool:
    """Detect blank separator pages without spending an API call."""

    pix = page.get_pixmap(
        dpi=40,
        colorspace=pymupdf.csGRAY,
        alpha=False,
    )

    samples = pix.samples

    if not samples:
        return True

    # Count pixels darker than near-white.
    dark_pixels = sum(
        1
        for pixel in samples
        if pixel < 235
    )

    dark_ratio = dark_pixels / len(samples)

    # Blank scans may contain borders, dust, and scanner marks.
    return dark_ratio < 0.012

def classify_pages(doc, model: str) -> list:
    """
    Classify every PDF page reliably.

    Text pages are classified for free.
    Blank pages become OTHER.
    Remaining scanned pages are classified individually and concurrently.
    """

    kinds: list[str | None] = [None] * len(doc)
    image_jobs: list[tuple[int, str]] = []

    for index, page in enumerate(doc):
        page_text = " ".join(
            page.get_text().upper().split()
        )

        # Free deterministic classification when a text layer exists.
        if "INJURED / WITNESS / PASSENGER" in page_text:
            kinds[index] = "INJURED_WITNESS"

        elif (
            "TRAFFIC CRASH CODING" in page_text
            or "TRAFFIC COLLISION CODING" in page_text
        ):
            kinds[index] = "CODING"

        elif (
            "TRAFFIC CRASH REPORT" in page_text
            or "TRAFFIC COLLISION REPORT" in page_text
        ):
            kinds[index] = "PARTY"

        elif (
            "SKETCH DIAGRAM" in page_text
            or re.search(r"\bSKETCH\b", page_text)
        ):
            kinds[index] = "SKETCH"

        elif (
            "NARRATIVE/SUPPLEMENTAL" in page_text
            or "CHP 556" in page_text
        ):
            kinds[index] = "NARRATIVE"

        elif is_effectively_blank(page):
            kinds[index] = "OTHER"

        else:
            # Scanned page with no usable text layer.
            image_jobs.append(
                (index, header_image(doc, index))
            )

    # Classify unresolved scanned pages independently.
    # One bad/blank image cannot shorten the result for every other page.
    if image_jobs:
        with ThreadPoolExecutor(
            max_workers=min(len(image_jobs), 6)
        ) as pool:
            futures = {
                index: pool.submit(
                    _call,
                    CLASSIFY_PROMPT,
                    image,
                    PageKindResult,
                    model,
                )
                for index, image in image_jobs
            }

            for index, future in futures.items():
                try:
                    result = future.result()
                    kinds[index] = result.kind
                except Exception as error:
                    raise RuntimeError(
                        f"Could not classify PDF page {index + 1}. "
                        "Extraction stopped to prevent missing report data."
                    ) from error

    # This should now always have exactly one entry per PDF page.
    return [
        kind if kind is not None else "OTHER"
        for kind in kinds
    ]


def extract_chp555_fast(pdf_path: Path, model: str = "gpt-6-luna") -> CaliforniaCHP555:
    with pymupdf.open(pdf_path) as doc:
        kinds = classify_pages(doc, model)
        print("  Pages: " + ", ".join(f"{i + 1}={k}" for i, k in enumerate(kinds)))
        party_idx = [i for i, k in enumerate(kinds) if k == "PARTY"]
        coding_idx = [i for i, k in enumerate(kinds) if k == "CODING"]
        injury_idx = [i for i, k in enumerate(kinds) if k == "INJURED_WITNESS"]
        if not party_idx or not coding_idx:
            raise UnsupportedReport("No CHP 555 party page or coding page found.")

        jobs = []
        jobs += [("party", PAGE1_PROMPT, page_image(doc, i), Page1) for i in party_idx]
        jobs += [("coding", PAGE2_PROMPT, page_image(doc, i, dpi=180), Page2) for i in coding_idx]
        jobs += [("columns", PARTY_COLUMNS_PROMPT, party_columns_image(doc, i), PartyColumns)
            for i in coding_idx]
        jobs += [("movement", MOVEMENT_PROMPT, movement_image(doc, i), MovementColumns)
            for i in coding_idx]
        jobs += [("injury", INJURY_PROMPT, page_image(doc, i, dpi=180), InjuryPage)
            for i in injury_idx]

    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures = [(kind, pool.submit(_call, prompt, img, schema, model))
                   for kind, prompt, img, schema in jobs]
        results = [(kind, f.result()) for kind, f in futures]

    party_pages = [r for k, r in results if k == "party"]
    coding_pages = [r for k, r in results if k == "coding"]
    column_pages = [r for k, r in results if k == "columns"]
    injury_pages = [r for k, r in results if k == "injury"]
    by_movement = {p.party_number: p.movement_preceding_crash
                   for k, r in results if k == "movement" for p in r.parties}

    first = party_pages[0]
    if not first.is_california_chp555:
        raise UnsupportedReport(f"Not a CA CHP 555 (detected state: {first.detected_state}).")

    by_party = {p.party_number: p for page in coding_pages for p in page.parties}
    by_column = {p.party_number: p for page in column_pages for p in page.parties}
    main_coding = coding_pages[0]
    pcf_party = str(main_coding.primary_factor_party or "").strip()

    seen, parties = set(), []
    for p in (p for page in party_pages for p in page.parties):
        if p.party_number in seen:
            continue
        seen.add(p.party_number)
        c, col = by_party.get(p.party_number), by_column.get(p.party_number)
        issued = c.citation_issued if c else None
        section = c.cited_section if c else None
        if pcf_party == str(p.party_number):
            section = section or main_coding.primary_factor_violation
            if main_coding.primary_factor_cited is not None:
                issued = main_coding.primary_factor_cited

        def pick(name, empty):
            value = getattr(col, name, empty) if col else empty
            return value or (getattr(c, name, empty) if c else empty)

        parties.append(Party(
            **p.model_dump(),
            citation_issued=issued,
            cited_section=section,
            sobriety=pick("sobriety", []),
            other_associated_factors=pick("other_associated_factors", []),
            special_information=pick("special_information", []),
            movement_preceding_crash=by_movement.get(p.party_number)
                or pick("movement_preceding_crash", None),
        ))

    warnings = [w for page in party_pages + coding_pages + injury_pages for w in page.warnings]
    return CaliforniaCHP555(
        report=first.report,
        parties=sorted(parties, key=lambda x: x.party_number),
        coding=main_coding.coding,
        people=[person for page in injury_pages for person in page.people],
        warnings=warnings,
    )
