"""PA keying rules: pure functions, no browser, no AI. Run first - these are fast."""
import copy
import re
from datetime import date

import pytest

from app.keying import pa_rules as r
from app.keying.pa_rules import map_pa, pa_codes

try:
    from tests.pa_fixtures import coded, sample_raw
except ImportError:                                  # pytest puts tests/ itself on sys.path
    from pa_fixtures import coded, sample_raw

TODAY = date(2026, 10, 24)

# The UAT dropdown screenshot, typed independently of the catalogs in pa_rules.py.
APP_OPTIONS = {
    "weather": ["1 Not Adverse Conditions", "2 Rain", "3 Sleet(Hail)", "4 Snow", "5 Fog", "6 Rain & Fog",
                "7 Sleet & Fog", "8 Other", "9 Unknown"],
    "road_condition": ["0 Dry", "1 Dry", "2 Sand, Mud, Dirt, Oil", "3 Snow Covered", "4 slush", "5 Ice",
                       "6 Ice Patches", "7 Water - Standing or Moving", "8 Other"],
    "speed_limit": [f"{n:02d} {n} MPH" for n in range(5, 75, 5)] + ["90 Not Posted", "99 Unknown"],
    "injury_code": ["0 Not Injured", "1 Fatal Injury", "2 Suspected Serious Injury", "3 Suspected Minor Injury",
                    "4 Possible Injury", "5 Died Prior to Crash", "8 Injury, Unknown Severity", "9 Unknown if Injured"],
    "alcohol_drugs": ["Alcohol", "Alcohol and Drugs", "Illegal Drugs", "Medication", "No", "Unknown"],
    "nonmotorist_actions": ["00 None", "01 Entering Or Crossing At Specified Location",
                            "02 Walking, Running, Jogging, or Playing", "03 Working", "04 Pushing Vehicle",
                            "05 Approaching Or Leaving Vehicle", "06 Working On Vehicle", "07 Standing",
                            "98 Other", "99 Unknown"],
    "protection": ["00 None Used/ Not Applicable", "01 Shoulder Belt Used", "02 Lap Belt Used",
                   "03 Lap and Shoulder Belt Used", "04 Child Safety Seat Used", "05 Motorcycle Helmet Used",
                   "06 Bicycle Helmet Used", "10 Safety Belt Used Improperly", "11 Child Safety Seat Used Improperly",
                   "12 Helmet Used Improperly", "21 Child Safety Seat (Rear Facing)",
                   "22 Child Safety Seat (Front Facing)", "23 Booster Seat", "24 Child Restraint Unknown",
                   "90 Restraint Used, Type Unknown", "98 Other Restraint Type", "99 Unknown"],
    "helmet": ["0 No Helmet", "1 Full Helmet", "2 3/4 Helmet Style", "3 1/2 Helmet Style", "9 Unknown"],
    "ejection": ["0 Not Applicable", "1 Not Ejected", "2 Partially Ejected", "3 Totally Ejected", "9 Unknown"],
    "vehicle_defects": ["00 None", "01 Tires", "02 Brake System", "03 Steering System", "04 Suspension",
                        "05 Power Train", "06 Exhaust", "07 Headlights", "08 Signal Lights", "09 Other Lights",
                        "10 Horn", "11 Mirrors", "12 Wipers", "13 Driver Seating/Control",
                        "14 Body, Doors, Hood, Etc", "15 Trailer Hitch", "16 Wheels", "17 Airbags",
                        "18 Trailer Overloaded", "19 Unsecured/Shifted Trailer Load", "20 Improper Towing",
                        "21 Obstructed Windshield", "99 Unknown"],
    "driver_actions": ["00 No Contributing Action", "01 Driver Was Distracted", "02 Driving Using Hand Held Phone",
                       "03 Driving Using Hands Free Phone", "04 Making Illegal U-Turn",
                       "05 Improper/Careless Turning", "06 Turning From Wrong Lane",
                       "07 Proceeding W/O Clearance After Stop", "08 Running Stop Sign", "09 Running Red Light",
                       "10 Failure To Respond To other Traffic Control Device", "11 Tailgating",
                       "12 Sudden Slowing/Stopping", "13 Illegally Stopped On Road",
                       "14 Careless Passing Or Lane Change", "15 Passing In No Passing Zone",
                       "16 Driving The Wrong Way On 1-Way Street", "17 Careless Or Illegal Backing On Roadway",
                       "18 Driving On The Wrong Side Of Road", "19 Making Improper Entrance To Highway",
                       "20 Making Improper Exit From Highway", "21 Careless Parking/Unparking",
                       "22 Over/Under Compensation At Curve", "23 Speeding", "24 Driving Too Fast For Conditions",
                       "25 Failure To Maintain Proper Speed", "26 Driver Fleeing Police (Pol Chase)",
                       "27 Driver Inexperience", "28 Failure To Use Specialized Equip",
                       "31 Texting/Typing on Eletronic Device", "32 Dialing", "92 Affected By Physical Condition",
                       "98 Other Improper Driving Actions", "99 Unknown"],
}


