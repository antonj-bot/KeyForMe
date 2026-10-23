"""NC (DMV-349 crash report) keying rules: raw extraction -> keying payload.

Pure functions: no I/O, no AI calls, no Playwright. Everything the NC guide, the NC training
deck, the General SOP and the user's decisions say about *what* to key lives here, so it can be
unit-tested without a browser or a PDF.

Place at:  app/keying/nc_rules.py        (NJ is the reference; generic helpers come from nj_rules)

Raw input (what app/extraction/nc_extractor.py returns; values as printed)
--------------------------------------------------------------------------
{
  "form_rev": "1/2009",                  # printed under DMV-349; the year drives the 2023 injury rule
  "local_use": "260816025HA/02",         # Local Use/Patrol Area  -> Report Identifier 1
  "crash_date": "08/16/2026", "crash_time": "03:49",
  "municipality": "ROCKINGHAM",          # the name after "In / Near" -> Incident City
  "on_road": "SR 1960", "from_road": "SR 1946",
  "latitude": "34.919383", "longitude": "-79.76735",
  "margin_boxes": {"3": "1", "4": "2", "5": "", "14": "8", ...},   # printed box number -> value
  "units": [{
      "number": 1, "column": "left",     # left / right column of the form (drives margin boxes 14-16 / 17-19)
      "form": 0,                         # which 2-page form the unit is on (set by the extractor merge)
      "hit_and_run": true, "parked": false, "pedestrian": false,
      "driver": {"first": "", "middle": "", "last": "", "suffix": "", "address_1": "", "city": "",
                 "state": "", "zip": "", "phone": "", "dob": "", "dl_number": "", "dl_state": "",
                 "alcohol_suspected": "1"},                       # box 37
      "owner":  {"first": "", "middle": "", "last": "", "suffix": "", "same_as_driver": false,
                 "same_address_as_driver": false, "address_1": "", "city": "", "state": "", "zip": ""},
      "vehicle": {"plate": "", "plate_state": "", "vin": "", "year": "", "make": "", "model": "",
                  "tad": "FD-2", "insurance_company": "", "policy_number": "",
                  "towed_by": "", "defects": "0", "speed_limit": "35"},   # boxes 59 and 60 are page 2
      "ems_taken": "A - Mission Hospital"                          # box 47 text under this unit's column
  }],
  "occupants": [{"row": "A", "vehicle": "1", "person_type": "1",   # columns 21 and 22 of the table
                 "name": "", "address_line": "", "dob": "", "form": 0,
                 "protection": "0", "airbag": "2", "ejection": "1", "injury": "5"}],   # 27, 28, 31, 32
  "charges": [{"name": "LESVIN GEOVANY GONZALES PEREZ", "charge": "Y0335457-1 - DRIVING WHILE IMPAIRED"}],
  "witnesses": [{"name": "", "address_line": "", "phone": ""}],
  "property_owners": [{"name": "STEVE WATKINS", "address_line": "", "phone": ""}]
}

Output payload keys follow the NJ payload: incident / units / other_parties / notes.

Coded fields
------------
NC coded fields are single numbers as printed ("5", not "05"; "10" stays "10"): the live app lists
the injury options as "5 No Injury". Several codes in one field are joined with ";" (the separator
app/core/options.py uses). General SOP: if the keying app's description disagrees with the printed
code, match the DESCRIPTION. The code tables below carry the printed meaning so check_catalog() can
compare them with the option lists copied out of the live app, and nc_option_map() builds the
{code: "N Description"} mapping that options.map_options() expects.
"""
from __future__ import annotations

import re
from datetime import date

from app.core.driver_rules import HIT_AND_RUN_NAME
# Generic helpers shared with NJ. Move them to app/keying/common.py when a third state needs them.
from app.keying.nj_rules import (
    _address, _blank_name, _has_address, _has_name, _num, _s, blank_like,
    fix_vin, license_number, name_part, norm_date, norm_time, person_from_boxes,
    split_name, text,
)


# ----------------------------------------------------------------- Report ID
def nc_report_id(local_use: str | None) -> str:
    """Local Use/Patrol Area -> Report ID 1: keep what is before the "/", a wide space, a spaced
    hyphen or the SECOND hyphen. '260804126HA/02' -> '260804126HA'; '26-06214/Z1' -> '26-06214'."""
    s = (local_use or "").strip()
    if not s:
        return ""
    s = re.split(r"\s*/\s*", s, maxsplit=1)[0]
    s = re.split(r"\s{2,}", s, maxsplit=1)[0]
    s = re.split(r"\s+-\s+", s, maxsplit=1)[0]
    parts = s.split("-")
    if len(parts) > 2:
        s = "-".join(parts[:2])
    return s.strip()


# ----------------------------------------------------------------- street / cross street
OMIT_PREFIXES = ("CL", "I", "LCL", "MILE", "ML", "NC", "PP", "PVA", "RP", "RU", "SL", "SR", "UNK", "US")
_PREFIX_RE = re.compile(r"^\s*(?:%s)(?![A-Za-z])[\s\-\.]*" % "|".join(OMIT_PREFIXES), re.I)


