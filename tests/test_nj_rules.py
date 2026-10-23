"""Offline tests for app/keying/nj_rules.py  (no browser, no PDF, no AI).

Run:  python -m pytest tests/test_nj_rules.py -q
All names, numbers and addresses below are invented.
"""
import json
from datetime import date

import pytest

import nj_rules as nj  # in the project: from app.keying import nj_rules as nj

TODAY = date(2026, 10, 23)


# ------------------------------------------------------------ coded fields: numbers only
@pytest.mark.parametrize("fn,raw,expected", [
    (nj.weather, "02", "02"), (nj.weather, "02 Rain", "02"), (nj.weather, "2", "02"),
    (nj.weather, "10", "10"), (nj.weather, "11", ""), (nj.weather, "00", ""), (nj.weather, "-", ""), (nj.weather, "", ""),
    (nj.road_condition, "09", "09"), (nj.road_condition, "10", ""),
    (nj.injury_code, "04", "04"), (nj.injury_code, "06", ""), (nj.injury_code, "O", ""),
    (nj.ejection, "01", "01"), (nj.ejection, "05", ""),
    (nj.safety_equipment, "12", "12"), (nj.safety_equipment, "13", ""), (nj.safety_equipment, "04", "04"),
    (nj.hospital_code, "0101", "0101"), (nj.hospital_code, "-", ""), (nj.hospital_code, "", ""), (nj.hospital_code, None, ""),
])
def test_numeric_coded_fields(fn, raw, expected):
    assert fn(raw) == expected


def test_contributing_circumstances_are_keyed_without_leading_zero():
    assert nj.contributing(["01", "-"]) == "1"
    assert nj.contributing(["07", "60"]) == "7;60"
    assert nj.contributing(["25", "-"]) == "25"                 # 25 = None
    assert nj.contributing(["01", "1"]) == "1"                  # no duplicates
    assert nj.contributing(["00", "99", "26"]) == ""            # not in the NJ list
    assert nj.contributing([None, ""]) == ""


@pytest.mark.parametrize("codes,expected", [
    (["01"], "YES"), (["04"], "YES"), (["07"], "YES"), (["08"], "YES"),
    (["05"], "NO"), (["06"], "NO"), (["99"], ""), ([], ""), ([None, "-"], ""),
    (["06", "02"], "YES"),                       # any occupant deployed -> YES (General SOP)
    (["06", "99"], "NO"),
])
def test_airbag_table(codes, expected):
    assert nj.airbag(codes) == expected


@pytest.mark.parametrize("raw,expected", [
    ("12", "Front"), ("01", "Right Front"), ("02", "Right Front"), ("03", "Right Side"),
    ("04", "Right Rear"), ("05", "Right Rear"), ("06", "Rear"), ("07", "Left Rear"), ("08", "Left Rear"),
    ("09", "Left Side"), ("10", "Left Front"), ("11", "Left Front"),
    ("13", "Multiple"), ("14", "Multiple"), ("15", "Multiple"),
    ("17", ""), ("-", ""), ("NA", ""), ("", ""), (None, ""), ("16", ""),
])
def test_impact_location(raw, expected):
    assert nj.impact_location(raw) == expected


@pytest.mark.parametrize("raw,expected", [("No", "No"), ("NO", "No"), ("Yes", "Yes"), ("refused", "Refused"), ("", ""), ("-", "")])
def test_alcohol(raw, expected):
    assert nj.alcohol_test(raw) == expected