# ----------------------------------------------------------------- catalogs
def test_catalogs_match_the_live_dropdown_screenshot():
    """The only known difference: the screenshot prints '1 Dry' for road surface, the SOP says code 1 is Wet."""
    assert r.check_catalog(APP_OPTIONS) == ["road_condition: app 1 'Dry' vs catalog 'Wet'"]


def test_check_catalog_reports_changes():
    bad = {"injury_code": ["0 Not Injured", "4 Maybe Hurt", "7 New Code"]}
    out = r.check_catalog(bad)
    assert any("4 'Maybe Hurt'" in p for p in out)
    assert any("7 'New Code'" in p and "no such code" in p for p in out)
    assert any("catalog code 1 'Fatal Injury' is not in the app list" in p for p in out)


def test_option_map():
    assert r.pa_option_map("injury_code")["4"] == "4 Possible Injury"
    assert r.pa_option_map("alcohol_drugs")["No"] == "No"


# ----------------------------------------------------------------- coded values
@pytest.mark.parametrize("raw,field,expected", [
    ("5", "speed_limit", "05"), ("35 MPH", "speed_limit", "35"), ("30", "speed_limit", "30"),
    ("NOT POSTED", "speed_limit", "90"), ("UNKNOWN", "speed_limit", "99"),
    (coded(code="0"), "protection", "00"), (coded(code="03"), "protection", "03"), (coded(code="3"), "protection", "03"),
    (coded(code="4"), "injury_code", "4"), (coded(code="8"), "injury_code", "8"),
    (coded("Lap and Shoulder Belt Used"), "protection", "03"),
    (coded("UNKNOWN"), "alcohol_drugs", "Unknown"), (coded("alcohol suspected"), "alcohol_drugs", "Alcohol"),
    (coded("Alcohol and Drugs"), "alcohol_drugs", "Alcohol and Drugs"), (coded("NO"), "alcohol_drugs", "No"),
    (coded("WET"), "road_condition", "1"), (coded("DRY"), "road_condition", "0"),
    (coded("SNOW"), "road_condition", "3"), (coded("ICE"), "road_condition", "5"),
    (coded("Rain"), "weather", "2"), (coded("Rain & Fog"), "weather", "6"), (coded("FOG"), "weather", "5"),
    (coded(code="2", text="Rain"), "weather", "2"),
    (coded("3/4 Helmet Style"), "helmet", "2"), (coded("1/2 Helmet Style"), "helmet", "3"),
    (coded("TEXTING/TYPING ON ELETRONIC DEVICE"), "driver_actions", "31"),
])
def test_codes_single(raw, field, expected):
    notes = []
    assert pa_codes(raw, field, notes) == expected


def test_number_present_in_dropdown_is_keyed_even_when_the_printed_words_differ():
    notes = []
    assert pa_codes(coded("Totally Ejected", "1"), "ejection", notes, "Unit 1 ejection") == "1"
    assert len(notes) == 1 and "keyed 1 (number wins)" in notes[0]


def test_description_wins_when_prefer_number_is_switched_off(monkeypatch):
    monkeypatch.setattr(r, "PREFER_NUMBER", False)
    assert pa_codes(coded("Totally Ejected", "1"), "ejection", []) == "3"


def test_number_not_in_dropdown_falls_back_to_description_then_blank():
    notes = []
    assert pa_codes(coded("Rain", "42"), "weather", notes) == "2"
    assert pa_codes(coded(code="42"), "weather", notes, "Weather") == ""
    assert notes == ["Weather: printed '42' is not in the PA dropdown; left blank"]


def test_unknown_description_is_blank_and_warns():
    notes = []
    assert pa_codes(coded("HAIL OF BULLETS"), "weather", notes, "Weather Conditions") == ""
    assert "left blank" in notes[0]


