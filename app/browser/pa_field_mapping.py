"""PA keying-form selectors for the shared engine, read from the live-form capture (mock/pa/pa_form.html).

Field ids end in -t<N>, a form-wide counter (unit 1: owner t1, driver t2, vehicle t1; unit 2: owner t4, ...),
so ids are NOT predictable: every selector matches the id PREFIX. Selectors are resolved INSIDE the active tab
panel, where the owner block comes first and the driver block second:
  * a person field that exists in both blocks matches 2 controls (owner = first, driver = second);
  * the driver-only fields (alcohol/drugs, driver actions, pedestrian actions, safety equipment, helmet, ejection,
    medical facility) match 1 control.
The shared engine (controls.fill_person, strict_person_pairs) relies on exactly that.

What the engine cannot do for PA (violation rows with their two radio groups, trailers) lives in pa_extras.py;
its selectors are at the bottom of this file.
"""
FRAME = "#formIframe"
UNIT_SECTION = "#section-page-base-owner-02"          # owner + driver + vehicle, one tab per vehicle
OTHER_SECTION = "#section-page-base-passenger-03"     # one tab per other party
TAB_ANCHORS = "li[role='tab'] > a.ui-tabs-anchor[role='presentation']"


def _text(stem):
    return f'input[id^="{stem}-"]:not([type="hidden"])'


def _area(stem):
    return f'textarea[id^="{stem}-"]'


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
    "weather": "#Incident_WeatherCondition",                          # multiselect
    "road_condition": "#Incident_RoadSurfaceCondition",               # multiselect
    "speed_limit": "#Incident_LossCrossStreetSpeedLimitDropDown",
}
HIT_AND_RUN = "#Incident_IncidentHitAndRun-v1"            # checkbox, handled by pa_extras

OWNER = {
    "first_name": _text("Person_FirstName"), "middle_name": _text("Person_MiddleName"),
    "last_name": _text("Person_LastName"), "suffix": _text("Person_NameSuffix"),
    "address_1": _area("Person_Address"), "address_2": _area("Person_Address2"),
    "state": _text("Person_State"), "city": _text("Person_City"), "zip_code": _text("Person_ZipCode"),
    "phone": _text("Person_HomePhone"),
}
DRIVER = {
    **OWNER,
    "date_of_birth": _text("Person_DateOfBirth"),
    "drivers_license": _text("Person_DriversLicenseNumber"),
    "drivers_license_state": _text("Person_DriversLicenseJurisdiction"),
    "injury_code": _text("Person_InjuryStatus"),
    "alcohol_drugs": _text("Person_AlcoholDrugUse"),                       # multiselect
    "driver_actions": _text("Person_DriverActionsAtTimeOfCrash"),          # Driver Actions (D), multiselect
    "nonmotorist_actions": _text("Person_NonMotoristActionsAtTimeOfCrash"),  # Pedestrian Actions (P), multiselect
    "protection": _text("Person_SafetyEquipmentRestraint"),                # E - Safety Equipment 1, multiselect
    "helmet": _text("Person_SafetyEquipmentHelmet"),                       # Driver / Passenger Helmet Type
    "ejection": _text("Person_Ejection"),                                  # G - Ejection
    "ems_to": _text("Person_TransportedTo"),                               # Medical Facility
}
VEHICLE = {
    "tag_number": _text("Vehicle_LicensePlate"), "tag_state": _text("Vehicle_RegistrationState"),
    "vin": _text("Vehicle_Vin"), "year": _text("Vehicle_ModelYear"), "make": _text("Vehicle_Make"),
    "model": _text("Vehicle_Model"), "insurance_carrier": _text("Vehicle_InsuranceCompany"),
    "policy_number": _text("Vehicle_InsurancePolicyNumber"),
    "policy_expiration": _text("Vehicle_InsuranceExpirationDate"),
    "impact_location": _text("Vehicle_DamagedAreas"),
    "vehicle_defects": _text("Vehicle_ContributingCircumstancesVehicle"),  # Possible Vehicle Failures (V)
}
RADIO_FIELDS = {"vehicle_towed": "VehicleTowed", "airbag_deployed": "AirBagDeployed"}

