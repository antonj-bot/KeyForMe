"""Offline tests for app/keying/nj_rules.py  (no browser, no PDF, no AI).

Run:  python -m pytest tests/test_nj_rules.py -q
All names, numbers and addresses below are invented.
"""
import json
from datetime import date

import pytest

from app.keying import nj_rules as nj
import nj_fixtures as fx

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


def test_contributing_circumstances_are_keyed_what_you_see():
    assert nj.contributing(["04", "-"]) == "04"                  # 04 stays 04
    assert nj.contributing(["01", "-"]) == "01"
    assert nj.contributing(["07", "60"]) == "07;60"
    assert nj.contributing(["4", "-"]) == "4"                    # printed without a zero: keyed without a zero
    assert nj.contributing(["25", "-"]) == "25"                  # 25 = None
    assert nj.contributing(["04", "4"]) == "04"                  # the same code twice is keyed once (first printed form)
    assert nj.contributing(["14", "04"]) == "14;04"
    assert nj.contributing(["00", "26"]) == "00;26"              # not in the NJ list: still keyed as printed
    assert nj.contributing([None, "", "-", "--", "***"]) == ""
    assert nj.contributing(None) == ""


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


def test_a_dash_in_a_name_is_never_keyed():
    blank = {"first_name": "", "middle_name": "", "last_name": "", "suffix": ""}
    assert nj.split_name("-") == blank and nj.split_name("--") == blank and nj.split_name("- -") == blank
    assert nj.split_name("JULIA - HARRISON") == {"first_name": "JULIA", "middle_name": "", "last_name": "HARRISON", "suffix": ""}
    assert nj.split_name("SMITH, -")["last_name"] == "SMITH" and nj.split_name("SMITH, -")["first_name"] == ""
    assert nj.split_name("JOHN - E - DOE")["middle_name"] == "E"
    assert nj.split_name("BERMEO-ALTAMIRANO")["last_name"] == "BERMEO-ALTAMIRANO"       # hyphens inside names stay
    assert nj.split_name("Mary-Ann Smith-Jones")["first_name"] == "Mary-Ann"
    assert nj.split_name("JULIA \u2013 HARRISON")["middle_name"] == "" and nj.split_name("\u2014") == blank   # en / em dash
    assert nj.split_name("SMITH & SONS")["last_name"] == "SMITH & SONS"                  # "&" in a company name stays
    assert nj.split_name("Jersey Central Power & Light")["last_name"] == "Jersey Central Power & Light"
    assert nj.person_from_boxes("-", "-", "-") == blank
    assert nj.person_from_boxes("JOHN", "-", "SMITH -") == {"first_name": "JOHN", "middle_name": "", "last_name": "SMITH", "suffix": ""}
    assert nj.person_from_boxes("JOHN -", "", "DOE")["first_name"] == "JOHN"
    assert nj.person_from_boxes("", "", "UNKNOWN")["last_name"] == "UNKNOWN"            # UNKNOWN is still KWYS in names


def test_dash_only_names_stay_blank_through_the_whole_mapper():
    raw = make_raw()
    raw["vehicles"][0]["driver"].update(first="-", middle="-", last="-")
    raw["vehicles"][1]["owner"] = fx.owner("-", a1="2 ELM ST")
    raw["occupants"][1]["name"] = "JAY - STAPLETON"
    raw["occupants"][2]["name"] = "-"
    raw["property_owners"] = [dict(name="-", address_line="8 PINE ST TRENTON NJ 08601")]
    out = nj.map_nj(raw, today=TODAY)
    d = out["units"][0]["driver"]
    assert (d["first_name"], d["middle_name"], d["last_name"]) == ("", "", "")
    o = out["units"][1]["owner"]
    assert (o["first_name"], o["middle_name"], o["last_name"]) == ("", "", "") and o["address_1"] == "2 ELM ST"
    jay = next(p for p in out["other_parties"] if p["last_name"] == "STAPLETON")
    assert (jay["first_name"], jay["middle_name"]) == ("JAY", "")
    for p in out["other_parties"]:
        assert "-" not in (p["first_name"], p["middle_name"], p["last_name"], p["suffix"])
    prop = [p for p in out["other_parties"] if p["person_type"] == "Property Owner"][0]
    assert (prop["first_name"], prop["last_name"]) == ("", "") and prop["address_1"] == "8 PINE ST"