# ------------------------------------------------------------ dates / times
@pytest.mark.parametrize("raw,kw,expected", [
    ("07/18/2026", {}, "07/18/2026"), ("7/8/2026", {}, "07/08/2026"), ("2026-07-18", {}, "07/18/2026"),
    ("06/15/26", {}, "06/15/2026"), ("08-10-2026", {}, "08/10/2026"),
    ("05/13/06", {}, "05/13/2006"),                                  # "06" -> 2006
    ("05/13/89", {}, "05/13/1989"),
    ("05/13/06", {"age": 20, "ref_year": 2026}, "05/13/2006"),        # age decides the century
    ("05/13/36", {"age": 90, "ref_year": 2026}, "05/13/1936"),
    ("05/13/", {}, ""), ("05/13", {}, ""), ("02/30/2026", {}, ""), ("13/01/2026", {}, ""), ("", {}, ""), (None, {}, ""),
])
def test_norm_date(raw, kw, expected):
    assert nj.norm_date(raw, today=TODAY, **kw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("2041", "20:41"), ("16 01", "16:01"), ("16:01", "16:01"), ("941", "09:41"), ("0000", "00:00"),
    ("2460", ""), ("2400", ""), ("abc", ""), ("", ""), (None, ""),
])
def test_norm_time(raw, expected):
    assert nj.norm_time(raw) == expected


# ------------------------------------------------------------ names
def test_split_name_variants():
    assert nj.split_name("JAYDEN T STAPLETON") == {"first_name": "JAYDEN", "middle_name": "T", "last_name": "STAPLETON", "suffix": ""}
    assert nj.split_name("Richard B McKelvey III")["suffix"] == "III"
    assert nj.split_name("Richard B McKelvey III")["last_name"] == "McKelvey"
    assert nj.split_name("MARY ANN LEE")["middle_name"] == "ANN"
    assert nj.split_name("DOE, JOHN E") == {"first_name": "JOHN", "middle_name": "E", "last_name": "DOE", "suffix": ""}
    assert nj.split_name("Cher")["last_name"] == "Cher"                      # one name -> last name
    assert nj.split_name("JANE ROE")["middle_name"] == ""
    assert nj.split_name("") == {"first_name": "", "middle_name": "", "last_name": "", "suffix": ""}
    assert nj.split_name(None)["last_name"] == ""
    assert nj.split_name("UNKNOWN")["last_name"] == "UNKNOWN"                 # KWYS


def test_company_names_go_to_last_name():
    for name in ("Ean Holdings LLC", "NJTA", "ACME CORP", "City of Trenton", "SMITH & SONS", "PSEG"):
        got = nj.split_name(name)
        assert got["last_name"] == name and got["first_name"] == "" and got["middle_name"] == ""
    assert nj.split_name("Pat Smith", company=True)["last_name"] == "Pat Smith"   # extractor flag wins
    assert nj.split_name("Pat Smith", company=False)["first_name"] == "Pat"


def test_person_from_boxes():
    assert nj.person_from_boxes("MICHEAL", "T", "PAINE")["middle_name"] == "T"
    assert nj.person_from_boxes("", "", "UNKNOWN")["last_name"] == "UNKNOWN"       # KWYS
    assert nj.person_from_boxes("-", "-", "-") == {"first_name": "", "middle_name": "", "last_name": "", "suffix": ""}
    assert nj.person_from_boxes("RICK", "", "LEE JR") == {"first_name": "RICK", "middle_name": "", "last_name": "LEE", "suffix": "JR"}
    co = nj.person_from_boxes("EAN", "", "HOLDINGS LLC", company_check=True)
    assert co["last_name"] == "EAN HOLDINGS LLC" and co["first_name"] == ""


