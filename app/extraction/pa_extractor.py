"""Pennsylvania Police Crash Report (AA-500 family) extraction.

PA reports are PDFs that may hold scanned images, searchable text or a mix, so EVERY page is rendered to an
image and read by the model, exactly like NC. A PA report has a variable number of pages (page 1 = crash data,
then one page per unit, then People Information pages, witnesses, narrative, diagram), so each page is read on
its own, in parallel, and the results are merged here:

  * crash data comes from the first page that carries it (the Incident Number printed in every page header
    is used to drop pages that belong to a DIFFERENT report, e.g. an unrelated attachment);
  * units are merged by unit number, occupants / witnesses / property owners are collected from every page;
  * a page the model says is not a PA crash report is skipped with a note.

The result is a RAW dict in the shape documented at the top of app/keying/pa_rules.py (map_pa turns it into the
keying payload). Nothing here decides what to key: values are returned as printed.
"""
from __future__ import annotations

import base64
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf
from pydantic import BaseModel, Field

from app.core.completeness import IncompleteExtractionError, missing_units

MAX_PAGES = 40


# ------------------------------------------------------------------ schema (all values as printed)
class PACoded(BaseModel):
    code: str | None = None
    text: str | None = None


class PAViolation(BaseModel):
    text: str | None = None
    charged: str | None = None            # the "Person Charged" text: YES / NO / WARNING / Y / N ...
    primary: bool = False                 # the line is marked as the Primary Vehicle Code Violation


class PAPerson(BaseModel):
    first: str | None = None
    middle: str | None = None
    last: str | None = None
    suffix: str | None = None
    address_1: str | None = None
    address_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    phone: str | None = None
    dob: str | None = None
    dl_number: str | None = None
    dl_state: str | None = None
    alcohol_drugs: list[PACoded] = Field(default_factory=list)
    driver_actions: list[PACoded] = Field(default_factory=list)
    helmet: list[PACoded] = Field(default_factory=list)
    violations: list[PAViolation] = Field(default_factory=list)


class PAParty(BaseModel):                 # owner, witness, property owner
    first: str | None = None
    middle: str | None = None
    last: str | None = None
    suffix: str | None = None
    address_1: str | None = None
    address_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    phone: str | None = None


class PAVehicle(BaseModel):
    plate: str | None = None
    plate_state: str | None = None
    vin: str | None = None
    year: str | None = None
    make: str | None = None
    model: str | None = None
    insurance_company: str | None = None
    policy_number: str | None = None
    policy_expiration: str | None = None
    towed: str | None = None              # the "Vehicle Towed" box
    towed_by: str | None = None
    impact_point: list[str] = Field(default_factory=list)       # "Initial Impact Point" (clock numbers)
    vehicle_failures: list[PACoded] = Field(default_factory=list)


class PATrailer(BaseModel):               # one "Trailing Units" row
    plate: str | None = None
    plate_state: str | None = None
    vin: str | None = None
    year: str | None = None               # only a printed vehicle / model year
    tag_year: str | None = None           # the "Tag Year" column (registration year, NOT a vehicle year)
    make: str | None = None               # "Unit Make"


class PAUnit(BaseModel):
    number: int
    unit_type: str | None = None
    hit_and_run: bool = False
    owner_is_driver: bool = False
    driver: PAPerson = Field(default_factory=PAPerson)
    owner: PAParty = Field(default_factory=PAParty)
    vehicle: PAVehicle = Field(default_factory=PAVehicle)
    passenger_helmet: list[PACoded] = Field(default_factory=list)
    trailers: list[PATrailer] = Field(default_factory=list)


