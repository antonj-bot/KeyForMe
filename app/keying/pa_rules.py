"""PA (Pennsylvania Police Crash Report, AA-500 family) keying rules: raw extraction -> keying payload.

Pure functions: no I/O, no AI calls, no Playwright. Everything the PA training deck, the PA mapping
guide and the live-app dropdown screenshot say about *what* to key lives here, so it can be unit-tested
without a browser or a PDF.  NC (app/keying/nc_rules.py) is the reference; generic helpers come from nj_rules.

Place at:  app/keying/pa_rules.py

Raw input (what app/extraction/pa_extractor.py returns; values as printed)
--------------------------------------------------------------------------
{
  "incident_number": "43-26-05679",      # "Incident Number"                       -> Report ID 1
  "report_number": "W1074304",           # "Report Number"                         -> Report ID 2 (only when printed)
  "cad_case_number": "",                 # "CAD/CASE Number" -> BOTH Report ID 1 and 2 (training slide "1/2")
  "investigation_date": "07/23/2026",    # only used to recover a missing year on the crash date
  "crash_date": "07/19/2026", "crash_time": "09:30",
  "municipality": "PHILADELPHIA CITY",
  "house_number": "", "street_name": "ROOSEVELT", "street_ending": "BOULEVARD", "route_number": "",
  "cross_street_name": "GRANT", "cross_street_ending": "", "not_in_intersection": "",
  "latitude": "40:04:53.610", "longitude": "-75:01:42.170",
  "weather": [{"code": "", "text": "CLOUDY"}],            # "Weather Conditions 1" and "2"
  "road_surface": [{"code": "", "text": "DRY"}],
  "speed_limit": "30 MPH",
  "hit_and_run_crash": false,            # report-level "Hit and Run" crash-involves box
  "units": [{
      "number": 1, "unit_type": "", "hit_and_run": false,   # hit_and_run: ONLY when the report ties it to THIS unit
      "owner_is_driver": false,                             # the "Owner/Driver" box on the driver row
      "driver": {"first": "", "middle": "", "last": "", "suffix": "", "address_1": "", "city": "", "state": "",
                 "zip": "", "phone": "", "dob": "", "dl_number": "", "dl_state": "",
                 "alcohol_drugs": [{"code": "", "text": ""}], "driver_actions": [{"code": "", "text": ""}],
                 "helmet": [{"code": "", "text": ""}],
                 "violations": [{"text": "", "charged": "", "primary": false}]},
      "owner":  {"first": "", "middle": "", "last": "", "suffix": "", "address_1": "", "city": "", "state": "",
                 "zip": "", "phone": ""},
      "vehicle": {"plate": "", "plate_state": "", "vin": "", "year": "", "make": "", "model": "",
                  "insurance_company": "", "policy_number": "", "policy_expiration": "",
                  "towed": "", "towed_by": "", "impact_point": [""],
                  "vehicle_failures": [{"code": "", "text": ""}]},
      "passenger_helmet": [{"code": "", "text": ""}],
      "trailers": [{"plate": "", "plate_state": "", "vin": "", "year": "", "make": ""}]
  }],
  "occupants": [{"unit": "1", "person_no": "1", "person_type": {"code": "", "text": "DRIVER"},
                 "first": "", ..., "phone": "", "dob": "",
                 "injury": [...], "safety_equipment": [...], "helmet": [...], "ejection": [...],
                 "pedestrian_actions": [...], "airbag": "", "medical_facility": "",
                 "violations": [...]}],
  "witnesses": [{"first": "", "middle": "", "last": "", "suffix": "", "address_1": "", "city": "", "state": "",
                 "zip": "", "phone": ""}],
  "property_owners": [ ...same shape... ]
}

Coded fields
------------
A coded value is {"code": "<as printed>", "text": "<as printed>"} (either may be empty). Rules (user decisions):
  1. If the printed NUMBER exists in the live PA dropdown, key that number (PREFER_NUMBER = True).
     "5" for a "05 ..." option keys "05": codes are compared as integers, the dropdown's spelling is keyed.
  2. Otherwise match the printed DESCRIPTION to a dropdown description.
  3. Otherwise leave the field blank and add a warning - never guess.
  Where the number wins but the printed description clearly disagrees with the dropdown, a warning is added.
Several codes in one field are joined with ";" (the separator app/core/options.py uses).
"""
from __future__ import annotations

import re
from datetime import date

from app.core.driver_rules import HIT_AND_RUN_NAME
from app.keying.nj_rules import (
    _address, _blank_name, _has_address, _has_name, _num, _s, blank_like, fix_vin, license_number,
    name_part, norm_date, norm_time, person_from_boxes, split_name, text,
)

# ----------------------------------------------------------------- switches
PREFER_NUMBER = True                    # False = description wins (old General SOP behaviour)
COPY_DRIVER_WHEN_OWNER_BLANK = False    # True = a plain empty owner also copies the driver (see _owner)

# ----------------------------------------------------------------- live-app dropdown catalogs
# Copied from the UAT dropdown screenshot (PA keying form). code -> description, the code spelled exactly
# as the dropdown spells it ("00", "05", "1"). Alcohol/Drug has no numbers: its code IS its description.
WEATHER = {"1": "Not Adverse Conditions", "2": "Rain", "3": "Sleet(Hail)", "4": "Snow", "5": "Fog",
           "6": "Rain & Fog", "7": "Sleet & Fog", "8": "Other", "9": "Unknown"}
