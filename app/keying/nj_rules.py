"""NJ (NJTR-1) keying rules: raw extraction -> keying payload.

Pure functions: no I/O, no AI calls, no Playwright. Everything the NJ keying
guide, the General SOP and the user's decisions say about *what* to key lives
here, so it can be unit-tested without a browser or a PDF.

Place at:  app/keying/nj_rules.py

Raw input (what the NJ extractor will return; one dict, values as printed)
--------------------------------------------------------------------------
{
  "case_number": "D040202602475C",  "police_dept": "East Orange",
  "crash_date": "07/18/2026",       "crash_time": "2058",
  "road_name": "Garden State Parkway", "cross_road": "", "speed_limit": "55",
  "latitude": "40.886591",          "longitude": "-74.151818",
  "environmental_condition": "02",  # box 103
  "road_surface_condition": "02",   # box 102
  "contributing": {"118a": "60", "118b": "-", "119a": "25", "119b": "-"},
  "damage_boxes": {"130": "09", "131": "09", "132": "09", "133": "04"},
  "has_box_134": true,              # new form (rev 01/22) shows boxes up to 134
  "vehicles": [{
      "number": 1, "parked": false, "hit_and_run": false,
      "policy_number": "...", "ins_code": "000", "narrative_insurance": "",
      "driver": {"first": "", "middle": "", "last": "", "dob": "", "dl_number": "",
                 "dl_state": "", "alcohol_given": "No",
                 "address_1": "", "address_2": "", "city": "", "state": "", "zip": ""},
      "owner":  {"same_as_driver": false, "first": "", "middle": "", "last": "",
                 "address_1": "", ...},
      "vehicle": {"vin": "", "year": "", "make": "", "model": "",
                  "plate": "", "plate_state": ""},
      "removal": {"driven": true, "left_at_scene": false, "towed_disabled": false,
                  "towed_disabled_impounded": false, "towed_impounded": false},
      "charges": ["39:4-88B FAILED TO MAINTAIN LANE"]
  }],
  "occupants": [{"vehicle": "1", "position": "01", "ejection": "01", "injury": "04",
                 "age": "36", "safety_available": "04", "safety_used": "04",
                 "airbag": "04", "hospital": "", "name": "JULIA HARRISON",
                 "address": {...} or "address_line": "415 BUCHANAN RD UTICA NY 13502"}],
  "property_owners": [{"name": "NJTA", "address_line": "", "company": true}]
}

Output payload keys follow the draft NJ form spec: incident / units / other_parties /
notes, plus per-person "same_as_*_address" booleans for other parties.
"""
from __future__ import annotations

import re
from datetime import date

# ----------------------------------------------------------------- text helpers
_NULL = {
    "", "-", "--", "---", "*", "**", "***", "****", "N/A", "NA", "N A", "NONE",
    "UNK", "UNKNOWN", "UU", "UK", "NOT AVAILABLE", "NOT APPLICABLE",
}


def _s(value) -> str:
    return " ".join(str(value).split()) if value is not None else ""


def blank_like(value) -> bool:
    """True for empty values, dashes/asterisks and null words (UNK, N/A, NONE...)."""
    t = _s(value).upper()
    return t in _NULL or not re.search(r"[A-Z0-9]", t)


def text(value) -> str:
    """Non-name text field: null placeholders are not keyable (General SOP)."""
    return "" if blank_like(value) else _s(value)


def name_part(value) -> str:
    """Name field: key what you see, including UNKNOWN/UNK; only bare punctuation is dropped."""
    t = _s(value)
    return t if re.search(r"[A-Za-z0-9]", t) else ""


# ----------------------------------------------------------------- numeric coded fields
def _num(raw):
    m = re.search(r"\d+", _s(raw))
    return int(m.group()) if m else None


def _code2(raw, lo: int, hi: int) -> str:
    n = _num(raw)
    return f"{n:02d}" if n is not None and lo <= n <= hi else ""


def weather(raw) -> str:          # box 103, form 103. Weather Condition: 01-10
    return _code2(raw, 1, 10)


def road_condition(raw) -> str:   # box 102, form 102. Road Condition: 01-09
    return _code2(raw, 1, 9)


def injury_code(raw) -> str:      # 01 Fatal ... 05 No Apparent Injury
    return _code2(raw, 1, 5)