# ------------------------------------------------------------ addresses
def test_address_helpers():
    assert nj.split_unit("12 OAK ST APT 4B") == ("12 OAK ST", "APT 4B")
    assert nj.split_unit("12 OAK ST #7") == ("12 OAK ST", "#7")
    assert nj.split_unit("12 OAK ST, P.O. BOX 55") == ("12 OAK ST", "P.O. BOX 55")
    assert nj.split_unit("P.O. BOX 55") == ("P.O. BOX 55", "")                      # nothing else to key as Address 1
    assert nj.split_city_state_zip("Passaic, NJ 07055-5114") == ("Passaic", "NJ", "07055-5114")
    assert nj.split_address_line("415 BUCHANAN RD UTICA NY 13502") == ("415 BUCHANAN RD", "", "UTICA", "NY", "13502")
    assert nj.split_address_line("156 TOWNLINE ROAD PEARL RIVER NY 10965")[2] == "PEARL RIVER"
    assert nj.split_address_line("1 MAIN ST APT 2 UTICA NY 13502") == ("1 MAIN ST", "APT 2", "UTICA", "NY", "13502")
    assert nj.split_address_line("9 ELM AVE UNIT 5B NEWARK NJ 07102") == ("9 ELM AVE", "UNIT 5B", "NEWARK", "NJ", "07102")
    assert nj.split_address_line("no zip here") == ("no zip here", "", "", "", "")


# ------------------------------------------------------------ vehicle helpers
def test_vin_follows_general_sop_letters_only():
    assert nj.fix_vin("1GNEVGRS3SJ260580") == "1GNEVGRS3SJ260580"
    assert nj.fix_vin("1gnevgrs3sj26o58q") == "1GNEVGRS3SJ260580"
    assert nj.fix_vin(" wmw sy3c59et 566252 ") == "WMWSY3C59ET566252"
    assert nj.fix_vin("NONE") == "" and nj.fix_vin("-") == "" and nj.fix_vin(None) == ""


def test_insurance_carrier_rule():
    assert nj.insurance_carrier("365", "") == "365"
    assert nj.insurance_carrier("000", "STATE FARM") == "000"          # 000 is keyed as 000
    assert nj.insurance_carrier("***", "STATE FARM") == "STATE FARM"   # asterisks: use the narrative
    assert nj.insurance_carrier("", "GEICO") == "GEICO"
    assert nj.insurance_carrier("*", "") == ""                         # nothing anywhere: blank
    assert nj.insurance_carrier(None, None) == ""


def test_towed_rule():
    assert nj.vehicle_towed({"towed_disabled": True}) == "YES"
    assert nj.vehicle_towed({"towed_impounded": True}) == "YES"
    assert nj.vehicle_towed({"towed_disabled_impounded": True}) == "YES"
    assert nj.vehicle_towed({"driven": True}) == "NO"
    assert nj.vehicle_towed({"left_at_scene": True}) == "NO"
    assert nj.vehicle_towed({}) == "" and nj.vehicle_towed(None) == ""


def test_null_placeholders_are_not_keyed_in_text_fields():
    for v in ("NONE", "N/A", "UNK", "Unknown", "UU", "-", "***", "", None):
        assert nj.text(v) == ""
    assert nj.text("000000000") == "000000000"          # series of the same number: KWYS
    assert nj.text("498908407") == "498908407"