# The screenshot shows "1 Dry" (a duplicate); the PA SOP says code 1 is Wet. Wet is kept so a printed "WET"
# still maps; the number is what gets keyed. Re-check with check_catalog() against the live list.
ROAD_SURFACE = {"0": "Dry", "1": "Wet", "2": "Sand, Mud, Dirt, Oil", "3": "Snow Covered", "4": "Slush",
                "5": "Ice", "6": "Ice Patches", "7": "Water - Standing or Moving", "8": "Other"}
SPEED_LIMIT = {f"{n:02d}": f"{n} MPH" for n in range(5, 75, 5)}
SPEED_LIMIT.update({"90": "Not Posted", "99": "Unknown"})
INJURY = {"0": "Not Injured", "1": "Fatal Injury", "2": "Suspected Serious Injury", "3": "Suspected Minor Injury",
          "4": "Possible Injury", "5": "Died Prior to Crash", "8": "Injury, Unknown Severity",
          "9": "Unknown if Injured"}
ALCOHOL_DRUGS = {k: k for k in ("Alcohol", "Alcohol and Drugs", "Illegal Drugs", "Medication", "No", "Unknown")}
DRIVER_ACTIONS = {
    "00": "No Contributing Action", "01": "Driver Was Distracted", "02": "Driving Using Hand Held Phone",
    "03": "Driving Using Hands Free Phone", "04": "Making Illegal U-Turn", "05": "Improper/Careless Turning",
    "06": "Turning From Wrong Lane", "07": "Proceeding W/O Clearance After Stop", "08": "Running Stop Sign",
    "09": "Running Red Light", "10": "Failure To Respond To other Traffic Control Device", "11": "Tailgating",
    "12": "Sudden Slowing/Stopping", "13": "Illegally Stopped On Road", "14": "Careless Passing Or Lane Change",
    "15": "Passing In No Passing Zone", "16": "Driving The Wrong Way On 1-Way Street",
    "17": "Careless Or Illegal Backing On Roadway", "18": "Driving On The Wrong Side Of Road",
    "19": "Making Improper Entrance To Highway", "20": "Making Improper Exit From Highway",
    "21": "Careless Parking/Unparking", "22": "Over/Under Compensation At Curve", "23": "Speeding",
    "24": "Driving Too Fast For Conditions", "25": "Failure To Maintain Proper Speed",
    "26": "Driver Fleeing Police (Pol Chase)", "27": "Driver Inexperience", "28": "Failure To Use Specialized Equip",
    "31": "Texting/Typing on Eletronic Device",           # "Eletronic" is how the app spells it
    "32": "Dialing", "92": "Affected By Physical Condition", "98": "Other Improper Driving Actions",
    "99": "Unknown"}
PEDESTRIAN_ACTIONS = {
    "00": "None", "01": "Entering Or Crossing At Specified Location", "02": "Walking, Running, Jogging, or Playing",
    "03": "Working", "04": "Pushing Vehicle", "05": "Approaching Or Leaving Vehicle", "06": "Working On Vehicle",
    "07": "Standing", "98": "Other", "99": "Unknown"}
SAFETY_EQUIPMENT = {
    "00": "None Used/ Not Applicable", "01": "Shoulder Belt Used", "02": "Lap Belt Used",
    "03": "Lap and Shoulder Belt Used", "04": "Child Safety Seat Used", "05": "Motorcycle Helmet Used",
    "06": "Bicycle Helmet Used", "10": "Safety Belt Used Improperly", "11": "Child Safety Seat Used Improperly",
    "12": "Helmet Used Improperly", "21": "Child Safety Seat (Rear Facing)", "22": "Child Safety Seat (Front Facing)",
    "23": "Booster Seat", "24": "Child Restraint Unknown", "90": "Restraint Used, Type Unknown",
    "98": "Other Restraint Type", "99": "Unknown"}
HELMET = {"0": "No Helmet", "1": "Full Helmet", "2": "3/4 Helmet Style", "3": "1/2 Helmet Style", "9": "Unknown"}
# The SOP document lists 2 = Totally / 3 = Partially (older form); the live dropdown is the reverse. Live wins.
EJECTION = {"0": "Not Applicable", "1": "Not Ejected", "2": "Partially Ejected", "3": "Totally Ejected", "9": "Unknown"}
VEHICLE_FAILURES = {
    "00": "None", "01": "Tires", "02": "Brake System", "03": "Steering System", "04": "Suspension",
    "05": "Power Train", "06": "Exhaust", "07": "Headlights", "08": "Signal Lights", "09": "Other Lights",
    "10": "Horn", "11": "Mirrors", "12": "Wipers", "13": "Driver Seating/Control", "14": "Body, Doors, Hood, Etc",
    "15": "Trailer Hitch", "16": "Wheels", "17": "Airbags", "18": "Trailer Overloaded",
    "19": "Unsecured/Shifted Trailer Load", "20": "Improper Towing", "21": "Obstructed Windshield", "99": "Unknown"}

