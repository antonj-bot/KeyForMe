# KeyForMe fix4
import re


def value(field):
    return field.value if hasattr(field, "value") else field


def text(field) -> str:
    v = value(field)
    return "" if v is None else str(v).strip()


# ---------- formats

def to_mmddyyyy(raw) -> str:
    t = str(raw or "").strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})$", t)
    if m:
        return f"{int(m.group(2)):02d}/{int(m.group(3)):02d}/{m.group(1)}"
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})$", t)
    if m:
        return f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{m.group(3)}"
    return t


def to_hhmm(raw) -> str:
    t = str(raw or "").strip()
    digits = re.sub(r"\D", "", t)
    if len(digits) == 4:
        return f"{digits[:2]}:{digits[2:]}"
    if len(digits) == 3:
        return f"0{digits[0]}:{digits[1:]}"
    return t


def format_phone(raw) -> str:
    """Keep digits and '-'. Anything else becomes a space. No leading space.
    '(323) 203-6513/NONE' -> '323 203-6513' (home phone only)."""
    first = str(raw or "").split("/")[0]
    s = re.sub(r"[^0-9-]", " ", first)
    s = re.sub(r" +", " ", s).strip()
    return s if re.search(r"\d", s) else ""


DAMAGE_LABELS = {
    "UNK": "UNK.", "UNKNOWN": "UNK.", "NONE": "NONE", "MINOR": "MINOR",
    "MOD": "MOD.", "MODERATE": "MOD.", "MAJOR": "MAJOR",
    "ROLL-OVER": "ROLL-OVER", "ROLLOVER": "ROLL-OVER", "ROLL OVER": "ROLL-OVER",
}


def damage_label(raw) -> str:
    t = str(raw or "").strip()
    return DAMAGE_LABELS.get(t.upper().rstrip(".").strip(), t)


# Keying-form dropdowns. Report wording must match the form wording, else blank.
INJURY_CODES = {
    "FATAL INJURY": "1",
    "SEVERE INJURY": "2",
    "OTHER VISIBLE INJURY": "3",
    "COMPLAINT OF PAIN": "4",
    "SUSPECTED SERIOUS INJURY": "5",
    "SUSPECTED MINOR INJURY": "6",
    "POSSIBLE INJURY": "7",
}

EJECTED_CODES = {"0", "1", "2", "3"}  # Not / Fully / Partially Ejected / Unknown

def injury_code(raw) -> str:
    wording = " ".join(str(raw or "").upper().split())
    return INJURY_CODES.get(wording, "")


def ejected_code(raw) -> str:
    t = str(raw or "").strip()
    return t if t in EJECTED_CODES else ""


def code(raw) -> str:
    t = str(raw or "").strip().upper()
    m = re.match(r"^([A-Z]{1,2}|\d{1,2})\b", t)
    return m.group(1) if m else ""


def codes(raw_list) -> list[str]:
    out = []
    for item in raw_list or []:
        c = code(item)
        if c and c not in out:
            out.append(c)
    return out


def first_code(raw_list, label: str, unit, notes: list) -> str:
    found = codes(raw_list)
    if len(found) > 1:
        where = f"Unit {unit}" if unit else "Incident"
        notes.append(f"{where}: {label} has {', '.join(found)} marked; keyed "
                     f"{found[0]}, key the rest manually.")
    return found[0] if found else ""


# ---------- names / addresses

def split_name_111(full_name) -> dict:
    parts = str(full_name or "").split()
    first = parts[0] if parts else ""
    last = parts[-1] if len(parts) > 1 else ""
    middle = " ".join(parts[1:-1]) if len(parts) > 2 else ""
    return {"first_name": first, "middle_name": middle, "last_name": last, "suffix": ""}


