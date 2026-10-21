# KeyForMe fix5
"""CA keying form selectors (from the Codegen recording).

Everything lives inside #formIframe. Person/vehicle ids end in -tN, and N keeps
counting up as units and other parties are added, so selectors match the id
PREFIX and use :visible (only the active tab's fields are visible).
"""

FRAME_SELECTOR = "#formIframe"
UNIT_SECTION = "#section-page-base-owner-02"
OTHER_SECTION = "#section-page-base-passenger-03"

STRUCTURE = {
    "add_unit_button": "#section-page-base-owner-02 div.st-nav-add",
    "add_other_button": "#section-page-base-passenger-03 div.st-nav-add",
}

INCIDENT = {
    "report_identifier_1": "#Incident_CaseIdentifier",
    "report_identifier_2": "#Incident_StateReportNumber",
    "incident_date": "#Incident_CrashDate",
    "time_2400": "#Incident_CrashTime",
    "incident_state": "#Incident_LossStateAbbr",
    "incident_city": "#Incident_CrashCity",
    "report_type": "#Incident_ReportTypeId",
    "incident_street": "#Incident_LossStreet",
    "incident_cross_street": "#Incident_LossCrossStreet",
    "latitude": "#Incident_Latitude",
    "longitude": "#Incident_Longitude",
    "number_injured": "#Incident_TotalNonfatalInjuries",
    "reporting_district": "#Incident_Precinct",
    "beat": "#Incident_Beat",
    "officer_id": "#Incident_OfficerId",
    "number_killed": "#Incident_TotalFatalInjuries",
    "or_distance": "#Incident_NextStreetDistance",
    "unit": "#Incident_NextStreetDistanceMeasure",
    "direction": "#Incident_NextStreetDirection",
    "reference_marker": "#Incident_ReferenceMarkers",
    "party_at_fault": "#Incident_MostHarmfulEvent",
    "weather": "#Incident_WeatherCondition",
    "lighting": "#Incident_LightCondition",
    "road_surface": "#Incident_RoadSurfaceCondition",
    "road_condition": "#Incident_UnusualRoadCondition",
    "traffic_control_devices": "#Incident_TrafficControlTypeAtIntersection",
    "type_of_collision": "#Incident_CrashType",
    "motor_vehicle_involved_with": "#Incident_MotorVehicleInvolvedWith",
}


def _p(name: str) -> str:
    return f"[id^='Person_{name}-']:visible"


# Fields shared by Owner and Driver (Owner is the 1st match in a unit, Driver the 2nd).
PERSON = {
    "first_name": _p("FirstName"),
    "middle_name": _p("MiddleName"),
    "last_name": _p("LastName"),
    "suffix": _p("NameSuffix"),
    "sex": _p("Sex"),
    "address_1": _p("Address"),
    "address_2": _p("Address2"),
    "state": _p("State"),
    "city": _p("City"),
    "zip_code": _p("ZipCode"),
    "home_phone": _p("HomePhone"),
    "date_of_birth": _p("DateOfBirth"),
    "drivers_license": _p("DriversLicenseNumber"),
    "drivers_license_state": _p("DriversLicenseJurisdiction"),
    "injury_code": _p("InjuryStatus"),
}

OWNER = {**PERSON, "same_as_driver_address": _p("SameAsDriverAddressGui")}

DRIVER = {
    **PERSON,
    "same_as_owner": "input[name*='Same_as_Driver_GUI']:visible",
    "sobriety": _p("ConditionAtTimeOfCrashCA"),
    "safety_equipment": _p("SafetyEquipmentRestraint"),
    "ejected": _p("Ejection"),
    "taken_to": _p("TransportedTo"),
    "other_associated_factors_inattention": _p("DriverDistractedBy"),
    "charge": "[id^='Citations_ViolationCode-']:visible",
    "cited_yes": "[id^='Citations_CitationIssued-'][id$='YES']:visible",
    "cited_no": "[id^='Citations_CitationIssued-'][id$='NO']:visible",
}

# Other Parties (passengers, witnesses, pedestrians, bicyclists).
OTHER = {
    "person_type": _p("PersonType"),
    **PERSON,
    "unit_number": _p("VehicleUnitNumber"),
    "same_as_owner_address": _p("SameAsOwnerAddressGui"),
    "same_as_driver_address": _p("SameAsDriverAddressGui"),
    "sobriety": _p("ConditionAtTimeOfCrashCA"),
    "non_motorist_actions": _p("NonMotoristActionsAtTimeOfCrash"),
    "safety_equipment": _p("SafetyEquipmentRestraint"),
    "ejected": _p("Ejection"),
    "taken_to": _p("TransportedTo"),
}

# Codes the form's Person Type field expects. FILL THESE IN (see chat).
# Person Type options on the form, keyed by the role read from the report.
PERSON_TYPE_CODES = {
    "WITNESS": "Witness",
    "PASSENGER": "Passenger",
    "PEDESTRIAN": "Pedestrian",
    "BICYCLIST": "Pedalcyclist",  # the report says BICYCLIST, the form says Pedalcyclist
    "OTHER": "",                  # left blank on purpose, see below
}


def _v(name: str) -> str:
    return f"[id^='Vehicle_{name}-']:visible"

VIN_POPUP_OK = (
    "div.ui-dialog.ui-front.ui-dialog-buttons "
    "div.ui-dialog-buttonpane button:first-child"
)

VEHICLE = {
    "tag_number": _v("LicensePlate"),
    "tag_state": _v("RegistrationState"),
    "vin": _v("Vin"),
    "year": _v("ModelYear"),
    "make": _v("Make"),
    "model": _v("Model"),
    "insurance_carrier": _v("InsuranceCompany"),
    "policy_number": _v("InsurancePolicyNumber"),
    "policy_expiration_date": _v("InsuranceExpirationDate"),
    "impact_location": _v("DamagedAreas"),
    "speed_limit": _v("PostedStatutorySpeedLimit"),
    "direction_of_travel": _v("DirectionOfTravelBeforeCrash"),
    "vehicle_type": _v("VehicleType"),
    "damage_extent": _v("DamageRating"),
    "special_information": _v("VehicleSpecialUse"),
    "other_associated_factors": _v("ContributingCircumstancesVehicle"),
    "movement_preceding_collision": _v("VehicleManeuverActionPrior"),
}

RADIO_ROWS = {
    "vehicle_towed": "Vehicle Towed",
    "airbag_deployed": "Airbag Deployed",
}