class PAOccupant(BaseModel):              # one "People Information" block
    unit: str | None = None
    person_no: str | None = None
    person_type: PACoded = Field(default_factory=PACoded)
    first: str | None = None
    middle: str | None = None
    last: str | None = None
    suffix: str | None = None
    address_1: str | None = None
    address_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    phone: str | None = None
    dob: str | None = None
    injury: list[PACoded] = Field(default_factory=list)
    safety_equipment: list[PACoded] = Field(default_factory=list)
    helmet: list[PACoded] = Field(default_factory=list)
    ejection: list[PACoded] = Field(default_factory=list)
    pedestrian_actions: list[PACoded] = Field(default_factory=list)
    airbag: str | None = None
    medical_facility: str | None = None
    violations: list[PAViolation] = Field(default_factory=list)


class PAPage(BaseModel):
    is_pa_crash_report: bool = True       # False: this page belongs to some other form / attachment
    incident_number: str | None = None
    report_number: str | None = None
    cad_case_number: str | None = None
    investigation_date: str | None = None
    crash_date: str | None = None
    crash_time: str | None = None
    municipality: str | None = None
    units_involved: int | None = None     # "# of Units"
    house_number: str | None = None
    street_name: str | None = None
    street_ending: str | None = None
    route_number: str | None = None
    cross_street_name: str | None = None
    cross_street_ending: str | None = None
    not_in_intersection: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    weather: list[PACoded] = Field(default_factory=list)
    road_surface: list[PACoded] = Field(default_factory=list)
    speed_limit: str | None = None
    hit_and_run_crash: bool = False
    units: list[PAUnit] = Field(default_factory=list)
    occupants: list[PAOccupant] = Field(default_factory=list)
    witnesses: list[PAParty] = Field(default_factory=list)
    property_owners: list[PAParty] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------ prompt
KEY_WHAT_YOU_SEE = (
    "KEY WHAT YOU SEE. Transcribe every value exactly as printed, including misspellings, punctuation, "
    "capitalization, leading zeros, identifiers and VIN characters. Never correct, normalize, translate, guess or "
    "invent. Return null for a blank or unreadable value. Never copy a value from one unit to another. "
    "For every coded or dropdown-like box return each printed value as {code, text}: the number as printed in "
    "code and the words as printed in text (either may be null); several printed values are several entries."
)