COMPANY_WORDS = (
    "INC", "LLC", "L.L.C", "CORP", "CORPORATION", "CO", "COMPANY", "LTD", "LP",
    "LLP", "PC", "PLLC", "GROUP", "HOLDINGS", "ENTERPRISE", "ENTERPRISES",
    "RENTAL", "RENTALS", "RENT", "LEASING", "LEASE", "MOTORS", "AUTO", "AUTOMOTIVE",
    "TRANSPORT", "TRANSPORTATION", "TRUCKING", "LOGISTICS", "FREIGHT", "EXPRESS",
    "SERVICES", "SERVICE", "SOLUTIONS", "SYSTEMS", "INDUSTRIES", "BANK",
    "CREDIT", "FINANCIAL", "FINANCE", "CAPITAL", "TRUST", "INSURANCE", "ASSOC",
    "ASSOCIATION", "UNIVERSITY", "COLLEGE", "SCHOOL", "DISTRICT", "CHURCH",
    "HOSPITAL", "DEPT", "DEPARTMENT", "AGENCY", "AUTHORITY", "CONSTRUCTION",
    "CONTRACTORS", "PLUMBING", "ELECTRIC", "FARMS", "HERTZ", "AVIS", "BUDGET",
    "UHAUL", "U-HAUL", "PENSKE", "RYDER", "FEDEX", "UPS", "AMAZON", "TESLA",
)
GOVERNMENT_PREFIXES = ("CITY OF", "COUNTY OF", "STATE OF", "TOWN OF", "US ", "U.S.")


def is_company(name: str) -> bool:
    upper = name.upper()
    if upper.startswith(GOVERNMENT_PREFIXES):
        return True
    words = set(re.findall(r"[A-Z0-9][A-Z0-9.\-']*", upper))
    words |= {w.rstrip(".") for w in words}
    return bool(words & set(COMPANY_WORDS))


def owner_name_fields(raw, is_company_flag=None) -> dict:
    name = " ".join(str(raw or "").split())
    if not name:
        return {"first_name": "", "middle_name": "", "last_name": "", "suffix": ""}
    if is_company_flag or is_company(name):
        return {"first_name": "", "middle_name": "", "last_name": name, "suffix": ""}
    owners = [p.strip() for p in re.split(r"\s+(?:OR|AND)\s+|\s*[&/]\s*", name, flags=re.I)
              if p.strip()]
    first_owner = owners[0]
    if len(owners) > 1 and len(first_owner.split()) == 1:
        first_owner = f"{first_owner} {owners[1].split()[-1]}"
    return split_name_111(first_owner)

def clean_city(raw) -> str:
    """
    Remove punctuation used as city separators.
    Preserve letters, numbers, and spaces.
    """
    city = str(raw or "")

    city = re.sub(r"[^A-Za-z0-9\s]", " ", city)
    city = re.sub(r"\s+", " ", city)

    return city.strip()

def split_city_state_zip(raw) -> dict:
    cleaned = " ".join(str(raw or "").split())

    cleaned = re.sub(
        r"\s+(?:US|USA|U\.S\.|U\.S\.A\.)$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    match = re.match(
        r"^(.*?)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$",
        cleaned,
        flags=re.IGNORECASE,
    )

    if not match:
        return {
            "city": "",
            "state": "",
            "zip_code": "",
        }

    return {
        "city": clean_city(match.group(1)),
        "state": match.group(2).upper(),
        "zip_code": match.group(3),
        }


UNIT_WORDS = r"APT|APARTMENT|UNIT|STE|SUITE|SPC|SPACE|LOT|BLDG|BUILDING|FL|FLOOR|RM|ROOM|TRLR|TRAILER|DEPT|PMB|BOX"


STREET_SUFFIXES = (r"STREET|ST|AVENUE|AVE|ROAD|RD|BOULEVARD|BLVD|DRIVE|DR|LANE|LN|"
                   r"COURT|CT|PLACE|PL|WAY|CIRCLE|CIR|PARKWAY|PKWY|TERRACE|TER|TRAIL|TRL")


def split_address(raw) -> tuple:
    t = " ".join(str(raw or "").split())
    # 'APT 85', 'STE. 200', '#4' at the end -> address 2
    m = re.search(
        rf"[\s,]+((?:{UNIT_WORDS})\.?\s*#?\s*(?:[A-Z0-9-]*\d[A-Z0-9-]*|[A-Z])|#\s*[A-Z0-9-]+)$",
        t, re.I,
    )
    if m and len(t[: m.start()].split()) >= 2:
        return t[: m.start()].strip(), m.group(1).strip()
    # '510E PLEASANT ST 6' -> number after the street type -> address 2
    m = re.search(rf"^(.*\b(?:{STREET_SUFFIXES})\.?)[\s,]+([A-Z]?\d+[A-Z]?|\d+-?[A-Z])$", t, re.I)
    if m and len(m.group(1).split()) >= 3:
        return m.group(1).strip(), m.group(2).strip()
    return t, ""


UNIT_AT_START = re.compile(
    rf"^((?:{UNIT_WORDS})\.?\s*#?\s*(?:[A-Z0-9-]*\d[A-Z0-9-]*|[A-Z])|#\s*[A-Z0-9-]+)[\s,]+(.+)$",
    re.I,
)


