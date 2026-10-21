"""Structured NM SH 10074 extraction; all values are source-faithful strings."""
from pydantic import BaseModel, Field


class NMIncident(BaseModel):
    crash_report_number: str | None = None
    case_number: str | None = None
    crash_date: str | None = None
    crash_time: str | None = None
    city: str | None = None
    county: str | None = None
    occurred_on: str | None = None
    intersection_with: str | None = None
    weather: str | None = None
    lighting: str | None = None
    road_condition: str | None = None
    road_surface: str | None = None
    traffic_control: str | None = None
    intersection_type: str | None = None
    manner_of_impact: str | None = None
    officer_id: str | None = None
    reporting_district: str | None = None
    first_harmful_event: str | None = None
    district: str | None = None


class NMUnit(BaseModel):
    unit_number: int
    driver_first_name: str | None = None
    driver_middle_name: str | None = None
    driver_last_name: str | None = None
    driver_address: str | None = None
    driver_city: str | None = None
    driver_state: str | None = None
    driver_zip: str | None = None
    driver_phone: str | None = None
    driver_dob: str | None = None
    driver_license: str | None = None
    driver_license_state: str | None = None
    driver_injury_code: str | None = None
    driver_sobriety: str | None = None
    driver_ejected: str | None = None
    driver_safety_equipment: str | None = None
    owner_first_name: str | None = None
    owner_middle_name: str | None = None
    owner_last_name: str | None = None
    owner_company_name: str | None = None
    owner_address: str | None = None
    owner_city: str | None = None
    owner_state: str | None = None
    owner_zip: str | None = None
    owner_phone: str | None = None
    vin: str | None = None
    plate: str | None = None
    plate_state: str | None = None
    year: str | None = None
    make: str | None = None
    model: str | None = None
    color: str | None = None
    insurance_carrier: str | None = None
    policy_number: str | None = None
    direction: str | None = None
    posted_speed: str | None = None
    towed: str | None = None
    damage_severity: str | None = None
    driver_actions: str | None = None
    driver_sex: str | None = None
    driver_physical_condition: str | None = None
    driver_seating_position: str | None = None
    driver_op_code: str | None = None

    airbag_code: str | None = None
    body_style: str | None = None
    unit_road_condition: str | None = None
    unit_traffic_control: str | None = None
    road_design: str | None = None

    apparent_contributing_factors: str | None = None

    sequence_first: str | None = None
    sequence_second: str | None = None
    sequence_third: str | None = None
    sequence_fourth: str | None = None


class NMPageExtraction(BaseModel):
    incident: NMIncident | None = None
    units: list[NMUnit] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class NMReport(BaseModel):
    incident: NMIncident
    units: list[NMUnit]
    warnings: list[str] = Field(default_factory=list)

class NMConclusion(BaseModel):
    district: str | None = None
    officer_id: str | None = None
