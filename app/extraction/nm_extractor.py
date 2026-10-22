"""New Mexico SH 10074 extraction.

The NM form can split one traffic unit across consecutive PDF pages.
Page 1 is extracted independently. Pages 2 and 3 are extracted together
so Unit 2's driver, vehicle, owner, and insurance remain associated.
"""

from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf

from app.nm_models import (
    NMIncident,
    NMPageExtraction,
    NMReport,
    NMUnit,
    NMConclusion,
)



from pydantic import BaseModel, Field
from app.core.completeness import IncompleteExtractionError, missing_units

class NMUnitInventory(BaseModel):
    unit_numbers: list[int] = Field(default_factory=list)
    uncertain: bool = False

UNIT_INVENTORY_PROMPT = (
    "Read only explicitly printed TRAFFIC UNIT / VEHICLE NO headings in these "
    "three consecutive NM SH 10074 report pages. Return distinct positive unit "
    "numbers for populated traffic-unit sections. Do not infer a second unit "
    "from this instruction or from narrative references. Ignore blank template "
    "blocks, passengers and witnesses. A vehicle/owner section without a repeated "
    "heading can continue the preceding unit. Set uncertain=true if any unit "
    "heading is unreadable, contradictory, or a continuation cannot be associated. "
    "Do not extract names, addresses, VINs or other personal fields."
)

KEY_WHAT_YOU_SEE = (
    "KEY WHAT YOU SEE. Transcribe values exactly as printed, including "
    "misspellings, punctuation, capitalization, identifiers, leading zeros, "
    "VIN characters, and insurance-carrier spelling. Never correct, normalize, "
    "guess, or invent source values. Return null when a value is blank or "
    "unreadable. Do not copy values between traffic units."
)

NM_EXTRACTION_RULES = (
    "Extract the case number separately from the crash report number. "
    "Read each field from its printed label. "

    "Extract First Harmful Event, intersection type, "
    "driver sex, injury code, seating position, OP code, "
    "ejection, airbag deployment code, and body style. "

    "Extract driver sobriety, physical condition, "
    "driver actions, road condition, traffic control, "
    "road design, and apparent contributing factors. "

    "Read Sequence of Events FIRST, SECOND, THIRD, "
    "and FOURTH separately. "

    "Never confuse Sequence of Events codes with Road Design. "
    "Preserve report codes exactly, including the letter O. "

    "Do not infer missing dates or driver's license numbers. "
    "Preserve all VIN characters exactly as printed. "
    
    "When multiple weather conditions or apparent contributing "
    "factors are explicitly marked, separate the selected option "
    "labels with a semicolon (;), not a comma. "
    "Preserve commas within a single option label, such as "
    "'BLOWING SAND, SOIL, DIRT'. "
    "Include only explicitly selected or printed values; "
    "do not infer additional conditions from the narrative. "
)


PAGE_1_PROMPT = (
    "Extract page 1 of a State of New Mexico Uniform Crash Report, "
    "form SH 10074, Rev July 2018. "

    "Extract the incident header and Traffic Unit 01. Traffic Unit 01 may "
    "continue lower on the same page. Associate every driver, owner, vehicle, "
    "insurance, plate, and VIN value on this page only with the printed "
    "TRAFFIC UNIT or VEHICLE NO. "

    "Owner and Driver are different people unless the report explicitly shows "
    "otherwise. Read Owner Phone separately from Driver Phone. "

    "For VIN, copy every printed character exactly. "
    "For insurance company and policy number, preserve exact spelling. "

    + KEY_WHAT_YOU_SEE
)


PAGES_2_AND_3_PROMPT = (
    "These are consecutive pages 2 and 3 of the SAME State of New Mexico "
    "Uniform Crash Report, form SH 10074, Rev July 2018. Read both images "
    "together and return one merged result for the traffic units shown. "

    "IMPORTANT PAGE STRUCTURE: "
    "Page 2 begins with condition and contributing-factor information that "
    "continues Traffic Unit 01. Later on page 2, the printed heading "
    "'TRAFFIC UNIT 02' begins Unit 02 and contains Unit 02's driver details. "
    "Page 3 begins with Vehicle Information that CONTINUES Traffic Unit 02, "
    "even if the TRAFFIC UNIT 02 heading is not repeated. Page 3's vehicle, "
    "VIN, plate, owner, insurance, towing, damage, condition, and driver-action "
    "information therefore belongs to Unit 02. "

    "Do not assign page 3's vehicle or owner information to Unit 01. "
    "Return Unit 01 only for fields that clearly continue Unit 01 at the top "
    "of page 2. Return Unit 02 by combining its driver section from page 2 "
    "with its vehicle and owner section from page 3. "

    "Use the printed traffic-unit number as unit_number. "
    "Owner and Driver are different people unless explicitly shown otherwise. "
    "Read Owner Phone separately from Driver Phone. "

    "For VIN, copy every printed character exactly. "
    "For insurance company and policy number, preserve exact spelling. "
    
    + KEY_WHAT_YOU_SEE
    
)

