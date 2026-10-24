"""NJ (NJTR-1) keying rules: raw extraction -> keying payload.

Pure functions: no I/O, no AI calls, no Playwright. Everything the NJ keying
guide, the General SOP and the user's decisions say about *what* to key lives
here, so it can be unit-tested without a browser or a PDF.

Place at:  app/keying/nj_rules.py

Raw input (what app/extraction/nj_extractor.py returns; values as printed)
--------------------------------------------------------------------------
{
  "case_number": "D040202602475C", "police_dept": "East Orange",
  "crash_date": "07/18/2026", "crash_time": "2058",
  "road_name": "...", "cross_road": "", "speed_limit": "55",
  "latitude": "...", "longitude": "...",
  "weather_code": "02",            # margin box 103
  "road_condition_code": "02",     # margin box 102
  "vehicles": [{
      "number": 1, "parked": false, "hit_and_run": false,
      "policy_number": "...", "ins_code": "000",
      "narrative_insurance": "", "narrative_policy": "",
      "driver": {"first": "", "middle": "", "last": "", "dob": "", "dl_number": "",
                 "dl_state": "", "alcohol_given": "No", "address_1": "", "address_2": "",
                 "city": "", "state": "", "zip": ""},
      "owner":  {"same_as_driver": false, "name": "Richard B McKelvey III",
                 "is_company": null, "address_1": "", "city": "", "state": "", "zip": ""},
      "vehicle": {"vin": "", "year": "", "make": "", "model": "",
                  "plate": "", "plate_state": ""},
      "removal": {"driven": true, "left_at_scene": false, "towed_disabled": false,
                  "towed_disabled_impounded": false, "towed_impounded": false},
      "charges": ["39:4-88B FAILED TO MAINTAIN LANE"],
      # damage and contributing circumstances belong to the PAGE the vehicle is on
      # (left vehicle: boxes 130/131 and 118a/118b; right vehicle: 132/133 and 119a/119b)
      "damage": {"new": "09", "old": "03", "new_form": true},
      "contributing": ["60", "-"]
  }],
  "occupants": [{"row": "A", "vehicle": "1", "position": "01", "ejection": "01",
                 "injury": "04", "age": "36", "safety_available": "04",
                 "safety_used": "04", "airbag": "04", "hospital": "",
                 "name": "JULIA HARRISON", "address_line": "415 BUCHANAN RD UTICA NY 13502"}],
  "property_owners": [{"name": "NJTA", "address_line": "", "is_company": true}]
}

Output payload keys follow the NJ form spec: incident / units / other_parties / notes.
Other parties carry "role" and "party_number" (what the shared engine reads) as well as
the readable "person_type" / "vehicle_number".
"""
from __future__ import annotations

import re
from datetime import date

from app.core.driver_rules import HIT_AND_RUN_NAME

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


_LICENSE_NULL = {"UNKNOWN", "NA", "N/A", "NOTAPPLICABLE"}


def license_number(value) -> str:
    """Driver's licence number: key what you see, so "NONE" is keyed. Only UNKNOWN, NA, N/A
    and NOT APPLICABLE (and boxes holding just dashes or asterisks) are left blank."""
    t = _s(value)
    if not re.search(r"[A-Za-z0-9]", t) or re.sub(r"\s+", "", t).upper() in _LICENSE_NULL:
        return ""
    return t


_PLACEHOLDER_TOKEN = re.compile(r"[-\u2010-\u2015_*.,]+")      # "-", "--", an en/em dash, "*", "_", "." or ","


def _drop_dashes(value) -> str:
    """Remove tokens made only of dashes / asterisks / dots / commas. Hyphens inside a name
    (BERMEO-ALTAMIRANO) and company symbols such as "&" are untouched."""
    return " ".join(tok for tok in _s(value).split() if not _PLACEHOLDER_TOKEN.fullmatch(tok))


def name_part(value) -> str:
    """Name field: key what you see, including UNKNOWN/UNK. A box holding only "-" is blank,
    and a stray "-" next to a real name is dropped ("JOHN -" -> "JOHN")."""
    return _drop_dashes(value)


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


