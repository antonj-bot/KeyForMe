"""NC keying-form selectors for the shared engine, read from the live-form capture (mock/nc/nc_form.html).

Field ids end in -t<N>, a form-wide counter (unit 1: owner t1, driver t2, vehicle t1; unit 2: owner t4, ...),
so ids are NOT predictable: every selector matches the id PREFIX. Selectors are resolved INSIDE the active tab
panel, where the owner block comes first and the driver block second:
  * a person field that exists in both blocks matches 2 controls (owner = first, driver = second);
  * the driver-only fields (alcohol/drugs, charge, contributing, protection, ejection, EMS) match 1 control.
The shared engine (controls.fill_person, strict_person_pairs) relies on exactly that.
Panel ids are tabs-1, tabs-2... in every section, so a panel is always looked up inside its own section.
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
    "weather": "#Incident_WeatherCondition",              # 4, 5 (multiselect)
    "road_condition": "#Incident_RoadSurfaceCondition",   # 3 (multiselect)
}
HIT_AND_RUN = "#Incident_IncidentHitAndRun-v1"            # checkbox, handled by nc_extras

OWNER = {
    "first_name": _text("Person_FirstName"), "middle_name": _text("Person_MiddleName"),
    "last_name": _text("Person_LastName"), "suffix": _text("Person_NameSuffix"),
    "address_1": _area("Person_Address"), "address_2": _area("Person_Address2"),
    "state": _text("Person_State"), "city": _text("Person_City"), "zip_code": _text("Person_ZipCode"),
}
DRIVER = {
    **OWNER,
    "phone": _text("Person_HomePhone"), "date_of_birth": _text("Person_DateOfBirth"),
    "drivers_license": _text("Person_DriversLicenseNumber"),
    "drivers_license_state": _text("Person_DriversLicenseJurisdiction"),
    "injury_code": _text("Person_InjuryStatus"),
    "alcohol_drugs": _text("Person_AlcoholDrugUse"),                       # 37 (multiselect)
    "charge": _text("Citations_CitationDetail"),                           # first charge; more via (+)
    "contributing": _text("Person_ContributingCircumstancesPerson"),       # 14-19 (multiselect)
    "protection": _text("Person_SafetyEquipmentRestraint"),                # 27 (multiselect)
    "ejection": _text("Person_Ejection"),                                  # 31
    "ems_to": _text("Person_TransportedTo"),                               # 47
}
VEHICLE = {
    "tag_number": _text("Vehicle_LicensePlate"), "tag_state": _text("Vehicle_RegistrationState"),
    "vin": _text("Vehicle_Vin"), "year": _text("Vehicle_ModelYear"), "make": _text("Vehicle_Make"),
    "model": _text("Vehicle_Model"), "insurance_carrier": _text("Vehicle_InsuranceCompany"),
    "policy_number": _text("Vehicle_InsurancePolicyNumber"),
    "impact_location": _text("Vehicle_DamagedAreas"),
    "vehicle_defects": _text("Vehicle_ContributingCircumstancesVehicle"),  # 59 (multiselect)
    "speed_limit": _text("Vehicle_PostedStatutorySpeedLimit"),             # 60
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
    "charge": _text("Citations_CitationDetail"),
    "nonmotorist_actions": _text("Person_NonMotoristActionsAtTimeOfCrash"),   # 8-9 (multiselect)
    "protection": _text("Person_SafetyEquipmentRestraint"), "ejection": _text("Person_Ejection"),
    "ems_to": _text("Person_TransportedTo"),
}
OTHER_KEYS = ("first_name", "middle_name", "last_name", "suffix", "address_1", "address_2", "state", "city",
              "zip_code", "phone", "date_of_birth", "drivers_license", "drivers_license_state", "injury_code",
              "alcohol_drugs", "charge", "nonmotorist_actions", "protection", "ejection", "ems_to")
# payload role -> text typed into the Party Type field. CONFIRM these against the Party Type list in the live app.
PERSON_TYPES = {
    "PASSENGER": "Passenger", "PEDESTRIAN": "Pedestrian", "PEDALCYCLIST": "Pedalcyclist",
    "NON-MOTORIST": "Non-Motorist", "UNKNOWN": "Unknown", "WITNESS": "Witness",
    "PROPERTY OWNER": "Property Owner",
}

# ---- controls the shared engine does not handle (nc_extras) -------------------------------------------
OWNER_SAME_AS_DRIVER_ADDRESS = 'input[type="checkbox"][id^="Person_SameAsDriverAddressGui-"]'   # unit panel: owner block only
OTHER_SAME_AS_DRIVER_ADDRESS = 'input[type="checkbox"][id^="Person_SameAsDriverAddressGui-"]'
OTHER_SAME_AS_OWNER_ADDRESS = 'input[type="checkbox"][id^="Person_SameAsOwnerAddressGui-"]'
CHARGE_ITEM = "td.citations div.item-content"            # one per charge
CHARGE_INPUT = 'input[id^="Citations_CitationDetail-"]'
CHARGE_ADD = "td.citations a.add-item"                   # the (+) link; the last one adds the next charge
