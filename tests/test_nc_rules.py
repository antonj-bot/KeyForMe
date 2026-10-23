"""NC rules tests. Fixture = the 'Witness, property owner and unit 1 citation' sample (form 1 of 2)."""
import sys
from datetime import date
from pathlib import Path

import pytest

from app.core.options import map_options
from app.keying import nc_rules as nc

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nc_fixtures import REFERENCE_ROWS, sample_raw  # noqa: E402

TODAY = date(2026, 10, 23)


# ------------------------------------------------------------------ small rules
def test_report_id_samples():
    assert nc.nc_report_id("260804126HA/02") == "260804126HA"
    assert nc.nc_report_id("26-06214/Z1") == "26-06214"
    assert nc.nc_report_id("202631739 - 03") == "202631739"
    assert nc.nc_report_id("25006870/111") == "25006870"
    assert nc.nc_report_id("") == ""


def test_streets():
    for raw, want in [("SR 2033", "2033"), ("US 17", "17"), ("I-95", "95"), ("NC 16", "16"),
                      ("SANDRA ST", "SANDRA ST"), ("SLOAN RD", "SLOAN RD"), ("UNK", ""),
                      ("VIRGIL STREET", "VIRGIL STREET"), ("RUTH ST", "RUTH ST")]:
        assert nc.nc_clean_street(raw) == want, raw


def test_codes_are_single_numbers_and_multiselect():
    assert nc.nc_injury("5") == "5" and nc.nc_injury("05") == "5"                  # "5 No Injury" in the app
    assert nc.nc_injury("3", 2023) == "" and nc.nc_injury("3", 2009) == "3"        # 2023 form skips 2 and 3
    assert nc.nc_codes(["4", "5"], nc.WEATHER) == "4;5"
    assert nc.nc_codes(["4", "4"], nc.WEATHER) == "4"
    assert nc.nc_codes(["-", "", None], nc.WEATHER) == ""
    assert nc.nc_codes(["99"], nc.WEATHER) == ""
    assert nc.nc_codes(["8"], nc.DRIVER_CONTRIB) == "8" and nc.nc_codes(["10"], nc.PROTECTION) == "10"
    assert nc.nc_codes(["0"], nc.VEHICLE_DEFECTS) == "0"


def test_option_map_works_with_the_shared_options_engine():
    warnings: list[str] = []
    injury = nc.nc_option_map("injury_code")
    assert map_options("injury", "5", injury, warnings) == "5 No Injury"
    assert map_options("weather", "4;5", nc.nc_option_map("weather"), warnings) == "4 Snowing;5 Fog, smog, smoke"
    assert warnings == []
    assert map_options("injury", "9", injury, warnings) == "" and warnings


@pytest.mark.parametrize("text", ["SELF TOW", "POLICE", "TOWING COMPANY", "PERSONAL REQUEST", "OWNER CALLED",
                                  "PRIVATE TOW", "OTHER", "COMPANY", "WATSON'S/ ROTATION/WATSON'S/ ROTATION"])
def test_towed_yes_rows(text):
    assert nc.nc_towed_basis(text) == ("YES", "table")


@pytest.mark.parametrize("text", ["DRIVER", "OWNER", "SELF", "OWNER'S REQUEST", "NOT TOWED", "DESTINATION-ON-WAY",
                                  "DRIVEN FROM SCENE", "CALLED THEIR OWN", "HANDLED/DRIVER",
                                  "DRIVEN TO DESTINATION / DRIVEN TO DESTINATION"])
def test_towed_no_rows(text):
    assert nc.nc_towed_basis(text) == ("NO", "table")


def test_towed_blank_company_names_and_stayed_on_scene():
    assert nc.nc_towed("") == "" and nc.nc_towed("N/A") == "" and nc.nc_towed(None) == ""
    assert nc.nc_towed_basis("KAR KARE/KAR KARE") == ("YES", "assumed")          # bare company name -> YES
    assert nc.nc_towed_basis("RAY FOWLERS") == ("YES", "assumed")
    assert nc.nc_towed_basis("STAYED ON SCENE/STAYED ON SCENE") == ("NO", "assumed")


