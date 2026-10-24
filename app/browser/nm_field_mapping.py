"""NM form selectors; pass field NAMES to person()/vehicle(), never CSS selectors."""
FRAME = "#formIframe"
UNIT_SECTION = "#section-page-base-owner-02"

INCIDENT = {
    "report_identifier_1": "#Incident_CaseIdentifier",
    "report_identifier_2": "#Incident_StateReportNumber",
    "incident_date": "#Incident_CrashDate",
    "time_2400": "#Incident_CrashTime",
    "incident_state": "#Incident_LossStateAbbr",
    "incident_city": "#Incident_CrashCity",
    "incident_street": "#Incident_LossStreet",
    "incident_cross_street": "#Incident_LossCrossStreet",
    "weather": "#Incident_WeatherCondition",
    "lighting": "#Incident_LightCondition",
    "district": "#Incident_Precinct",
    "first_harmful_event": "#Incident_CrashType",
    "intersection_type": "#Incident_IntersectionType",
}


from app.browser.selectors import person, vehicle




OWNER = {
    "first_name": person("FirstName"),
    "middle_name": person("MiddleName"),
    "last_name": person("LastName"),
    "address_1": person("Address"),
    "address_2": person("Address2"),
    "state": person("State"),
    "city": person("City"),
    "zip_code": person("ZipCode"),
    "home_phone": person("HomePhone"),
}
DRIVER = {
    **OWNER,
    "date_of_birth": person("DateOfBirth"),
    "drivers_license": person("DriversLicenseNumber"),
    "drivers_license_state": person("DriversLicenseJurisdiction"),
    "injury_code": person("InjuryStatus"),
    "sobriety": person("AlcoholDrugUse"),
    "ejected": person("Ejection"),
    "op_code": person("SafetyEquipmentRestraint"),
    "driver_actions": person("DriverActionsAtTimeOfCrash"),
    "sex": person("Sex"),
    "physical_condition": person("ConditionAtTimeOfCrash"),
    "seating_position": person("SeatingPosition"),
    # No verified OP Code control in the NM capture.
}
VEHICLE = {
    "vin": vehicle("Vin"),
    "tag_number": vehicle("LicensePlate"),
    "tag_state": vehicle("RegistrationState"),
    "year": vehicle("ModelYear"),
    "make": vehicle("Make"),
    "model": vehicle("Model"),
    "insurance_carrier": vehicle("InsuranceCompany"),
    "policy_number": vehicle("InsurancePolicyNumber"),
    "speed_limit": vehicle("PostedStatutorySpeedLimit"),
    "road_condition": vehicle("RoadSurfaceCondition"),
    "body_style": vehicle("BodyTypeCategory"),
    "traffic_control": vehicle("TrafficControlDeviceType"),
    "apparent_contributing_factors": vehicle("ContributingCircumstancesVehicle"),
    "road_design": vehicle("TrafficwayDescription"),
    "sequence_first": vehicle("EventSequence"),
}