# Apply additional NM extraction instructions
PAGE_1_PROMPT += NM_EXTRACTION_RULES

PAGE_1_PROMPT += (
    "IMPORTANT FIELD DISTINCTIONS: "

    "Intersection Type must come only from the field "
    "explicitly labeled INTERSECTION TYPE. "

    "Do not use Manner of Impact, crash configuration, "
    "or INTERSECTING PATH (T-BONE) as Intersection Type. "

    "First Harmful Event must come only from its "
    "corresponding labeled field. "

    "Do not use Sequence of Events codes such as MVT "
    "as First Harmful Event. "

    "Preserve the exact printed values. "
)
PAGES_2_AND_3_PROMPT += NM_EXTRACTION_RULES

PAGES_2_AND_3_PROMPT += (
    "CONTINUATION PAGE RESPONSIBILITIES: Extract Traffic Unit 01 continuation "
    "and Traffic Unit 02 details using the printed unit headings. "
    "Return incident containing ONLY intersection_type, weather, and lighting, "
    "read from their explicitly labeled fields in the Condition Information "
    "sections. Leave all other incident fields null. "
    "If these sections disagree on any of the three fields, return null for "
    "that field and report the disagreement in warnings; never guess. "
    "Return null for blank or unreadable values. "
    "INTERSECTING PATH (T-BONE) is crash configuration, not Intersection Type. "
    "MVT is a Sequence of Events code, not First Harmful Event. "
)


PAGE_4_PROMPT = (
    "This is page 4 of a New Mexico Uniform Crash Report SH 10074. "
    "Extract ONLY district and officer_id from the CONCLUSION section. "
    "Read district from the field labeled District. "
    "Read officer_id from the field labeled ID Number. "
    "Do not confuse District with Agency, Rank, Case Number, "
    "or Crash Report Number. "
    "Do not extract vehicle or driver information. "
    "Preserve values exactly as printed. "
    "Return null for blank or unreadable fields."
)

def _image(page, dpi: int = 180) -> str:
    pix = page.get_pixmap(
        dpi=dpi,
        colorspace=pymupdf.csGRAY,
        alpha=False,
    )

    encoded = base64.b64encode(
        pix.tobytes(
            "jpeg",
            jpg_quality=85,
        )
    ).decode("ascii")

    return "data:image/jpeg;base64," + encoded


def _extract_images(
    images: list[str],
    prompt: str,
    model: str,
    schema=NMPageExtraction,
):

    content = []

    for page_number, image_url in enumerate(
        images,
        start=1,
    ):
        content.append(
            {
                "type": "input_text",
                "text": f"IMAGE {page_number}:",
            }
        )

        content.append(
            {
                "type": "input_image",
                "image_url": image_url,
                "detail": "high",
            }
        )

    from app.ai.runtime import get_ai_client
    return get_ai_client().parse(
        model=model,
        instructions=prompt,
        content=content,
        schema=schema,
        reasoning_effort="none",
    )


def _merge_fields(
    previous,
    incoming,
    warnings: list[str],
    label: str,
):
    data = previous.model_dump()

    for field, new_value in incoming.model_dump().items():
        if new_value in (None, ""):
            continue

        old_value = data.get(field)

        if (
            old_value not in (None, "")
            and old_value != new_value
        ):
            warnings.append(
                f"{label}: conflicting readings for {field}; "
                f"first={old_value!r}, second={new_value!r}; "
                "manual review required."
            )

            # Never silently overwrite a populated source value.
            continue

        data[field] = new_value

    return type(previous)(**data)


def merge_pages(
    pages: list[NMPageExtraction],
) -> NMReport:
    warnings: list[str] = []
    incident = NMIncident()
    units: dict[int, NMUnit] = {}

    for page in pages:
        warnings.extend(page.warnings)

        if page.incident is not None:
            incident = _merge_fields(
                incident,
                page.incident,
                warnings,
                "Incident",
            )

        for unit in page.units:
            if unit.unit_number < 1:
                warnings.append(
                    "Invalid unit number skipped."
                )
                continue

            existing = units.get(unit.unit_number)

            if existing is None:
                units[unit.unit_number] = unit
                continue

            units[unit.unit_number] = _merge_fields(
                existing,
                unit,
                warnings,
                f"Unit {unit.unit_number}",
            )

    if not units:
        raise ValueError(
            "No NM traffic units found; nothing should be keyed."
        )

    return NMReport(
        incident=incident,
        units=[
            units[number]
            for number in sorted(units)
        ],
        warnings=warnings,
    )


