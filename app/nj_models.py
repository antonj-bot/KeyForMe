"""Pydantic schemas for what the AI reads from an NJTR-1 report.

These describe the PRINTED values only (key what you see). All keying decisions live in
app/keying/nj_rules.py. Every field has a default so a partly unreadable page still parses.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class NJPageKind(BaseModel):
    kind: Literal["UNIT", "NARRATIVE", "OTHER"]


class NJInventory(BaseModel):
    """Which vehicle numbers a unit page prints (fields 23 and 53) - nothing else."""
    vehicle_numbers: list[int] = Field(default_factory=list)
    uncertain: bool = False


class NJVehicleRaw(BaseModel):
    number: int | None = None
    side: Literal["LEFT", "RIGHT"] | None = None
    parked: bool = False
    hit_and_run: bool = False
    policy_number: str | None = None
    ins_code: str | None = None
    driver_first: str | None = None
    driver_middle: str | None = None
    driver_last: str | None = None
    driver_dob: str | None = None
    driver_license_number: str | None = None
    driver_license_state: str | None = None
    driver_address_1: str | None = None
    driver_city: str | None = None
    driver_state: str | None = None
    driver_zip: str | None = None
    alcohol_given: str | None = None
    owner_same_as_driver: bool = False
    owner_name: str | None = None
    owner_is_company: bool | None = None
    owner_address_1: str | None = None
    owner_city: str | None = None
    owner_state: str | None = None
    owner_zip: str | None = None
    vin: str | None = None
    year: str | None = None
    make: str | None = None
    model: str | None = None
    plate: str | None = None
    plate_state: str | None = None
    driven: bool = False
    left_at_scene: bool = False
    towed_disabled: bool = False
    towed_disabled_and_impounded: bool = False
    towed_impounded: bool = False
    charges: list[str] = Field(default_factory=list)
    damage_new: str | None = None        # margin box 130 (LEFT) / 132 (RIGHT)
    damage_old: str | None = None        # margin box 131 (LEFT) / 133 (RIGHT)
    contributing_codes: list[str] = Field(default_factory=list)   # 118a,118b (LEFT) / 119a,119b (RIGHT)


class NJOccupantRaw(BaseModel):
    row: str | None = None               # A-J
    vehicle: str | None = None           # column 83: a number, or P / B / O
    position: str | None = None          # column 84
    ejection: str | None = None          # 85
    injury: str | None = None            # 86
    age: str | None = None               # 87
    safety_available: str | None = None  # 92
    safety_used: str | None = None       # 93
    airbag: str | None = None            # 94
    hospital: str | None = None          # 95
    name: str | None = None              # name only, as printed
    address: str | None = None           # the rest of the name-and-address cell, as printed


class NJPropertyRaw(BaseModel):
    name: str | None = None
    address: str | None = None
    is_company: bool | None = None


class NJUnitPage(BaseModel):
    case_number: str | None = None
    police_dept: str | None = None
    crash_date: str | None = None
    crash_time: str | None = None
    road_name: str | None = None
    cross_road: str | None = None
    speed_limit: str | None = None
    latitude: str | None = None
    longitude: str | None = None
    weather_code: str | None = None          # margin box 103
    road_condition_code: str | None = None   # margin box 102
    form_shows_box_134: bool = True
    vehicles: list[NJVehicleRaw] = Field(default_factory=list)
    occupants: list[NJOccupantRaw] = Field(default_factory=list)
    property_owners: list[NJPropertyRaw] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class NJNarrativeItem(BaseModel):
    vehicle: int | None = None
    text: str = ""
    field: str | None = None                 # "25" for "... - Field 25"


class NJNarrativePage(BaseModel):
    occupants: list[NJOccupantRaw] = Field(default_factory=list)          # rows E-J
    other_descriptions: list[NJNarrativeItem] = Field(default_factory=list)
    additional_citations: list[NJNarrativeItem] = Field(default_factory=list)
    insurance_statements: list[NJNarrativeItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