def nc_clean_street(s: str | None) -> str:
    """Drop the listed route prefixes, keep the rest. 'SR 2033' -> '2033', 'I-95' -> '95',
    'SANDRA ST' stays. A bare prefix ('UNK') -> ''."""
    return _PREFIX_RE.sub("", (s or "").strip(), count=1).strip()


# ----------------------------------------------------------------- printed code meanings
WEATHER = {1: "Clear", 2: "Cloudy", 3: "Raining", 4: "Snowing", 5: "Fog, smog, smoke",
           6: "Sleet, hail, freezing rain/drizzle", 7: "Severe crosswinds",
           8: "Blowing sand, dirt, snow", 9: "Other"}
ROAD_SURFACE = {1: "Dry", 2: "Wet", 3: "Water (standing, moving)", 4: "Ice", 5: "Snow", 6: "Slush",
                7: "Sand, mud, dirt, gravel", 8: "Fuel, oil", 9: "Other", 10: "Unknown"}
PERSON_TYPE = {1: "Driver", 2: "Passenger", 3: "Pedestrian", 4: "Pedalcyclist", 5: "Non-Motorist",
               6: "Unknown", 7: "Unknown"}          # 6 = "Other": read the narrative, else Unknown
INJURY = {1: "Killed", 2: "Disabling Injury", 3: "Evident Injury", 4: "Possible Injury",
          5: "No Injury", 6: "Unknown Injury"}      # matches the option list in the live app
INJURY_SKIP_2023_FORM = {2, 3}                      # guide: 2023 form version, do not capture 2 and 3
PROTECTION = {0: "None Used", 1: "Lap Belt Only", 2: "Shoulder and Lap Belt", 3: "Shoulder Belt Only",
              4: "Child Restraint", 5: "Helmet (Motorcyclist or Non-Motorist)", 6: "Protective Pads",
              7: "Reflective Clothing", 8: "Lighting", 9: "Other", 10: "Unable to Determine"}
EJECTION = {1: "Not Ejected", 2: "Totally Ejected", 3: "Partially Ejected", 4: "Unknown"}
ALCOHOL_DRUG = {0: "No", 1: "Yes - alcohol, Impairment Suspected",
                2: "Yes - alcohol, No Impairment Suspected", 3: "Yes - Other Drugs, Impairment Suspected",
                4: "Yes - Other Drugs, No Impairment Suspected",
                5: "Yes - Alcohol and Other Drugs, Impairment Suspected",
                6: "Yes - Alcohol and Other Drugs, No Impairment Suspected", 7: "Unknown"}
VEHICLE_DEFECTS = {0: "None detected", 1: "Brakes", 2: "Headlights", 3: "Rear Lights", 4: "Steering",
                   5: "Tires", 6: "Other Defects", 7: "Unknown"}
DRIVER_CONTRIB = {
    0: "No Contributing Circumstances Indicated", 1: "Disregarded Yield Sign", 2: "Disregarded Stop Sign",
    3: "Disregarded Other Traffic Signs", 4: "Disregarded Traffic Signals", 5: "Disregarded Road Markings",
    6: "Exceeded Authorized Speed Limit", 7: "Exceeded Safe Speed for Conditions",
    8: "Failure to Reduce Speed", 9: "Improper Turn", 10: "Right Turn on Red",
    11: "Crossed Centerline/Going Wrong Way", 12: "Improper Lane change", 13: "Use of Improper Lane",
    14: "Overcorrected/Oversteered", 15: "Passed Stopped School Bus", 16: "Passed on Hill",
    17: "Passed on Curve", 18: "Other Improper Passing", 19: "Failed to Yield Right of Way",
    20: "Inattention", 21: "Improper Backing", 22: "Improper Parking", 23: "Driver Distracted",
    24: "Improper or No Signal", 25: "Followed Too Closely",
    26: "Operated Vehicle in Erratic, Reckless, Careless, Negligent or Aggressive Manner",
    27: "Swerved or Avoided Due to Wind, Slippery Surface, Vehicle, Object or Non-Motorist",
    28: "Visibility Obscured", 29: "Operated Defective Equipment", 30: "Alcohol Use", 31: "Drug Use",
    32: "Other", 33: "Unable to Determine", 34: "Unknown",
    35: "Driver Distracted by Electronic Communication Device (cell phone, texting, etc.)",
    36: "Driver Distracted by Other Electronic Device (Navigation Device, DVD Player, etc.)",
    37: "Driver Distracted by Other Inside the Vehicle",
    38: "Driver Distracted by External Distraction (Outside the Vehicle)"}
NONMOTORIST_CONTRIB = {0: "None", 1: "Coming from behind parked vehicle", 2: "Darting",
                       3: "Lying and/or illegally in the roadway", 4: "Failure to yield right of way",
                       5: "Not visible (dark clothing, etc.)", 6: "Inattentive (talking, eating, etc.)",
                       7: "Failure to obey traffic signs, signals", 8: "Wrong side of road",
                       9: "Other", 10: "Unknown"}