def test_airbag_any_occupant():
    assert nc.nc_airbag(["1", "2"]) == "YES"
    assert nc.nc_airbag(["1", "1"]) == "NO"
    assert nc.nc_airbag(["0", "5", None, ""]) == ""


def test_ems_letters_and_destination():
    assert nc.nc_ems_letters("A,C,D - REFUSED") == (["A", "C", "D"], "REFUSED")
    assert nc.nc_ems_letters("A - Mission Hospital") == (["A"], "Mission Hospital")
    assert nc.nc_ems_letters("A-N/A") == (["A"], "N/A")
    assert nc.nc_ems_letters("Mission Hospital") == ([], "Mission Hospital")
    assert nc.nc_ems_letters("Duke - Raleigh") == ([], "Duke - Raleigh")            # not a row letter
    assert not nc.nc_has_destination("N/A,") and not nc.nc_has_destination("") and nc.nc_has_destination("Not Transported")


def test_redaction_and_dob():
    assert nc.nc_dob("XX/XX/1985") == "" and nc.nc_dob("09/22/1994") == "09/22/1994"
    assert nc.nc_is_redacted("XX") and nc.nc_is_redacted("XXXXXXX") and not nc.nc_is_redacted("XXA169")
    assert nc.nc_text("14XXXXXXXXXXXXX") == "" and nc.nc_text("null") == "" and nc.nc_text("UNK") == ""


def test_impact_location_matrix():
    for tad, want in [("FC-1", "Front"), ("FD-1", "Front"), ("FR-2", "Right Front"), ("RFQ-1", "Right Front"),
                      ("RP-3", "Right Side"), ("RD-3", "Right Side"), ("RBQ-1", "Right Rear"), ("BR-1", "Right Rear"),
                      ("BD-2", "Rear"), ("BC-2", "Rear"), ("LBQ-1", "Left Rear"), ("BL-1", "Left Rear"),
                      ("LP-7", "Left Side"), ("LD-7", "Left Side"), ("LFQ-1", "Left Front"), ("FL-1", "Left Front"),
                      ("L&T-3", "Multiple"), ("R&T-3", "Multiple"), ("Top-4", "Multiple"), ("Und-1", "Multiple"),
                      ("ND", ""), ("ZZ-1", ""), ("", "")]:
        assert nc.nc_impact_location(tad) == want, tad
    assert nc.nc_impact_location(["FD-1", "BD-2"]) == "Multiple"                    # front and rear is always Multiple
    assert nc.nc_impact_location(["FD-1", "FC-3"]) == "Front"
    assert nc.nc_impact_location(["ND", "FD-1"]) == "Front"
    assert all(v in nc.IMPACT_OPTIONS or v == "" for v in nc.TAD_TO_IMPACT.values())


def test_charge_routing_owner_vs_driver_spelling():
    d, o = "LESVIN GEOVANY GONZALES PEREZ", "LESVIN GEOVANY GONZALEZ PEREZ"
    assert nc.nc_route_charge(d, d, o) == "driver"
    assert nc.nc_route_charge(o, d, o) == "other_unknown"
    assert nc.nc_route_charge("LESVIN GONZALES PEREZ", d, o) == "disregard"       # missing middle name


def test_check_catalog_against_the_real_injury_list():
    live = ["1 Killed", "2 Disabling Injury", "3 Evident Injury", "4 Possible Injury", "5 No Injury", "6 Unknown Injury"]
    assert nc.check_catalog({"injury_code": live}) == []                           # the screenshot from the live app
    problems = nc.check_catalog({"injury_code": ["5 Unknown Injury", "6 No Injury"]})
    assert any("description matches printed code 6" in p for p in problems)
    assert any("zero-padded" in p for p in nc.check_catalog({"injury_code": ["05 | No Injury"]}))


