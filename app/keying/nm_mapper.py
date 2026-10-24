"""NM mapping. Owner details intentionally include phone (unlike CA)."""



from __future__ import annotations
import re
from app.nm_models import NMReport

from app.keying.nm_dropdowns import apply_nm_dropdowns
from app.core.driver_rules import apply_placeholder_name


def phone(raw: str | None) -> str:
    return re.sub(r" +", " ", re.sub(r"[^0-9-]", " ", raw or "")).strip()


def date(raw: str | None) -> str:
    t = (raw or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})", t)
    return f"{m[2]}/{m[3]}/{m[1]}" if m else t


def clock(raw: str | None) -> str:
    t = (raw or "").strip()
    return t[:2] + ":" + t[2:] if re.fullmatch(r"\d{4}", t) else t


def address(raw: str | None) -> tuple[str, str]:
    t = (raw or "").strip()
    m = re.search(r"[\s,]+((?:APT|APARTMENT|UNIT|STE|SUITE|SPC|SPACE)\.?\s*#?\s*[A-Z0-9-]+)$", t, re.I)
    return (t[:m.start()].strip(), m[1]) if m else (t, "")

import re
from datetime import datetime


def nm_driver_license(raw) -> str:
    """Ignore dash-only or nonnumeric license placeholders."""
    text = str(raw or "").strip()

    return text if re.search(r"\d", text) else ""


def nm_dob(raw) -> str:
    """Only key complete, valid dates."""
    text = date(raw)

    if not re.fullmatch(r"\d{2}/\d{2}/\d{4}", text):
        return ""

    try:
        datetime.strptime(text, "%m/%d/%Y")
    except ValueError:
        return ""

    return text


def nm_airbag(raw) -> str:
    """Apply the NM airbag rule."""
    value = str(raw or "").strip().upper()

    if not value:
        return ""

    if value in {"N", "NA", "N/A"}:
        return "NO"

    if value.isalpha():
        return "YES"

    return ""

def nm_intersection_type(raw) -> str:
    """Map recognized intersection descriptions to NM form text."""
    value = " ".join(str(raw or "").upper().split())

    # Normalize separators for matching only.
    value = re.sub(r"[-_]+", " ", value)
    value = " ".join(value.split())

    mappings = {
        # Five-Point or More
        "FIVE POINT OR MORE": "FIVE-POINT OR MORE",
        "5 POINT OR MORE": "FIVE-POINT OR MORE",

        # Four-Way
        "FOUR WAY": "FOUR-WAY",
        "FOUR WAY INTERSECTION": "FOUR-WAY",
        "4 WAY": "FOUR-WAY",
        "4 WAY INTERSECTION": "FOUR-WAY",

        # L Int
        "L INT": "L INT",
        "L INTERSECTION": "L INT",

        # Not an Intersection
        "NOT AN INTERSECTION": "NOT AN INTERSECTION",

        # Roundabout
        "ROUNDABOUT": "ROUNDABOUT",

        # T Int
        "T INT": "T INT",
        "T INTERSECTION": "T INT",

        # Traffic Circle
        "TRAFFIC CIRCLE": "TRAFFIC CIRCLE",

        # Y Int
        "Y INT": "Y INT",
        "Y INTERSECTION": "Y INT",
    }

    return mappings.get(value, "")

def map_nm(report: NMReport) -> dict:
    incident = report.incident
    payload = {
        "incident": {
            "report_identifier_1": incident.case_number or "",
            "report_identifier_2": incident.crash_report_number or "",
            "incident_date": date(incident.crash_date),
            "time_2400": clock(incident.crash_time),
            "incident_state": "NM",
            "incident_city": incident.city or "",
            "incident_street": incident.occurred_on or "",
            "incident_cross_street": incident.intersection_with or "",
            "weather": incident.weather or "",
            "lighting": incident.lighting or "",
            "road_condition": incident.road_condition or "",
            "road_surface": incident.road_surface or "",
            "traffic_control_devices": incident.traffic_control or "",
            "type_of_collision": incident.manner_of_impact or "",
            "reporting_district": incident.reporting_district or "",
            "officer_id": incident.officer_id or "",
            "first_harmful_event": incident.first_harmful_event or "",
            "district": incident.district or incident.reporting_district or "",
            "intersection_type": nm_intersection_type(
                incident.intersection_type
            ),
        },
        "units": [],
        "other_parties": [],
        "notes": list(report.warnings),
    }
    for u in report.units:
        driver1, driver2 = address(u.driver_address)
        owner1, owner2 = address(u.owner_address)
        payload["units"].append({
            "party_number": u.unit_number,
            "driver": {
                "first_name": u.driver_first_name or "",
                "middle_name": u.driver_middle_name or "",
                "last_name": u.driver_last_name or "",
                "sex": u.driver_sex or "",
                "address_1": driver1, "address_2": driver2,
                "city": u.driver_city or "", "state": u.driver_state or "",
                "zip_code": u.driver_zip or "", "home_phone": phone(u.driver_phone),
                "date_of_birth": nm_dob(u.driver_dob),
                "drivers_license": nm_driver_license(u.driver_license),
                "drivers_license_state": u.driver_license_state or "",
                "injury_code": u.driver_injury_code or "",
                "sobriety": u.driver_sobriety or "",
                "ejected": u.driver_ejected or "",
                "safety_equipment": u.driver_safety_equipment or "",
                "driver_actions": u.driver_actions or "",
                "physical_condition": u.driver_physical_condition or "",
                "seating_position": u.driver_seating_position or "",
                "op_code": u.driver_op_code or "",
            },
            "owner": {
                "first_name": "" if u.owner_company_name else (u.owner_first_name or ""),
                "middle_name": "" if u.owner_company_name else (u.owner_middle_name or ""),
                "last_name": u.owner_company_name or u.owner_last_name or "",
                "address_1": owner1, "address_2": owner2,
                "city": u.owner_city or "", "state": u.owner_state or "",
                "zip_code": u.owner_zip or "", "home_phone": phone(u.owner_phone),
            },
            "vehicle": {
                "vin": u.vin or "", "tag_number": u.plate or "",
                "tag_state": u.plate_state or "", "year": u.year or "",
                "make": u.make or "", "model": u.model or "",
                "color": u.color or "", "insurance_carrier": u.insurance_carrier or "",
                "policy_number": u.policy_number or "",
                "direction_of_travel": u.direction or "",
                "speed_limit": u.posted_speed or "",
                "vehicle_towed": u.towed or "",
                "damage_extent": u.damage_severity or "",
                "airbag_deployed": nm_airbag(u.airbag_code),
                "body_style": u.body_style or "",
                "road_condition": u.unit_road_condition or "",
                "traffic_control": u.unit_traffic_control or "",
                "road_design": u.road_design or "",
                "apparent_contributing_factors": u.apparent_contributing_factors or "",
                "sequence_first": u.sequence_first or "",
                "sequence_second": u.sequence_second or "",
                "sequence_third": u.sequence_third or "",
                "sequence_fourth": u.sequence_fourth or "",
            },
        })
    # Blank driver name: PARKED (parked mark, priority) or HIT AND RUN (hit-and-run mark). A printed name always wins.
    # No notes are added here: NM filling is cancelled when the payload has notes.
    for source, unit in zip(report.units, payload["units"]):
        apply_placeholder_name(
            unit["driver"],
            bool(getattr(source, "parked_vehicle", None)),
            bool(getattr(source, "hit_and_run", None)),
        )
    return apply_nm_dropdowns(payload)