# Which table backs which keying-form field (names are the keys used in the payload).
CATALOGS = {
    "weather": WEATHER, "road_condition": ROAD_SURFACE, "party_type": PERSON_TYPE, "injury_code": INJURY,
    "protection": PROTECTION, "ejection": EJECTION, "alcohol_drugs": ALCOHOL_DRUG,
    "vehicle_defects": VEHICLE_DEFECTS, "driver_contributing": DRIVER_CONTRIB,
    "nonmotorist_contributing": NONMOTORIST_CONTRIB,
}
MULTISELECT = {"weather", "road_condition", "protection", "alcohol_drugs", "vehicle_defects",
               "driver_contributing", "nonmotorist_contributing"}   # rows the form marks "multiselect"; joined with ";"


def _code(raw, table: dict, *, skip: set[int] = frozenset()) -> str:
    n = _num(raw)
    if n is None or n not in table or n in skip:
        return ""
    return str(n)


def nc_codes(raw_values, table: dict, *, skip: set[int] = frozenset()) -> str:
    """One or many printed codes -> '5' or '5;7' (de-duplicated, order kept). Unknown codes dropped."""
    if isinstance(raw_values, (str, int)) or raw_values is None:
        raw_values = [raw_values]
    out: list[str] = []
    for raw in raw_values:
        if blank_like(raw):
            continue
        code = _code(raw, table, skip=skip)
        if code and code not in out:
            out.append(code)
    return ";".join(out)


def form_year(form_rev: str | None) -> int | None:
    m = re.search(r"(19|20)\d{2}", _s(form_rev))
    return int(m.group()) if m else None


def nc_injury(raw, year: int | None = None) -> str:
    return _code(raw, INJURY, skip=INJURY_SKIP_2023_FORM if year == 2023 else frozenset())


def nc_option_map(field: str) -> dict[str, str]:
    """{'5': '5 No Injury', ...} for options.map_options(field, raw, mapping): printed code -> app option text."""
    return {str(code): f"{code} {desc}" for code, desc in CATALOGS[field].items()}


def check_catalog(app_options: dict[str, list[str]]) -> list[str]:
    """Compare option lists copied from the live NC app with the printed meanings above.
    app_options: {"injury_code": ["1 Killed", "5 No Injury", ...], ...}
    Returns one line per discrepancy; General SOP: where they differ, match DESCRIPTIONS."""
    problems: list[str] = []
    norm = lambda t: re.sub(r"[^a-z0-9]+", " ", t.lower()).strip()
    for field, options in app_options.items():
        table = CATALOGS.get(field)
        if not table:
            problems.append(f"{field}: no NC table to compare against")
            continue
        seen = {}
        for opt in options:
            m = re.match(r"\s*(\d+)\s*[|\-:.]?\s*(.*)$", opt)
            if not m:
                problems.append(f"{field}: cannot read option '{opt}'")
                continue
            seen[int(m[1])] = m[2]
            if len(m[1]) > 1 and m[1].startswith("0"):
                problems.append(f"{field}: app shows a zero-padded code '{m[1]}'; NC payload codes are unpadded")
            want = table.get(int(m[1]))
            if want is None:
                problems.append(f"{field}: app has {m[1]} '{m[2]}' but the NC form has no such code")
            elif norm(want) != norm(m[2]):
                by_desc = next((c for c, d in table.items() if norm(d) == norm(m[2])), None)
                hint = f"; description matches printed code {by_desc}" if by_desc is not None else ""
                problems.append(f"{field}: app {int(m[1])} '{m[2]}' vs printed '{want}'{hint}")
        for code, desc in table.items():
            if code not in seen:
                problems.append(f"{field}: printed code {code} '{desc}' is not in the app list")
    return problems


# ----------------------------------------------------------------- Impact Location (TAD)
# TAD is "FD-2" (area letters, then severity 0-7; severity is not keyed). The mapping below is the
# user's Damage Impact Matrix (spreadsheet screenshot). ND = no damage -> blank. Several different
# areas on one vehicle (e.g. Front + Rear) -> Multiple, as the user confirmed.
IMPACT_OPTIONS = ("Front", "Right Front", "Right Side", "Right Rear", "Rear",
                  "Left Rear", "Left Side", "Left Front", "Multiple")
TAD_TO_IMPACT = {
    "FC": "Front", "FD": "Front",
    "FR": "Right Front", "RFQ": "Right Front",
    "RP": "Right Side", "RD": "Right Side",
    "RBQ": "Right Rear", "BR": "Right Rear",
    "BD": "Rear", "BC": "Rear",
    "LBQ": "Left Rear", "BL": "Left Rear",
    "LP": "Left Side", "LD": "Left Side",
    "LFQ": "Left Front", "FL": "Left Front",
    "L&T": "Multiple", "R&T": "Multiple", "TOP": "Multiple", "UND": "Multiple",
    "ND": "",
}


def nc_tad_code(raw) -> str:
    s = re.sub(r"\s+", "", str(raw or "")).upper()
    code = re.split(r"[-\u2013:]", s, maxsplit=1)[0]
    return code if code in TAD_TO_IMPACT else ""


def nc_tad_tokens(tad_values) -> list[str]:
    """The TAD box can hold several codes ('FC-2,FD-3'): one token per code."""
    if tad_values is None or isinstance(tad_values, str):
        tad_values = [tad_values]
    return [t for v in tad_values for t in re.split(r"[,;/\s]+", str(v or "")) if t]


