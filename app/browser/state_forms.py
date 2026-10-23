"""Adapters contain form differences, not copies of the filling workflow."""
from app.browser.form_spec import FormSpec
from app.browser import field_mapping as ca
from app.browser import nm_field_mapping as nm
from app.browser import nj_field_mapping as nj
from app.browser import nc_field_mapping as nc
from app.core.tabs import TabSpec

CA = FormSpec(
    state="CA", frame=ca.FRAME_SELECTOR, unit_section=ca.UNIT_SECTION,
    incident=ca.INCIDENT, owner=ca.OWNER, driver=ca.DRIVER, vehicle=ca.VEHICLE,
    person_order=("driver", "owner"), strict_person_pairs=False,
    tab_after_text=False, dropdown_prefix_codes=True, field_timeout_ms=30000,
    checkbox_fields=("same_as_driver_address", "same_as_owner"), cited=True,
    radio_rows=ca.RADIO_ROWS, popup_ok=ca.VIN_POPUP_OK,
    accept_native_dialogs=True,
    other_section=ca.OTHER_SECTION, other=ca.OTHER,
    other_keys=("first_name", "middle_name", "last_name", "suffix", "sex",
                "address_1", "address_2", "state", "city", "zip_code",
                "home_phone", "date_of_birth", "injury_code", "safety_equipment",
                "ejected", "taken_to"),
    person_types=ca.PERSON_TYPE_CODES,
)
NM = FormSpec(
    state="NM", frame=nm.FRAME, unit_section=nm.UNIT_SECTION,
    incident=nm.INCIDENT, owner=nm.OWNER, driver=nm.DRIVER, vehicle=nm.VEHICLE,
    tabs=TabSpec(anchors="li[role='tab'] > a.ui-tabs-anchor[role='presentation']", settle_ms=300),
    radio_fields={"vehicle_towed": "VehicleTowed", "airbag_deployed": "AirBagDeployed"},
    radios_before_vin=True, units_before_incident=True,
)
NJ = FormSpec(
    state="NJ", frame=nj.FRAME, unit_section=nj.UNIT_SECTION,
    incident=nj.INCIDENT, owner=nj.OWNER, driver=nj.DRIVER, vehicle=nj.VEHICLE,
    tabs=TabSpec(anchors=nj.TAB_ANCHORS, settle_ms=300),
    radio_fields=nj.RADIO_FIELDS, radios_before_vin=True, units_before_incident=True,
    other_section=nj.OTHER_SECTION, other=nj.OTHER, other_keys=nj.OTHER_KEYS,
    person_types=nj.PERSON_TYPES,
)

NC = FormSpec(
    state="NC", frame=nc.FRAME, unit_section=nc.UNIT_SECTION,
    incident=nc.INCIDENT, owner=nc.OWNER, driver=nc.DRIVER, vehicle=nc.VEHICLE,
    tabs=TabSpec(anchors=nc.TAB_ANCHORS, settle_ms=300),
    radio_fields=nc.RADIO_FIELDS, radios_before_vin=True, units_before_incident=True,
    other_section=nc.OTHER_SECTION, other=nc.OTHER, other_keys=nc.OTHER_KEYS,
    person_types=nc.PERSON_TYPES,
)

FORMS = {"CA": CA, "NM": NM, "NJ": NJ, "NC": NC}

def get_form_spec(state):
    code = str(state or "").strip().upper()
    if code not in FORMS:
        raise ValueError("No verified form adapter is registered for this state.")
    return FORMS[code]
