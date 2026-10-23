"""North Carolina DMV-349 crash report extraction.

The NC report is a scanned image. One DMV-349 "form" is TWO pages: page 1 holds the header, the
incident, Unit 1 (left) and Unit 2 (right) and the A-H person table; page 2 holds the per-unit
boxes (59, 60), the diagram footer (Traveling / Parked), the narrative, property damage, witnesses
and the traffic-violation (charge) lines. A report with more than two units adds a second form
("Form 2 of 2") with Units 3 and 4, and so on. A form whose Supplemental Report box is ticked REPLACES
the original report: only the supplemental form(s) are keyed (see select_forms).

So pages are read in PAIRS (1+2, 3+4, ...), one model call per pair, in parallel. The result is a
RAW dict in the shape documented at the top of app/keying/nc_rules.py (map_nc turns it into the
keying payload). Nothing here decides what to key: values are returned as printed.
"""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf
from pydantic import BaseModel, Field

from app.core.completeness import IncompleteExtractionError, missing_units


# ------------------------------------------------------------------ schema (all values as printed)
class NCPerson(BaseModel):
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
    phone_area: str | None = None                  # the digits inside "H ( 516 )"
    dob: str | None = None
    dl_number: str | None = None
    dl_state: str | None = None
    alcohol_suspected: str | None = None          # box 37 only


class NCOwner(BaseModel):
    first: str | None = None
    middle: str | None = None
    last: str | None = None
    suffix: str | None = None
    same_as_driver: bool = False                   # the "Same as Driver?" box under the owner name
    same_address_as_driver: bool = False           # the "Same Address as Driver?" box
    address_1: str | None = None
    address_2: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None


class NCVehicle(BaseModel):
    plate: str | None = None
    plate_state: str | None = None
    vin: str | None = None
    year: str | None = None
    make: str | None = None
    model: str | None = None
    tad: str | None = None                         # box 43, e.g. FD-2
    insurance_company: str | None = None
    policy_number: str | None = None
    towed_by: str | None = None                    # the "Veh# n Towed To/By" text beside the person table
    defects: str | None = None                     # page 2 box 59 for this unit
    speed_limit: str | None = None                 # page 2 box 60 for this unit


class NCMarginBox(BaseModel):
    box: str                                       # the printed box number beside the margin box
    value: str | None = None


class NCUnit(BaseModel):
    number: int
    column: str = "left"                           # "left" = unit block on the left half of page 1, else "right"
    hit_and_run: bool = False                      # HIT & RUN box in the unit header
    pedestrian: bool = False                       # PEDESTRIAN box in the unit header
    parked: bool = False                           # page 2 footer: "Unit# n was: [ ] Traveling [ ] Parked"
    driver: NCPerson = Field(default_factory=NCPerson)
    owner: NCOwner = Field(default_factory=NCOwner)
    vehicle: NCVehicle = Field(default_factory=NCVehicle)
    ems_taken: str | None = None                   # box 47 text under this unit's column, WITH any row letter


class NCOccupant(BaseModel):
    row: str | None = None                         # the letter A-H in the first column
    vehicle: str | None = None                     # column 21
    person_type: str | None = None                 # column 22
    name: str | None = None
    address_line: str | None = None
    dob: str | None = None
    protection: str | None = None                  # column 27
    airbag: str | None = None                      # column 28
    ejection: str | None = None                    # column 31
    injury: str | None = None                      # column 32


class NCCharge(BaseModel):
    name: str | None = None
    charge: str | None = None


class NCParty(BaseModel):
    name: str | None = None                        # property owner: the person/company name only
    description: str | None = None                 # "FENCE/HOUSE" etc. (discarded downstream)
    address_1: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    phone: str | None = None
    phone_area: str | None = None                  # the digits inside "Phone No. ( 910 )"