def nc_impact_location(tad_values) -> str:
    """One TAD -> its option; several (in one box or as a list): the same option -> that option, different
    options -> Multiple, so Front + Rear is Multiple."""
    opts = {TAD_TO_IMPACT[c] for c in (nc_tad_code(t) for t in nc_tad_tokens(tad_values)) if c}
    opts.discard("")
    if not opts:
        return ""
    return opts.pop() if len(opts) == 1 else "Multiple"


# ----------------------------------------------------------------- vehicle towed / airbag
_TOW_YES = re.compile(r"owner called|self tow|private tow|personal request|\bpolice\b|towing|tow company|"
                      r"\bcompany\b|rotation|wrecker|\bother\b")
_TOW_NO = re.compile(r"driven from scene|driven to destination|destination|called their own|handled|"
                     r"owners? request|owner's request|not towed|stayed on scene|left at scene|"
                     r"\bdriver\b|\bowner\b|\bself\b")


def nc_towed_basis(towed_by: str | None) -> tuple[str, str]:
    """(value, basis). Value is 'YES' / 'NO' / '' (N/A). Basis is 'table' when the text is a row of the
    towing classification table, 'assumed' when it is not: a bare company name is a tow company (YES, the
    user's rule); 'stayed on scene' is not a tow (NO). YES rows are checked first because 'OWNER CALLED'
    (YES) contains 'OWNER' (NO):
      YES: Self Tow, Police, Towing Company, Personal Request, Owner Called, Private Tow, Other, Company
      NO:  Driver, Owner, Self, Owner's Request, Not Towed, Destination-on-way, Driven From Scene,
           Called Their Own, Handled/Driver, Driven To Destination"""
    s = " ".join((towed_by or "").lower().replace("\u2019", "'").split())
    if blank_like(s.strip(" ,./;-")):
        return "", "table"
    if _TOW_YES.search(s):
        return "YES", "table"
    if re.search(r"stayed on scene|left at scene", s):
        return "NO", "assumed"
    if _TOW_NO.search(s):
        return "NO", "table"
    return "YES", "assumed"


def nc_towed(towed_by: str | None) -> str:
    return nc_towed_basis(towed_by)[0]


def nc_airbag(codes) -> str:
    """Column 28 per occupant: 2, 3, 4 deployed -> YES; 1 not deployed -> NO; 0, 5, blank -> N/A ('').
    If ANY occupant (driver or passenger) of the vehicle has a deployed code the vehicle is YES."""
    nums = [n for n in (_num(c) for c in codes) if n is not None]
    if any(n in (2, 3, 4) for n in nums):
        return "YES"
    if any(n == 1 for n in nums):
        return "NO"
    return ""


# ----------------------------------------------------------------- box 47: injured taken by EMS to
_EMS = re.compile(r"^\s*([A-H](?:\s*[,&/\-]\s*[A-H])*)\s*[-\u2013:]\s*(.+)$", re.I)


def nc_has_destination(ems_text: str | None) -> bool:
    """A real box-47 value. Blank and N/A are not values (General SOP null words)."""
    return not blank_like(_s(ems_text).strip(" ,.;-"))


def nc_ems_letters(ems_field: str | None) -> tuple[list[str], str]:
    """'A,C,D - REFUSED' -> (['A','C','D'], 'REFUSED'). No letter indicator -> ([], text)."""
    t = " ".join(_s(ems_field).split())
    m = _EMS.match(t)
    if not m:
        return [], t
    return re.findall(r"[A-H]", m[1].upper()), m[2].strip()


# ----------------------------------------------------------------- redaction / dob
def nc_is_redacted(s: str | None) -> bool:
    """A series of X means redacted: disregard (training deck). A whole box of X / punctuation
    ('XX', 'XX/XX'), a run of four or more X, or a XX/XX/ date. A plate like XXA169 is NOT redacted."""
    t = _s(s).upper()
    return bool(t) and bool(re.fullmatch(r"[X\W_]+", t) and "X" in t or re.search(r"X{4,}", t)
                            or re.search(r"\bXX[/-]XX\b", t))


def _scrub(obj):
    """The system that prints the report writes the literal word null into empty boxes, and redacted
    boxes are a series of X: both are blank."""
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    if isinstance(obj, str) and (obj.strip().lower() == "null" or nc_is_redacted(obj)):
        return ""
    return obj


def nc_text(value) -> str:
    """Non-name text: nulls and redactions are not keyable."""
    return "" if nc_is_redacted(_s(value)) or _s(value).lower() == "null" else text(value)


def nc_dob(value) -> str:
    """MM/DD/YYYY only; partial or redacted dates (XX/XX/1985) are blank."""
    return "" if nc_is_redacted(_s(value)) else norm_date(value)