# payload field name -> catalog (the names are the keys used in the payload)
CATALOGS = {
    "weather": WEATHER, "road_condition": ROAD_SURFACE, "speed_limit": SPEED_LIMIT, "injury_code": INJURY,
    "alcohol_drugs": ALCOHOL_DRUGS, "driver_actions": DRIVER_ACTIONS, "nonmotorist_actions": PEDESTRIAN_ACTIONS,
    "protection": SAFETY_EQUIPMENT, "helmet": HELMET, "ejection": EJECTION, "vehicle_defects": VEHICLE_FAILURES,
}
# rows the form marks "multiselect"; their values are joined with ";"
MULTISELECT = {"weather", "road_condition", "alcohol_drugs", "driver_actions", "nonmotorist_actions",
               "protection", "helmet", "vehicle_defects"}
# Words that carry the same meaning as a dropdown option but are spelled differently on the printed report.
# Each use adds an informational note so the keyer can confirm it.
ALIASES = {
    "weather": {"no adverse conditions": "1", "clear": "1", "cloudy": "1"},
}


def _norm(s) -> str:
    return re.sub(r"[^a-z0-9]+", " ", _s(s).lower().replace("&", " and ")).strip()


def pa_option_map(field: str) -> dict[str, str]:
    """{'05': '05 Child Safety...'} for options.map_options(): printed code -> app option text."""
    table = CATALOGS[field]
    if field in {"alcohol_drugs"}:
        return {k: v for k, v in table.items()}
    return {k: f"{k} {v}" for k, v in table.items()}


def check_catalog(app_options: dict[str, list[str]]) -> list[str]:
    """Compare option lists copied from the live PA app with the catalogs above.
    app_options: {"injury_code": ["0 Not Injured", ...], ...}. One line per discrepancy."""
    problems: list[str] = []
    for field, options in app_options.items():
        table = CATALOGS.get(field)
        if not table:
            problems.append(f"{field}: no PA catalog to compare against")
            continue
        seen: dict[int, str] = {}
        for opt in options:
            if field == "alcohol_drugs":
                if _norm(opt) not in {_norm(k) for k in table}:
                    problems.append(f"{field}: app has '{opt}' which is not in the PA catalog")
                continue
            m = re.match(r"\s*(\d+)\s*[|\-:.]?\s*(.*)$", opt)
            if not m:
                problems.append(f"{field}: cannot read option '{opt}'")
                continue
            code_txt, desc = m[1], m[2]
            by_int = {int(k): k for k in table}
            n = int(code_txt)
            seen[n] = desc
            if n not in by_int:
                problems.append(f"{field}: app has {code_txt} '{desc}' but the PA catalog has no such code")
                continue
            if by_int[n] != code_txt:
                problems.append(f"{field}: app spells code {n} as '{code_txt}', catalog uses '{by_int[n]}'")
            if _norm(table[by_int[n]]) != _norm(desc):
                problems.append(f"{field}: app {code_txt} '{desc}' vs catalog '{table[by_int[n]]}'")
        if field != "alcohol_drugs":
            for k, desc in table.items():
                if int(k) not in seen:
                    problems.append(f"{field}: catalog code {k} '{desc}' is not in the app list")
    return problems


# ----------------------------------------------------------------- coded values
def _coded_items(raw) -> list[tuple[str, str]]:
    """Anything the extractor / a test may hand over -> [(code, description)].

    Do not use nj_rules.blank_like here: that helper deliberately treats values such as UNKNOWN as blank
    for ordinary text fields, while UNKNOWN is a valid option in several PA coded dropdowns.
    """
    if raw is None:
        return []
    if isinstance(raw, (str, int, dict)):
        raw = [raw]
    out: list[tuple[str, str]] = []
    for r in raw:
        if isinstance(r, dict):
            code, desc = _s(r.get("code")), _s(r.get("text"))
        else:
            s = _s(r)
            if re.fullmatch(r"\d{1,3}", s):
                code, desc = s, ""
            else:
                m = re.match(r"^(\d{1,3})(?:\s*[-\u2013:.)]\s*|\s+)(\S.*)$", s)   # "05 - Rain", "35 MPH"
                code, desc = (m[1], m[2]) if m else ("", s)
        # UNKNOWN is a valid PA dropdown label. N/A is only a blank placeholder for these coded fields.
        if _s(code).lower() in {"", "null", "none", "n/a", "na", "n.a.", "-", "--"}:
            code = ""
        if _s(desc).lower() in {"", "null", "none", "n/a", "na", "n.a.", "-", "--"}:
            desc = ""
        if code or desc:
            out.append((code, desc))
    return out


def _by_description(table: dict[str, str], desc: str, alias: dict[str, str] | None = None) -> tuple[str, bool]:
    """(key, used_alias). Exact normalised match first, then the single longest label contained in the text,
    then a text that is itself contained in exactly one label."""
    d = _norm(re.sub(r"^\d{1,3}\s*[-\u2013:.)]?\s+", "", desc))
    if not d:
        return "", False
    labels = {k: _norm(v) for k, v in table.items()}
    for k, v in labels.items():
        if v == d:
            return k, False
    if alias and d in alias:
        return alias[d], True
    inside = sorted(((len(v), k) for k, v in labels.items() if len(v) >= 2 and v in d), reverse=True)
    if inside and (len(inside) == 1 or inside[0][0] > inside[1][0]):
        return inside[0][1], False
    holds = [k for k, v in labels.items() if len(d) >= 3 and d in v]
    if len(holds) == 1:
        return holds[0], False
    return "", False