def test_unknown_contributing_code_is_keyed_with_a_review_note():
    raw = make_raw()
    raw["vehicles"][0]["contributing"] = ["04", "26"]
    out = nj.map_nj(raw, today=TODAY)
    assert out["units"][0]["vehicle"]["contributing"] == "04;26"
    assert any("contributing circumstance '26'" in n for n in out["notes"])
    assert not any("contributing circumstance '04'" in n for n in out["notes"])


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
    assert nj.split_address_line("346 JEFFERSON AVE, #2A, BROOKLYN, NY 11221") == ("346 JEFFERSON AVE", "#2A", "BROOKLYN", "NY", "11221")
    assert nj.split_address_line("57 STATE ST, EAST ORANGE, NJ 07017-1117") == ("57 STATE ST", "", "EAST ORANGE", "NJ", "07017-1117")
    assert nj.split_address_line("no zip here") == ("no zip here", "", "", "", "")
    assert nj.split_unit("63 ELMWOOD AVE, 2ND FL") == ("63 ELMWOOD AVE", "2ND FL")


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
    assert nj.insurance_carrier("*", "(NY) STATE FARM - Field 25") == "STATE FARM"   # narrative text is cleaned
    assert nj.clean_narrative_value("(NY) STATE FARM - Field 55") == "STATE FARM"
    assert nj.clean_narrative_value("993 FOR HIRE SELF INSURER") == "993 FOR HIRE SELF INSURER"
    assert nj.insurance_carrier(None, None) == ""


def test_towed_rule():
    assert nj.vehicle_towed({"towed_disabled": True}) == "YES"
    assert nj.vehicle_towed({"towed_impounded": True}) == "YES"
    assert nj.vehicle_towed({"towed_disabled_impounded": True}) == "YES"
    assert nj.vehicle_towed({"driven": True}) == "NO"
    assert nj.vehicle_towed({"left_at_scene": True}) == "NO"
    assert nj.vehicle_towed({}) == "" and nj.vehicle_towed(None) == ""


@pytest.mark.parametrize("raw,expected", [
    ("NONE", "NONE"), ("none", "none"), ("498908407", "498908407"), ("R6094 25900 04611", "R6094 25900 04611"),
    ("000000000", "000000000"),
    ("UNKNOWN", ""), ("Unknown", ""), ("NA", ""), ("na", ""), ("N/A", ""), ("n/a", ""),
    ("NOT APPLICABLE", ""), ("Not  Applicable", ""), ("-", ""), ("--", ""), ("***", ""), ("", ""), (None, ""),
])
def test_license_number_rule(raw, expected):
    assert nj.license_number(raw) == expected


def test_license_rule_is_only_for_the_license_field():
    assert nj.text("NONE") == "" and nj.text("UNKNOWN") == ""            # other text fields keep the SOP null list


def test_null_placeholders_are_not_keyed_in_text_fields():
    for v in ("NONE", "N/A", "UNK", "Unknown", "UU", "-", "***", "", None):
        assert nj.text(v) == ""
    assert nj.text("000000000") == "000000000"          # series of the same number: KWYS
    assert nj.text("498908407") == "498908407"