# ----------------------------------------------------------------- phone numbers
def nc_phone(number, area=None) -> str:
    """Home phone as printed, area code first: '516 530-0635'.
    The report prints 'H ( 516 ) 530-0635'. The extractor returns the part in the parentheses as `area` and the
    rest as `number`; a complete number in `number` (any common format) is accepted too. Only 7 digits and no
    area code -> '530-0635'. Anything that is not a plain 7/10-digit phone (an extension...) is kept as printed.
    Redacted or null -> ''."""
    n, a = nc_text(number), nc_text(area)
    if not n:
        return ""
    digits = re.sub(r"\D", "", n)
    if len(digits) == 11 and digits.startswith("1"):
        digits = digits[1:]
    if len(digits) == 10:
        return f"{digits[:3]} {digits[3:6]}-{digits[6:]}"
    if len(digits) == 7:
        code = re.sub(r"\D", "", a)
        if len(code) == 3:
            return f"{code} {digits[:3]}-{digits[3:]}"
        return f"{digits[:3]}-{digits[3:]}"
    return n


def _phone(who: str, src: dict, notes: list[str]) -> str:
    value = nc_phone(src.get("phone"), src.get("phone_area"))
    if re.fullmatch(r"\d{3}-\d{4}", value):
        notes.append(f"{who}: phone '{value}' has no area code on the report")
    return value


# ----------------------------------------------------------------- address line 2 (apartment / unit)
_UNIT_WORDS = r"(?:APT|APARTMENT|UNIT|STE|SUITE|SPC|SPACE|LOT|RM|ROOM|FL|FLOOR|BLDG|BUILDING|TRLR|TRAILER)"
_UNIT_ID = r"(?:[A-Z]|[A-Z]{0,2}-?\d[A-Z0-9-]*)"       # one letter, or anything holding a digit: B, 4C, 2022B
_NC_UNIT_RE = re.compile(
    rf"^(?P<a1>.*?\S)\s*[,\s]\s*(?P<a2>(?:{_UNIT_WORDS}\b\.?[\s,#]*{_UNIT_ID}|#\s*{_UNIT_ID}))\s*$", re.I)


def nc_split_unit(address_1) -> tuple[str, str]:
    """'2008 S MEBANE ST, APT,2022B' -> ('2008 S MEBANE ST', 'APT,2022B'). The unit part is kept exactly as printed.
    The shared splitter misses 'APT,2022B' (a comma straight after APT). A street that merely contains a unit word
    ('12 LOT ST', '100 PARK FL') and a state-and-zip tail ('FL 33101') are left alone."""
    t = _s(address_1)
    m = _NC_UNIT_RE.match(t)
    if not m:
        return t, ""
    a1, a2 = m.group("a1").rstrip(" ,"), m.group("a2")
    if not re.search(r"[A-Za-z0-9]", a1) or re.fullmatch(r"(?i)(?:FL|FLOOR)[\s,.#]*\d{5}(?:-\d{4})?", a2):
        return t, ""
    return a1, a2


def _nc_address(src, who, notes) -> dict:
    """The shared address helper, then the NC unit rule: apartment / unit text goes in Address 2.
    An Address 2 that is already filled is never touched."""
    a = _address(src, who, notes)
    if a["address_1"] and not a["address_2"]:
        a1, a2 = nc_split_unit(a["address_1"])
        if a2:
            a["address_1"], a["address_2"] = a1, a2
    return a


# ----------------------------------------------------------------- names / charges
def _full_name(n: dict) -> str:
    return " ".join(x for x in (n.get("first_name"), n.get("middle_name"), n.get("last_name"), n.get("suffix")) if x)


def nc_names_match(a: str, b: str) -> bool:
    """Charges rule: names must be identical (case/space-insensitive). A missing middle name is a mismatch."""
    n = lambda x: re.sub(r"[^A-Z0-9 ]", "", re.sub(r"\s+", " ", (x or "").strip().upper()))
    return bool(n(a)) and n(a) == n(b)


def nc_route_charge(charge_name: str, driver_name: str, owner_name: str) -> str:
    """'driver' | 'other_unknown' | 'disregard' (Charge(s) rule in the guide)."""
    if nc_names_match(charge_name, driver_name):
        return "driver"
    if nc_names_match(charge_name, owner_name):
        return "other_unknown"
    return "disregard"


# ----------------------------------------------------------------- the mapper
def _coded(label: str, raw, fn, notes: list[str]) -> str:
    value = fn(raw)
    if not value and not blank_like(raw) and _num(raw) is not None:
        notes.append(f"{label}: code '{_s(raw)}' is not in the NC list (or is skipped for this form version); left blank")
    return value


def _margin(margin: dict, box) -> str:
    return _s((margin or {}).get(str(box)))


def _unit_side_boxes(column: str, kind: str) -> list[int]:
    if kind == "driver":
        return [14, 15, 16] if column != "right" else [17, 18, 19]
    return [8] if column != "right" else [9]      # non-motorist; the 06/2023 form adds 10-11, see extractor notes


