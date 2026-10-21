"""New Mexico extraction and supervised form-filling pipeline."""

from pathlib import Path

from app.extraction.nm_extractor import extract_nm
from app.keying.nm_mapper import map_nm


NAME = "New Mexico SH 10074"


def extract(pdf_path: Path, model: str) -> dict:
    report = extract_nm(pdf_path, model)
    return map_nm(report)


def fill(page, payload: dict) -> None:
    from app.browser.nm_filler import (
        ensure_nm_units,
        fill_nm_form,
    )
    from app.browser.nm_field_mapping import FRAME, UNIT_SECTION
    from app.ui import server as ui

    units = payload.get("units", [])

    if not units:
        raise ValueError("No NM units available to fill.")

    # Stop before modifying the form if extraction needs review.
    notes = payload.get("notes", [])

    if notes:
        for note in notes:
            ui.log(str(note), "warning")

        raise ValueError(
            "NM extraction has unresolved notes; filling cancelled."
        )

    # The current NM filler does not create vehicle units.
    section = page.frame_locator(FRAME).locator(UNIT_SECTION)

    if section.count() != 1:
        raise RuntimeError(
            "NM vehicle-unit section missing or ambiguous."
        )

    available = section.locator(
        "a.ui-tabs-anchor[href^='#tabs-']"
    ).count()

    if available < len(units):
        ui.log(
            f"NM requires {len(units)} vehicle units, "
            f"but the form has {available}. "
            "Add the missing units manually, then retry.",
            "warning",
        )

        # Create missing units before filling incident or person fields.
        ensure_nm_units(
            page,
            required=len(units),
            log=ui.log,
        )

    ui.log(
        "NM supervised filling started. "
        "Review VIN lookup dialogs and all keyed fields.",
        "warning",
    )

    warnings = fill_nm_form(page, payload) or []

    for warning in warnings:
        ui.log(str(warning), "warning")

    ui.update(warnings=len(warnings))

    ui.log(
        "NM filler finished. Review skipped fields and "
        "VIN lookup results before saving.",
        "warning" if warnings else "success",
    )