def address_fields(street, city_state_zip) -> dict:
    line1, line2 = split_address(street)
    csz = split_city_state_zip(city_state_zip)
    m = UNIT_AT_START.match(csz["city"])
    if m:
        line2 = " ".join(x for x in (line2, m.group(1).strip()) if x)
        csz["city"] = clean_city(m.group(2))
    return {"address_1": line1, "address_2": line2, **csz}


DIRECTIONS = {
    "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
    "NORTHEAST": "NE", "NORTHWEST": "NW", "SOUTHEAST": "SE", "SOUTHWEST": "SW",
    "NORTHBOUND": "N", "SOUTHBOUND": "S", "EASTBOUND": "E", "WESTBOUND": "W",
}


def direction_code(raw) -> str:
    t = re.sub(r"[^A-Z]", "", str(raw or "").upper())
    return DIRECTIONS.get(t, t)


def distance_unit(raw) -> str:
    t = str(raw or "").upper().rstrip(".")
    if t in {"FEET", "FOOT", "FT", "F"}:
        return "F"
    if t in {"MILES", "MILE", "MI", "M"}:
        return "M"
    return t


def parse_offset(raw) -> dict:
    cleaned = re.sub(r"^OR:?\s*", "", str(raw or "").strip(), flags=re.I)
    m = re.match(
        r"^(\d+)\s+(FEET|FT|MILES?|MI)\.?\s+(NORTH|SOUTH|EAST|WEST)\s+OF\s+(.+)$",
        cleaned, re.I,
    )
    if not m:
        return {"or_distance": "", "unit": "", "direction": "", "reference_marker": cleaned}
    return {"or_distance": m.group(1), "unit": distance_unit(m.group(2)),
            "direction": direction_code(m.group(3)), "reference_marker": m.group(4).strip()}


# ---------- yes / no fields

def yes_no_na_from_airbag(c) -> str:
    return {"L": "YES", "M": "NO"}.get(text(c).upper(), "NA")


def vehicle_towed(party) -> str:
    tow = text(party.tow_company)
    disposition = text(party.disposition).upper()
    if tow or "TOW" in disposition:
        return "YES"
    if "DRIVEN" in disposition or disposition == "DRIVER":
        return "NO"
    return "NA"


def cited_value(raw) -> str:
    if raw is True or str(raw).upper() in {"YES", "Y", "TRUE"}:
        return "YES"
    if raw is False or str(raw).upper() in {"NO", "N", "FALSE"}:
        return "NO"
    return ""


def _marked(raw) -> bool:
    """A report-level mark. False, blank, NO, N, 0 and NONE are NOT marks; anything else printed is."""
    if isinstance(raw, str):
        return raw.strip().upper() not in {"", "NO", "N", "0", "FALSE", "NONE", "N/A", "NA", "NOT MARKED"}
    return bool(raw)


def hit_and_run(report) -> bool:
    return (_marked(value(report.report.felony_hit_and_run))
            or _marked(value(report.report.misdemeanor_hit_and_run)))


# A name box that holds only a placeholder word is keyed in LAST name, exactly like a blank one would be.
PLACEHOLDER_NAME = re.compile(
    r"^(?:PARKED(?:\s+(?:VEHICLE|VEH\.?|CAR|UNOCCUPIED))?|HIT\s*(?:AND|&|/|N)\s*RUN)\.?$", re.I)


def driver_name_fields(reported_name, parked: bool, hit_and_run_flag: bool) -> dict:
    """Key what is written. Only a BLANK name box gets a placeholder:
    PARKED (parked-vehicle box marked) has priority, then HIT AND RUN (the report is a hit and run)."""
    name = " ".join(str(reported_name or "").split())
    if name and not PLACEHOLDER_NAME.match(name):
        return split_name_111(name)
    names = split_name_111("")
    if name:
        names["last_name"] = name
    elif parked:
        names["last_name"] = "PARKED"
    elif hit_and_run_flag:
        names["last_name"] = "HIT AND RUN"
    return names


def has_vehicle_data(party) -> bool:
    fields = (party.driver_name, party.driver_license_number,
              party.license_plate, party.vin, party.vehicle_make)
    return any(text(f) for f in fields) or bool(getattr(party, "parked_vehicle", False))


# ---------- injured / witness / passengers

def is_injured_driver(person, party_number: int) -> bool:
    return (not person.witness_only and not person.passenger_only
            and text(person.injured_was).upper().startswith("DRIVER")
            and text(person.party_number) == str(party_number))


