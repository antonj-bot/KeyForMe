"""North Carolina DMV-349 extraction and supervised form-filling pipeline."""
import copy
from pathlib import Path

from app.extraction.nc_extractor import extract_nc
from app.keying.nc_rules import map_nc

NAME = "North Carolina DMV-349"
ENABLED = True          # app/registry.py only registers pipelines that say so


def extract(pdf_path: Path, model: str) -> dict:
    return map_nc(extract_nc(pdf_path, model))


def to_engine_payload(payload: dict) -> dict:
    """What the shared engine can fill. Hit & Run, extra charges and the Same As boxes are handled by
    app/browser/nc_extras.py, so they are removed here."""
    data = copy.deepcopy(payload)
    data.get("incident", {}).pop("hit_and_run", None)
    for unit in data.get("units", []):
        unit.get("driver", {}).pop("extra_charges", None)
        unit.get("owner", {}).pop("same_as_driver_address", None)
    for party in data.get("other_parties", []):
        party.pop("extra_charges", None)
        party.pop("same_as_driver_address", None)
        party.pop("same_as_owner_address", None)
    return data


def fill(page, payload: dict) -> None:
    from app.browser.engine import fill_form
    from app.browser.nc_extras import fill_nc_extras
    from app.ui import server as ui

    if not payload.get("units"):
        raise ValueError("No NC units available to fill.")
    for note in payload.get("notes", []):                   # advisory: shown, never blocks filling
        ui.log(str(note), "warning")
    ui.log("NC supervised filling started. Missing units and other parties are created automatically.", "warning")
    warnings = list(fill_form(page, to_engine_payload(payload), state="NC", log=ui.log) or [])
    warnings += fill_nc_extras(page, payload, log=ui.log)
    for warning in warnings:
        ui.log(str(warning), "warning")
    ui.update(warnings=len(warnings))
    ui.log("NC filler finished. Review skipped fields, charges, coded fields and VIN lookup results before saving.",
           "warning" if warnings or payload.get("notes") else "success")