# ------------------------------------------------------------ the full mapper
def make_raw():
    return {
        "case_number": "X123202600001Z", "police_dept": "East Orange",
        "crash_date": "07/18/2026", "crash_time": "2058",
        "road_name": "Test Parkway", "cross_road": "", "speed_limit": "55",
        "latitude": "40.1", "longitude": "-74.1",
        "environmental_condition": "02", "road_surface_condition": "02",
        "contributing": {"118a": "60", "118b": "-", "119a": "25", "119b": "-"},
        "damage_boxes": {"130": "09", "131": "03", "132": "12", "133": "04"}, "has_box_134": True,
        "vehicles": [
            {"number": 1, "parked": False, "hit_and_run": False, "ins_code": "000", "policy_number": "P-1",
             "driver": {"first": "ANA", "middle": "", "last": "ROE", "dob": "12/24/89", "dl_number": "D123", "dl_state": "NY",
                        "alcohol_given": "No", "address_1": "1 MAIN ST APT 2", "city": "UTICA", "state": "NY", "zip": "13502"},
             "owner": {"same_as_driver": True, "first": "ANA", "middle": "", "last": "ROE",
                       "address_1": "1 MAIN ST APT 2", "city": "UTICA", "state": "NY", "zip": "13502"},
             "vehicle": {"vin": "1GNEVGRS3SJ26O58Q", "year": "2025", "make": "CHEVROLET", "model": "TRAVERSE", "plate": "ABC1", "plate_state": "NY"},
             "removal": {"towed_disabled": True},
             "charges": ["39:4-88B FAILED TO MAINTAIN LANE", "39:3-10 UNLICENSED DRIVER"]},
            {"number": 2, "parked": False, "hit_and_run": True, "ins_code": "***", "narrative_insurance": "STATE FARM",
             "driver": {"first": "BEN", "middle": "T", "last": "POE", "dl_number": "NONE", "dl_state": "NY", "alcohol_given": ""},
             "owner": {"same_as_driver": False, "first": "BEN", "middle": "", "last": "POE", "address_1": "2 ELM ST", "city": "PEARL RIVER", "state": "NY", "zip": "10965"},
             "vehicle": {"vin": "WMWSY3C59ET566252", "year": "2014", "make": "MINI", "model": "COOPER", "plate": "KYN5066", "plate_state": "NY"},
             "removal": {"driven": True}},
            {"number": 3, "parked": True,
             "driver": {"first": "", "middle": "", "last": "", "alcohol_given": "No"},
             "owner": {"same_as_driver": False, "first": "", "middle": "", "last": "Ean Holdings LLC", "address_1": "9 OAK AVE", "city": "TULSA", "state": "OK", "zip": "74134"},
             "vehicle": {"vin": "NONE", "make": "FORD", "model": "EXPLORER", "plate": "G40LXS", "plate_state": "NJ"}},
        ],
        "occupants": [
            {"row": "A", "vehicle": "1", "position": "01", "ejection": "01", "injury": "04", "age": "36", "safety_available": "04",
             "safety_used": "04", "airbag": "04", "hospital": ""},
            {"row": "B", "vehicle": "1", "position": "03", "ejection": "01", "injury": "03", "age": "17", "safety_available": "04",
             "safety_used": "04", "airbag": "04", "name": "JAY T STAPLETON", "address_line": "1 MAIN ST APT 2 UTICA NY 13502"},
            {"row": "C", "vehicle": "1", "position": "07", "injury": "05", "airbag": "99", "name": "KAY STAPLETON",
             "address": {"address_1": "77 FAR RD", "city": "UTICA", "state": "NJ", "zip": "13502"}},
            {"row": "D", "vehicle": "2", "position": "01", "injury": "05", "age": "49", "airbag": "06"},
            {"row": "E", "vehicle": "2", "position": "00", "name": "UNKNOWN"},
            {"row": "F", "vehicle": "P", "position": "", "name": "WALT WALKER", "injury": "02"},
        ],
        "property_owners": [
            {"name": "NJTA", "company": True},
            {"name": "Karen Odonnell", "address_line": "5 RIVER RD TRENTON NJ 08601"},
            {"name": "", "address_line": "8 PINE ST TRENTON NJ 08601"},
            {"name": "", "address_line": ""},
        ],
    }


@pytest.fixture
def out():
    return nj.map_nj(make_raw(), today=TODAY)


def test_incident(out):
    inc = out["incident"]
    assert inc["report_identifier_1"] == "X123202600001Z" and inc["report_identifier_2"] == ""
    assert inc["incident_date"] == "07/18/2026" and inc["time_2400"] == "20:58"
    assert inc["incident_city"] == "East Orange"            # from the "Police Dept. of" box
    assert inc["incident_state"] == "NJ" and inc["incident_street"] == "Test Parkway"
    assert inc["weather"] == "02" and inc["road_condition"] == "02" and inc["speed_limit"] == "55"
    assert inc["hit_and_run"] == "1"                         # unit 2 is marked Hit & Run