# ------------------------------------------------------------------ the mapper on the real sample
def test_map_incident():
    inc = nc.map_nc(sample_raw(), today=TODAY)["incident"]
    assert inc["report_identifier_1"] == "260816025HA"
    assert inc["incident_date"] == "08/16/2026" and inc["time_2400"] == "03:49"
    assert inc["incident_state"] == "NC" and inc["incident_city"] == "ROCKINGHAM"
    assert inc["incident_street"] == "1960" and inc["incident_cross_street"] == "1946"
    assert inc["weather"] == "1" and inc["road_condition"] == "2" and inc["hit_and_run"] == "1"


def test_map_unit1_driver_vehicle():
    u1 = nc.map_nc(sample_raw(), today=TODAY)["units"][0]
    d, v = u1["driver"], u1["vehicle"]
    assert (d["first_name"], d["middle_name"], d["last_name"]) == ("LESVIN", "GEOVANY", "GONZALES PEREZ")
    assert u1["hit_and_run"] is True                         # flag only; the name is printed so it stays
    assert d["injury_code"] == "5" and d["alcohol_drugs"] == "1"
    assert d["protection"] == "0" and d["ejection"] == "1"
    assert d["contributing"] == "8"                          # margin box 14 (left column); "-" ignored
    assert d["date_of_birth"] == "09/22/1994" and d["drivers_license"] == ""
    assert d["charge"] == "Y0335457-1 - DRIVING WHILE IMPAIRED"
    assert d["extra_charges"] == ["HIT AND RUN/ NO OPERATOR'S LICENSE FAILURE TO"]
    assert v["vehicle_towed"] == "YES" and v["airbag_deployed"] == "YES"
    assert v["impact_location"] == "Front" and v["vehicle_defects"] == "0" and v["speed_limit"] == "35"
    assert v["tag_number"] == "XXA169" and v["tag_state"] == "SC" and v["vin"] == "1GNSCJE0XDR157820"


def test_owner_spelled_differently_is_kept_as_printed():
    assert nc.map_nc(sample_raw(), today=TODAY)["units"][0]["owner"]["last_name"] == "GONZALEZ PEREZ"


def test_unit2_parked_no_driver_name():
    p = nc.map_nc(sample_raw(), today=TODAY)
    u2 = p["units"][1]
    assert u2["driver"]["last_name"] == "PARKED" and u2["hit_and_run"] is False
    assert u2["driver"]["address_1"] == ""                    # "null" is not keyable
    assert u2["vehicle"]["vehicle_towed"] == "NO" and u2["vehicle"]["airbag_deployed"] == ""
    assert u2["owner"]["last_name"] == "RAINWATER" and u2["owner"]["zip_code"] == "283794771"
    assert u2["vehicle"]["impact_location"] == "Right Rear" and u2["vehicle"]["speed_limit"] == "0"
    assert any("STAYED ON SCENE" in n and "towing table" in n for n in p["notes"])   # an assumption is shown


def test_other_parties_witness_and_property_owner():
    ops = nc.map_nc(sample_raw(), today=TODAY)["other_parties"]
    assert sorted(o["role"] for o in ops) == ["PROPERTY OWNER", "WITNESS"]
    w = next(o for o in ops if o["role"] == "WITNESS")
    assert (w["first_name"], w["middle_name"], w["last_name"]) == ("TARA", "NICOLE", "THOMAS")
    assert w["address_1"] == "110 ALEO 9TH AVE" and w["zip_code"] == "28379"
    po = next(o for o in ops if o["role"] == "PROPERTY OWNER")
    assert (po["first_name"], po["last_name"]) == ("STEVE", "WATKINS")


# ------------------------------------------------------------------ rules the sample does not exercise
def test_hit_and_run_driver_without_name_and_both_boxes():
    raw = sample_raw()
    raw["units"][0]["driver"] = {"first": "", "middle": "", "last": ""}
    assert nc.map_nc(raw, today=TODAY)["units"][0]["driver"]["last_name"] == "HIT AND RUN"
    raw["units"][0]["parked"] = True
    p = nc.map_nc(raw, today=TODAY)
    assert p["units"][0]["driver"]["last_name"] == "" and p["units"][0]["hit_and_run"] is False
    assert any("both Parked and Hit & Run" in n for n in p["notes"])