# ------------------------------------------------------------ the full mapper (synthetic report)
def make_raw():
    return {
        "case_number": "X123202600001Z", "police_dept": "East Orange",
        "crash_date": "07/18/2026", "crash_time": "2058",
        "road_name": "Test Parkway", "cross_road": "", "speed_limit": "55",
        "latitude": "40.1", "longitude": "-74.1", "weather_code": "02", "road_condition_code": "02",
        "vehicles": [
            fx.veh(1, ins="000", policy="P-1", charges=["39:4-88B FAILED TO MAINTAIN LANE", "39:3-10 UNLICENSED DRIVER"],
                   driver_=fx.driver("ANA", "", "ROE", "12/24/89", "D123", "NY", "No", "1 MAIN ST APT 2", "UTICA", "NY", "13502"),
                   owner_=fx.owner("ANA ROE", same=True, a1="1 MAIN ST APT 2", city="UTICA", state="NY", zip="13502"),
                   vehicle_=fx.vehicle("1GNEVGRS3SJ26O58Q", "2025", "CHEVROLET", "TRAVERSE", "ABC1", "NY"),
                   removal=dict(towed_disabled=True), damage_new="09", damage_old="03", contributing=["60", "-"]),
            fx.veh(2, hit_and_run=True, ins="***", narr_ins="STATE FARM",
                   driver_=fx.driver("BEN", "T", "POE", dl="NONE", alcohol=""),
                   owner_=fx.owner("BEN POE", a1="2 ELM ST", city="PEARL RIVER", state="NY", zip="10965"),
                   vehicle_=fx.vehicle("WMWSY3C59ET566252", "2014", "MINI", "COOPER", "KYN5066", "NY"),
                   removal=dict(driven=True), damage_new="12", damage_old="06", contributing=["25", "-"]),
            fx.veh(3, parked=True,
                   driver_=fx.driver(alcohol="No"),
                   owner_=fx.owner("Ean Holdings LLC", a1="9 OAK AVE", city="TULSA", state="OK", zip="74134"),
                   vehicle_=fx.vehicle("NONE", "", "FORD", "EXPLORER", "G40LXS", "NJ")),
        ],
        "occupants": [
            fx.occ("A", "01", "01", "01", "04", "36", "04", "04", "04"),
            fx.occ("B", "01", "03", "01", "03", "17", "04", "04", "04", name="JAY T STAPLETON", address="1 MAIN ST APT 2 UTICA NY 13502"),
            fx.occ("C", "01", "07", "", "05", "", "", "", "99", name="KAY STAPLETON"),
            fx.occ("D", "02", "01", "", "05", "49", "", "", "06"),
            fx.occ("E", "02", "00", "", "", "", "", "", "", name="UNKNOWN"),
            fx.occ("F", "P", "", "", "02", "", "", "", "", name="WALT WALKER", address="3 PARK RD OSLO NY 10001"),
        ],
        "property_owners": [
            dict(name="NJTA", is_company=True),
            dict(name="Karen Odonnell", address_line="5 RIVER RD TRENTON NJ 08601"),
            dict(name="", address_line="8 PINE ST TRENTON NJ 08601"),
            dict(name="", address_line=""),
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


def test_unit_1(out):
    u = out["units"][0]
    d = u["driver"]
    assert d["first_name"] == "ANA" and d["date_of_birth"] == "12/24/1989"          # age 36 in 2026 -> 1989
    assert d["injury_code"] == "04" and d["ejection"] == "01" and d["safety_available"] == "04" and d["alcohol_test"] == "No"
    assert (d["address_1"], d["address_2"]) == ("1 MAIN ST", "APT 2")
    assert d["charge"] == "39:4-88B FAILED TO MAINTAIN LANE" and d["extra_charges"] == ["39:3-10 UNLICENSED DRIVER"]
    assert (u["owner"]["first_name"], u["owner"]["last_name"]) == ("ANA", "ROE")      # Same As Driver: names only
    assert u["owner"]["address_1"] == "1 MAIN ST"                                      # owner address as printed
    v = u["vehicle"]
    assert v["vin"] == "1GNEVGRS3SJ260580"                                            # O and Q replaced
    assert v["insurance_carrier"] == "000" and v["vehicle_towed"] == "YES" and v["airbag_deployed"] == "YES"
    assert v["contributing"] == "60" and v["impact_location"] == "Left Side"


def test_unit_2_rules(out):
    u = out["units"][1]
    assert u["driver"]["drivers_license"] == "NONE" and u["driver"]["alcohol_test"] == ""        # NONE is keyed as printed
    assert u["vehicle"]["insurance_carrier"] == "STATE FARM" and u["vehicle"]["vehicle_towed"] == "NO"
    assert u["vehicle"]["airbag_deployed"] == "NO" and u["vehicle"]["contributing"] == "25"
    assert u["vehicle"]["impact_location"] == "Front"
    assert u["owner"]["last_name"] == "POE" and u["owner"]["first_name"] == "BEN"


def test_parked_unit_keys_parked_and_other_details(out):
    u = out["units"][2]
    assert u["driver"]["last_name"] == "PARKED" and u["driver"]["first_name"] == ""
    assert u["driver"]["alcohol_test"] == "No"                                                    # other details still keyed
    assert u["owner"]["last_name"] == "Ean Holdings LLC" and u["owner"]["first_name"] == ""        # company -> last name
    assert u["vehicle"]["vin"] == "" and u["vehicle"]["contributing"] == "" and u["vehicle"]["impact_location"] == ""


def test_parked_with_names_keys_names_and_unknown_is_kept():
    raw = make_raw()
    raw["vehicles"][2]["driver"].update(first="CAL", last="DOE")
    assert nj.map_nj(raw, today=TODAY)["units"][2]["driver"]["last_name"] == "DOE"
    raw["vehicles"][2]["driver"].update(first="", last="Unknown")
    assert nj.map_nj(raw, today=TODAY)["units"][2]["driver"]["last_name"] == "Unknown"           # KWYS
    raw["vehicles"][2]["parked"] = False
    raw["vehicles"][2]["driver"].update(first="", last="")
    assert nj.map_nj(raw, today=TODAY)["units"][2]["driver"]["last_name"] == ""                    # not parked: no PARKED


def test_driver_name_falls_back_to_occupant_row():
    raw = make_raw()
    raw["vehicles"][0]["driver"].update(first="", middle="", last="")
    raw["occupants"][0]["name"] = "ROE, ANA"
    d = nj.map_nj(raw, today=TODAY)["units"][0]["driver"]
    assert (d["first_name"], d["last_name"]) == ("ANA", "ROE")


def test_same_as_driver_never_copies_the_parked_placeholder():
    raw = make_raw()
    raw["vehicles"][2]["owner"].update(same_as_driver=True, name="")
    o = nj.map_nj(raw, today=TODAY)["units"][2]["owner"]
    assert o["last_name"] == "" and o["first_name"] == ""


def test_other_parties(out):
    parties = out["other_parties"]
    jay = next(p for p in parties if p["first_name"] == "JAY")
    assert (jay["person_type"], jay["role"], jay["party_number"]) == ("Passenger", "PASSENGER", "1")
    assert (jay["middle_name"], jay["last_name"]) == ("T", "STAPLETON") and jay["injury_code"] == "03"
    # a printed address is keyed (KWYS) and the Same As boxes are NOT ticked
    assert (jay["address_1"], jay["address_2"], jay["city"]) == ("1 MAIN ST", "APT 2", "UTICA")
    assert jay["same_as_driver_address"] is False and jay["same_as_owner_address"] is False
    # no address printed -> tick Same As Driver (the driver of vehicle 1 has an address)
    kay = next(p for p in parties if p["first_name"] == "KAY")
    assert kay["person_type"] == "Passenger" and kay["address_1"] == "" and kay["same_as_driver_address"] is True
    unk = next(p for p in parties if p["last_name"] == "UNKNOWN")
    assert unk["person_type"] == "Unknown" and unk["party_number"] == "2"                       # seating position 0
    ped = next(p for p in parties if p["last_name"] == "WALKER")
    assert ped["person_type"] == "Pedestrian" and ped["party_number"] == "" and ped["address_1"] == "3 PARK RD"
    assert ped["same_as_driver_address"] is False                                               # no vehicle -> never ticked


def test_no_address_and_driver_has_none_ticks_owner():
    raw = make_raw()
    raw["vehicles"][0]["driver"].update(address_1="", city="", state="", zip="")
    kay = next(p for p in nj.map_nj(raw, today=TODAY)["other_parties"] if p["first_name"] == "KAY")
    assert kay["same_as_driver_address"] is False and kay["same_as_owner_address"] is True


def test_drivers_are_not_duplicated_as_other_parties(out):
    names = [(p["first_name"], p["last_name"]) for p in out["other_parties"]]
    assert ("ANA", "ROE") not in names and ("BEN", "POE") not in names


def test_property_owners(out):
    props = [p for p in out["other_parties"] if p["person_type"] == "Property Owner"]
    assert len(props) == 3 and all(p["role"] == "PROPERTY OWNER" for p in props)                # the empty one is skipped
    assert props[0]["last_name"] == "NJTA" and props[0]["first_name"] == ""
    assert (props[1]["first_name"], props[1]["last_name"]) == ("Karen", "Odonnell")
    assert props[1]["address_1"] == "5 RIVER RD" and props[1]["city"] == "TRENTON" and props[1]["zip_code"] == "08601"
    assert props[2]["first_name"] == "" and props[2]["last_name"] == "" and props[2]["address_1"] == "8 PINE ST"
    assert any("no owner name or address" in n for n in out["notes"])


def test_older_form_without_box_134_uses_131_and_133():
    raw = make_raw()
    raw["vehicles"][0]["damage"]["new_form"] = False
    raw["vehicles"][1]["damage"]["new_form"] = False
    units = nj.map_nj(raw, today=TODAY)["units"]
    assert units[0]["vehicle"]["impact_location"] == "Right Side"            # old box 03
    assert units[1]["vehicle"]["impact_location"] == "Rear"                  # old box 06


def test_unrecognised_codes_blank_the_field_and_add_a_note():
    raw = make_raw()
    raw["weather_code"] = "77"
    raw["occupants"][0]["injury"] = "09"
    raw["occupants"][2]["airbag"] = "09"
    out = nj.map_nj(raw, today=TODAY)
    assert out["incident"]["weather"] == "" and out["units"][0]["driver"]["injury_code"] == ""
    assert any("Weather" in n for n in out["notes"]) and any("injury" in n for n in out["notes"])
    assert any("airbag code '09'" in n for n in out["notes"])


def test_dashes_and_99_do_not_create_notes():
    raw = make_raw()
    raw["weather_code"] = "-"
    raw["occupants"][0]["injury"] = "-"
    notes = nj.map_nj(raw, today=TODAY)["notes"]
    assert not any("Weather" in n or "injury" in n or "airbag" in n for n in notes)


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


def test_policy_falls_back_to_narrative_when_asterisk():
    raw = make_raw()
    raw["vehicles"][0]["policy_number"] = "*"
    raw["vehicles"][0]["narrative_policy"] = "ABC-123 - Field 24"
    assert nj.map_nj(raw, today=TODAY)["units"][0]["vehicle"]["policy_number"] == "ABC-123"


def test_city_box_holding_city_state_zip_is_split():
    raw = make_raw()
    raw["vehicles"][0]["driver"].update(city="Passaic, NJ 07055-5114", state="", zip="")
    d = nj.map_nj(raw, today=TODAY)["units"][0]["driver"]
    assert (d["city"], d["state"], d["zip_code"]) == ("Passaic", "NJ", "07055-5114")


def test_owner_boxes_still_work_without_a_single_name_string():
    raw = make_raw()
    raw["vehicles"][1]["owner"] = dict(first="PEACE", middle="", last="BLEWUADAH", address_1="1 X ST")
    o = nj.map_nj(raw, today=TODAY)["units"][1]["owner"]
    assert (o["first_name"], o["last_name"]) == ("PEACE", "BLEWUADAH")


def test_company_flag_from_the_extractor_beats_the_word_list():
    raw = make_raw()
    raw["vehicles"][1]["owner"] = fx.owner("ACME TOWING", company=True)
    assert nj.map_nj(raw, today=TODAY)["units"][1]["owner"]["last_name"] == "ACME TOWING"
    raw["vehicles"][1]["owner"] = fx.owner("ACME TOWING")
    assert nj.map_nj(raw, today=TODAY)["units"][1]["owner"]["first_name"] == "ACME"      # no flag, no keyword: person-style split


# ------------------------------------------------------------ the six sample reports
def run(name):
    return nj.map_nj(fx.ALL[name], today=TODAY)


def test_standard_report():
    o = run("STANDARD")
    inc = o["incident"]
    assert (inc["report_identifier_1"], inc["incident_city"], inc["incident_date"], inc["time_2400"]) == \
        ("D040202602475C", "New Jersey State Police", "07/18/2026", "20:58")
    u1, u2 = o["units"]
    assert u1["vehicle"]["insurance_carrier"] == "000" and u2["vehicle"]["insurance_carrier"] == "000"   # 000 is keyed as 000
    assert (u1["vehicle"]["vehicle_towed"], u2["vehicle"]["vehicle_towed"]) == ("YES", "NO")
    assert (u1["vehicle"]["airbag_deployed"], u2["vehicle"]["airbag_deployed"]) == ("YES", "NO")
    assert (u1["vehicle"]["contributing"], u2["vehicle"]["contributing"]) == ("60", "25")
    assert (u1["vehicle"]["impact_location"], u2["vehicle"]["impact_location"]) == ("Left Side", "Left Side")
    assert (u1["driver"]["injury_code"], u1["driver"]["ejection"], u1["driver"]["safety_used"]) == ("04", "01", "04")
    assert (u2["owner"]["first_name"], u2["owner"]["middle_name"], u2["owner"]["last_name"]) == ("MICHEAL", "T", "PAINE")
    assert o["incident"]["hit_and_run"] == ""
    parties = o["other_parties"]
    assert [(p["person_type"], p["first_name"], p["party_number"]) for p in parties] == [
        ("Passenger", "JAYDEN", "1"), ("Passenger", "CAYSEN", "1"), ("Property Owner", "", "")]
    assert parties[0]["state"] == "NJ" and parties[0]["address_1"] == "415 BUCHANAN RD"          # printed state is keyed as printed
    assert parties[0]["same_as_driver_address"] is False
    assert parties[2]["last_name"] == "NJTA"
    assert not o["notes"] or all("split from one line" in n for n in o["notes"])


def test_three_units_report():
    o = run("THREE_UNITS")
    assert o["incident"]["incident_date"] == "08/08/2026" and o["incident"]["incident_cross_street"] == "ELM AVENUE"
    u1, u2, u3 = o["units"]
    assert u1["driver"]["date_of_birth"] == "08/04/1993"                      # "93" + age 33 -> 1993
    assert (u1["driver"]["first_name"], u1["driver"]["middle_name"], u1["driver"]["last_name"]) == ("TYRIK", "CHARLES", "JONES")
    assert u1["driver"]["injury_code"] == "03"
    assert (u1["driver"]["address_1"], u1["driver"]["address_2"]) == ("399 BRISTOL ST", "APT C")
    assert u1["driver"]["charge"] == "39:4-88B FAILED TO MAINTAIN LANE" and len(u1["driver"]["extra_charges"]) == 3
    assert (u1["owner"]["first_name"], u1["owner"]["middle_name"], u1["owner"]["last_name"]) == ("ERIC", "M", "LOPEZ")
    assert u1["owner"]["address_2"] == "APT 2B"
    assert u1["vehicle"]["insurance_carrier"] == "RentalCover.com"            # code was "*": narrative value
    assert u1["vehicle"]["impact_location"] == "Front" and u2["vehicle"]["impact_location"] == "Left Rear"
    assert u1["vehicle"]["contributing"] == "14;04"
    assert (u2["owner"]["first_name"], u2["owner"]["last_name"]) == ("MAYRA", "BERMEO-ALTAMIRANO")  # Same As Driver
    assert u2["driver"]["drivers_license_state"] == "NJ"
    # unit 3 is on the second unit page and is parked with owner details only
    assert u3["driver"]["last_name"] == "PARKED" and u3["driver"]["drivers_license"] == "NONE" and u3["vehicle"]["vehicle_towed"] == "NO"
    assert u3["owner"]["last_name"] == "PALOMEQUEPACHECO" and u3["owner"]["first_name"] == "JAIME" and u3["owner"]["middle_name"] == "G"
    assert u3["vehicle"]["impact_location"] == "Right Front" and u3["vehicle"]["contributing"] == "25;01"
    ems = next(p for p in o["other_parties"] if p["last_name"] == "EMANUEL")
    assert (ems["first_name"], ems["middle_name"], ems["person_type"], ems["party_number"]) == ("JABARI", "SHAHKIR", "Passenger", "1")
    assert (ems["address_1"], ems["address_2"], ems["city"], ems["state"], ems["zip_code"]) == \
        ("346 JEFFERSON AVE", "#2A", "BROOKLYN", "NY", "11221")
    prop = [p for p in o["other_parties"] if p["person_type"] == "Property Owner"]
    assert len(prop) == 1 and prop[0]["first_name"] == "" and prop[0]["last_name"] == "" and prop[0]["address_1"] == "746 BERGEN BLVD"


def test_violation_report():
    o = run("VIOLATION")
    assert o["incident"]["hit_and_run"] == "1" and o["incident"]["time_2400"] == "00:40"
    u1, u2 = o["units"]
    assert u1["driver"]["charge"] == "39:4-97 - Careless Driving" and len(u1["driver"]["extra_charges"]) == 6
    assert u1["owner"]["last_name"] == "Ean Holdings LLC" and u1["owner"]["first_name"] == ""
    assert u1["vehicle"]["policy_number"] == ""                                # "UNKNOWN" is a null value in a text field
    assert u1["vehicle"]["insurance_carrier"] == "000" and u1["vehicle"]["vehicle_towed"] == "YES"
    assert u1["vehicle"]["impact_location"] == "Multiple"                      # box 15 = overturned
    assert u1["driver"]["ejection"] == "" and u1["driver"]["safety_used"] == ""   # printed "00" is not an NJ code
    assert u1["driver"]["hospital"] == "6501"
    assert u2["driver"]["last_name"] == "PARKED" and u2["driver"]["alcohol_test"] == ""
    assert (u2["owner"]["first_name"], u2["owner"]["middle_name"], u2["owner"]["last_name"], u2["owner"]["suffix"]) == \
        ("Richard", "B", "McKelvey", "III")
    assert u2["vehicle"]["contributing"] == "25" and u2["vehicle"]["impact_location"] == "Right Rear"
    props = [p for p in o["other_parties"] if p["person_type"] == "Property Owner"]
    assert [(p["first_name"], p["last_name"]) for p in props] == [("Karen", "Odonnell"), ("", "Jersey Central Power & Light")]
    assert any("ejection" in n for n in o["notes"])


def test_four_unit_report():
    o = run("FOUR_UNITS")
    assert [u["party_number"] for u in o["units"]] == [1, 2, 3, 4]
    u1, u2, u3, u4 = o["units"]
    assert u1["driver"]["date_of_birth"] == "05/13/2006"                       # "06" -> 2006
    assert u2["driver"]["date_of_birth"] == "03/04/1991"
    assert u1["vehicle"]["airbag_deployed"] == "YES" and u1["vehicle"]["vehicle_towed"] == "YES"
    assert u1["driver"]["hospital"] == "5707" and u1["driver"]["injury_code"] == "03"
    assert u2["driver"]["address_1"] == "63 ELMWOOD AVE" and u2["driver"]["address_2"] == "2ND FL"
    assert (u3["driver"]["last_name"], u4["driver"]["last_name"]) == ("PARKED", "PARKED")
    assert u3["driver"]["drivers_license"] == "NONE" and u4["driver"]["drivers_license"] == ""   # printed NONE is keyed
    assert (u3["owner"]["first_name"], u3["owner"]["last_name"]) == ("THOMAS", "MERRITT")
    assert u3["owner"]["address_2"] == "APT. 4A" and u3["vehicle"]["impact_location"] == "Left Front"
    assert u4["vehicle"]["impact_location"] == "Right Rear" and u4["vehicle"]["vehicle_towed"] == "NO"
    assert u3["vehicle"]["airbag_deployed"] == "" and u3["vehicle"]["insurance_carrier"] == "945"
    assert [p for p in o["other_parties"] if p["person_type"] == "Property Owner"] == []   # parked cars are units, not property
    assert o["other_parties"] == []


def test_veh2_parked_report():
    o = run("VEH2_PARKED")
    u1, u2 = o["units"]
    assert u1["owner"]["first_name"] == "Ebenezer" and u1["owner"]["last_name"] == "Goodlin"
    assert u1["vehicle"]["airbag_deployed"] == "NO" and u1["vehicle"]["insurance_carrier"] == "000"
    assert u1["driver"]["date_of_birth"] == "12/16/1950" and u1["driver"]["injury_code"] == "05"
    assert u2["driver"]["last_name"] == "PARKED"
    assert (u2["owner"]["first_name"], u2["owner"]["last_name"], u2["owner"]["city"]) == ("Peace", "Blewuadah", "Trenton")
    assert (u1["vehicle"]["impact_location"], u2["vehicle"]["impact_location"]) == ("Front", "Rear")
    assert o["incident"]["incident_date"] == "08/10/2026" and o["incident"]["time_2400"] == "09:50"


def test_normal_two_unit_report_with_city_state_zip_in_one_box():
    o = run("NORMAL_2")
    assert o["incident"]["incident_date"] == "06/09/2026" and o["incident"]["time_2400"] == "16:01"
    u1, u2 = o["units"]
    assert (u1["driver"]["city"], u1["driver"]["state"], u1["driver"]["zip_code"]) == ("Passaic", "NJ", "07055-5114")
    assert u2["driver"]["address_2"] == "Apt 2" and u2["driver"]["address_1"] == "119 Jefferson St"
    assert u1["driver"]["date_of_birth"] == "04/30/1961"                       # "61" with age 65 -> 1961
    assert (u2["owner"]["first_name"], u2["owner"]["last_name"]) == ("Eusebio", "Mejia")
    assert u1["driver"]["drivers_license"] == "R6094 25900 04611"
    assert o["other_parties"] == []                                            # no passengers
    assert (u1["vehicle"]["year"], u2["vehicle"]["year"]) == ("08", "17")      # printed two-digit years are keyed as printed