def ejection(raw) -> str:         # 01 Not Ejected ... 04 Trapped
    return _code2(raw, 1, 4)


def safety_equipment(raw) -> str:  # 01 None ... 12 Safety Vest (Ped Only)
    return _code2(raw, 1, 12)


def hospital_code(raw) -> str:
    """Digits as printed (form list is numeric, e.g. 0101). Dash / blank -> ''."""
    n = re.search(r"\d+", _s(raw))
    return n.group() if n else ""


# Apparent Contributing Circumstances (overlay page 2). The form's list shows the
# code WITHOUT a leading zero ("1 Unsafe Speed"), so codes are keyed as 1, 2, ... 60.
_CONTRIB = (set(range(1, 22)) | {25, 29} | set(range(31, 41)) | {49}
            | set(range(51, 62)) | {69} | set(range(71, 79)) | {85, 89})


def contributing(codes) -> str:
    out = []
    for raw in codes:
        n = _num(raw)
        if n in _CONTRIB and str(n) not in out:
            out.append(str(n))
    return ";".join(out)          # multi-select separator: confirm on the live form


# Airbag deployment (box 94): 1-4, 7-8 YES; 5-6 NO; 99 NA (user's table).
def airbag(codes) -> str:
    nums = [n for n in (_num(c) for c in codes) if n is not None]
    if any(n in (1, 2, 3, 4, 7, 8) for n in nums):
        return "YES"
    if any(n in (5, 6) for n in nums):
        return "NO"
    return ""


# Principal Damage clock value -> form option text (NJ guide matrix, single X rows).
_IMPACT = {
    12: "Front", 1: "Right Front", 2: "Right Front", 3: "Right Side",
    4: "Right Rear", 5: "Right Rear", 6: "Rear", 7: "Left Rear", 8: "Left Rear",
    9: "Left Side", 10: "Left Front", 11: "Left Front",
    13: "Multiple", 14: "Multiple", 15: "Multiple",       # roof / undercarriage / overturned
}                                                        # 17, dash, NA -> blank


def impact_location(raw) -> str:
    return _IMPACT.get(_num(raw), "")


def alcohol_test(raw) -> str:     # box 48 Given: No / Yes / Refused
    t = _s(raw).upper()
    for word in ("NO", "YES", "REFUSED"):
        if t == word or t.startswith(word):
            return word.title()
    return ""


# ----------------------------------------------------------------- dates and times
def _century(yy: int, age, ref_year, today: date) -> int:
    cands = (1900 + yy, 2000 + yy)
    if age is not None and ref_year:
        target = ref_year - age
        return min(cands, key=lambda y: abs(y - target))
    return 2000 + yy if yy <= today.year % 100 else 1900 + yy


def norm_date(raw, *, age=None, ref_year=None, today: date | None = None) -> str:
    """MM/DD/YYYY. Two-digit year: use the person's age if known, else 06 -> 2006.
    Missing year or an impossible date -> ''."""
    today = today or date.today()
    t = _s(raw)
    m = re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t)
    if m:
        y, mo, d = (int(g) for g in m.groups())
    else:
        m = re.fullmatch(r"(\d{1,2})\s*[/.\-\s]\s*(\d{1,2})\s*[/.\-\s]\s*(\d{2}|\d{4})", t)
        if not m:
            return ""
        mo, d, ys = int(m[1]), int(m[2]), m[3]
        y = int(ys) if len(ys) == 4 else _century(int(ys), age, ref_year, today)
    try:
        date(y, mo, d)
    except ValueError:
        return ""
    return f"{mo:02d}/{d:02d}/{y:04d}"


def norm_time(raw) -> str:
    """24-hour HH:MM from 2041, '16 01', 16:01, 941. Invalid -> ''."""
    m = re.fullmatch(r"(\d{1,2})\s*[:.]?\s*(\d{2})", _s(raw))
    if not m:
        return ""
    h, mi = int(m[1]), int(m[2])
    return f"{h:02d}:{mi:02d}" if h <= 23 and mi <= 59 else ""