def map_nc(raw: dict, *, today: date | None = None) -> dict:
    """Raw DMV-349 extraction -> keying payload (see the module docstring)."""
    today = today or date.today()
    raw = _scrub(raw)
    notes: list[str] = list(raw.get("notes") or [])
    year = form_year(raw.get("form_rev"))
    margin = raw.get("margin_boxes") or {}
    units_raw = sorted(raw.get("units") or [], key=lambda u: _num(u.get("number")) or 0)
    occupants = list(raw.get("occupants") or [])
    crash_date = norm_date(raw.get("crash_date"), today=today)

    incident = {
        "report_identifier_1": nc_report_id(raw.get("local_use")),
        "report_identifier_2": "",
        "incident_date": crash_date,
        "time_2400": norm_time(raw.get("crash_time")),
        "incident_state": "NC",
        "incident_city": text(raw.get("municipality")),
        "incident_street": nc_clean_street(raw.get("on_road")),
        "incident_cross_street": nc_clean_street(raw.get("from_road")),
        "latitude": text(raw.get("latitude")),
        "longitude": text(raw.get("longitude")),
        "weather": nc_codes([_margin(margin, 4), _margin(margin, 5)], WEATHER),       # boxes 4 and 5
        "road_condition": nc_codes([_margin(margin, 3)], ROAD_SURFACE),               # box 3
        "hit_and_run": "1" if any(u.get("hit_and_run") for u in units_raw) else "",
    }

    # ---- occupant rows: tag each with its unit so the rows can be used by units and other parties
    rows = []
    for i, o in enumerate(occupants):
        rows.append({**o, "_i": i, "_veh": _num(o.get("vehicle")), "_ptype": _num(o.get("person_type")),
                     "_letter": _s(o.get("row")).upper()[:1], "_form": _num(o.get("form")) or 0})
    used: set[int] = set()

    # ---- box 47 (Injured Taken by EMS to). One box sits under each unit column, per form.
    #  * "A - Mission Hospital": the letter is the person-table row (column 21 = vehicle, 22 = type), so
    #    the text belongs to that row's person, e.g. A = unit 1 driver, C = unit 1 passenger.
    #  * Without a letter: exactly ONE such value on the form -> the one injured person (injury 1-4);
    #    TWO such values -> all left blank. Blank and N/A are not values.
    ems_by_row: dict[int, str] = {}
    forms_seen = sorted({_num(u.get("form")) or 0 for u in units_raw})
    for f in forms_seen:
        plain: list[tuple[int, str]] = []
        for u in (x for x in units_raw if (_num(x.get("form")) or 0) == f):
            letters, ems_text = nc_ems_letters(u.get("ems_taken"))
            if not nc_has_destination(ems_text):
                continue
            if letters:
                hit = [r for r in rows if r["_form"] == f and r["_letter"] in letters]
                if not hit:
                    notes.append(f"Unit {_num(u.get('number'))}: box 47 '{_s(u.get('ems_taken'))}' names row "
                                 f"{','.join(letters)} but no such person row was read; disregarded")
                for r in hit:
                    ems_by_row[r["_i"]] = ems_text
            else:
                plain.append((_num(u.get("number")), ems_text))
        if len(plain) >= 2:
            notes.append("Box 47 has a destination in both fields and neither names a person row; "
                         "all 'Injured Taken by EMS to' fields left blank")
        elif plain:
            injured = [r for r in rows if r["_form"] == f and _num(r.get("injury")) in (1, 2, 3, 4)]
            if len(injured) == 1:
                ems_by_row[injured[0]["_i"]] = plain[0][1]
            else:
                notes.append(f"Box 47 '{plain[0][1]}' has no row letter and the injured person cannot be "
                             f"identified ({len(injured)} injured); disregarded")

    charges_in = [c for c in (raw.get("charges") or []) if text(c.get("charge"))]
    charge_used = [False] * len(charges_in)

    def charges_for(name: str) -> list[str]:
        out = []
        for k, c in enumerate(charges_in):
            if nc_names_match(c.get("name"), name):
                out.append(text(c.get("charge")))
                charge_used[k] = True
        return out

    units, other_parties = [], []
    by_number: dict[int, dict] = {}
    for u in units_raw:
        n = _num(u.get("number")) or (len(units) + 1)
        label = f"Unit {n}"
        d, ow, veh = u.get("driver") or {}, u.get("owner") or {}, u.get("vehicle") or {}
        umargin = u.get("margin_boxes") or margin               # margin boxes of the form this unit is on
        urows = [r for r in rows if r["_veh"] == n]
        drv_row = next((r for r in urows if r["_ptype"] == 1), None)
        if drv_row:
            used.add(drv_row["_i"])

        dn = person_from_boxes(d.get("first"), d.get("middle"), d.get("last"))
        if not dn["suffix"]:
            dn["suffix"] = name_part(d.get("suffix"))
        if nc_is_redacted(_full_name(dn)):
            dn = _blank_name()
        hit_run, parked = bool(u.get("hit_and_run")), bool(u.get("parked"))
        printed_driver = _has_name(dn)
        engine_hit_and_run = hit_run
        if not printed_driver:
            if hit_run and parked:
                engine_hit_and_run = False
                notes.append(f"{label}: marked both Parked and Hit & Run with no driver name; "
                             "driver last name left blank, key it by hand")
            elif hit_run:
                dn["last_name"] = HIT_AND_RUN_NAME
            elif parked:
                dn["last_name"] = "PARKED"

        if u.get("pedestrian"):
            # Header box PEDESTRIAN: no vehicle tab, the person is an Other Party (Pedestrian/Pedalcyclist).
            drv_row = drv_row or (urows[0] if urows else None)
            if drv_row:
                used.add(drv_row["_i"])
            ptype = PERSON_TYPE.get(drv_row["_ptype"] if drv_row else 3, "Pedestrian")
            if ptype not in ("Pedestrian", "Pedalcyclist", "Non-Motorist"):
                ptype = "Pedestrian"
            other_parties.append({
                # party_number stays blank: the shared engine keys it into Vehicle #, and a pedestrian has none
                "role": ptype.upper(), "party_number": "", "person_type": ptype, **dn,
                **_nc_address(d, f"{label} pedestrian", notes), "vehicle_number": "",
                "date_of_birth": nc_dob(d.get("dob")),
                "drivers_license": license_number(d.get("dl_number")),
                "drivers_license_state": text(d.get("dl_state")).upper(),
                "injury_code": nc_injury(drv_row.get("injury"), year) if drv_row else "",
                "alcohol_drugs": nc_codes([d.get("alcohol_suspected")], ALCOHOL_DRUG),
                "protection": nc_codes([drv_row.get("protection")], PROTECTION) if drv_row else "",
                "ejection": nc_codes([drv_row.get("ejection")], EJECTION) if drv_row else "",
                "nonmotorist_actions": nc_codes([_margin(umargin, b) for b in _unit_side_boxes(u.get("column", "left"), "non")],
                                                NONMOTORIST_CONTRIB),
                "ems_to": nc_text(ems_by_row.get(drv_row["_i"])) if drv_row else "",
                "charge": "", "extra_charges": [], "same_as_driver_address": False, "same_as_owner_address": False,
            })
            notes.append(f"{label}: PEDESTRIAN box ticked; keyed as an Other Party with no vehicle tab, "
                         "check the unit numbering")
            continue

        ch = charges_for(_full_name(dn)) if printed_driver else []
        driver = {
            **dn, **_nc_address(d, f"{label} driver", notes),
            "phone": _phone(f"{label} driver", d, notes),
            "date_of_birth": nc_dob(d.get("dob")),
            "drivers_license": license_number(d.get("dl_number")),
            "drivers_license_state": text(d.get("dl_state")).upper(),
            "injury_code": nc_injury(drv_row.get("injury"), year) if drv_row else "",
            "alcohol_drugs": nc_codes([d.get("alcohol_suspected")], ALCOHOL_DRUG),
            "charge": ch[0] if ch else "", "extra_charges": ch[1:],
            "contributing": nc_codes([_margin(umargin, b) for b in _unit_side_boxes(u.get("column", "left"), "driver")],
                                     DRIVER_CONTRIB),
            "protection": nc_codes([drv_row.get("protection")], PROTECTION) if drv_row else "",
            "ejection": nc_codes([drv_row.get("ejection")], EJECTION) if drv_row else "",
            "ems_to": nc_text(ems_by_row.get(drv_row["_i"])) if drv_row else "",
        }
        for r in ([drv_row] if drv_row else []):
            for fld, tbl, nm in (("injury", INJURY, "injury"), ("protection", PROTECTION, "protection"),
                                 ("ejection", EJECTION, "ejection")):
                _coded(f"{label} {nm}", r.get(fld), lambda x, t=tbl: _code(x, t), notes)

        # owner: key what is printed; blank + "Same as Driver?" ticked -> the driver's name (guide)
        printed_owner = person_from_boxes(ow.get("first"), ow.get("middle"), ow.get("last"), company_check=True)
        if not printed_owner["suffix"]:
            printed_owner["suffix"] = name_part(ow.get("suffix"))
        if nc_is_redacted(_full_name(printed_owner)):
            printed_owner = _blank_name()
        if not _has_name(printed_owner) and ow.get("same_as_driver"):
            on = {"first_name": dn["first_name"], "middle_name": dn["middle_name"],
                  "last_name": dn["last_name"] if printed_driver else "", "suffix": dn["suffix"]}
            if not printed_driver:
                on["first_name"] = on["middle_name"] = ""
        else:
            on = printed_owner
        oaddr = _nc_address(ow, f"{label} owner", notes)
        daddr = _nc_address(d, f"{label} driver", notes)
        same_addr = bool(ow.get("same_address_as_driver")) and not _has_address(oaddr) and _has_address(daddr)
        owner = {**on, **oaddr, "same_as_driver_address": same_addr}

        codes = [r.get("airbag") for r in urows]
        towed, tow_basis = nc_towed_basis(veh.get("towed_by"))
        if tow_basis == "assumed":
            notes.append(f"{label}: 'Towed By' reads '{_s(veh.get('towed_by'))}', not a row of the towing table; "
                         f"keyed {towed} (a bare company name is a tow company)")
        vehicle = {
            "vin": fix_vin(veh.get("vin")), "year": text(veh.get("year")), "make": text(veh.get("make")),
            "model": text(veh.get("model")),
            "tag_number": text(veh.get("plate")), "tag_state": text(veh.get("plate_state")).upper(),
            "insurance_carrier": text(veh.get("insurance_company")),
            "policy_number": text(veh.get("policy_number")),
            "vehicle_towed": towed, "airbag_deployed": nc_airbag(codes),
            "impact_location": nc_impact_location(veh.get("tad")),
            "vehicle_defects": nc_codes([veh.get("defects")], VEHICLE_DEFECTS),
            "speed_limit": re.sub(r"\D", "", _s(veh.get("speed_limit"))),     # the field accepts numbers only
        }
        if vehicle["vin"] and len(vehicle["vin"]) != 17:
            notes.append(f"{label}: VIN has {len(vehicle['vin'])} characters; keyed as printed, review")
        if not blank_like(veh.get("tad")) and not any(nc_tad_code(t) for t in nc_tad_tokens(veh.get("tad"))):
            notes.append(f"{label}: TAD '{_s(veh.get('tad'))}' is not in the impact matrix; Impact Location left blank")
        units.append({"party_number": n, "hit_and_run": engine_hit_and_run, "parked": parked,
                      "owner": owner, "driver": driver, "vehicle": vehicle})
        by_number[n] = units[-1]

    # ---- other parties: passengers / pedestrians / pedalcyclists / unknown
    for r in rows:
        if r["_i"] in used or r["_veh"] is None and blank_like(r.get("name")):
            continue
        if blank_like(r.get("name")) and blank_like(r.get("address_line")):
            continue
        name = split_name(r.get("name"), r.get("company"))
        ptype = PERSON_TYPE.get(r["_ptype"] or 0)
        if r["_ptype"] == 1 and r["_veh"] in by_number:          # a second "driver" row for the same unit
            ptype = "Unknown"
            notes.append(f"Row {r['_letter']}: second driver row for unit {r['_veh']}; keyed as Unknown")
        if ptype is None:
            ptype = "Unknown"
            notes.append(f"Row {r['_letter']}: person type '{_s(r.get('person_type'))}' missing; keyed as Unknown")
        addr = _nc_address(r, f"Row {r['_letter']}", notes)
        unit = by_number.get(r["_veh"]) if r["_veh"] else None
        same_driver = same_owner = False
        if unit and not _has_address(addr):
            if _has_address(unit["driver"]):
                same_driver = True
            elif _has_address(unit["owner"]):
                same_owner = True
        ch = charges_for(_full_name(name)) if _has_name(name) else []
        other_parties.append({
            "role": ptype.upper(), "party_number": str(r["_veh"] or ""), "person_type": ptype, **name, **addr,
            "vehicle_number": str(r["_veh"] or ""), "date_of_birth": nc_dob(r.get("dob")),
            "drivers_license": "", "drivers_license_state": "",
            "injury_code": nc_injury(r.get("injury"), year),
            "alcohol_drugs": "",
            "protection": nc_codes([r.get("protection")], PROTECTION),
            "ejection": nc_codes([r.get("ejection")], EJECTION),
            "nonmotorist_actions": "",
            "ems_to": nc_text(ems_by_row.get(r["_i"])),
            "charge": ch[0] if ch else "", "extra_charges": ch[1:],
            "same_as_driver_address": same_driver, "same_as_owner_address": same_owner,
        })

    # ---- charges whose name matched nobody on the driver / passenger side
    owners = {n: _full_name(u["owner"]) for n, u in by_number.items()}
    for k, c in enumerate(charges_in):
        if charge_used[k]:
            continue
        route = "disregard"
        for n, u in by_number.items():
            if nc_route_charge(c.get("name"), _full_name(u["driver"]), owners[n]) == "other_unknown":
                route = "other_unknown"
        if route == "other_unknown":
            nm = split_name(c.get("name"))
            other_parties.append({
                "role": "UNKNOWN", "party_number": "", "person_type": "Unknown", **nm, **_nc_address({}, "", []),
                "vehicle_number": "", "date_of_birth": "", "drivers_license": "", "drivers_license_state": "",
                "injury_code": "", "alcohol_drugs": "", "protection": "", "ejection": "",
                "nonmotorist_actions": "", "ems_to": "", "charge": text(c.get("charge")), "extra_charges": [],
                "same_as_driver_address": False, "same_as_owner_address": False,
            })
            notes.append(f"Charge for '{_s(c.get('name'))}' matches the vehicle owner, not the driver: "
                         "added as Other Party Unknown with name and charge only")
        else:
            notes.append(f"Charge '{text(c.get('charge'))}' for '{_s(c.get('name'))}' does not match any "
                         "listed person exactly; disregarded")

    # ---- property owners and witnesses (name + address + phone)
    for key, role, label in (("property_owners", "PROPERTY OWNER", "Property Owner"),
                             ("witnesses", "WITNESS", "Witness")):
        for p in raw.get(key) or []:
            nm_text = _s(p.get("name"))
            name = split_name(nm_text, p.get("is_company")) if nm_text else _blank_name()
            addr = _nc_address(p, label, notes)
            if not _has_name(name) and not _has_address(addr):
                notes.append(f"{label} listed with no name or address; not keyed")
                continue
            other_parties.append({
                "role": role, "party_number": "", "person_type": label, **name, **addr,
                "phone": _phone(label, p, notes), "vehicle_number": "", "date_of_birth": "",
                "drivers_license": "", "drivers_license_state": "", "injury_code": "", "alcohol_drugs": "",
                "protection": "", "ejection": "", "nonmotorist_actions": "", "ems_to": "",
                "charge": "", "extra_charges": [],
                "same_as_driver_address": False, "same_as_owner_address": False,
            })

    return {"incident": incident, "units": units, "other_parties": other_parties, "notes": notes}