PAGE_PROMPT = (
    "This is ONE page of a Commonwealth of Pennsylvania Police Crash Report (the AA-500 family of forms, "
    "'Pennsylvania Police Crash Report'). Return ONLY what is printed on THIS page and leave everything else "
    "empty. Set is_pa_crash_report=false if the page is not part of such a report (another form, a theft or "
    "incident report, a cover sheet, a blank page). "
    "HEADER (repeated on each page): incident_number = 'Incident Number'; report_number = 'Report Number'; "
    "cad_case_number = 'CAD/CASE Number' (use this instead when the page prints a CAD/CASE number). "
    "CRASH DATA PAGE: investigation_date; crash_date exactly as printed (even when the year is missing, e.g. "
    "'06/06,'); crash_time; municipality = the name in 'Municipality' (not the County); units_involved = '# of "
    "Units'; Principal Road: house_number, street_name, street_ending ('St. Ending'), route_number ('Route "
    "Number'); Intersecting Road: cross_street_name, cross_street_ending ('St. Ending'), and not_in_intersection "
    "= the text of any 'If Not in Intersection' / location line used when no intersecting street is named; "
    "GPS: latitude and longitude as Degrees:Minutes:Seconds.Decimal (for example 40:04:53.610), with a leading "
    "'-' when printed; weather = every value in 'Weather Conditions 1' and 'Weather Conditions 2'; road_surface "
    "= every value in 'Road Surface Conditions'; speed_limit = the Principal Road 'Speed Limit' as printed; "
    "hit_and_run_crash = true ONLY if the 'Hit and Run' box under 'Crash Involves' is marked. "
    "UNIT PAGE (one unit per page; a page can hold several): number = 'Unit Number' (001 -> 1); unit_type = "
    "'Type Unit'; hit_and_run = true ONLY when a hit-and-run indication is printed against THIS unit (for "
    "example a driver presence / fled-the-scene entry for this unit); never set it merely because the crash-level "
    "box is marked. Driver block: first, middle (MI), last, suffix, dob, phone ('Telephone Number'), the whole "
    "street line in address_1, city, state, zip, dl_number ('License Number'), dl_state ('License State'); "
    "owner_is_driver = true if the 'Owner/Driver' box is marked; one violations entry per printed 'Violation 1-4' "
    "line with the 'Person Charged' text in charged, primary=true only if that line is marked as the primary "
    "vehicle code violation; alcohol_drugs = 'Alcohol/Drugs Suspected'; driver_actions = 'Driver Action'. "
    "Owner block: 'Owner First Name', 'Owner MI', 'Owner Last Name or Business Name' (a business name goes in "
    "last), suffix, street address, city, state, zip, telephone. Vehicle: year = 'Model Year', make, model, vin, "
    "plate = 'License Plate', plate_state = 'Reg. State', towed = 'Vehicle Towed', towed_by, insurance_company "
    "('Insurance Company'), policy_number, policy_expiration ('Expiration Date' in the insurance row), "
    "impact_point = 'Initial Impact Point' (the clock number as printed), vehicle_failures = 'Possible Vehicle "
    "Failures'. Motorcycle block: 'Driver Helmet Type' -> driver.helmet, 'Passenger Helmet Type' -> "
    "passenger_helmet. Trailing Units: one trailers entry per filled row (plate = 'Tag Number', plate_state = "
    "'Tag State', tag_year = 'Tag Year', make = 'Unit Make'; leave year empty unless a vehicle year is printed). "
    "Never copy driver data into the owner block or the reverse. "
    "PEOPLE INFORMATION PAGE: one occupants entry per person block that has any entry: unit = the 'Unit' box, "
    "person_no, person_type = 'Person Type', first/middle/last/suffix, address, phone, dob, injury = 'Injury "
    "Severity', safety_equipment = 'Safety Equipment 1' (ignore 'Safety Equipment 2'), ejection = 'Ejection', "
    "airbag = 'Airbag', medical_facility = 'Medical Facility', pedestrian_actions if printed. "
    "Witness blocks -> witnesses; property damage owners -> property_owners (name, address, phone). "
    "Put anything ambiguous in warnings instead of guessing. " + KEY_WHAT_YOU_SEE
)


# PA live report guard 46888
PAGE_PROMPT += (" IMPORTANT PA RULES: CAD/CASE Number is Report ID 1 only, never Report ID 2. Never derive RID2. "
                "Cross Street must come from printed intersecting Street Name/Street Ending fields. Never treat "
                "Mile Post, Tenths, Or Miles, Feet, route numbers, or numeric values such as 298 6 as a cross street.")

# ------------------------------------------------------------------ plumbing
def _image(page, dpi: int = 170) -> str:
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    return "data:image/jpeg;base64," + base64.b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode("ascii")


def _extract_page(image: str, number: int, model: str, schema=PAPage) -> PAPage:
    content = [{"type": "input_text", "text": f"PAGE {number}:"},
               {"type": "input_image", "image_url": image, "detail": "high"}]
    from app.ai.runtime import get_ai_client
    return get_ai_client().parse(model=model, instructions=PAGE_PROMPT, content=content, schema=schema,
                                 reasoning_effort="none")


def _same_incident(a: str | None, b: str | None) -> bool:
    n = lambda x: re.sub(r"[^A-Z0-9]", "", (x or "").upper())
    return not n(a) or not n(b) or n(a) == n(b)


def _key(*parts) -> str:
    return "|".join(re.sub(r"\s+", " ", str(p or "").strip().upper()) for p in parts)