class NCFormExtraction(BaseModel):
    form_rev: str | None = None                    # e.g. "1/2009" printed under DMV-349
    form_number: int | None = None                 # "Form 1 of 2" -> 1
    form_total: int | None = None
    supplemental: bool = False
    units_involved: int | None = None              # "No of Units Involved"
    local_use: str | None = None
    crash_date: str | None = None
    crash_time: str | None = None
    municipality: str | None = None
    on_road: str | None = None
    from_road: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    margin_boxes: list[NCMarginBox] = Field(default_factory=list)
    units: list[NCUnit] = Field(default_factory=list)
    occupants: list[NCOccupant] = Field(default_factory=list)
    charges: list[NCCharge] = Field(default_factory=list)
    witnesses: list[NCParty] = Field(default_factory=list)
    property_owners: list[NCParty] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


# ------------------------------------------------------------------ prompts
KEY_WHAT_YOU_SEE = (
    "KEY WHAT YOU SEE. Transcribe every value exactly as printed, including misspellings, punctuation, "
    "capitalization, leading zeros, identifiers, VIN characters and the literal word null or a series of X. "
    "Never correct, normalize, translate, guess or invent. Return null for a blank or unreadable value. "
    "Never copy a value from one unit to another."
)

FORM_PROMPT = (
    "These are the two consecutive pages of ONE North Carolina DMV-349 Crash Report form (page 1 then page 2). "
    "Return one merged result. "

    "PAGE 1. Header: the revision printed under DMV-349 (form_rev), 'Form _ of _' (form_number, form_total), "
    "the Supplemental Report box in the header row beside 'Form _ of _' (supplemental = true ONLY if that "
    "box is marked with an X; the 'Non-Reportable' box beside it is a different box), 'No of Units Involved' "
    "(units_involved), and Local Use/Patrol "
    "Area (local_use, copy it whole, e.g. 260816025HA/02). Return crash_date and crash_time (24-hour clock) from "
    "the Date and Time boxes. 'Crash occurred In/Near ___ Municipality': return the name written there as "
    "municipality (not the County). 'On' road and 'from' road: return the text printed on the On line as on_road "
    "and on the 'from' line as from_road (do not return the 'toward' road). Latitude and Longitude as printed. "

    "UNIT BLOCKS. The left unit block (column=left) and right unit block (column=right) each start with "
    "'UNIT # n' and the boxes VEHICLE / PEDESTRIAN / HIT & RUN / COMMERCIAL VEHICLE (left) or OTHER (right). "
    "Set hit_and_run only if the HIT & RUN box of that unit is marked; pedestrian only if that unit's PEDESTRIAN "
    "box is marked. Use the printed unit number. A unit that is entirely blank is not a unit; do not return it. "
    "Driver: First, Middle, Last, Suffix, Address, City, State, Zip, Home phone (H), DOB, D.L. # and the State on "
    "the D.L. line, and box 37 Alcohol/Drugs Suspected (alcohol_suspected). Owner: First, Middle, Last, Suffix "
    "(a company name goes in last), the 'Same as Driver?' box (same_as_driver) and the 'Same Address as Driver?' "
    "box (same_address_as_driver), then the owner's address, city, state, zip. Vehicle: Plate #, Plate State, VIN, "
    "Vehicle Make, Vehicle Year, 43 TAD (every code printed in the box, e.g. FD-2 or FC-2,FD-3), Insurance Company, Policy #. Owner and driver are different "
    "people unless the report shows otherwise. Read the VIN character by character. "
    "ADDRESSES. Return the street line in address_1 exactly as printed. If the street line also holds an "
    "apartment, unit, suite or lot part (for example '2008 S MEBANE ST, APT,2022B'), return that part, "
    "exactly as printed, in address_2 and keep only the street in address_1. "
    "PHONE NUMBERS. The driver's Home phone is printed 'H ( area code ) number'. Return the digits inside "
    "the parentheses as phone_area and the number after them as phone (for example phone_area '516', phone "
    "'530-0635'). Never drop the area code. Do the same for the witness and property-owner Phone No. lines. "
    "Ignore the work phone (W). "

    "PERSON TABLE (rows A-H at the bottom of page 1; the column numbers 21 to 32 are printed above it). Return one "
    "occupant per row that has ANY entry: row letter; vehicle = column 21; person_type = column 22; name and "
    "address from the 'Names and Addresses' area of that row; dob = the date printed at the left of that row's name "
    "line, if any; protection = column 27; airbag = column 28; ejection = column 31; injury = column 32. Do not "
    "return empty rows. The text 'Veh# n Towed To/By:' beside the rows belongs to unit n: return it as that unit's "
    "vehicle.towed_by. Under each unit column, '46 Name of EMS' and '47 Injured Taken by EMS to' are separate boxes: "
    "return the 47 text as that unit's ems_taken exactly as printed, INCLUDING a leading row letter such as "
    "'A - Mission Hospital' or 'A,C,D - REFUSED'. "

    "PAGE 2. Per-unit columns: box 59 Vehicle Defects and box 60 Authorized Speed Limit for each unit "
    "(vehicle.defects, vehicle.speed_limit). Under the diagram, 'Unit# n was: [ ] Traveling [ ] Parked Facing' - set "
    "parked for that unit only if the Parked box is marked. Property damage (box 86): property_owners with the "
    "owner name only in name, the property type (FENCE, HOUSE...) in description, then address and phone separately; "
    "return nothing if only a state-property box is ticked. Witnesses: name, address, phone. 'Traffic violation(s)': "
    "one charge per printed line with the person's name in name and the text in charge. "

    "MARGIN BOXES. Boxes sit along the left and right edges of page 1 and page 2. Each has a SMALL printed box "
    "number in its corner and a LARGER handwritten or typed value inside. For EVERY margin box that has a value, "
    "return the small box number as box and the value as value in margin_boxes (for example box '3' value '1'). "
    "Do not decide what the boxes mean and do not confuse the number with the value. "

    "Put anything ambiguous in warnings instead of guessing. "
    + KEY_WHAT_YOU_SEE
)