def person_role(person) -> str:
    if person.witness_only:
        return "WITNESS"
    if person.passenger_only:
        return "PASSENGER"
    was = text(person.injured_was).upper()
    if was.startswith("PASS"):
        return "PASSENGER"
    if was.startswith("PED"):
        return "PEDESTRIAN"
    if was.startswith("BICYC"):
        return "BICYCLIST"
    if was.startswith("DRIVER"):
        return "DRIVER"
    return "OTHER"


def map_other_party(person) -> dict:
    return {
        "role": person_role(person),
        "party_number": text(person.party_number),
        **split_name_111(text(person.name)),
        **normalize_other_party_address(
            text(person.street_address),
            text(person.city_state_zip),
        ),
        "date_of_birth": to_mmddyyyy(value(person.birth_date)),
        "home_phone": format_phone(value(person.telephone)),
        "sex": text(person.sex),
        "age": text(person.age),
        "seat_position": text(person.seat_position),
        "safety_equipment": text(person.safety_equipment),
        "injury_code": injury_code(value(person.extent_of_injury)),
        "ejected": ejected_code(value(person.ejected)),
        "taken_to": text(person.taken_to),
    }
    
def normalize_other_party_address(street, location) -> dict:
    street = " ".join(str(street or "").split())
    location = " ".join(str(location or "").split())

    # Remove trailing country marker.
    combined = " ".join(
        part for part in (street, location) if part
    )

    combined = re.sub(
        r"\s+(?:US|USA|U\.S\.|U\.S\.A\.)$",
        "",
        combined,
        flags=re.IGNORECASE,
    ).strip()

    # Extract state and ZIP from the end.
    match = re.match(
        r"^(.*?)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$",
        combined,
        flags=re.IGNORECASE,
    )

    if not match:
        return address_fields(street, location)

    before_state = match.group(1)
    state = match.group(2).upper()
    zip_code = match.group(3)

    # Recognize a unit followed by the city.
    unit_match = re.match(
        r"^(.*?\b(?:APT|APARTMENT|UNIT|STE|SUITE|"
        r"SPC|SPACE|LOT|BLDG|BUILDING|FL|FLOOR|"
        r"RM|ROOM|TRLR|TRAILER|PMB|BOX)\.?"
        r"\s*#?\s*[A-Z0-9-]+)\s+(.+)$",
        before_state,
        flags=re.IGNORECASE,
    )

    if unit_match:
        street_part = unit_match.group(1).strip()
        city = unit_match.group(2).strip()
    else:
        # If location already contains CITY STATE ZIP,
        # preserve the existing street field.
        parsed = split_city_state_zip(location)

        if parsed["city"]:
            return {
                **address_fields(street, location),
            }

        return {
            "address_1": street,
            "address_2": "",
            "city": "",
            "state": state,
            "zip_code": zip_code,
        }

    address_1, address_2 = split_address(street_part)

    return {
        "address_1": address_1,
        "address_2": address_2,
        "city": city,
        "state": state,
        "zip_code": zip_code,
    }

# ---------- mapping

OWNER_KEYS = ("first_name", "middle_name", "last_name", "suffix",
              "same_as_driver_address", "address_1", "address_2",
              "state", "city", "zip_code")


def map_owner(party, driver: dict, notes: list) -> dict:
    same = value(party.owner_same_as_driver)
    owner_name = text(party.owner_name)

    if same is not False and not owner_name:
        owner = {k: driver.get(k, "") for k in OWNER_KEYS}
        owner["same_as_driver_address"] = True
        return owner

    names = owner_name_fields(owner_name, value(getattr(party, "owner_is_company", None)))
    if names["last_name"] == owner_name and not names["first_name"]:
        notes.append(f"Unit {party.party_number}: owner keyed as company '{owner_name}'.")

    owner = {**names, "same_as_driver_address": False,
             **address_fields(text(party.owner_street_address),
                              text(party.owner_city_state_zip))}
    return {k: owner.get(k, "") for k in OWNER_KEYS}