def merge_pages(pages: list[PAPage]) -> dict:
    """Combine the per-page results into the raw dict map_pa reads. Pages are given in PDF order."""
    notes: list[str] = []
    base_id: str | None = None
    kept: list[tuple[int, PAPage]] = []
    for idx, p in enumerate(pages, start=1):
        for w in p.warnings:
            notes.append(f"Page {idx}: {w}")
        if not p.is_pa_crash_report:
            notes.append(f"Page {idx} is not part of a PA crash report; ignored")
            continue
        ident = p.incident_number or p.cad_case_number
        if base_id is None and ident:
            base_id = ident
        if not _same_incident(base_id, ident):
            notes.append(f"Page {idx} belongs to incident '{ident}', not '{base_id}'; ignored")
            continue
        kept.append((idx, p))
    if not kept:
        raise ValueError("No PA crash report pages found; nothing should be keyed.")

    raw: dict = {k: None for k in (
        "incident_number", "report_number", "cad_case_number", "investigation_date", "crash_date", "crash_time",
        "municipality", "house_number", "street_name", "street_ending", "route_number", "cross_street_name",
        "cross_street_ending", "not_in_intersection", "latitude", "longitude", "speed_limit", "units_involved")}
    raw.update({"weather": [], "road_surface": [], "hit_and_run_crash": False,
                "units": [], "occupants": [], "witnesses": [], "property_owners": []})
    seen_units: dict[int, int] = {}
    seen_occ: set[str] = set()
    seen_party: set[str] = set()
    for idx, p in kept:
        for k in [k for k, v in raw.items() if v is None]:
            v = getattr(p, k)
            if v not in (None, ""):
                raw[k] = v
        for k in ("weather", "road_surface"):
            if not raw[k] and getattr(p, k):
                raw[k] = [c.model_dump() for c in getattr(p, k)]
        raw["hit_and_run_crash"] = raw["hit_and_run_crash"] or p.hit_and_run_crash
        for u in p.units:
            if u.number < 1:
                notes.append(f"Page {idx}: invalid unit number skipped")
                continue
            if u.number in seen_units:
                notes.append(f"Unit {u.number} appears on pages {seen_units[u.number]} and {idx}; first reading kept")
                continue
            seen_units[u.number] = idx
            raw["units"].append(u.model_dump())
        for o in p.occupants:
            k = _key(o.unit, o.person_no, o.first, o.last)
            if k in seen_occ:
                continue
            seen_occ.add(k)
            raw["occupants"].append(o.model_dump())
        for field in ("witnesses", "property_owners"):
            for w in getattr(p, field):
                k = _key(field, w.first, w.last, w.address_1)
                if k in seen_party:
                    continue
                seen_party.add(k)
                raw[field].append(w.model_dump())
    raw["notes"] = notes
    return raw


def check_units(raw: dict) -> None:
    """Never key a report with a unit missing: compare the printed '# of Units' with what was read."""
    expected = raw.get("units_involved")
    actual = {u["number"] for u in raw["units"]}
    if not actual:
        raise ValueError("No PA units found; nothing should be keyed.")
    if not expected:
        raw["notes"].append("'# of Units' unreadable; unit count not verified")
        return
    missing = missing_units(set(range(1, int(expected) + 1)), actual)
    if missing:
        raise IncompleteExtractionError(
            f"PA report lists {expected} units but unit(s) {sorted(missing)} were not extracted; filling cancelled.")


def extract_pa(pdf_path: Path, model: str = "gpt-6-luna") -> dict:
    """PDF (scanned, searchable or mixed) -> raw PA dict (see app/keying/pa_rules.py)."""
    with pymupdf.open(pdf_path) as pdf:
        count = len(pdf)
        if count < 1 or count > MAX_PAGES:
            raise ValueError(f"A PA crash report has 1-{MAX_PAGES} pages; this file has {count}.")
        images = [_image(pdf.load_page(i)) for i in range(count)]
    with ThreadPoolExecutor(max_workers=min(4, count)) as pool:
        pages = list(pool.map(lambda a: _extract_page(a[1], a[0] + 1, model), enumerate(images)))
    raw = merge_pages(pages)
    check_units(raw)
    return raw


def extract_payload(pdf_path: Path, model: str = "gpt-6-luna") -> dict:
    """Raw extraction -> keying payload."""
    from app.keying.pa_rules import map_pa
    return map_pa(extract_pa(pdf_path, model))