def _resolve(field: str, code: str, desc: str, notes: list[str], label: str) -> str:
    table = CATALOGS[field]
    by_int = {int(k): k for k in table if k.isdigit()}
    printed = f"{code} {desc}".strip()
    n = _num(code) if code else None
    if n is None and code and not by_int:                  # description-only catalog: the "code" is a word
        desc, code = desc or code, ""
    if PREFER_NUMBER and n is not None and n in by_int:
        key = by_int[n]
        if desc:
            hit, _ = _by_description(table, desc)
            if hit and hit != key:
                notes.append(f"{label}: printed '{printed}' but the app lists {key} as '{table[key]}'; keyed {key} "
                             f"(number wins) - review")
        return key
    if desc:
        hit, used_alias = _by_description(table, desc, ALIASES.get(field))
        if hit:
            if used_alias:
                notes.append(f"{label}: printed '{desc}' keyed as {hit} {table[hit]} (alias) - confirm")
            return hit
    if n is not None and n in by_int and not PREFER_NUMBER:
        return by_int[n]
    notes.append(f"{label}: printed '{printed}' is not in the PA dropdown; left blank")
    return ""


def pa_codes(raw, field: str, notes: list[str] | None = None, label: str | None = None) -> str:
    """One or many printed values -> '5' or '01;03' (de-duplicated, order kept); unmatched values are dropped
    with a warning."""
    notes = [] if notes is None else notes
    label = label or field
    keyed: list[str] = []
    for code, desc in _coded_items(raw):
        key = _resolve(field, code, desc, notes, label)
        if key and key not in keyed:
            keyed.append(key)
    if field not in MULTISELECT and len(keyed) > 1:
        notes.append(f"{label}: {len(keyed)} values printed for a single-value field; keyed {keyed[0]} only")
        keyed = keyed[:1]
    return ";".join(keyed)


# ----------------------------------------------------------------- Impact Location
IMPACT_OPTIONS = ("Front", "Front & Rear", "Left Front", "Left Rear", "Left Side", "Middle", "Multiple", "NA",
                  "Rear", "Right Front", "Right Rear", "Right Side")
CLOCK_TO_IMPACT = {1: "Right Front", 2: "Right Side", 3: "Right Side", 4: "Right Side", 5: "Right Rear",
                   6: "Rear", 7: "Left Rear", 8: "Left Side", 9: "Left Side", 10: "Left Side", 11: "Left Front",
                   12: "Front", 13: "Multiple", 14: "Multiple", 15: "Multiple", 99: ""}    # 13 top, 14 under, 15 towed unit
_WORD_IMPACT = (("towed unit", "Multiple"), ("undercarriage", "Multiple"), ("top", "Multiple"), ("unknown", ""))


def pa_impact_location(values, notes: list[str] | None = None, label: str = "Impact Location") -> str:
    """Initial Impact Point (clock number or words) -> dropdown option. One area -> that option; different areas
    -> Multiple (same convention as NC); 99 / unknown -> blank."""
    notes = [] if notes is None else notes
    if values is None or isinstance(values, (str, int)):
        values = [values]
    opts: set[str] = set()
    for v in values:
        s = _norm(v)
        if not s:
            continue
        m = re.search(r"(?<!\d)(\d{1,2})(?!\d)", s)
        if m and int(m[1]) in CLOCK_TO_IMPACT:
            opts.add(CLOCK_TO_IMPACT[int(m[1])])
            continue
        hit = next((opt for opt in IMPACT_OPTIONS if _norm(opt) == s), None)
        if hit:
            opts.add(hit)
            continue
        word = next((o for w, o in _WORD_IMPACT if w in s), None)
        if word is not None:
            opts.add(word)
            continue
        notes.append(f"{label}: printed '{_s(v)}' is not a clock position or a listed area; left blank")
    opts.discard("")
    if not opts:
        return ""
    return opts.pop() if len(opts) == 1 else "Multiple"


# ----------------------------------------------------------------- airbag / towed
def pa_airbag(values) -> str:
    """Per-person airbag entries of ONE vehicle -> YES / NO / '' (NA).
    Not Deployed -> NO; Curtain, Front, Side, 04 Other (knee, airbelt...) -> YES; 97 / N/A -> NA.
    Any deployed entry makes the vehicle YES."""
    if values is None or isinstance(values, (str, int)):
        values = [values]
    yes = no = False
    for v in values:
        s = _norm(v)
        if not s:
            continue
        n = _num(v)
        if n == 97 or s in {"na", "not applicable", "n a"}:
            continue
        if "not deployed" in s or "no deploy" in s:
            no = True
        elif n == 4 or re.search(r"curtain|front|side|knee|airbelt|air belt|other|deployed", s):
            yes = True
    return "YES" if yes else "NO" if no else ""


_TOW_NO = re.compile(r"^(no|n|0|false|not towed|driven|driven from scene)$")
_TOW_YES = re.compile(r"^(yes|y|1|true|towed)$")


def pa_towed(towed, towed_by) -> tuple[str, str]:
    """(value, basis). Value 'YES' / 'NO' / '' (NA). basis 'printed' or 'assumed'.
    A printed yes/no is used; with nothing printed in "Vehicle Towed" but a "Towed By" company named, YES is
    assumed (flagged). The SOP says this field always needs analysis, so assumed values add a warning."""
    t = _norm(towed)
    by = _s(towed_by)
    if _TOW_YES.match(t):
        return "YES", "printed"
    if _TOW_NO.match(t):
        return "NO", "printed"
    if not blank_like(by):
        return "YES", "assumed"
    return "", "printed"