def extract_nm(
    pdf_path: Path,
    model: str = "gpt-6-luna",
) -> NMReport:

    with pymupdf.open(pdf_path) as pdf:

        if len(pdf) < 4:
            raise ValueError(
                "Expected at least four pages in this NM report."
            )

        page_1_image = _image(pdf.load_page(0))
        page_2_image = _image(pdf.load_page(1))
        page_3_image = _image(pdf.load_page(2))
        page_4_image = _image(pdf.load_page(3))

    with ThreadPoolExecutor(max_workers=4) as pool:

        inventory_future = pool.submit(
            _extract_images,
            [page_1_image, page_2_image, page_3_image],
            UNIT_INVENTORY_PROMPT, model, NMUnitInventory,
        )

        # Page 1: Incident and Unit 1
        page_1_future = pool.submit(
            _extract_images,
            [page_1_image],
            PAGE_1_PROMPT,
            model,
        )

        # Pages 2-3: Unit 1 continuation and Unit 2
        pages_2_3_future = pool.submit(
            _extract_images,
            [page_2_image, page_3_image],
            PAGES_2_AND_3_PROMPT,
            model,
        )

        # Page 4: District and Officer ID
        page_4_future = pool.submit(
            _extract_images,
            [page_4_image],
            PAGE_4_PROMPT,
            model,
            NMConclusion,
        )

        page_1_result = page_1_future.result()
        pages_2_3_result = pages_2_3_future.result()
        conclusion = page_4_future.result()
        inventory = inventory_future.result()

    if inventory.uncertain:
        raise IncompleteExtractionError(
            "NM unit inventory is uncertain; filling cancelled for review."
        )
    expected = set(inventory.unit_numbers)
    results = [page_1_result, pages_2_3_result]
    actual = {unit.unit_number for result in results for unit in result.units}
    missing = missing_units(expected, actual)
    recovery = None
    if missing:
        print("NM completeness: missing unit identifiers; targeted recovery started.")
        # One recovery only, on the same three-page structured section.
        # Preserve both sides of a split unit; never re-download or re-detect state.
        prompt = (
            "These are consecutive PDF pages 1, 2 and 3 of the SAME NM SH 10074 report. "
            "Extract ONLY populated units with these printed identifiers: "
            + ", ".join(str(n) for n in sorted(missing)) + ". "
            "Read unit headings directly; never create a unit to satisfy the request. "
            "Combine driver details with vehicle/owner/insurance continuations across "
            "page boundaries. Do not copy fields between units. Return incident=null. "
            "Return no other units. If the requested unit cannot be read, omit it "
            "and explain in warnings. " + KEY_WHAT_YOU_SEE + NM_EXTRACTION_RULES
        )
        recovery = _extract_images(
            [page_1_image, page_2_image, page_3_image], prompt, model,
        )
        if any(unit.unit_number not in missing for unit in recovery.units):
            raise IncompleteExtractionError(
                "NM recovery returned an unrequested unit; filling cancelled."
            )
        recovered_ids = [unit.unit_number for unit in recovery.units]
        if len(recovered_ids) != len(set(recovered_ids)):
            raise IncompleteExtractionError("NM recovery returned duplicate units; filling cancelled.")
        if missing_units(expected, actual | set(recovered_ids)):
            raise IncompleteExtractionError(
                "NM unit extraction remains incomplete after one recovery; filling cancelled."
            )
        # Ignore recovery incident fields by design, even if the model returns them.
        recovery.incident = None
        print("NM completeness: missing unit identifiers recovered.")

    # Preserve approved condition fields without accepting unrelated
    # incident fields from continuation pages.
    continuation_incident = pages_2_3_result.incident
    pages_2_3_result.incident = NMIncident(
        intersection_type=(
            continuation_incident.intersection_type
            if continuation_incident is not None else None
        ),
        weather=(
            continuation_incident.weather
            if continuation_incident is not None else None
        ),
        lighting=(
            continuation_incident.lighting
            if continuation_incident is not None else None
        ),
    )

    # Intersection Type belongs to the continuation condition sections.
    # Retain page 1 Weather/Lighting so genuine conflicts remain visible.
    if page_1_result.incident is not None:
        page_1_result.incident.intersection_type = None

    merge_inputs = [page_1_result, pages_2_3_result]
    if recovery is not None:
        merge_inputs.append(recovery)
    report = merge_pages(merge_inputs)
    if missing_units(expected, {unit.unit_number for unit in report.units}):
        raise IncompleteExtractionError("NM merged report is incomplete; filling cancelled.")

    if conclusion.district:
        report.incident.district = conclusion.district

    if conclusion.officer_id:
        report.incident.officer_id = conclusion.officer_id

    return report