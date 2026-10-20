"""CA keying form locators derived from Playwright recording.

All form controls live inside #formIframe. Repeated units are handled by first
activating the unit tab, then using visible controls. This avoids hard-coding
-t1, -t2, -t3 suffixes that change as units/people are added.
"""

FRAME_SELECTOR = "#formIframe"
UNIT_SECTION = "#section-page-base-owner-02"

STRUCTURE = {
    "add_unit_button": "#section-page-base-owner-02 div.st-nav-add",
    "delete_unit_button": "#formDeleteVehicle",
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
    "special_conditions": "#Incident_AccidentCondition",
    "number_injured": "#Incident_TotalNonfatalInjuries",
    "reporting_district": "#Incident_Precinct",
    "beat": "#Incident_Beat",
    "officer_id": "#Incident_OfficerId",
    "number_killed": "#Incident_TotalFatalInjuries",
    "milepost_distance": "#Incident_MilepostNextStreetDistance",
    "milepost_unit": "#Incident_MilepostNextStreetDistanceMeasure",
    "milepost_direction": "#Incident_MilepostNextStreetDirection",
    "milepost_marker": "#Incident_Milepost",
    "or_distance": "#Incident_NextStreetDistance",
    "unit": "#Incident_NextStreetDistanceMeasure",
    "direction": "#Incident_NextStreetDirection",
    "reference_marker": "#Incident_ReferenceMarkers",
    "party_at_fault": "#Incident_MostHarmfulEvent",
    "photographs_by": "#Incident_PhotographsBy",
    "weather": "#Incident_WeatherCondition",
    "lighting": "#Incident_LightCondition",
    "road_surface": "#Incident_RoadSurfaceCondition",
    "road_condition": "#Incident_UnusualRoadCondition",
    "traffic_control_devices": "#Incident_TrafficControlTypeAtIntersection",
    "type_of_collision": "#Incident_CrashType",
    "motor_vehicle_involved_with": "#Incident_MotorVehicleInvolvedWith",
}

# Prefix selectors deliberately omit the changing -tN suffix.
OWNER = {
    "first_name": "[id^='Person_FirstName-']:visible",
    "middle_name": "[id^='Person_MiddleName-']:visible",
    "last_name": "[id^='Person_LastName-']:visible",
    "suffix": "[id^='Person_NameSuffix-']:visible",
    "sex": "[id^='Person_Sex-']:visible",
    "same_as_driver_address": "[id^='Person_SameAsDriverAddressGui-']:visible",
    "address_1": "[id^='Person_Address-']:visible",
    "address_2": "[id^='Person_Address2-']:visible",
    "state": "[id^='Person_State-']:visible",
    "city": "[id^='Person_City-']:visible",
    "zip_code": "[id^='Person_ZipCode-']:visible",
    "home_phone": "[id^='Person_HomePhone-']:visible",
    "date_of_birth": "[id^='Person_DateOfBirth-']:visible",
    "drivers_license": "[id^='Person_DriversLicenseNumber-']:visible",
    "drivers_license_state": "[id^='Person_DriversLicenseJurisdiction-']:visible",
    "injury_code": "[id^='Person_InjuryStatus-']:visible",
}

DRIVER = {
    **OWNER,
    "same_as_owner": "input[name*='Same_as_Driver_GUI']:visible",
    "sobriety": "[id^='Person_ConditionAtTimeOfCrashCA-']:visible",
    "safety_equipment": "[id^='Person_SafetyEquipmentRestraint-']:visible",
    "ejected": "[id^='Person_Ejection-']:visible",
    "taken_to": "[id^='Person_TransportedTo-']:visible",
    "other_associated_factors_inattention": "[id^='Person_DriverDistractedBy-']:visible",
    "charge": "[id^='Citations_ViolationCode-']:visible",
    "cited_yes": "[id^='Citations_CitationIssued-'][id$='YES']:visible",
    "cited_no": "[id^='Citations_CitationIssued-'][id$='NO']:visible",
}

VEHICLE = {
    "tag_number": "[id^='Vehicle_LicensePlate-']:visible",
    "tag_state": "[id^='Vehicle_RegistrationState-']:visible",
    "vin": "[id^='Vehicle_Vin-']:visible",
    "year": "[id^='Vehicle_ModelYear-']:visible",
    "make": "[id^='Vehicle_Make-']:visible",
    "model": "[id^='Vehicle_Model-']:visible",
    "insurance_carrier": "[id^='Vehicle_InsuranceCompany-']:visible",
    "policy_number": "[id^='Vehicle_InsurancePolicyNumber-']:visible",
    "policy_expiration_date": "[id^='Vehicle_InsuranceExpirationDate-']:visible",
    "impact_location": "[id^='Vehicle_DamagedAreas-']:visible",
    "speed_limit": "[id^='Vehicle_PostedStatutorySpeedLimit-']:visible",
    "direction_of_travel": "[id^='Vehicle_DirectionOfTravelBeforeCrash-']:visible",
    "vehicle_type": "[id^='Vehicle_VehicleType-']:visible",
    "damage_extent": "[id^='Vehicle_DamageRating-']:visible",
    "special_information": "[id^='Vehicle_VehicleSpecialUse-']:visible",
    "other_associated_factors": "[id^='Vehicle_ContributingCircumstancesVehicle-']:visible",
    "movement_preceding_collision": "[id^='Vehicle_VehicleManeuverActionPrior-']:visible",
}

RADIO_ROWS = {
    "vehicle_towed": "Vehicle Towed Yes No NA",
    "airbag_deployed": "Airbag Deployed Yes No NA",
}