# ----------------------------------------------------------------- street / coordinates / dates
def pa_street(house, name, ending, route) -> str:
    """House number + street name + st. ending; with no street name or ending, the route number."""
    if not (text(name) or text(ending)):
        return text(route)
    return " ".join(x for x in (text(house), text(name), text(ending)) if x)


def pa_cross_street(name, ending, not_in_intersection) -> str:
    """Street name + street ending; with neither, the 'If Not in Intersection' text."""
    joined = " ".join(x for x in (text(name), text(ending)) if x)
    return joined or text(not_in_intersection)


def pa_coord(value) -> str:
    """PA coordinates contain no spaces or colons; preserve minus and decimal point."""
    return re.sub(r"[^0-9.-]+", "", _s(value))


def pa_time(value) -> str:
    """PA Time (2400): '09:30', '0930', or '930' -> '0930'. Never retain the colon."""
    digits = re.sub(r"\D", "", _s(value))
    if len(digits) == 3:
        digits = "0" + digits
    if len(digits) != 4:
        return ""
    hour, minute = int(digits[:2]), int(digits[2:])
    return digits if 0 <= hour <= 23 and 0 <= minute <= 59 else ""


def _year_of(s) -> str:
    m = re.search(r"(?<!\d)((?:19|20)\d{2})(?!\d)", _s(s))
    return m[1] if m else ""


def pa_crash_date(crash_date, report_ids, investigation_date, notes: list[str], today: date | None = None) -> str:
    """MM/DD/YYYY. A crash date printed without its year ('06/06,') takes the year of the Report ID, else the
    Investigation Date (training slide 'Capture year of Report ID or from Investigation Date')."""
    s = _s(crash_date).rstrip(",. ")
    m = re.fullmatch(r"(\d{1,2})[/-](\d{1,2})", s)
    if m:
        year = next((y for y in (_year_of(i) for i in report_ids) if y), "") or _year_of(investigation_date)
        if year:
            s = f"{m[1]}/{m[2]}/{year}"
            notes.append(f"Crash date printed without a year; year {year} taken from the Report ID / Investigation Date")
        else:
            notes.append("Crash date printed without a year and no year found in the Report ID or Investigation Date")
    return norm_date(s, today=today)


# ----------------------------------------------------------------- charges
_CHARGED = {"y": "YES", "yes": "YES", "1": "YES", "true": "YES", "n": "NO", "no": "NO", "0": "NO", "false": "NO",
            "w": "WARNING", "warning": "WARNING", "warn": "WARNING"}


def pa_violations(items, label: str, notes: list[str]) -> list[dict]:
    """[{text, charged, primary}] -> [{kind, text, charged}].
    kind 'violation' = the "Violation" radio, 'primary' = the "Primary Vehicle Code Violation" radio.
    Rows with no violation text are dropped (a Charged? answer alone cannot be keyed)."""
    out: list[dict] = []
    for i, v in enumerate(items or [], 1):
        txt = text(v.get("text") if isinstance(v, dict) else v)
        if not txt:
            if isinstance(v, dict) and not blank_like(v.get("charged")):
                notes.append(f"{label}: violation row {i} has a Charged? answer but no violation text; not keyed")
            continue
        raw_charged = _norm(v.get("charged")) if isinstance(v, dict) else ""
        charged = _CHARGED.get(raw_charged, "")
        if raw_charged and not charged:
            notes.append(f"{label}: violation {i} Charged? '{_s(v.get('charged'))}' is not Yes / No / Warning; left unset")
        out.append({"kind": "primary" if isinstance(v, dict) and v.get("primary") else "violation",
                    "text": txt, "charged": charged})
    return out


# ----------------------------------------------------------------- people
_SAME_RE = re.compile(r"^\s*(same|same as (the )?(driver|operator)|owner\s*/\s*driver)\s*\.?\s*$", re.I)


def _is_same(s) -> bool:
    return bool(_SAME_RE.match(_s(s)))


def _name_boxes(p: dict, *, company_check: bool = False) -> dict:
    n = person_from_boxes(p.get("first"), p.get("middle"), p.get("last"), company_check=company_check)
    if not n.get("suffix"):
        n["suffix"] = name_part(p.get("suffix"))
    return n


def _owner(o: dict, d_name: dict, d_addr: dict, owner_is_driver: bool, label: str, notes: list[str]):
    """Owner name / address. KWYS. The driver's values are copied ONLY into owner fields that are empty, and only
    when the report says so: 'SAME AS DRIVER' typed in the owner boxes, or the Owner/Driver box ticked
    (COPY_DRIVER_WHEN_OWNER_BLANK = True also copies when the owner is plainly empty)."""
    name = _name_boxes(o, company_check=True)
    if any(_is_same(name[k]) for k in ("first_name", "middle_name", "last_name")):
        name = _blank_name()
        owner_is_driver = True
    addr = _pa_live_address({k: ("" if _is_same(v) else v) for k, v in o.items()}, label, notes)
    if any(_is_same(o.get(k)) for k in ("address_1", "address_2", "city", "state", "zip")):
        owner_is_driver = True
    copy = owner_is_driver or COPY_DRIVER_WHEN_OWNER_BLANK
    if copy and not _has_name(name) and _has_name(d_name):
        name = {k: d_name[k] for k in ("first_name", "middle_name", "last_name", "suffix")}
        notes.append(f"{label}: owner name empty; copied from the driver")
    if copy and not _has_address(addr) and _has_address(d_addr):
        addr = dict(d_addr)
        notes.append(f"{label}: owner address empty; copied from the driver")
    return name, addr