def test_weather_alias_is_flagged():
    notes = []
    assert pa_codes([coded("CLOUDY"), coded("CLOUDY")], "weather", notes) == "1"       # de-duplicated
    assert notes and "alias" in notes[0]


def test_multiselect_joins_with_semicolon_and_dedupes():
    assert pa_codes([coded(code="1"), coded("Wipers"), coded(code="01")], "vehicle_defects", []) == "01;12"


def test_single_value_field_keeps_first_and_warns():
    notes = []
    assert pa_codes([coded(code="0"), coded(code="1")], "injury_code", notes) == "0"
    assert "single-value" in notes[0]


def test_blank_and_null_words_are_skipped():
    assert pa_codes([coded(None, None), coded("null"), coded("N/A")], "weather", []) == ""
    assert pa_codes(None, "weather", []) == ""


def test_plain_strings_are_accepted():
    assert pa_codes(["42", "Rain"], "weather", []) == "2"                 # 42 is not a weather code -> description
    assert pa_codes("05", "weather", []) == "5"                           # codes compare as integers, dropdown spelling wins
    assert pa_codes("12 - Wipers", "vehicle_defects", []) == "12"


# ----------------------------------------------------------------- impact / airbag / towed
@pytest.mark.parametrize("raw,expected", [
    (["1"], "Right Front"), (["2"], "Right Side"), (["3"], "Right Side"), (["4"], "Right Side"),
    (["5"], "Right Rear"), (["6"], "Rear"), (["7"], "Left Rear"), (["8"], "Left Side"), (["9"], "Left Side"),
    (["10"], "Left Side"), (["11"], "Left Front"), (["12"], "Front"), (["12 O'CLOCK"], "Front"),
    (["13"], "Multiple"), (["14"], "Multiple"), (["15"], "Multiple"), (["99"], ""), (["UNKNOWN"], ""),
    (["13 = TOP"], "Multiple"), (["UNDERCARRIAGE"], "Multiple"), (["RIGHT FRONT"], "Right Front"),
    (["12", "6"], "Multiple"), (["3", "4"], "Right Side"), ([], ""), (None, ""), ([None, ""], ""),
])
def test_impact_location(raw, expected):
    assert r.pa_impact_location(raw) == expected


def test_impact_location_unreadable_value_warns():
    notes = []
    assert r.pa_impact_location(["somewhere"], notes) == ""
    assert "somewhere" in notes[0]


@pytest.mark.parametrize("raw,expected", [
    (["Not Deployed"], "NO"), (["Curtain"], "YES"), (["Front"], "YES"), (["Side"], "YES"), (["04"], "YES"),
    (["04 = Other (knee, airbelt, etc.)"], "YES"), (["97"], ""), (["97 = Not Applicable"], ""), (["N/A"], ""),
    (["Not Deployed", "Front"], "YES"), (["Not Deployed", "97"], "NO"), ([], ""), ([None], ""),
])
def test_airbag(raw, expected):
    assert r.pa_airbag(raw) == expected


@pytest.mark.parametrize("towed,by,expected", [
    ("YES", None, ("YES", "printed")), ("no", "", ("NO", "printed")), ("1", None, ("YES", "printed")),
    (None, "ABC TOWING", ("YES", "assumed")), (None, None, ("", "printed")), ("", "N/A", ("", "printed")),
])
def test_towed(towed, by, expected):
    assert r.pa_towed(towed, by) == expected


# ----------------------------------------------------------------- street, coordinates, date, report id
def test_street_and_cross_street():
    assert r.pa_street("12", "ROOSEVELT", "BOULEVARD", "1") == "12 ROOSEVELT BOULEVARD"
    assert r.pa_street(None, None, None, "SR 611") == "SR 611"          # route number only when no street
    assert r.pa_street(None, "IROQUOIS", None, "T420") == "IROQUOIS"
    assert r.pa_cross_street("GRANT", "AVENUE", "X") == "GRANT AVENUE"
    assert r.pa_cross_street(None, None, "ON EXIT OF SAMS CLUB") == "ON EXIT OF SAMS CLUB"


def test_coordinates_drop_colons_keep_numbers_and_periods():
    assert r.pa_coord("40:04:53.610") == "400453.610"
    assert r.pa_coord("-75 : 01 : 42 . 170".replace(" . ", ".")) == "-750142.170"
    assert r.pa_coord(None) == ""


