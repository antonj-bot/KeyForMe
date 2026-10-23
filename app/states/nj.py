"""New Jersey NJTR-1 extraction and supervised form-filling pipeline."""
import copy
from pathlib import Path

from app.extraction.nj_extractor import extract_nj
from app.keying.nj_rules import map_nj

NAME = "New Jersey NJTR-1"


def extract(pdf_path: Path, model: str) -> dict:
    return map_nj(extract_nj(pdf_path, model))


def to_engine_payload(payload: dict) -> dict:
    """What the shared engine can fill. Hit & Run, extra charges and the Same As boxes are
    handled by app/browser/nj_extras.py, so they are removed here."""
    data = copy.deepcopy(payload)
    data.get("incident", {}).pop("hit_and_run", None)
    for unit in data.get("units", []):
        unit.get("driver", {}).pop("extra_charges", None)
    for party in data.get("other_parties", []):
        party.pop("same_as_driver_address", None)
        party.pop("same_as_owner_address", None)
    return data


def fill(page, payload: dict) -> None:
    from app.browser.engine import fill_form
    from app.browser.nj_extras import fill_nj_extras
    from app.ui import server as ui

    if not payload.get("units"):
        raise ValueError("No NJ units available to fill.")
    for note in payload.get("notes", []):                   # advisory: shown, never blocks filling
        ui.log(str(note), "warning")
    ui.log("NJ supervised filling started. Missing units and other parties are created automatically.", "warning")
    warnings = list(fill_form(page, to_engine_payload(payload), state="NJ", log=ui.log) or [])
    warnings += fill_nj_extras(page, payload, log=ui.log)
    for warning in warnings:
        ui.log(str(warning), "warning")
    ui.update(warnings=len(warnings))
    ui.log("NJ filler finished. Review skipped fields, charges and VIN lookup results before saving.",
           "warning" if warnings or payload.get("notes") else "success")
