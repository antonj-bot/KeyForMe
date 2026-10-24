# KeyForMe fix4
from typing import Literal

from pydantic import BaseModel

Value = str | int | float | bool | None

PageKind = Literal["PARTY", "CODING", "INJURED_WITNESS", "SKETCH", "NARRATIVE", "OTHER"]


class PageKinds(BaseModel):
    kinds: list[PageKind]

class PageKindResult(BaseModel):
    kind: PageKind


class ReportFields(BaseModel):
    local_report_number: Value
    crash_date: Value
    crash_time: Value
    notification_date: Value
    notification_time: Value
    city: Value
    county: Value
    judicial_district: Value
    reporting_district: Value
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


class PartyPage1(BaseModel):
    party_number: int
    driver_license_number: Value
    driver_license_state: Value
    driver_license_class: Value
    driver_name: Value
    parked_vehicle: bool = False   # the PARKED VEHICLE box in the party strip
    street_address: Value
    city_state_zip: Value
    driver_city: Value
    driver_state: Value
    driver_zip_code: Value
    birth_date: Value
    home_phone: Value
    owner_same_as_driver: bool | None
    owner_name: Value
    owner_is_company: bool | None
    owner_street_address: Value
    owner_city_state_zip: Value
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
    disposition: Value
    tow_company: Value
    direction_of_travel: Value
    roadway: Value
    lane: Value
    speed_limit: Value


class Page2Party(BaseModel):
    """Coding-page columns are party numbers (1-3, or 4-6 on a second coding page)."""
    party_number: int
    citation_issued: Value
    cited_section: Value
    movement_preceding_crash: Value
    sobriety: list[str]
    other_associated_factors: list[str]
    special_information: list[str]


class PartyColumns(BaseModel):
    parties: list[Page2Party]

class MovementParty(BaseModel):
    party_number: int
    movement_preceding_crash: Value

class MovementColumns(BaseModel):
    parties: list[MovementParty]    

class Party(PartyPage1):
    citation_issued: Value
    cited_section: Value
    movement_preceding_crash: Value = None
    sobriety: list[str] = []
    other_associated_factors: list[str] = []
    special_information: list[str] = []


class CodingFields(BaseModel):
    primary_factor_code: Value
    traffic_control_device: Value
    crash_type: Value
    motor_vehicle_involved_with: list[str]
    weather: list[str]
    lighting: Value
    roadway_surface: Value
    roadway_conditions: list[str]
    pedestrian_action: Value


class Page1(BaseModel):
    is_california_chp555: bool
    detected_state: str | None
    report: ReportFields
    parties: list[PartyPage1]
    warnings: list[str]


class Page2(BaseModel):
    primary_factor_party: Value
    primary_factor_violation: Value
    primary_factor_cited: Value
    coding: CodingFields
    parties: list[Page2Party]
    warnings: list[str]


class InjuredPerson(BaseModel):
    """One filled row on the INJURED / WITNESS / PASSENGERS page."""
    witness_only: bool
    passenger_only: bool
    row_number: Value
    age: Value
    sex: Value
    extent_of_injury: Value   # FATAL / SUSPECTED SERIOUS / SUSPECTED MINOR / POSSIBLE
    injured_was: Value        # DRIVER / PASS. / PED. / BICYCLIST / OTHER
    party_number: Value
    seat_position: Value
    air_bag: Value
    safety_equipment: Value
    ejected: Value
    name: Value
    birth_date: Value
    street_address: Value
    city_state_zip: Value
    telephone: Value
    transported_by: Value
    ems_run_number: Value
    taken_to: Value


class InjuryPage(BaseModel):
    people: list[InjuredPerson]
    warnings: list[str]


class CaliforniaCHP555(BaseModel):
    document_state: Literal["CA"] = "CA"
    form_type: Literal["CHP_555"] = "CHP_555"
    report: ReportFields
    parties: list[Party]
    coding: CodingFields
    people: list[InjuredPerson] = []
    warnings: list[str] = []