# ------------------------------------------------------------------ plumbing
def _image(page, dpi: int = 180) -> str:
    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
    return "data:image/jpeg;base64," + base64.b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode("ascii")


def _extract_images(images: list[str], prompt: str, model: str, schema=NCFormExtraction):
    content = []
    for n, url in enumerate(images, start=1):
        content.append({"type": "input_text", "text": f"PAGE {n}:"})
        content.append({"type": "input_image", "image_url": url, "detail": "high"})
    from app.ai.runtime import get_ai_client
    return get_ai_client().parse(model=model, instructions=prompt, content=content, schema=schema,
                                 reasoning_effort="none")


def _margin_dict(boxes) -> dict[str, str]:
    out: dict[str, str] = {}
    for b in boxes or []:
        box, value = (b.box, b.value) if hasattr(b, "box") else (b.get("box"), b.get("value"))
        if box is not None and value not in (None, ""):
            out.setdefault(str(box).strip(), str(value).strip())
    return out


def _pages(indexes) -> str:
    return ", ".join(f"{2 * i + 1}-{2 * i + 2}" for i in indexes)


def select_forms(forms):
    """A form whose Supplemental Report box is ticked REPLACES the original report: key only the supplemental
    form(s) and disregard the original one(s). With no supplemental form, or when every form is supplemental,
    nothing changes. Returns (forms_to_use, note); note is None when nothing was dropped."""
    flagged = [i for i, f in enumerate(forms) if f.supplemental]
    if not flagged or len(flagged) == len(forms):
        return list(forms), None
    dropped = [i for i in range(len(forms)) if i not in flagged]
    note = (f"Supplemental Report box is ticked on pages {_pages(flagged)}: only the supplemental report is keyed; "
            f"the original report on pages {_pages(dropped)} is disregarded")
    return [forms[i] for i in flagged], note