def map_party(report, party, notes: list) -> dict:
    n = party.party_number
    reported_name = text(party.driver_name)
    parked = bool(value(getattr(party, "parked_vehicle", False)))
    names = driver_name_fields(reported_name, parked, hit_and_run(report))
    if parked and not reported_name:
        notes.append(f"Unit {n}: driver name is blank and the parked-vehicle box is marked; keyed PARKED.")

    injured = next((p for p in report.people if is_injured_driver(p, n)), None)
    address = address_fields(
    text(party.street_address),
    text(party.city_state_zip),
)
    # Prefer individually extracted fields when available.
    address["city"] = (
        text(party.driver_city)
        or address["city"]
    )

    address["state"] = (
        text(party.driver_state)
        or address["state"]
    )

    address["zip_code"] = (
        text(party.driver_zip_code)
        or address["zip_code"]
    )
    driver = {
        **names,
        **address,
        "home_phone": format_phone(value(party.home_phone)),
        "date_of_birth": to_mmddyyyy(value(party.birth_date)),
        "drivers_license": text(party.driver_license_number),
        "drivers_license_state": text(party.driver_license_state),
        "injury_code": injury_code(value(injured.extent_of_injury)) if injured else "",
        "sobriety": first_code(party.sobriety, "Sobriety", n, notes),
        "safety_equipment": text(party.safety_equipment_code),
        "ejected": ejected_code(value(injured.ejected)) if injured else "",
        "taken_to": text(injured.taken_to) if injured else "",
        "charge": text(party.cited_section),
        "cited": cited_value(value(party.citation_issued)),
    }
    if injured and value(injured.extent_of_injury) and not driver["injury_code"]:
        notes.append(f"Unit {n}: injury '{text(injured.extent_of_injury)}' has no matching "
                     "code; Injury Code left blank.")

    vehicle = {
        "vin": text(party.vin),
        "tag_number": text(party.license_plate),
        "tag_state": text(party.license_plate_state),
        "year": text(party.vehicle_year),
        "make": text(party.vehicle_make),
        "model": text(party.vehicle_model),
        "insurance_carrier": text(party.insurance_carrier),
        "policy_number": text(party.policy_number),
        "vehicle_towed": vehicle_towed(party),
        "airbag_deployed": yes_no_na_from_airbag(value(party.air_bag_code)),
        "speed_limit": text(party.speed_limit),
        "direction_of_travel": direction_code(text(party.direction_of_travel)),
        "vehicle_type": text(party.vehicle_type),
        "damage_extent": damage_label(value(party.damage_severity)),
        "special_information": first_code(party.special_information, "Special Information", n, notes),
        "other_associated_factors": first_code(party.other_associated_factors, "Other Associated Factors", n, notes),
        "movement_preceding_collision": code(party.movement_preceding_crash),
    }
    return {"party_number": n,
            "owner": map_owner(party, driver, notes),
            "driver": driver, "vehicle": vehicle}


def map_ca_keying(report) -> dict:
    r, c = report.report, report.coding
    notes = []
    offset = parse_offset(value(r.intersection_or_offset))
    incident = {
        "report_identifier_1": text(r.local_report_number),
        "report_identifier_2": "",
        "incident_date": to_mmddyyyy(value(r.crash_date)),
        "time_2400": to_hhmm(value(r.crash_time)),
        "incident_state": "CA",
        "incident_city": text(r.city),
        "report_type": "A",
        "incident_street": text(r.crash_roadway),
        "incident_cross_street": offset["reference_marker"],
        "latitude": text(r.latitude),
        "longitude": text(r.longitude),
        "number_injured": text(r.number_injured),
        "reporting_district": text(r.reporting_district),
        "beat": text(r.beat),
        "officer_id": text(r.officer_id),
        "number_killed": text(r.number_killed),
        **offset,
        "party_at_fault": code(c.primary_factor_code),
        "weather": first_code(c.weather, "Weather", None, notes),
        "lighting": code(c.lighting),
        "road_surface": code(c.roadway_surface),
        "road_condition": first_code(c.roadway_conditions, "Road Condition", None, notes),
        "traffic_control_devices": code(c.traffic_control_device),
        "type_of_collision": code(c.crash_type),
        "motor_vehicle_involved_with": first_code(
            c.motor_vehicle_involved_with, "Motor Vehicle Involved With", None, notes),
    }
    vehicle_parties = sorted(
        (p for p in report.parties if has_vehicle_data(p)),
        key=lambda p: p.party_number,
    )
    units = [map_party(report, p, notes) for p in vehicle_parties]
    unit_numbers = {u["party_number"] for u in units}
    other_parties = [
        map_other_party(p) for p in report.people
        if not any(is_injured_driver(p, n) for n in unit_numbers)
    ]
    return {"incident": incident, "units": units,
            "other_parties": other_parties, "notes": notes}