def pa_person_role(person_type, label: str, notes: list[str]) -> tuple[str, str]:
    """Printed Person Type -> (role, person_type text). Roles are the keys of pa_field_mapping.PERSON_TYPES."""
    items = _coded_items(person_type)
    s = " ".join(_norm(c) + " " + _norm(d) for c, d in items)
    if re.search(r"pedalcycl|bicycl|cyclist", s):
        return "PEDALCYCLIST", "Pedalcyclist"
    if re.search(r"non motorist|nonmotorist", s):
        return "NON-MOTORIST", "Non-Motorist"
    if "pedestrian" in s:
        return "PEDESTRIAN", "Pedestrian"
    if "passenger" in s or "occupant" in s:
        return "PASSENGER", "Passenger"
    if "driver" in s or "operator" in s:
        return "DRIVER", "Driver"
    if s.strip():
        printed = "; ".join(f"{c} {d}".strip() for c, d in items)
        notes.append(f"{label}: Person Type '{printed}' is not recognised; keyed as Unknown")
    return "UNKNOWN", "Unknown"


def _unit_kind(unit_type) -> str:
    s = _norm(unit_type)
    if re.search(r"pedalcycl|bicycl|cyclist", s):
        return "PEDALCYCLIST"
    if "pedestrian" in s:
        return "PEDESTRIAN"
    return "VEHICLE"


def _scrub(obj):
    """The report printer writes the literal word null into empty boxes: blank."""
    if isinstance(obj, dict):
        return {k: _scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_scrub(v) for v in obj]
    if isinstance(obj, str) and obj.strip().lower() == "null":
        return ""
    return obj


def pa_text(value) -> str:
    """PA KWYS text. Preserve the literal word NONE; the shared NJ text helper treats it as blank."""
    s = re.sub(r"\s+", " ", _s(value)).strip()
    return "" if s.lower() in {"", "null"} else s


def pa_dob(value) -> str:
    """MM/DD/YYYY only. Placeholder dates such as 99/99/9999 are blank."""
    s = _s(value)
    if re.fullmatch(r"[9\W_]+", s) or re.search(r"[Xx]{2}", s):
        return ""
    return norm_date(value)


# ----------------------------------------------------------------- the mapper
def _empty_other(role: str, ptype: str, **kw) -> dict:
    base = {
        "role": role, "party_number": "", "person_type": ptype, **_blank_name(),
        "address_1": "", "address_2": "", "city": "", "state": "", "zip_code": "", "phone": "",
        "vehicle_number": "", "date_of_birth": "", "drivers_license": "", "drivers_license_state": "",
        "injury_code": "", "alcohol_drugs": "", "driver_actions": "", "nonmotorist_actions": "",
        "protection": "", "helmet": "", "ejection": "", "ems_to": "", "violations": [],
    }
    base.update(kw)
    return base


# PA LIVE REPORT FIX 46888
# PA-specific presentation rules confirmed against the live PA report.
def _pa_live_time(value) -> str:
    digits = re.sub(r"\D", "", _s(value))
    if len(digits)==3: digits="0"+digits
    if len(digits)!=4: return ""
    h,m=int(digits[:2]),int(digits[2:])
    return f"{h:02d}:{m:02d}" if 0<=h<=23 and 0<=m<=59 else ""

def _pa_live_coord(value) -> str:
    return re.sub(r"[^0-9.-]+", "", _s(value))

def _pa_live_cross_street(name, ending, fallback) -> str:
    street=" ".join(x for x in (text(name),text(ending)) if x)
    other=text(fallback)
    if other and re.fullmatch(r"[0-9.\s]+",other): other=""
    return street or other

def _pa_live_phone(value) -> str:
    return re.sub(r"\s+"," ",_s(value).replace("("," ").replace(")"," ")).strip()

def _pa_live_address(src: dict, who: str, notes: list[str]) -> dict:
    a1,a2=text(src.get("address_1")),text(src.get("address_2"))
    m=re.search(r"\s+(APT|APARTMENT|UNIT|STE|SUITE)\b",a1,re.I)
    if m:
        moved=a1[m.start():].strip(); a1=a1[:m.start()].strip()
        a2=" ".join(x for x in (moved,a2) if x)
    return {"address_1":a1,"address_2":a2,"city":text(src.get("city")),
            "state":text(src.get("state")).upper(),"zip_code":text(src.get("zip"))}