def test_crash_date_year_comes_from_report_id_then_investigation_date():
    notes = []
    assert r.pa_crash_date("06/06,", ["PA 2025-701966"], "6/6/2025", notes, TODAY) == "06/06/2025"
    assert notes and "year 2025" in notes[0]
    assert r.pa_crash_date("06/06,", ["202607025541"], "07/23/2026", [], TODAY) == "06/06/2026"   # 12-digit id has no year
    assert r.pa_crash_date("07/19/2026", ["x"], None, [], TODAY) == "07/19/2026"
    notes = []
    assert r.pa_crash_date("06/06", ["x"], None, notes, TODAY) == ""
    assert "no year found" in notes[0]


def test_report_ids():
    raw = sample_raw()
    assert map_pa(raw, today=TODAY)["incident"]["report_identifier_1"] == "202607025541"
    assert map_pa(raw, today=TODAY)["incident"]["report_identifier_2"] == ""
    raw.update(incident_number="43-26-05679", report_number="W1074304")
    inc = map_pa(raw, today=TODAY)["incident"]
    assert (inc["report_identifier_1"], inc["report_identifier_2"]) == ("43-26-05679", "W1074304")
    raw.update(incident_number=None, report_number=None, cad_case_number="PA 2026-926780")
    inc = map_pa(raw, today=TODAY)["incident"]
    assert (inc["report_identifier_1"], inc["report_identifier_2"]) == ("PA 2026-926780", "")


# ----------------------------------------------------------------- violations
def test_violations_keep_type_text_and_charged():
    notes = []
    out = r.pa_violations([
        {"text": "75 3361", "charged": "YES", "primary": True},
        {"text": " 75 3714 ", "charged": "Warning"},
        {"text": "75 3111", "charged": "N"},
        {"text": "75 3112", "charged": "maybe"},
        {"text": None, "charged": "YES"},
        {"text": "", "charged": None},
    ], "Unit 1", notes)
    assert out == [{"kind": "primary", "text": "75 3361", "charged": "YES"},
                   {"kind": "violation", "text": "75 3714", "charged": "WARNING"},
                   {"kind": "violation", "text": "75 3111", "charged": "NO"},
                   {"kind": "violation", "text": "75 3112", "charged": ""}]
    assert any("maybe" in n for n in notes) and any("no violation text" in n for n in notes)


# ----------------------------------------------------------------- the mapper
def payload():
    return map_pa(sample_raw(), today=TODAY)


def test_incident_block():
    inc = payload()["incident"]
    assert inc == {
        "report_identifier_1": "202607025541", "report_identifier_2": "", "incident_date": "07/19/2026",
        "time_2400": "09:30", "incident_state": "PA", "incident_city": "PHILADELPHIA CITY",
        "incident_street": "ROOSEVELT BOULEVARD", "incident_cross_street": "GRANT AVENUE",
        "latitude": "400453.610", "longitude": "-750142.170", "weather": "1", "road_condition": "0",
        "speed_limit": "30", "hit_and_run": "1"}


def test_unit_one_payload():
    u = payload()["units"][0]
    assert u["party_number"] == 1 and u["hit_and_run"] is False
    d = u["driver"]
    assert (d["first_name"], d["last_name"], d["date_of_birth"], d["drivers_license"], d["drivers_license_state"]) == \
        ("BRITNEY", "CABAN", "09/06/1990", "29649264", "PA")
    assert d["address_1"] == "2225 NORTH LAWRENCE STREET" and d["zip_code"] == "19133"
    assert d["phone"] == "000 000-0000"
    assert d["injury_code"] == "0" and d["protection"] == "03" and d["ejection"] == "1"
    assert d["alcohol_drugs"] == "Unknown" and d["driver_actions"] == "24;23"
    assert d["ems_to"] == "NONE"
    assert d["violations"] == [{"kind": "primary", "text": "75 3361 SPEED", "charged": "YES"},
                               {"kind": "violation", "text": "75 3714 CARELESS", "charged": "WARNING"}]
    v = u["vehicle"]
    assert v["vin"] == "1HGCM56715A042022" and v["tag_state"] == "PA" and v["year"] == "2005"
    assert v["vehicle_towed"] == "YES" and v["impact_location"] == "Front" and v["vehicle_defects"] == "01"
    assert v["airbag_deployed"] == "YES"                     # driver Front + passenger Not Deployed -> YES
    assert u["trailers"] == [{"tag_number": "TRL1234", "tag_state": "PA", "vin": "", "year": "", "make": "UTILITY"}]