# Apparent Contributing Circumstances (overlay page 2): KWYS. The printed digits are keyed
# exactly as printed ("04" stays "04"); only blanks and dashes are dropped. A code that is not in
# the list below is still keyed, with a review note from the mapper.
_CONTRIB = (set(range(1, 22)) | {25, 29} | set(range(31, 41)) | {49}
            | set(range(51, 62)) | {69} | set(range(71, 79)) | {85, 89})


def contributing_codes(codes) -> list[str]:
    """Printed codes in order, de-duplicated by value ("04" and "4" are the same code)."""
    out, seen = [], set()
    for raw in codes or []:
        m = re.search(r"\d+", _s(raw))
        if not m or blank_like(raw):
            continue
        key = int(m.group())
        if key not in seen:
            seen.add(key)
            out.append(m.group())
    return out


def contributing(codes) -> str:
    return ";".join(contributing_codes(codes))          # multi-select separator: confirm on the live form


# Airbag deployment (box 94): 1-4 and 7-8 YES; 5 and 6 NO; 99 NA (blank). Any other code is blank.
def airbag(codes) -> str:
    nums = [n for n in (_num(c) for c in codes) if n is not None]
    if any(n in (1, 2, 3, 4, 7, 8) for n in nums):
        return "YES"
    if any(n in (5, 6) for n in nums):
        return "NO"
    return ""


_AIRBAG_KNOWN = {1, 2, 3, 4, 5, 6, 7, 8, 99}


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
    t = _drop_dashes(full).strip(" ,")
    blank = {"first_name": "", "middle_name": "", "last_name": "", "suffix": ""}
    if not t:
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
    r"|\d+(?:ST|ND|RD|TH)\s+(?:FL|FLOOR)\.?"
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
    parts = [x.strip() for x in t.split(",") if x.strip()]
    if len(parts) >= 3:                                   # "street[, unit], city, ST 12345"
        m_sz = re.fullmatch(r"([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)", parts[-1])
        if m_sz:
            unit = ", ".join(parts[1:-2])
            a1, a2 = parts[0], unit
            if not a2:
                a1, a2 = split_unit(a1)
            return a1, a2, parts[-2], m_sz[1].upper(), m_sz[2]
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
    elif city and not (st or zp) and _CSZ_RE.match(city):      # "Passaic, NJ 07055-5114" in the City box
        city, st, zp = split_city_state_zip(city)
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


_NARR_PREFIX = re.compile(r"^\s*\(?[A-Za-z]{2}\)\s*")
_NARR_SUFFIX = re.compile(r"\s*[-\u2013]\s*Field\s*\d+\w*\s*$", re.I)


def clean_narrative_value(value) -> str:
    """'(NY) STATE FARM - Field 25' -> 'STATE FARM'."""
    t = _NARR_SUFFIX.sub("", _s(value))
    t = _NARR_PREFIX.sub("", t) if re.match(r"^\s*\([A-Za-z]{2}\)\s*\S", t) else t
    return text(t)


def insurance_carrier(ins_code, narrative_name) -> str:
    """Printed NJ insurance code as seen (000 stays 000). Blank / asterisks -> narrative name,
    else blank."""
    code = text(ins_code)
    return code if code else clean_narrative_value(narrative_name)


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


def _blank_name() -> dict:
    return {"first_name": "", "middle_name": "", "last_name": "", "suffix": ""}


def _has_name(n: dict) -> bool:
    return any(n.get(k) for k in ("first_name", "middle_name", "last_name"))


def _has_address(a: dict) -> bool:
    return any(a.get(k) for k in ("address_1", "city", "state", "zip_code"))


def _owner_name(ow: dict) -> dict:
    """Owner name printed as separate boxes OR as one string (company-aware)."""
    if _s(ow.get("name")):
        return split_name(ow.get("name"), ow.get("is_company"))
    return person_from_boxes(ow.get("first"), ow.get("middle"), ow.get("last"), company_check=True)


