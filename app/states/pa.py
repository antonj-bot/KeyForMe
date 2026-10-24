"""Pennsylvania Police Crash Report (AA-500) extraction and supervised form-filling pipeline."""
import copy
from pathlib import Path

from app.extraction.pa_extractor import extract_pa
from app.keying.pa_rules import map_pa

NAME = "Pennsylvania Police Crash Report"
ENABLED = True          # app/registry.py only registers pipelines that say so


def extract(pdf_path: Path, model: str) -> dict:
    return map_pa(extract_pa(pdf_path, model))


def to_engine_payload(payload: dict) -> dict:
    """What the shared engine can fill. Hit & Run, violation rows and trailers are handled by
    app/browser/pa_extras.py, so they are removed here."""
    data = copy.deepcopy(payload)
    data.get("incident", {}).pop("hit_and_run", None)
    for unit in data.get("units", []):
        unit.get("driver", {}).pop("violations", None)
        unit.pop("trailers", None)
    for party in data.get("other_parties", []):
        party.pop("violations", None)
    return data


def fill(page, payload: dict) -> None:
    from app.browser import pa_field_mapping
    from app.browser.engine import fill_form
    from app.browser.pa_extras import fill_pa_extras
    from app.ui import server as ui
    if not payload.get("units"):
        raise ValueError("No PA units available to fill.")
    for note in payload.get("notes", []):                   # advisory: shown, never blocks filling
        ui.log(str(note), "warning")
    if not pa_field_mapping.PERSON_TYPES_VERIFIED and payload.get("other_parties"):
        ui.log("PA Party Type wording is not verified against UAT yet; check every Other Party's Party Type.", "warning")
    ui.log("PA supervised filling started. Missing units and other parties are created automatically.", "warning")
    warnings = list(fill_form(page, to_engine_payload(payload), state="PA", log=ui.log) or [])
    warnings += fill_pa_extras(page, payload, log=ui.log)
    for warning in warnings:
        ui.log(str(warning), "warning")
    ui.update(warnings=len(warnings))
    ui.log("PA filler finished. Review skipped fields, violations, coded fields, trailers and VIN lookup results "
           "before saving.", "warning" if warnings or payload.get("notes") else "success")