def test_owner_same_as_driver_copies_name_only_when_blank():
    raw = sample_raw()
    raw["units"][0]["owner"] = {"first": "", "middle": "", "last": "", "same_as_driver": True,
                                "same_address_as_driver": True}
    u = nc.map_nc(raw, today=TODAY)["units"][0]
    assert (u["owner"]["first_name"], u["owner"]["last_name"]) == ("LESVIN", "GONZALES PEREZ")
    assert u["owner"]["address_1"] == "" and u["owner"]["same_as_driver_address"] is True


def test_charge_matching_owner_becomes_unknown_other_party():
    raw = sample_raw()
    raw["charges"] = [{"name": "LESVIN GEOVANY GONZALEZ PEREZ", "charge": "SPEEDING"},
                      {"name": "LESVIN GONZALES PEREZ", "charge": "NO LICENSE"}]
    p = nc.map_nc(raw, today=TODAY)
    unk = [o for o in p["other_parties"] if o["role"] == "UNKNOWN"]
    assert len(unk) == 1 and unk[0]["charge"] == "SPEEDING" and unk[0]["last_name"] == "PEREZ"
    assert p["units"][0]["driver"]["charge"] == ""
    assert any("disregarded" in n for n in p["notes"])


def test_nd_has_no_damage_and_no_note_but_unknown_tad_does():
    raw = sample_raw()
    raw["units"][0]["vehicle"]["tad"] = "ND-0"
    p = nc.map_nc(raw, today=TODAY)
    assert p["units"][0]["vehicle"]["impact_location"] == "" and not any("TAD" in n for n in p["notes"])
    raw["units"][0]["vehicle"]["tad"] = "QQ-2"
    assert any("TAD 'QQ-2'" in n for n in nc.map_nc(raw, today=TODAY)["notes"])


# ------------------------------------------------------------------ box 47 (Injured Taken by EMS to)
def _with_people(injury_by_row=None, ems1="", ems2=""):
    """Reference person table: A unit 1 driver, B unit 2 driver, C unit 1 passenger, D and E unit 2 passengers."""
    raw = sample_raw()
    names = {"C": "MARIA LOPEZ", "D": "JOSE RUIZ", "E": "ANA RUIZ"}
    inj = {"A": "5", "B": "5", "C": "5", "D": "5", "E": "5", **(injury_by_row or {})}
    raw["occupants"] = [{"row": r, "vehicle": v, "person_type": t, "name": names.get(r, ""), "address_line": "",
                         "protection": "2", "airbag": "1", "ejection": "1", "injury": inj[r]}
                        for r, v, t in REFERENCE_ROWS]
    raw["units"][0]["ems_taken"], raw["units"][1]["ems_taken"] = ems1, ems2
    return raw


def _ems(p):
    out = {"u1": p["units"][0]["driver"]["ems_to"], "u2": p["units"][1]["driver"]["ems_to"]}
    out.update({o["first_name"]: o["ems_to"] for o in p["other_parties"] if o["role"] == "PASSENGER"})
    return out


def test_ems_with_identifier_uses_the_row_letter_mapping():
    p = nc.map_nc(_with_people(ems1="B - Mission Hospital", ems2="C,E - REFUSED"), today=TODAY)
    assert _ems(p) == {"u1": "", "u2": "Mission Hospital", "MARIA": "REFUSED", "JOSE": "", "ANA": "REFUSED"}
    p = nc.map_nc(_with_people(ems1="A - Mission Hospital"), today=TODAY)            # most likely the unit 1 driver
    assert _ems(p)["u1"] == "Mission Hospital" and _ems(p)["u2"] == ""


def test_ems_without_identifier_one_value_goes_to_the_one_injured_person():
    p = nc.map_nc(_with_people({"C": "3"}, ems1="Mission Hospital"), today=TODAY)
    assert _ems(p) == {"u1": "", "u2": "", "MARIA": "Mission Hospital", "JOSE": "", "ANA": ""}
    p = nc.map_nc(_with_people({"B": "4"}, ems2="Mission Hospital"), today=TODAY)       # either column
    assert _ems(p)["u2"] == "Mission Hospital"


