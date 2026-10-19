import re
from typing import Any


def value(field: Any):
    return field.value if hasattr(field, "value") else field


def split_name_111(full_name: str | None) -> dict[str, str]:
    """Current CA rule: first token / middle token(s) / last token."""
    parts = (full_name or "").strip().split()
    if not parts:
        return {"first_name": "", "middle_name": "", "last_name": "", "suffix": ""}
    if len(parts) == 1:
        return {"first_name": parts[0], "middle_name": "", "last_name": "", "suffix": ""}
    if len(parts) == 2:
        return {"first_name": parts[0], "middle_name": "", "last_name": parts[1], "suffix": ""}
    return {"first_name": parts[0], "middle_name": " ".join(parts[1:-1]), "last_name": parts[-1], "suffix": ""}


def split_city_state_zip(text: str | None) -> dict[str, str]:
    match = re.match(r"^(.*?)\s+([A-Z]{2})\s+(\d{5}(?:-\d{4})?)$", (text or "").strip())
    if not match:
        return {"city": "", "state": "", "zip_code": ""}
    return {"city": match.group(1), "state": match.group(2), "zip_code": match.group(3)}


def parse_offset(text: str | None) -> dict[str, str | bool]:
    cleaned = (text or "").strip().rstrip(".")
    match = re.match(r"^(\d+)\s+(FEET|FT|MILES?|MI)\s+(NORTH|SOUTH|EAST|WEST)\s+OF\s+(.+)$", cleaned, re.I)
    if not match:
        return {"at_intersection": bool(cleaned), "or_distance": "", "unit": "", "direction": "", "reference_marker": cleaned}
    unit = "FT" if match.group(2).upper() in {"FEET", "FT"} else "MILES"
    return {"at_intersection": False, "or_distance": match.group(1), "unit": unit, "direction": match.group(3).upper(), "reference_marker": match.group(4).upper()}


def yes_no_na_from_airbag(code: str | None) -> str:
    return {"L": "YES", "M": "NO"}.get((code or "").upper(), "NA")


def vehicle_towed(party) -> str:
    tow = str(value(party.tow_company) or "").strip()
    disposition = str(value(party.disposition) or "").upper()
    if tow:
        return "YES"
    if "DRIVEN AWAY" in disposition or disposition == "DRIVER":
        return "NO"
    return "NA"


def hit_and_run(report) -> bool:
    return bool(value(report.report.felony_hit_and_run) or value(report.report.misdemeanor_hit_and_run))


def map_party(report, party) -> dict:
    reported_name = str(value(party.driver_name) or "").strip()
    names = split_name_111(reported_name)
    if hit_and_run(report) and not reported_name:
        names["last_name"] = "HIT AND RUN"

    address = split_city_state_zip(value(party.city_state_zip))
    driver = {
        **names,
        "address_1": value(party.street_address) or "",
        "address_2": "",
        **address,
        "date_of_birth": value(party.birth_date) or "",
        "drivers_license": value(party.driver_license_number) or "",
        "drivers_license_state": value(party.driver_license_state) or "",
        "safety_equipment": value(party.safety_equipment_code) or "",
        "ejected": getattr(party, "ejected", None) and value(party.ejected) or "",
        "taken_to": getattr(party, "taken_to", None) and value(party.taken_to) or "",
        "charge": value(party.cited_section) or "",
        "cited": "YES" if value(party.citation_issued) is True else "NO" if value(party.citation_issued) is False else "",
    }
    owner = {**driver, "same_as_driver_address": True}
    for removable in ("safety_equipment", "ejected", "taken_to", "charge", "cited"):
        owner.pop(removable, None)

    vehicle = {
        "vehicle_number": party.party_number,
        "tag_number": value(party.license_plate) or "",
        "tag_state": value(party.license_plate_state) or "",
        "vin": value(party.vin) or "",
        "year": value(party.vehicle_year) or "",
        "make": value(party.vehicle_make) or "",
        "model": value(party.vehicle_model) or "",
        "insurance_carrier": value(party.insurance_carrier) or "",
        "policy_number": value(party.policy_number) or "",
        "policy_expiration_date": "",
        "vehicle_towed": vehicle_towed(party),
        "airbag_deployed": yes_no_na_from_airbag(value(party.air_bag_code)),
        "impact_location": "",
        "speed_limit": value(party.speed_limit) or "",
        "direction_of_travel": value(party.direction_of_travel) or "",
        "vehicle_type": value(party.vehicle_type) or "",
        "damage_extent": value(party.damage_severity) or "",
    }
    return {"party_number": party.party_number, "owner": owner, "driver": driver, "vehicle": vehicle}


def map_ca_keying(report) -> dict:
    offset = parse_offset(value(report.report.intersection_or_offset))
    time_2400 = str(value(report.report.crash_time) or "").replace(":", "")
    incident = {
        "hit_and_run": hit_and_run(report),
        "report_identifier_1": value(report.report.local_report_number) or "",
        "report_identifier_2": "",
        "incident_date": value(report.report.crash_date) or "",
        "time_2400": time_2400,
        "incident_state": "CA",
        "incident_city": value(report.report.city) or "",
        "report_type": "A",
        "incident_street": value(report.report.crash_roadway) or "",
        "incident_cross_street": offset["reference_marker"],
        "latitude": value(report.report.latitude) or "",
        "longitude": value(report.report.longitude) or "",
        "number_injured": value(report.report.number_injured),
        "reporting_district": value(report.report.beat) or "",
        "beat": value(report.report.beat) or "",
        "officer_id": value(report.report.officer_id) or "",
        "number_killed": value(report.report.number_killed),
        **offset,
        "party_at_fault": value(report.coding.party_at_fault) or "",
        "weather": [value(x) for x in report.coding.weather],
        "lighting": value(report.coding.lighting) or "",
        "road_surface": value(report.coding.roadway_surface) or "",
        "road_condition": [value(x) for x in report.coding.roadway_conditions],
        "type_of_collision": value(report.coding.crash_type) or "",
    }
    units = [map_party(report, p) for p in sorted(report.parties, key=lambda x: x.party_number)]
    return {"incident": incident, "units": units, "other_parties": []}