def merge_forms(forms: list[NCFormExtraction]) -> dict:
    """Combine the per-form results into the raw dict map_nc reads. Form 1 owns the incident; each unit
    and occupant is tagged with its form index so letters A-H and margin boxes 14-19 stay per form."""
    warnings: list[str] = []
    forms, supplemental_note = select_forms(forms)
    if supplemental_note:
        warnings.append(supplemental_note)
    first = forms[0]
    raw: dict = {
        "form_rev": first.form_rev, "local_use": first.local_use, "crash_date": first.crash_date,
        "crash_time": first.crash_time, "municipality": first.municipality, "on_road": first.on_road,
        "from_road": first.from_road, "latitude": first.latitude, "longitude": first.longitude,
        "margin_boxes": _margin_dict(first.margin_boxes),
        "units": [], "occupants": [], "charges": [], "witnesses": [], "property_owners": [], "notes": [],
    }
    seen_units: dict[int, int] = {}
    for idx, f in enumerate(forms):
        warnings.extend(f.warnings)
        for key in ("local_use", "crash_date", "crash_time", "municipality", "on_road", "from_road"):
            a, b = getattr(first, key), getattr(f, key)
            if idx and b and a and a != b and not f.supplemental:
                warnings.append(f"Form {idx + 1}: {key} reads {b!r}, form 1 reads {a!r}; form 1 used")
        margin = _margin_dict(f.margin_boxes)
        for u in f.units:
            if u.number < 1:
                warnings.append("Invalid unit number skipped.")
                continue
            if u.number in seen_units:
                warnings.append(f"Unit {u.number} appears on more than one form; first reading kept")
                continue
            seen_units[u.number] = idx
            d = u.model_dump()
            d["form"], d["margin_boxes"] = idx, margin
            raw["units"].append(d)
        for o in f.occupants:
            d = o.model_dump()
            d["form"] = idx
            raw["occupants"].append(d)
        raw["charges"].extend(c.model_dump() for c in f.charges)
        raw["witnesses"].extend(w.model_dump() for w in f.witnesses)
        raw["property_owners"].extend(p.model_dump() for p in f.property_owners)
    raw["notes"] = warnings
    raw["supplemental_only"] = bool(supplemental_note)
    raw["units_involved"] = max((f.units_involved or 0 for f in forms), default=0) or None
    return raw


def check_units(raw: dict) -> None:
    """Never key a report with a unit missing: compare the printed 'No of Units Involved' with what was read."""
    expected = raw.get("units_involved")
    actual = {u["number"] for u in raw["units"]}
    if not actual:
        raise ValueError("No NC units found; nothing should be keyed.")
    if not expected:
        raw["notes"].append("'No of Units Involved' unreadable; unit count not verified")
        return
    missing = missing_units(set(range(1, int(expected) + 1)), actual)
    if missing:
        hint = (" Only the supplemental report is keyed (its box is ticked): check that the Supplemental Report "
                "box was read correctly and that the supplemental form lists every unit."
                if raw.get("supplemental_only") else "")
        raise IncompleteExtractionError(
            f"NC report lists {expected} units but unit(s) {sorted(missing)} were not extracted; filling cancelled." + hint)


def extract_nc(pdf_path: Path, model: str = "gpt-6-luna") -> dict:
    """Image PDF -> raw NC dict (see app/keying/nc_rules.py)."""
    with pymupdf.open(pdf_path) as pdf:
        count = len(pdf)
        if count < 2 or count % 2:
            raise ValueError(f"An NC DMV-349 report is made of 2-page forms; this file has {count} page(s).")
        images = [_image(pdf.load_page(i)) for i in range(count)]
    pairs = [images[i:i + 2] for i in range(0, count, 2)]
    with ThreadPoolExecutor(max_workers=min(4, len(pairs))) as pool:
        forms = list(pool.map(lambda pair: _extract_images(pair, FORM_PROMPT, model), pairs))
    raw = merge_forms(forms)
    check_units(raw)
    return raw


def extract_payload(pdf_path: Path, model: str = "gpt-6-luna") -> dict:
    """Raw extraction -> keying payload."""
    from app.keying.nc_rules import map_nc
    return map_nc(extract_nc(pdf_path, model))
