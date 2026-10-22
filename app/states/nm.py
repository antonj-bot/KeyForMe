"""New Mexico extraction and supervised form-filling pipeline."""

from pathlib import Path

from app.extraction.nm_extractor import extract_nm
from app.keying.nm_mapper import map_nm


NAME = "New Mexico SH 10074"


def extract(pdf_path: Path, model: str) -> dict:
    report = extract_nm(pdf_path, model)
    return map_nm(report)


def fill(page, payload: dict) -> None:
    from app.browser.engine import fill_form
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

    ui.log(
        "NM supervised filling started. "
        "Missing vehicle units will be created automatically.",
        "warning",
    )

    warnings = fill_form(
        page,
        payload,
        state="NM",
        log=ui.log,
    ) or []

    for warning in warnings:
        ui.log(str(warning), "warning")

    ui.update(warnings=len(warnings))

    ui.log(
        "NM filler finished. Review skipped fields and "
        "VIN lookup results before saving.",
        "warning" if warnings else "success",
    )