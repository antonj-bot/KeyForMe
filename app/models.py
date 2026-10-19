from typing import Literal
from pydantic import BaseModel, Field

class Evidence(BaseModel):
    page: Literal[1, 2]
    label: str
    raw_value: str | None = None

class Value(BaseModel):
    value: str | int | float | bool | None = None
    confidence: float = Field(ge=0, le=1)
    evidence: Evidence

class Party(BaseModel):
    party_number: int = Field(ge=1)
    driver_license_number: Value
    driver_license_state: Value
    driver_license_class: Value
    driver_name: Value
    street_address: Value
    city_state_zip: Value
    birth_date: Value
    vehicle_year: Value
    vehicle_make: Value
    vehicle_model: Value
    vehicle_color: Value
    license_plate: Value
    license_plate_state: Value
    vin: Value
    vehicle_type: Value
    air_bag_code: Value
    safety_equipment_code: Value
    insurance_carrier: Value
    policy_number: Value
    damage_severity: Value
    rollover: Value
    disposition: Value
    tow_company: Value
    direction_of_travel: Value
    roadway: Value
    lane: Value
    speed_limit: Value
    citation_issued: Value
    cited_section: Value

class ReportFields(BaseModel):
    local_report_number: Value
    crash_date: Value
    crash_time: Value
    notification_date: Value
    notification_time: Value
    city: Value
    county: Value
    judicial_district: Value
    beat: Value
    crash_roadway: Value
    intersection_or_offset: Value
    latitude: Value
    longitude: Value
    number_injured: Value
    number_killed: Value
    tow_away: Value
    felony_hit_and_run: Value
    misdemeanor_hit_and_run: Value
    ncic_number: Value
    officer_id: Value

class CodingFields(BaseModel):
    party_at_fault: Value
    primary_crash_factor: Value
    primary_violation_code: Value
    crash_type: Value
    weather: list[Value]
    lighting: Value
    roadway_surface: Value
    roadway_conditions: list[Value]
    pedestrian_action: Value

class CaliforniaCHP555(BaseModel):
    document_state: Literal['CA'] = 'CA'
    form_type: Literal['CHP_555'] = 'CHP_555'
    report: ReportFields
    parties: list[Party]
    coding: CodingFields
    warnings: list[str] = []
