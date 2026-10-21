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
)


KEY_WHAT_YOU_SEE = (
    "KEY WHAT YOU SEE. Transcribe values exactly as printed, including "
    "misspellings, punctuation, capitalization, identifiers, leading zeros, "
    "VIN characters, and insurance-carrier spelling. Never correct, normalize, "
    "guess, or invent source values. Return null when a value is blank or "
    "unreadable. Do not copy values between traffic units."
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
) -> NMPageExtraction:
    # Delayed import lets mapping unit tests run without importing OpenAI.
    from openai import OpenAI

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

    response = OpenAI().responses.parse(
        model=model,
        reasoning={
            "effort": "none",
        },
        input=[
            {
                "role": "system",
                "content": prompt,
            },
            {
                "role": "user",
                "content": content,
            },
        ],
        text_format=NMPageExtraction,
    )

    result = response.output_parsed

    if result is None:
        raise RuntimeError(
            "NM extraction returned no structured result."
        )

    return result


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
        if len(pdf) < 3:
            raise ValueError(
                "Expected at least three pages in the NM report."
            )

        page_1_image = _image(
            pdf.load_page(0),
        )

        page_2_image = _image(
            pdf.load_page(1),
        )

        page_3_image = _image(
            pdf.load_page(2),
        )

    # Two API requests run simultaneously:
    # 1. Page 1 and Unit 1
    # 2. Pages 2-3 together, preserving Unit 2 continuation context
    with ThreadPoolExecutor(
        max_workers=2,
    ) as pool:
        page_1_future = pool.submit(
            _extract_images,
            [page_1_image],
            PAGE_1_PROMPT,
            model,
        )

        pages_2_3_future = pool.submit(
            _extract_images,
            [
                page_2_image,
                page_3_image,
            ],
            PAGES_2_AND_3_PROMPT,
            model,
        )

        page_1_result = page_1_future.result()
        pages_2_3_result = pages_2_3_future.result()

    return merge_pages(
        [
            page_1_result,
            pages_2_3_result,
        ]
    )