# ----------------------------------------------------------------- names
_SUFFIX = {"JR", "SR", "II", "III", "IV"}
_COMPANY_WORDS = (
    "LLC", "INC", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LP", "LLP", "TRUST",
    "HOLDINGS", "PROPERTIES", "ASSOCIATES", "ASSOCIATION", "AUTHORITY", "DEPARTMENT",
    "DEPT", "TOWNSHIP", "BOROUGH", "COUNTY", "SCHOOL", "CHURCH", "BANK", "LEASING",
    "RENTAL", "RENTALS", "SERVICES", "ENTERPRISES", "GROUP", "MOTORS", "REALTY",
    "MANAGEMENT", "UTILITIES", "TRANSIT", "NJTA", "NJDOT", "PSEG",
)
_COMPANY_RE = re.compile(
    r"\b(?:" + "|".join(_COMPANY_WORDS) + r")\b\.?|\b(?:CITY|TOWN|STATE|TOWNSHIP|BOROUGH|COUNTY) OF\b|[&@]",
    re.I,
)


def is_company(value) -> bool:
    return bool(_COMPANY_RE.search(_s(value)))


def _strip_suffix(tokens: list[str]) -> tuple[list[str], str]:
    if len(tokens) > 1 and tokens[-1].rstrip(".").upper() in _SUFFIX:
        return tokens[:-1], tokens[-1].rstrip(".")
    return tokens, ""


def split_name(full, company: bool | None = None) -> dict:
    """One printed name string -> first / middle / last / suffix.
    Companies go entirely into the last name (General SOP). 'LAST, FIRST M' is reordered."""
    t = _s(full).strip(" ,")
    blank = {"first_name": "", "middle_name": "", "last_name": "", "suffix": ""}
    if not t or not re.search(r"[A-Za-z0-9]", t):
        return blank
    if company is None:
        company = is_company(t)
    if company:
        return {**blank, "last_name": t}
    if "," in t:
        last_part, _, rest = t.partition(",")
        last_tokens, suffix = _strip_suffix(last_part.split())
        rest_tokens, suffix2 = _strip_suffix(rest.split())
        return {"first_name": rest_tokens[0] if rest_tokens else "",
                "middle_name": " ".join(rest_tokens[1:]),
                "last_name": " ".join(last_tokens), "suffix": suffix or suffix2}
    tokens, suffix = _strip_suffix(t.split())
    if len(tokens) == 1:
        return {**blank, "last_name": tokens[0], "suffix": suffix}      # one name -> last name
    return {"first_name": tokens[0], "middle_name": " ".join(tokens[1:-1]),
            "last_name": tokens[-1], "suffix": suffix}


def person_from_boxes(first, middle, last, *, company_check: bool = False) -> dict:
    """Name printed in separate boxes. A suffix typed after the last name moves to Suffix."""
    f, m, l = name_part(first), name_part(middle), name_part(last)
    tokens, suffix = _strip_suffix(l.split()) if l else ([], "")
    l = " ".join(tokens)
    if company_check and is_company(" ".join(x for x in (f, m, l) if x)):
        return {"first_name": "", "middle_name": "", "last_name": " ".join(x for x in (f, m, l) if x), "suffix": ""}
    return {"first_name": f, "middle_name": m, "last_name": l, "suffix": suffix}


# ----------------------------------------------------------------- addresses
_UNIT_RE = re.compile(
    r"[\s,]+((?:APT|APARTMENT|UNIT|STE|SUITE|SPC|SPACE|LOT|RM|ROOM|FL|FLOOR|BLDG|BUILDING|TRLR|TRAILER)\.?\s*#?\s*[A-Z0-9-]+"
    r"|#\s*[A-Z0-9-]+|P\.?\s?O\.?\s*BOX\s*\d+)$", re.I)
_STREET_SUFFIX = {
    "ST", "STREET", "RD", "ROAD", "AVE", "AVENUE", "BLVD", "BOULEVARD", "DR", "DRIVE", "LN", "LANE",
    "CT", "COURT", "PL", "PLACE", "WAY", "TER", "TERRACE", "HWY", "HIGHWAY", "PKWY", "PARKWAY", "CIR",
    "CIRCLE", "TRL", "TRAIL", "PIKE", "SQ", "SQUARE", "PLZ", "PLAZA", "ALY", "ALLEY", "RT", "ROUTE",
}
_LEADING_UNIT_RE = re.compile(
    r"^((?:APT|APARTMENT|UNIT|STE|SUITE|SPC|SPACE|LOT|RM|ROOM|FL|FLOOR|BLDG|BUILDING)\.?\s*#?\s*[A-Z0-9-]+|#\s*[A-Z0-9-]+)\s+(.+)$", re.I)
