"""NJ form selectors (from the captured NJ keying form).

Pass field NAMES to person()/vehicle(); never CSS selectors. Everything lives inside
#formIframe. Person/vehicle ids end in -tN and N keeps counting up as units and other
parties are added, so selectors match the id PREFIX and use :visible (only the active
tab's fields are visible).
"""
FRAME = "#formIframe"
UNIT_SECTION = "#section-page-base-owner-02"
OTHER_SECTION = "#section-page-base-passenger-03"


from app.browser.selectors import person, vehicle




INCIDENT = {
    "report_identifier_1": "#Incident_CaseIdentifier",
    "report_identifier_2": "#Incident_StateReportNumber",
    "incident_date": "#Incident_CrashDate",
    "time_2400": "#Incident_CrashTime",
    "incident_state": "#Incident_LossStateAbbr",
    "incident_city": "#Incident_CrashCity",
    "incident_street": "#Incident_LossStreet",
    "incident_cross_street": "#Incident_LossCrossStreet",
    "latitude": "#Incident_Latitude",
    "longitude": "#Incident_Longitude",
    "weather": "#Incident_WeatherCondition",
    "road_condition": "#Incident_RoadSurfaceCondition",
    "speed_limit": "#Incident_LossCrossStreetSpeedLimit",
}
HIT_AND_RUN = "#Incident_IncidentHitAndRun-v1"          # checkbox: handled by app/browser/nj_extras.py

_PERSON = {
    "first_name": person("FirstName"), "middle_name": person("MiddleName"), "last_name": person("LastName"),
    "suffix": person("NameSuffix"), "address_1": person("Address"), "address_2": person("Address2"),
    "state": person("State"), "city": person("City"), "zip_code": person("ZipCode"),
    "home_phone": person("HomePhone"), "date_of_birth": person("DateOfBirth"),
    "drivers_license": person("DriversLicenseNumber"), "drivers_license_state": person("DriversLicenseJurisdiction"),
    "injury_code": person("InjuryStatus"),
}
CHARGE = "[id^='Citations_CitationDetail-']:visible"
OWNER = dict(_PERSON)
DRIVER = {
    **_PERSON,
    "alcohol_test": person("AlcoholDrugTestGiven"), "charge": CHARGE,
    "safety_available": person("SafetyEquipmentAvailable"), "ejection": person("Ejection"),
    "hospital": person("TransportedToList"), "safety_used": person("SafetyEquipmentRestraint"),
}
VEHICLE = {
    "tag_number": vehicle("LicensePlate"), "tag_state": vehicle("RegistrationState"), "vin": vehicle("Vin"),
    "year": vehicle("ModelYear"), "make": vehicle("Make"), "model": vehicle("Model"),
    "insurance_carrier": vehicle("InsuranceCompany"), "policy_number": vehicle("InsurancePolicyNumber"),
    "policy_expiration_date": vehicle("InsuranceExpirationDate"),
    "contributing": vehicle("ContributingCircumstancesVehicle"), "impact_location": vehicle("DamagedAreas"),
}
OTHER = {
    **{k: v for k, v in _PERSON.items()},
    "person_type": person("PersonType"), "unit_number": person("VehicleUnitNumber"),
    "alcohol_test": person("AlcoholDrugTestGiven"), "charge": CHARGE,
    "safety_available": person("SafetyEquipmentAvailable"), "ejection": person("Ejection"),
    "hospital": person("TransportedToList"), "safety_used": person("SafetyEquipmentRestraint"),
    "same_as_driver_address": person("SameAsDriverAddressGui"),
    "same_as_owner_address": person("SameAsOwnerAddressGui"),
}
OTHER_KEYS = (
    "first_name", "middle_name", "last_name", "suffix", "address_1", "address_2", "state", "city", "zip_code",
    "home_phone", "date_of_birth", "injury_code", "alcohol_test", "safety_available", "ejection", "hospital",
    "safety_used",
)
# Party Type text on the form, keyed by the role in the payload (nj_rules writes the upper-case role).
PERSON_TYPES = {
    "PASSENGER": "Passenger", "UNKNOWN": "Unknown", "PEDESTRIAN": "Pedestrian",
    "PEDALCYCLIST": "Pedalcyclist", "PROPERTY OWNER": "Property Owner",
}
RADIO_FIELDS = {"vehicle_towed": "VehicleTowed", "airbag_deployed": "AirBagDeployed"}
TAB_ANCHORS = "li[role='tab'] > a.ui-tabs-anchor[role='presentation']"