OTHER = {
    "person_type": _text("Person_PersonType"), "unit_number": _text("Person_VehicleUnitNumber"),
    "first_name": _text("Person_FirstName"), "middle_name": _text("Person_MiddleName"),
    "last_name": _text("Person_LastName"), "suffix": _text("Person_NameSuffix"),
    "address_1": _area("Person_Address"), "address_2": _area("Person_Address2"),
    "state": _text("Person_State"), "city": _text("Person_City"), "zip_code": _text("Person_ZipCode"),
    "phone": _text("Person_HomePhone"), "date_of_birth": _text("Person_DateOfBirth"),
    "drivers_license": _text("Person_DriversLicenseNumber"),
    "drivers_license_state": _text("Person_DriversLicenseJurisdiction"),
    "injury_code": _text("Person_InjuryStatus"), "alcohol_drugs": _text("Person_AlcoholDrugUse"),
    "driver_actions": _text("Person_DriverActionsAtTimeOfCrash"),
    "nonmotorist_actions": _text("Person_NonMotoristActionsAtTimeOfCrash"),
    "protection": _text("Person_SafetyEquipmentRestraint"), "helmet": _text("Person_SafetyEquipmentHelmet"),
    "ejection": _text("Person_Ejection"), "ems_to": _text("Person_TransportedTo"),
}
OTHER_KEYS = ("first_name", "middle_name", "last_name", "suffix", "address_1", "address_2", "state", "city",
              "zip_code", "phone", "date_of_birth", "drivers_license", "drivers_license_state", "injury_code",
              "alcohol_drugs", "driver_actions", "nonmotorist_actions", "protection", "helmet", "ejection", "ems_to")

# payload role -> text typed into the Party Type field.
# UNVERIFIED: the wording below is NC's. Confirm each one against the Party Type list on the UAT site, then set
# PERSON_TYPES_VERIFIED = True (until then every PA fill logs a reminder).
PERSON_TYPES = {
    "PASSENGER": "Passenger", "PEDESTRIAN": "Pedestrian", "PEDALCYCLIST": "Pedalcyclist",
    "NON-MOTORIST": "Non-Motorist", "UNKNOWN": "Unknown", "WITNESS": "Witness",
    "PROPERTY OWNER": "Property Owner",
}
PERSON_TYPES_VERIFIED = False

# ---- controls the shared engine does not handle (pa_extras) ---------------------------------------------
# Violation rows: td.citations holds one div.item-content per violation; each has the type radios, the text input
# that matches the type, the (+) link and its own Charged? radios. Row-relative selectors (ids are not predictable).
CITATION_ITEM = "td.citations div.item-content"
CITATION_ADD = "td.citations a.add-item"                    # the last one adds the next row
CITATION_KIND = {                                           # radio value CITATION is labelled "Violation"
    "violation": 'input[type="radio"][id*="CitationOrViolation-"][value="CITATION"]',
    "primary": 'input[type="radio"][id*="CitationOrViolation-"][value="VIOLATION"]',   # "Primary Vehicle Code Violation"
}
CITATION_TEXT = {
    "violation": 'input[id^="Citations_CitationDetail-"]',
    "primary": 'input[id^="Citations_ViolationCode-"]',
}
CITATION_CHARGED = {
    "YES": 'input[type="radio"][id*="CitationIssued-"][value="YES"]',
    "NO": 'input[type="radio"][id*="CitationIssued-"][value="NO"]',
    "WARNING": 'input[type="radio"][id*="CitationIssued-"][value="WARNING"]',
}
# Trailers: the button in a unit panel creates a new tab whose owner/driver are copied by the site.
ADD_TRAILER = 'input[id^="Vehicle_AddTrailerGui-"]'
UNIT_NUMBER = 'input[id^="Vehicle_UnitNumber-"]'