def map_pa(raw: dict, *, today: date | None = None) -> dict:
    """Raw PA extraction -> keying payload {incident, units, other_parties, notes} (see the module docstring)."""
    today = today or date.today()
    raw = _scrub(raw)
    notes: list[str] = list(raw.get("notes") or [])
    units_raw = sorted(raw.get("units") or [], key=lambda u: _num(u.get("number")) or 0)
    occupants = [dict(o) for o in (raw.get("occupants") or [])]

    ids = [text(raw.get("incident_number")), text(raw.get("report_number")), text(raw.get("cad_case_number"))]
    id1 = ids[0] or ids[2]
    id2 = ids[1]                                           # explicit Report Number only
    unit_hr = [u for u in units_raw if u.get("hit_and_run")]
    incident = {
        "report_identifier_1": id1,
        "report_identifier_2": id2,
        "incident_date": pa_crash_date(raw.get("crash_date"), ids, raw.get("investigation_date"), notes, today),
        "time_2400": _pa_live_time(raw.get("crash_time")),
        "incident_state": "PA",
        "incident_city": text(raw.get("municipality")),
        "incident_street": pa_street(raw.get("house_number"), raw.get("street_name"), raw.get("street_ending"),
                                     raw.get("route_number")),
        "incident_cross_street": _pa_live_cross_street(raw.get("cross_street_name"), raw.get("cross_street_ending"),
                                                 raw.get("not_in_intersection")),
        "latitude": _pa_live_coord(raw.get("latitude")),
        "longitude": _pa_live_coord(raw.get("longitude")),
        "weather": pa_codes(raw.get("weather"), "weather", notes, "Weather Conditions"),
        "road_condition": pa_codes(raw.get("road_surface"), "road_condition", notes, "Road Surface Condition"),
        "speed_limit": pa_codes(raw.get("speed_limit"), "speed_limit", notes, "Speed Limit"),
        # crash-level box OR a unit tied to the hit-and-run; units themselves are flagged one by one below
        "hit_and_run": "1" if (raw.get("hit_and_run_crash") or unit_hr) else "",
    }
    if raw.get("hit_and_run_crash") and not unit_hr:
        notes.append("Hit & Run is ticked for the crash but no unit is tied to it; the incident box is ticked, "
                     "no unit is marked as hit and run")
    if not incident["report_identifier_1"]:
        notes.append("Report ID 1: no Incident Number or CAD/CASE Number found")

    rows = []
    for i, o in enumerate(occupants):
        role, ptype = pa_person_role(o.get("person_type"), f"Person {_s(o.get('person_no')) or i + 1}", notes)
        rows.append({**o, "_i": i, "_veh": _num(o.get("unit")), "_role": role, "_ptype": ptype})
    used: set[int] = set()

    units, other_parties = [], []
    by_number: dict[int, dict] = {}
    for u in units_raw:
        n = _num(u.get("number")) or (len(units) + 1)
        label = f"Unit {n}"
        d, ow, veh = u.get("driver") or {}, u.get("owner") or {}, u.get("vehicle") or {}
        urows = [r for r in rows if r["_veh"] == n]
        drv_row = next((r for r in urows if r["_role"] == "DRIVER"), None)
        if drv_row:
            used.add(drv_row["_i"])
        dn = _name_boxes(d)
        daddr = _pa_live_address(d, f"{label} driver", notes)
        hit_run = bool(u.get("hit_and_run"))
        if hit_run and not _has_name(dn):
            dn["last_name"] = HIT_AND_RUN_NAME
        kind = _unit_kind(u.get("unit_type"))

        def inj(row):
            return pa_codes(row.get("injury"), "injury_code", notes, f"{label} injury") if row else ""

        def prot(row):
            return pa_codes(row.get("safety_equipment"), "protection", notes, f"{label} safety equipment") if row else ""

        def ejec(row):
            return pa_codes(row.get("ejection"), "ejection", notes, f"{label} ejection") if row else ""

        def ems(row):
            return pa_text(row.get("medical_facility")) if row else ""

        if kind != "VEHICLE":      # pedestrian / pedalcyclist "unit": a person, no vehicle tab
            drv_row = drv_row or next((r for r in urows), None)
            if drv_row:
                used.add(drv_row["_i"])
            role = kind
            other_parties.append(_empty_other(
                role, "Pedestrian" if role == "PEDESTRIAN" else "Pedalcyclist", **dn, **daddr,
                phone=_pa_live_phone(d.get("phone")), date_of_birth=pa_dob(d.get("dob")),
                drivers_license=license_number(d.get("dl_number")), drivers_license_state=text(d.get("dl_state")).upper(),
                injury_code=inj(drv_row),
                alcohol_drugs=pa_codes(d.get("alcohol_drugs"), "alcohol_drugs", notes, f"{label} alcohol/drugs"),
                nonmotorist_actions=pa_codes((drv_row or {}).get("pedestrian_actions"), "nonmotorist_actions", notes,
                                             f"{label} pedestrian actions"),
                protection=prot(drv_row), helmet=pa_codes(d.get("helmet"), "helmet", notes, f"{label} helmet"),
                ejection=ejec(drv_row), ems_to=ems(drv_row),
                violations=pa_violations(d.get("violations"), label, notes)))
            notes.append(f"{label}: type '{_s(u.get('unit_type'))}' is not a motor vehicle; keyed as an Other Party "
                         "with no vehicle tab, check the unit numbering")
            continue

        owner_name, owner_addr = _owner(ow, dn, daddr, bool(u.get("owner_is_driver")), f"{label} owner", notes)
        driver = {
            **dn, **daddr, "phone": _pa_live_phone(d.get("phone")),
            "date_of_birth": pa_dob(d.get("dob")),
            "drivers_license": license_number(d.get("dl_number")),
            "drivers_license_state": text(d.get("dl_state")).upper(),
            "injury_code": inj(drv_row),
            "alcohol_drugs": pa_codes(d.get("alcohol_drugs"), "alcohol_drugs", notes, f"{label} alcohol/drugs"),
            "driver_actions": pa_codes(d.get("driver_actions"), "driver_actions", notes, f"{label} driver actions"),
            "nonmotorist_actions": pa_codes((drv_row or {}).get("pedestrian_actions"), "nonmotorist_actions", notes,
                                            f"{label} pedestrian actions"),
            "protection": prot(drv_row),
            "helmet": pa_codes(d.get("helmet"), "helmet", notes, f"{label} driver helmet"),
            "ejection": ejec(drv_row), "ems_to": ems(drv_row),
            "violations": pa_violations(d.get("violations"), f"{label} driver", notes),
        }
        owner = {**owner_name, **owner_addr, "phone": _pa_live_phone(ow.get("phone"))}
        towed, basis = pa_towed(veh.get("towed"), veh.get("towed_by"))
        if basis == "assumed":
            notes.append(f"{label}: Vehicle Towed is blank but Towed By reads '{_s(veh.get('towed_by'))}'; keyed YES - confirm")
        vehicle = {
            "vin": fix_vin(veh.get("vin")), "year": text(veh.get("year")), "make": text(veh.get("make")),
            "model": text(veh.get("model")), "tag_number": text(veh.get("plate")),
            "tag_state": text(veh.get("plate_state")).upper(),
            "insurance_carrier": text(veh.get("insurance_company")), "policy_number": text(veh.get("policy_number")),
            "policy_expiration": pa_text(veh.get("policy_expiration")),
            "vehicle_towed": towed, "airbag_deployed": pa_airbag([r.get("airbag") for r in urows]),
            "impact_location": pa_impact_location(veh.get("impact_point"), notes, f"{label} impact location"),
            "vehicle_defects": pa_codes(veh.get("vehicle_failures"), "vehicle_defects", notes,
                                        f"{label} possible vehicle failures"),
        }
        if vehicle["vin"] and len(vehicle["vin"]) != 17:
            notes.append(f"{label}: VIN has {len(vehicle['vin'])} characters; keyed as printed, review")
        trailers = []
        for t_i, t in enumerate(u.get("trailers") or [], 1):
            tr = {"tag_number": text(t.get("plate")), "tag_state": text(t.get("plate_state")).upper(),
                  "vin": fix_vin(t.get("vin")), "year": text(t.get("year")), "make": text(t.get("make"))}
            if any(tr.values()):
                trailers.append(tr)
            if text(t.get("tag_year")) and not tr["year"]:
                notes.append(f"{label}: trailer {t_i} Tag Year '{text(t.get('tag_year'))}' is a registration year; "
                             "not keyed as a vehicle year")
        units.append({"party_number": n, "hit_and_run": hit_run, "owner": owner, "driver": driver,
                      "vehicle": vehicle, "trailers": trailers})
        by_number[n] = units[-1]

        # passenger helmet (motorcycle block of the unit page) belongs to the unit's one passenger
        ph = u.get("passenger_helmet")
        if _coded_items(ph):
            pax = [r for r in urows if r["_role"] == "PASSENGER"]
            if len(pax) == 1:
                pax[0]["_helmet"] = pa_codes(ph, "helmet", notes, f"{label} passenger helmet")
            else:
                notes.append(f"{label}: passenger helmet printed but {len(pax)} passengers listed; not keyed")

    # ---- other parties: passengers / pedestrians / pedalcyclists / unknown from People Information
    for r in rows:
        if r["_i"] in used:
            continue
        if not (text(r.get("first")) or text(r.get("last")) or text(r.get("address_1"))):
            continue
        label = f"Person {_s(r.get('person_no')) or r['_i'] + 1}"
        role, ptype = r["_role"], r["_ptype"]
        if role == "DRIVER":
            role, ptype = "UNKNOWN", "Unknown"
            notes.append(f"{label}: second driver row for unit {_s(r.get('unit'))}; keyed as Unknown")
        other_parties.append(_empty_other(
            role, ptype, **_name_boxes(r), **_pa_live_address(r, label, notes),
            phone=_pa_live_phone(r.get("phone")), vehicle_number=str(r["_veh"] or ""),
            party_number=str(r["_veh"] or ""), date_of_birth=pa_dob(r.get("dob")),
            injury_code=pa_codes(r.get("injury"), "injury_code", notes, f"{label} injury"),
            nonmotorist_actions=pa_codes(r.get("pedestrian_actions"), "nonmotorist_actions", notes,
                                         f"{label} pedestrian actions"),
            protection=pa_codes(r.get("safety_equipment"), "protection", notes, f"{label} safety equipment"),
            helmet=r.get("_helmet") or pa_codes(r.get("helmet"), "helmet", notes, f"{label} helmet"),
            ejection=pa_codes(r.get("ejection"), "ejection", notes, f"{label} ejection"),
            ems_to=pa_text(r.get("medical_facility")),
            violations=pa_violations(r.get("violations"), label, notes)))

    # ---- witnesses and property owners
    for key, role, label in (("witnesses", "WITNESS", "Witness"), ("property_owners", "PROPERTY OWNER", "Property Owner")):
        for p in raw.get(key) or []:
            name, addr = _name_boxes(p, company_check=(role == "PROPERTY OWNER")), _pa_live_address(p, label, notes)
            if not _has_name(name) and not _has_address(addr):
                notes.append(f"{label} listed with no name or address; not keyed")
                continue
            other_parties.append(_empty_other(role, label, **name, **addr, phone=_pa_live_phone(p.get("phone"))))
    return {"incident": incident, "units": units, "other_parties": other_parties, "notes": notes}