def test_no_hit_and_run_means_blank():
    raw = make_raw()
    raw["vehicles"][1]["hit_and_run"] = False
    assert nj.map_nj(raw, today=TODAY)["incident"]["hit_and_run"] == ""


def test_unit_1_driver_owner_vehicle(out):
    u = out["units"][0]
    assert u["driver"]["first_name"] == "ANA" and u["driver"]["date_of_birth"] == "12/24/1989"      # age 36 in 2026
    assert u["driver"]["injury_code"] == "04" and u["driver"]["ejection"] == "01"
    assert u["driver"]["safety_available"] == "04" and u["driver"]["alcohol_test"] == "No"
    assert u["driver"]["address_1"] == "1 MAIN ST" and u["driver"]["address_2"] == "APT 2"
    assert u["driver"]["charge"] == ["39:4-88B FAILED TO MAINTAIN LANE", "39:3-10 UNLICENSED DRIVER"]
    assert (u["owner"]["first_name"], u["owner"]["last_name"]) == ("ANA", "ROE")                     # same as driver
    assert u["owner"]["address_1"] == "1 MAIN ST"                                                    # owner address as printed
    v = u["vehicle"]
    assert v["vin"] == "1GNEVGRS3SJ260580"                                                           # O and Q replaced
    assert v["insurance_carrier"] == "000" and v["vehicle_towed"] == "YES"
    assert v["airbag_deployed"] == "YES" and v["contributing"] == "60" and v["impact_location"] == "Left Side"


def test_unit_2_rules(out):
    u = out["units"][1]
    assert u["driver"]["drivers_license"] == "" and u["driver"]["alcohol_test"] == ""                # NONE is not keyed
    assert u["vehicle"]["insurance_carrier"] == "STATE FARM" and u["vehicle"]["vehicle_towed"] == "NO"
    assert u["vehicle"]["airbag_deployed"] == "NO" and u["vehicle"]["contributing"] == "25"
    assert u["vehicle"]["impact_location"] == "Front"
    assert u["owner"]["last_name"] == "POE" and u["owner"]["address_1"] == "2 ELM ST"


def test_parked_unit_keys_parked_and_other_details(out):
    u = out["units"][2]
    assert u["driver"]["last_name"] == "PARKED" and u["driver"]["first_name"] == ""
    assert u["driver"]["alcohol_test"] == "No"                                                       # other details still keyed
    assert u["owner"]["last_name"] == "Ean Holdings LLC" and u["owner"]["first_name"] == ""          # company -> last name
    assert u["vehicle"]["vin"] == "" and u["vehicle"]["contributing"] == "" and u["vehicle"]["impact_location"] == ""


def test_parked_with_names_keys_names_and_unknown_is_kept():
    raw = make_raw()
    raw["vehicles"][2]["driver"].update(first="CAL", last="DOE")
    assert nj.map_nj(raw, today=TODAY)["units"][2]["driver"]["last_name"] == "DOE"
    raw["vehicles"][2]["driver"].update(first="", last="Unknown")
    assert nj.map_nj(raw, today=TODAY)["units"][2]["driver"]["last_name"] == "Unknown"          # KWYS
    raw["vehicles"][2]["parked"] = False
    raw["vehicles"][2]["driver"].update(first="", last="")
    assert nj.map_nj(raw, today=TODAY)["units"][2]["driver"]["last_name"] == ""                   # not parked: no PARKED


def test_same_as_driver_never_copies_the_parked_placeholder():
    raw = make_raw()
    raw["vehicles"][2]["owner"].update(same_as_driver=True, last="")
    assert nj.map_nj(raw, today=TODAY)["units"][2]["owner"]["last_name"] == ""