_CSZ_RE = re.compile(r"^(.*?)[,\s]+([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)$")


def split_unit(line: str) -> tuple[str, str]:
    """Street line -> (address_1, address_2). Apt/Unit/Ste/Lot/Fl/P.O. Box go to Address 2."""
    t = _s(line)
    m = _UNIT_RE.search(t)
    if m and t[:m.start()].strip(" ,"):
        return t[:m.start()].strip(" ,"), _s(m[1])
    return t, ""


def split_city_state_zip(line: str) -> tuple[str, str, str]:
    m = _CSZ_RE.match(_s(line))
    return (m[1].strip(" ,"), m[2].upper(), m[3]) if m else ("", "", "")


def split_address_line(line: str) -> tuple[str, str, str, str, str]:
    """Best-effort split of '415 BUCHANAN RD UTICA NY 13502'. The extractor should return
    the parts separately; this is only a fallback and callers add a review note."""
    t = _s(line)
    m = _CSZ_RE.match(t)
    if not m:
        return t, "", "", "", ""
    rest, state, zip_code = m[1].strip(" ,"), m[2].upper(), m[3]
    tokens = rest.split()
    idx = [i for i, tok in enumerate(tokens) if i >= 1 and tok.rstrip(".,").upper() in _STREET_SUFFIX and i < len(tokens) - 1]
    if not idx:
        return rest, "", "", state, zip_code
    cut = idx[-1]
    street, city = " ".join(tokens[:cut + 1]), " ".join(tokens[cut + 1:])
    a1, a2 = split_unit(street)
    m_unit = _LEADING_UNIT_RE.match(city)                  # "APT 2 UTICA" -> unit APT 2, city UTICA
    if m_unit and not a2:
        a2, city = _s(m_unit[1]), m_unit[2]
    return a1, a2, city.strip(" ,"), state, zip_code


def _address(src: dict | None, who: str, notes: list[str]) -> dict:
    d = src or {}
    a1 = _s(d.get("address_1") or d.get("address"))
    line = _s(d.get("address_line"))
    if not line and not d.get("address_1") and _CSZ_RE.match(a1):
        line, a1 = a1, ""                      # a one-line "street city ST 12345" string
    a2, city, st, zp = _s(d.get("address_2")), _s(d.get("city")), _s(d.get("state")), _s(d.get("zip") or d.get("zip_code"))
    csz = _s(d.get("city_state_zip"))
    if csz and not (city or st or zp):
        city, st, zp = split_city_state_zip(csz)
    if line and not a1:
        a1, a2b, city2, st2, zp2 = split_address_line(line)
        a2, city, st, zp = a2 or a2b, city or city2, st or st2, zp or zp2
        notes.append(f"{who}: address was split from one line; review city/state/zip")
    if a1 and not a2:
        a1, a2 = split_unit(a1)
    return {"address_1": text(a1), "address_2": text(a2), "city": text(city),
            "state": text(st).upper(), "zip_code": text(zp)}


def _same_address(a: dict, b: dict) -> bool:
    def key(x):
        return re.sub(r"[^A-Z0-9]", "", f"{x.get('address_1', '')}{x.get('zip_code', '')}".upper())
    ka, kb = key(a), key(b)
    return bool(ka) and ka == kb


# ----------------------------------------------------------------- vehicle helpers
def fix_vin(raw) -> str:
    """General SOP: I -> 1, O and Q -> 0; everything else as printed."""
    t = re.sub(r"\s+", "", _s(raw)).upper()
    if blank_like(t):
        return ""
    return t.replace("I", "1").replace("O", "0").replace("Q", "0")


def insurance_carrier(ins_code, narrative_name) -> str:
    """Printed NJ insurance code as seen (000 stays 000). Blank / asterisks -> narrative name,
    else blank."""
    code = text(ins_code)
    return code if code else text(narrative_name)


def vehicle_towed(removal: dict | None) -> str:
    r = removal or {}
    if r.get("towed_disabled") or r.get("towed_disabled_impounded") or r.get("towed_impounded"):
        return "YES"
    if r.get("driven") or r.get("left_at_scene"):
        return "NO"
    return ""