def test_ems_without_identifier_two_values_leaves_everything_blank():
    p = nc.map_nc(_with_people({"C": "3"}, ems1="Mission Hospital", ems2="Not Transported"), today=TODAY)
    assert set(_ems(p).values()) == {""}
    assert any("both fields" in n for n in p["notes"])


def test_ems_without_identifier_needs_exactly_one_injured_person():
    p = nc.map_nc(_with_people({"C": "3", "D": "4"}, ems1="Mission Hospital"), today=TODAY)
    assert set(_ems(p).values()) == {""} and any("cannot be identified" in n for n in p["notes"])
    p = nc.map_nc(_with_people(ems1="Mission Hospital"), today=TODAY)                  # nobody injured
    assert set(_ems(p).values()) == {""}


def test_ems_identifier_value_does_not_count_as_a_plain_value():
    p = nc.map_nc(_with_people({"C": "3"}, ems1="A - Mission Hospital", ems2="Not Transported"), today=TODAY)
    assert _ems(p)["u1"] == "Mission Hospital" and _ems(p)["MARIA"] == "Not Transported"


def test_ems_na_is_not_a_value_and_a_missing_row_is_reported():
    p = nc.map_nc(_with_people({"C": "3"}, ems1="A-N/A", ems2="Mission Hospital"), today=TODAY)
    assert _ems(p)["MARIA"] == "Mission Hospital"
    raw = _with_people(ems1="H - Mission Hospital")
    p = nc.map_nc(raw, today=TODAY)
    assert set(_ems(p).values()) == {""} and any("no such person row" in n for n in p["notes"])


def test_passengers_same_address_and_airbag_from_any_occupant():
    p = nc.map_nc(_with_people(), today=TODAY)
    maria = next(o for o in p["other_parties"] if o["first_name"] == "MARIA")
    assert maria["person_type"] == "Passenger" and maria["vehicle_number"] == "1"
    assert maria["same_as_driver_address"] is True and maria["injury_code"] == "5"
    assert maria["protection"] == "2" and maria["ejection"] == "1"


def test_2023_form_skips_injury_2_and_3():
    raw = sample_raw()
    raw["form_rev"] = "06/2023"
    raw["occupants"][0]["injury"] = "3"
    assert nc.map_nc(raw, today=TODAY)["units"][0]["driver"]["injury_code"] == ""


def test_pedestrian_unit_becomes_other_party_without_vehicle_tab_or_number():
    raw = sample_raw()
    raw["units"][1] = {"number": 2, "column": "right", "pedestrian": True,
                       "driver": {"first": "ANA", "middle": "", "last": "RUIZ", "address_1": "5 MAIN ST"},
                       "owner": {}, "vehicle": {}}
    raw["occupants"].append({"row": "B", "vehicle": "2", "person_type": "3", "injury": "4", "protection": "",
                             "ejection": "", "airbag": ""})
    p = nc.map_nc(raw, today=TODAY)
    assert [u["party_number"] for u in p["units"]] == [1]
    ped = next(o for o in p["other_parties"] if o["role"] == "PEDESTRIAN")
    assert ped["last_name"] == "RUIZ" and ped["injury_code"] == "4"
    assert ped["party_number"] == "" and ped["vehicle_number"] == ""          # the engine would key it into Vehicle #


def test_redacted_values_are_blank():
    raw = sample_raw()
    raw["units"][0]["driver"].update({"dob": "XX/XX/1994", "dl_number": "XXXXXXXXXXXX", "address_1": "XXXXXXX"})
    d = nc.map_nc(raw, today=TODAY)["units"][0]["driver"]
    assert d["date_of_birth"] == "" and d["address_1"] == "" and d["drivers_license"] == ""


def test_unknown_code_leaves_blank_and_notes():
    raw = sample_raw()
    raw["occupants"][0]["injury"] = "9"
    p = nc.map_nc(raw, today=TODAY)
    assert p["units"][0]["driver"]["injury_code"] == "" and any("injury" in n for n in p["notes"])