def test_owner_is_keyed_as_printed_never_copied_when_filled():
    raw = sample_raw()
    raw["units"][0]["owner"].update(first="OTHER", last="PERSON", address_1="1 ELSEWHERE RD", city="ERIE", zip="16501")
    raw["units"][0]["owner_is_driver"] = True                 # ticked, but the owner boxes are filled: keep them
    o = map_pa(raw, today=TODAY)["units"][0]["owner"]
    assert (o["first_name"], o["last_name"], o["address_1"], o["city"]) == ("OTHER", "PERSON", "1 ELSEWHERE RD", "ERIE")


def test_owner_copies_driver_only_into_empty_fields_when_the_report_says_so():
    raw = sample_raw()
    raw["units"][0]["owner"] = {"last": "SAME AS DRIVER", "address_1": "SAME"}
    p = map_pa(raw, today=TODAY)
    o = p["units"][0]["owner"]
    assert (o["first_name"], o["last_name"]) == ("BRITNEY", "CABAN") and o["address_1"] == "2225 NORTH LAWRENCE STREET"
    assert any("copied from the driver" in n for n in p["notes"])
    raw["units"][0]["owner"] = {"first": "ACME", "last": None}      # ticked box + partly filled name -> name kept
    raw["units"][0]["owner_is_driver"] = True
    o = map_pa(raw, today=TODAY)["units"][0]["owner"]
    assert o["first_name"] == "ACME" and o["last_name"] == ""
    assert o["address_1"] == "2225 NORTH LAWRENCE STREET"            # only the empty address is copied


def test_plain_empty_owner_stays_empty_unless_switched_on(monkeypatch):
    raw = sample_raw()
    raw["units"][0]["owner"] = {}
    assert map_pa(raw, today=TODAY)["units"][0]["owner"]["last_name"] == ""
    monkeypatch.setattr(r, "COPY_DRIVER_WHEN_OWNER_BLANK", True)
    assert map_pa(raw, today=TODAY)["units"][0]["owner"]["last_name"] == "CABAN"


def test_hit_and_run_flag_is_per_unit():
    p = payload()
    assert p["units"][0]["hit_and_run"] is False
    assert p["units"][1]["hit_and_run"] is True and p["units"][1]["driver"]["last_name"] == "HIT AND RUN"
    assert p["incident"]["hit_and_run"] == "1"


def test_crash_level_hit_and_run_ticks_the_incident_box_but_no_unit():
    raw = sample_raw()
    raw["units"][1]["hit_and_run"] = False
    p = map_pa(raw, today=TODAY)
    assert p["incident"]["hit_and_run"] == "1"
    assert [u["hit_and_run"] for u in p["units"]] == [False, False]
    assert p["units"][1]["driver"]["last_name"] == ""
    assert any("no unit is tied" in n for n in p["notes"])
    raw["hit_and_run_crash"] = False
    assert map_pa(raw, today=TODAY)["incident"]["hit_and_run"] == ""


def test_passenger_other_party():
    others = payload()["other_parties"]
    pax = others[0]
    assert pax["role"] == "PASSENGER" and pax["person_type"] == "Passenger" and pax["vehicle_number"] == "1"
    assert (pax["first_name"], pax["last_name"]) == ("NAHZYRA", "EUTSEY")
    assert pax["address_1"] == "1228 VETERANS HWY"
    assert pax["address_2"] == "APT H5"
    assert pax["date_of_birth"] == ""                       # 99/99/9999 is a placeholder
    assert pax["injury_code"] == "4" and pax["protection"] == "03" and pax["ems_to"] == "TEMPLE"


def test_witness_and_property_owner():
    raw = sample_raw()
    raw["property_owners"] = [{"last": "CITY OF PHILADELPHIA", "address_1": "1 CITY HALL"}, {}]
    p = map_pa(raw, today=TODAY)
    roles = [o["role"] for o in p["other_parties"]]
    assert roles == ["PASSENGER", "WITNESS", "PROPERTY OWNER"]
    assert p["other_parties"][1]["phone"] == "215 555-0100"
    assert any("no name or address" in n for n in p["notes"])