# ----------------------------------------------------------------- the mapper
def _coded(label: str, raw, fn, notes: list[str]) -> str:
    value = fn(raw)
    if not value and not blank_like(raw) and _num(raw) is not None:
        notes.append(f"{label}: code '{_s(raw)}' is not in the NJ list; left blank")
    return value


def _occupant_party(o: dict, pos: int | None) -> str | None:
    veh = _s(o.get("vehicle")).upper()
    if veh == "B":
        return "Pedalcyclist"
    if veh == "P":
        return "Pedestrian"
    if veh == "O" or pos == 0:
        return "Unknown"
    if pos is not None and pos >= 2:
        return "Passenger"
    return None


def map_nj(raw: dict, *, today: date | None = None) -> dict:
    """Raw NJTR-1 extraction -> keying payload (see module docstring)."""
    today = today or date.today()
    notes: list[str] = list(raw.get("notes") or [])
    vehicles = sorted(raw.get("vehicles") or [], key=lambda v: _num(v.get("number")) or 0)
    occupants = list(raw.get("occupants") or [])
    crash_date = norm_date(raw.get("crash_date"), today=today)
    crash_year = int(crash_date[-4:]) if crash_date else None

    incident = {
        "report_identifier_1": text(raw.get("case_number")),
        "report_identifier_2": "",
        "incident_date": crash_date,
        "time_2400": norm_time(raw.get("crash_time")),
        "incident_state": "NJ",
        "incident_city": text(raw.get("police_dept")),         # "2. Police Dept. of" box, KWYS
        "incident_street": text(raw.get("road_name")),
        "incident_cross_street": text(raw.get("cross_road")),
        "latitude": text(raw.get("latitude")),
        "longitude": text(raw.get("longitude")),
        "weather": _coded("Weather (box 103)", raw.get("environmental_condition"), weather, notes),
        "road_condition": _coded("Road condition (box 102)", raw.get("road_surface_condition"), road_condition, notes),
        "speed_limit": text(raw.get("speed_limit")),
        "hit_and_run": "1" if any(v.get("hit_and_run") for v in vehicles) else "",
    }

    boxes = raw.get("damage_boxes") or {}
    has_134 = raw.get("has_box_134", True)
    damage = {1: boxes.get("130" if has_134 else "131"), 2: boxes.get("132" if has_134 else "133")}
    contrib = raw.get("contributing") or {}
    contrib_by_unit = {1: [contrib.get("118a"), contrib.get("118b")], 2: [contrib.get("119a"), contrib.get("119b")]}

    units, other_parties, used_driver_rows = [], [], set()
    for v in vehicles:
        n = _num(v.get("number")) or (len(units) + 1)
        label = f"Unit {n}"
        occ = [(i, o) for i, o in enumerate(occupants) if _s(o.get("vehicle")) == str(n)]
        drv_row = next(((i, o) for i, o in occ if _num(o.get("position")) == 1), None)
        if drv_row:
            used_driver_rows.add(drv_row[0])
        d_occ = drv_row[1] if drv_row else {}
        d, ow, veh = v.get("driver") or {}, v.get("owner") or {}, v.get("vehicle") or {}

        # --- driver (printed names win; PARKED only when nothing is printed)
        dn = person_from_boxes(d.get("first"), d.get("middle"), d.get("last"))
        printed_driver_name = any(dn[k] for k in ("first_name", "middle_name", "last_name"))
        if not printed_driver_name and v.get("parked"):
            dn["last_name"] = "PARKED"
        driver = {
            **dn, **_address(d, f"{label} driver", notes),
            "date_of_birth": norm_date(d.get("dob"), age=_num(d_occ.get("age")), ref_year=crash_year, today=today),
            "drivers_license": text(d.get("dl_number")),
            "drivers_license_state": text(d.get("dl_state")).upper(),
            "injury_code": _coded(f"{label} injury", d_occ.get("injury"), injury_code, notes),
            "ejection": _coded(f"{label} ejection", d_occ.get("ejection"), ejection, notes),
            "safety_available": _coded(f"{label} safety equipment available", d_occ.get("safety_available"), safety_equipment, notes),
            "safety_used": _coded(f"{label} safety equipment used", d_occ.get("safety_used"), safety_equipment, notes),
            "hospital": hospital_code(d_occ.get("hospital")),
            "alcohol_test": alcohol_test(d.get("alcohol_given")),
            "charge": [text(c) for c in (v.get("charges") or []) if text(c)],
        }

        # --- owner (Same As Driver: copy first/middle/last only; address as printed)
        if ow.get("same_as_driver"):
            on = {"first_name": dn["first_name"] if printed_driver_name else "",
                  "middle_name": dn["middle_name"] if printed_driver_name else "",
                  "last_name": dn["last_name"] if printed_driver_name else "", "suffix": dn["suffix"]}
        else:
            on = person_from_boxes(ow.get("first"), ow.get("middle"), ow.get("last"), company_check=True)
        owner = {**on, **_address(ow, f"{label} owner", notes)}

        vehicle = {
            "vin": fix_vin(veh.get("vin")), "year": text(veh.get("year")),
            "make": text(veh.get("make")), "model": text(veh.get("model")),
            "tag_number": text(veh.get("plate")), "tag_state": text(veh.get("plate_state")).upper(),
            "insurance_carrier": insurance_carrier(v.get("ins_code"), v.get("narrative_insurance")),
            "policy_number": text(v.get("policy_number")),
            "vehicle_towed": vehicle_towed(v.get("removal")),
            "airbag_deployed": airbag([o.get("airbag") for _, o in occ]),
            "contributing": contributing(contrib_by_unit.get(n, [])),
            "impact_location": impact_location(damage.get(n)),
        }
        if vehicle["vin"] and (len(vehicle["vin"]) != 17):
            notes.append(f"{label}: VIN has {len(vehicle['vin'])} characters; keyed as printed, review")
        units.append({"party_number": n, "owner": owner, "driver": driver, "vehicle": vehicle})

    by_number = {u["party_number"]: u for u in units}

    # --- other parties: passengers, pedestrians, pedalcyclists, unknown
    for i, o in enumerate(occupants):
        if i in used_driver_rows:
            continue
        pos = _num(o.get("position"))
        veh_no = _s(o.get("vehicle")).upper()
        party = _occupant_party(o, pos)
        if party is None:
            party = "Unknown"
            notes.append(f"Occupant {_s(o.get('row') or i + 1)}: seating position missing or a second driver; keyed as Unknown")
        name = split_name(o.get("name"), o.get("company"))
        addr = _address(o["address"] if isinstance(o.get("address"), dict) else o,
                        f"Occupant {_s(o.get('row') or i + 1)}", notes)
        unit = by_number.get(_num(veh_no)) if veh_no.isdigit() else None
        party_row = {
            "person_type": party, **name, **addr,
            "vehicle_number": veh_no if veh_no.isdigit() else "",
            "date_of_birth": "",
            "injury_code": _coded("Occupant injury", o.get("injury"), injury_code, notes),
            "ejection": _coded("Occupant ejection", o.get("ejection"), ejection, notes),
            "safety_available": _coded("Occupant safety equipment available", o.get("safety_available"), safety_equipment, notes),
            "safety_used": _coded("Occupant safety equipment used", o.get("safety_used"), safety_equipment, notes),
            "hospital": hospital_code(o.get("hospital")),
            "same_as_driver_address": bool(unit and _same_address(addr, unit["driver"])),
            "same_as_owner_address": bool(unit and not _same_address(addr, unit["driver"]) and _same_address(addr, unit["owner"])),
        }
        other_parties.append(party_row)

    # --- property owners (field 135): name + address; description is discarded
    for p in raw.get("property_owners") or []:
        name_text = _s(p.get("name"))
        name = split_name(name_text, p.get("company")) if name_text else {"first_name": "", "middle_name": "", "last_name": "", "suffix": ""}
        addr = _address(p, "Property owner", notes)
        if not name_text and not addr["address_1"]:
            notes.append("Property damage listed with no owner name or address; no Property Owner keyed")
            continue
        other_parties.append({
            "person_type": "Property Owner", **name, **addr, "vehicle_number": "", "date_of_birth": "",
            "injury_code": "", "ejection": "", "safety_available": "", "safety_used": "", "hospital": "",
            "same_as_driver_address": False, "same_as_owner_address": False,
        })

    return {"incident": incident, "units": units, "other_parties": other_parties, "notes": notes}