def test_other_parties(out):
    parties = out["other_parties"]
    by_name = {p["last_name"]: p for p in parties}
    jay = next(p for p in parties if p["first_name"] == "JAY")
    assert (jay["person_type"], jay["first_name"], jay["middle_name"], jay["vehicle_number"]) == ("Passenger", "JAY", "T", "1")
    assert jay["injury_code"] == "03" and jay["safety_used"] == "04"
    assert jay["address_1"] == "1 MAIN ST" and jay["address_2"] == "APT 2" and jay["city"] == "UTICA"
    assert jay["same_as_driver_address"] is True                              # same address as unit 1's driver
    kay = next(p for p in parties if p["first_name"] == "KAY")
    assert kay["person_type"] == "Passenger" and kay["same_as_driver_address"] is False and kay["state"] == "NJ"
    unk = by_name["UNKNOWN"]
    assert unk["person_type"] == "Unknown" and unk["vehicle_number"] == "2"   # seating position 0
    ped = by_name["WALKER"]
    assert ped["person_type"] == "Pedestrian" and ped["vehicle_number"] == "" and ped["injury_code"] == "02"


def test_drivers_are_not_duplicated_as_other_parties(out):
    names = [(p["first_name"], p["last_name"]) for p in out["other_parties"]]
    assert ("ANA", "ROE") not in names and ("BEN", "POE") not in names


def test_property_owners(out):
    props = [p for p in out["other_parties"] if p["person_type"] == "Property Owner"]
    assert len(props) == 3                                                   # the empty one is skipped
    assert props[0]["last_name"] == "NJTA" and props[0]["first_name"] == ""   # company -> last name only
    assert (props[1]["first_name"], props[1]["last_name"]) == ("Karen", "Odonnell")
    assert props[1]["address_1"] == "5 RIVER RD" and props[1]["city"] == "TRENTON" and props[1]["zip_code"] == "08601"
    assert props[2]["first_name"] == "" and props[2]["last_name"] == "" and props[2]["address_1"] == "8 PINE ST"
    assert any("no owner name or address" in n for n in out["notes"])


def test_older_form_without_box_134_uses_131_and_133():
    raw = make_raw()
    raw["has_box_134"] = False                                               # boxes 131 (V1) and 133 (V2)
    units = nj.map_nj(raw, today=TODAY)["units"]
    assert units[0]["vehicle"]["impact_location"] == "Right Side"            # 131 = 03
    assert units[1]["vehicle"]["impact_location"] == "Right Rear"            # 133 = 04


def test_unrecognised_codes_blank_the_field_and_add_a_note():
    raw = make_raw()
    raw["environmental_condition"] = "77"
    raw["occupants"][0]["injury"] = "09"
    out = nj.map_nj(raw, today=TODAY)
    assert out["incident"]["weather"] == "" and out["units"][0]["driver"]["injury_code"] == ""
    assert any("Weather" in n for n in out["notes"]) and any("injury" in n for n in out["notes"])


def test_dashes_do_not_create_notes():
    raw = make_raw()
    raw["environmental_condition"] = "-"
    raw["occupants"][0]["injury"] = "-"
    notes = nj.map_nj(raw, today=TODAY)["notes"]
    assert not any("Weather" in n or "injury" in n for n in notes)


def test_one_line_address_split_adds_review_note(out):
    assert any("split from one line" in n for n in out["notes"])


def test_payload_is_json_serialisable(out):
    assert json.loads(json.dumps(out)) == out


@pytest.mark.parametrize("raw", [{}, {"vehicles": None, "occupants": None}, {"vehicles": [{}], "occupants": [{}]},
                                 {"vehicles": [{"number": "x"}], "occupants": [{"vehicle": None, "position": None}]}])
def test_empty_or_partial_input_never_raises(raw):
    out = nj.map_nj(raw, today=TODAY)
    assert set(out) == {"incident", "units", "other_parties", "notes"}
    assert out["incident"]["incident_state"] == "NJ"


def test_units_are_ordered_by_vehicle_number():
    raw = make_raw()
    raw["vehicles"].reverse()
    assert [u["party_number"] for u in nj.map_nj(raw, today=TODAY)["units"]] == [1, 2, 3]