def test_pedestrian_unit_becomes_an_other_party_without_a_vehicle_tab():
    raw = sample_raw()
    raw["units"].append({"number": 3, "unit_type": "PEDESTRIAN", "driver": {"first": "PAT", "last": "WALKER"},
                         "owner": {}, "vehicle": {}})
    raw["occupants"].append({"unit": "3", "person_no": "1", "person_type": coded("PEDESTRIAN"),
                             "first": "PAT", "last": "WALKER", "injury": [coded(code="3")],
                             "pedestrian_actions": [coded(code="1")]})
    p = map_pa(raw, today=TODAY)
    assert [u["party_number"] for u in p["units"]] == [1, 2]
    ped = [o for o in p["other_parties"] if o["role"] == "PEDESTRIAN"]
    assert len(ped) == 1 and ped[0]["last_name"] == "WALKER" and ped[0]["injury_code"] == "3"
    assert ped[0]["nonmotorist_actions"] == "01" and ped[0]["vehicle_number"] == ""


def test_person_roles():
    n = []
    assert r.pa_person_role(coded("Passenger"), "p", n) == ("PASSENGER", "Passenger")
    assert r.pa_person_role(coded("PEDESTRIAN"), "p", n) == ("PEDESTRIAN", "Pedestrian")
    assert r.pa_person_role(coded("Bicyclist"), "p", n) == ("PEDALCYCLIST", "Pedalcyclist")
    assert r.pa_person_role(coded("Other Non-Motorist"), "p", n) == ("NON-MOTORIST", "Non-Motorist")
    assert r.pa_person_role(coded("DRIVER"), "p", n) == ("DRIVER", "Driver")
    assert r.pa_person_role(coded("Martian"), "p", n) == ("UNKNOWN", "Unknown") and "Martian" in n[0]
    assert r.pa_person_role(None, "p", n) == ("UNKNOWN", "Unknown")


def test_second_driver_row_becomes_unknown():
    raw = sample_raw()
    raw["occupants"].append({"unit": "1", "person_no": "3", "person_type": coded("DRIVER"), "first": "EXTRA", "last": "ROW"})
    others = map_pa(raw, today=TODAY)["other_parties"]
    assert any(o["role"] == "UNKNOWN" and o["last_name"] == "ROW" for o in others)


def test_null_words_are_blank():
    raw = sample_raw()
    raw["units"][0]["driver"]["first"] = "null"
    raw["units"][0]["vehicle"]["make"] = "NULL"
    u = map_pa(raw, today=TODAY)["units"][0]
    assert u["driver"]["first_name"] == "" and u["vehicle"]["make"] == ""


def test_short_vin_and_assumed_towed_and_trailer_tag_year_are_flagged():
    raw = sample_raw()
    raw["units"][0]["vehicle"].update(vin="ABC123", towed=None)
    notes = map_pa(raw, today=TODAY)["notes"]
    assert any("VIN has 6 characters" in n for n in notes)
    assert any("Vehicle Towed is blank" in n for n in notes)
    assert any("Tag Year '2026' is a registration year" in n for n in notes)


def test_mapper_does_not_mutate_its_input():
    raw = sample_raw()
    before = copy.deepcopy(raw)
    map_pa(raw, today=TODAY)
    assert raw == before


def test_every_payload_key_has_a_form_selector_or_is_handled_elsewhere():
    """Guards against a payload key that silently never reaches the form."""
    from app.browser import pa_field_mapping as m
    from app.keying.nj_rules import _address, person_from_boxes
    p = payload()
    # whatever the shared NJ helpers add on their own (they are used the same way by NC) is not PA's concern
    engine_only = {"violations", "hit_and_run", "role", "party_number", "person_type", "vehicle_number"}
    engine_only |= set(_address({}, "x", [])) | set(person_from_boxes("", "", ""))
    engine_only -= set(m.OWNER)
    for key in p["units"][0]["driver"]:
        assert key in m.DRIVER or key in engine_only, f"driver.{key} has no selector"
    for key in p["units"][0]["owner"]:
        assert key in m.OWNER, f"owner.{key} has no selector"
    for key in p["units"][0]["vehicle"]:
        assert key in m.VEHICLE or key in m.RADIO_FIELDS, f"vehicle.{key} has no selector"
    for key in p["incident"]:
        assert key in m.INCIDENT or key == "hit_and_run", f"incident.{key} has no selector"
    for o in p["other_parties"]:
        for key in o:
            assert key in m.OTHER or key in engine_only or key in ("role", "suffix"), f"other.{key} has no selector"
    for role in {o["role"] for o in p["other_parties"]}:
        assert role in m.PERSON_TYPES