def _damage(v: dict) -> str:
    """Principal damage: box 130 (V-left) / 132 (V-right) on the new form that shows box 134;
    131 / 133 on the older one. Values arrive already assigned to the right vehicle."""
    d = v.get("damage") or {}
    return impact_location(d.get("new") if d.get("new_form", True) else d.get("old"))


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
        "weather": _coded("Weather (box 103)", raw.get("weather_code"), weather, notes),
        "road_condition": _coded("Road condition (box 102)", raw.get("road_condition_code"), road_condition, notes),
        "speed_limit": text(raw.get("speed_limit")),
        "hit_and_run": "1" if any(v.get("hit_and_run") for v in vehicles) else "",
    }

    units, other_parties, used_rows = [], [], set()
    for v in vehicles:
        n = _num(v.get("number")) or (len(units) + 1)
        label = f"Unit {n}"
        occ = [(i, o) for i, o in enumerate(occupants) if _num(o.get("vehicle")) == n]
        drv_row = next(((i, o) for i, o in occ if _num(o.get("position")) == 1), None)
        if drv_row:
            used_rows.add(drv_row[0])
        d_occ = drv_row[1] if drv_row else {}
        d, ow, veh = v.get("driver") or {}, v.get("owner") or {}, v.get("vehicle") or {}

        # --- driver: printed boxes win; the occupant row is the fallback; HIT AND RUN / PARKED only when no name anywhere
        dn = person_from_boxes(d.get("first"), d.get("middle"), d.get("last"))
        if not _has_name(dn) and _s(d_occ.get("name")):
            dn = split_name(d_occ.get("name"), d_occ.get("company"))
        printed_driver = _has_name(dn)
        engine_hit_and_run = bool(v.get("hit_and_run"))      # the flag the shared engine reads
        if not printed_driver:
            # Blank name: PARKED has priority over HIT AND RUN. A written name always wins.
            if v.get("parked"):
                dn["last_name"] = "PARKED"
            elif v.get("hit_and_run"):                     # General SOP, all states
                dn["last_name"] = HIT_AND_RUN_NAME
        charges = [text(c) for c in (v.get("charges") or []) if text(c)]
        driver = {
            **dn, **_address(d, f"{label} driver", notes),
            "date_of_birth": norm_date(d.get("dob"), age=_num(d_occ.get("age")), ref_year=crash_year, today=today),
            "drivers_license": license_number(d.get("dl_number")),
            "drivers_license_state": text(d.get("dl_state")).upper(),
            "injury_code": _coded(f"{label} injury", d_occ.get("injury"), injury_code, notes),
            "ejection": _coded(f"{label} ejection", d_occ.get("ejection"), ejection, notes),
            "safety_available": _coded(f"{label} safety equipment available", d_occ.get("safety_available"), safety_equipment, notes),
            "safety_used": _coded(f"{label} safety equipment used", d_occ.get("safety_used"), safety_equipment, notes),
            "hospital": hospital_code(d_occ.get("hospital")),
            "alcohol_test": alcohol_test(d.get("alcohol_given")),
            "charge": charges[0] if charges else "",         # first charge goes through the engine
            "extra_charges": charges[1:],                     # the rest use the form's (+) button
        }

        # --- owner (Same As Driver: copy first/middle/last only; address always as printed)
        if ow.get("same_as_driver"):
            on = {"first_name": dn["first_name"], "middle_name": dn["middle_name"],
                  "last_name": dn["last_name"] if printed_driver else "",
                  "suffix": dn["suffix"]}
            if not printed_driver:
                on["first_name"] = on["middle_name"] = ""
        else:
            on = _owner_name(ow)
        owner = {**on, **_address(ow, f"{label} owner", notes)}

        codes = [o.get("airbag") for _, o in occ]
        vehicle = {
            "vin": fix_vin(veh.get("vin")), "year": text(veh.get("year")),
            "make": text(veh.get("make")), "model": text(veh.get("model")),
            "tag_number": text(veh.get("plate")), "tag_state": text(veh.get("plate_state")).upper(),
            "insurance_carrier": insurance_carrier(v.get("ins_code"), v.get("narrative_insurance")),
            "policy_number": text(v.get("policy_number")) or clean_narrative_value(v.get("narrative_policy")),
            "vehicle_towed": vehicle_towed(v.get("removal")),
            "airbag_deployed": airbag(codes),
            "contributing": contributing(v.get("contributing") or []),
            "impact_location": _damage(v),
        }
        for c in contributing_codes(v.get("contributing") or []):
            if int(c) not in _CONTRIB:
                notes.append(f"{label}: contributing circumstance '{c}' is not in the NJ list; keyed as printed, review")
        for c in codes:
            k = _num(c)
            if k is not None and k not in _AIRBAG_KNOWN:
                notes.append(f"{label}: airbag code '{_s(c)}' is not in the NJ list; ignored")
        if vehicle["vin"] and len(vehicle["vin"]) != 17:
            notes.append(f"{label}: VIN has {len(vehicle['vin'])} characters; keyed as printed, review")
        units.append({"party_number": n, "hit_and_run": engine_hit_and_run,
                      "owner": owner, "driver": driver, "vehicle": vehicle})

    by_number = {u["party_number"]: u for u in units}

    # --- other parties: passengers, pedestrians, pedalcyclists, unknown
    for i, o in enumerate(occupants):
        if i in used_rows:
            continue
        pos = _num(o.get("position"))
        veh_no = _s(o.get("vehicle")).upper()
        row = _s(o.get("row")) or str(i + 1)
        party = _occupant_party(o, pos)
        if party is None:
            party = "Unknown"
            notes.append(f"Occupant {row}: seating position missing or a second driver; keyed as Unknown")
        name = split_name(o.get("name"), o.get("company"))
        addr = _address(o["address"] if isinstance(o.get("address"), dict) else o, f"Occupant {row}", notes)
        veh_digits = str(int(veh_no)) if veh_no.isdigit() else ""       # "01" -> "1" (form unit numbers)
        unit = by_number.get(int(veh_digits)) if veh_digits else None
        # Passenger address: key what is printed; only when none is printed tick Same As Driver
        # (or Same As Owner when that vehicle has no driver address).
        same_driver = same_owner = False
        if unit and not _has_address(addr):
            if _has_address(unit["driver"]):
                same_driver = True
            elif _has_address(unit["owner"]):
                same_owner = True
        other_parties.append({
            "role": party.upper(), "party_number": veh_digits,
            "person_type": party, **name, **addr,
            "vehicle_number": veh_digits, "date_of_birth": "",
            "injury_code": _coded(f"Occupant {row} injury", o.get("injury"), injury_code, notes),
            "ejection": _coded(f"Occupant {row} ejection", o.get("ejection"), ejection, notes),
            "safety_available": _coded(f"Occupant {row} safety equipment available", o.get("safety_available"), safety_equipment, notes),
            "safety_used": _coded(f"Occupant {row} safety equipment used", o.get("safety_used"), safety_equipment, notes),
            "hospital": hospital_code(o.get("hospital")),
            "same_as_driver_address": same_driver, "same_as_owner_address": same_owner,
        })

    # --- property owners (field 135): name + address; the description is discarded
    for p in raw.get("property_owners") or []:
        name_text = _s(p.get("name"))
        name = split_name(name_text, p.get("is_company")) if name_text else _blank_name()
        addr = _address(p, "Property owner", notes)
        if not _has_name(name) and not _has_address(addr):
            notes.append("Property damage listed with no owner name or address; no Property Owner keyed")
            continue
        other_parties.append({
            "role": "PROPERTY OWNER", "party_number": "", "person_type": "Property Owner",
            **name, **addr, "vehicle_number": "", "date_of_birth": "",
            "injury_code": "", "ejection": "", "safety_available": "", "safety_used": "", "hospital": "",
            "same_as_driver_address": False, "same_as_owner_address": False,
        })

    return {"incident": incident, "units": units, "other_parties": other_parties, "notes": notes}
