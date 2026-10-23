"""Tests for four NC fixes found on report-1253501714 (a report with an original form AND a supplemental form):

  1. 'APT,2022B' after the street went into Address 1: apartment / unit text belongs in Address 2.
  2. Supplemental Report box ticked: key ONLY the supplemental form; the original form is disregarded.
  3. Home phone '( 516 ) 530-0635' was keyed as '530-0635': the area code must be kept.
  4. A TAD box with several codes ('FC-2,FD-3') used only the first code (front + rear must be Multiple).

The fixture below is that PDF, read from its page images (pages 1-2 = original form, pages 3-4 = supplemental form).
The model call is never made: forms are built by hand and sent through the real merge / rules code.
"""
import sys
from datetime import date
from pathlib import Path

import pytest

from app.core.completeness import IncompleteExtractionError
from app.extraction import nc_extractor as ex
from app.keying import nc_rules as nc

sys.path.insert(0, str(Path(__file__).resolve().parent))

TODAY = date(2026, 10, 23)
CHARGE = {"name": "KENIEL ANTHONY KIRLEW", "charge": "6812H27 - FAIL TO REDUCE SPEED."}


def unit1(dob="02/28/1993"):
    return {
        "number": 1, "column": "left",
        "driver": {"first": "KENIEL", "middle": "ANTHONY", "last": "KIRLEW",
                   "address_1": "2008 S MEBANE ST, APT,2022B", "city": "BURLINGTON", "state": "NC", "zip": "272157674",
                   "phone_area": "516", "phone": "530-0635", "dob": dob, "dl_number": "46469078", "dl_state": "NC",
                   "alcohol_suspected": "0"},
        "owner": {"first": "KENIEL", "middle": "ANTHONY", "last": "KIRLEW",
                  "address_1": "2008 S MEBANE ST, APT,2022B", "city": "BURLINGTON", "state": "NC", "zip": "272157674"},
        "vehicle": {"plate": "KJC4936", "plate_state": "NC", "vin": "KMHLM4AG5MU175634", "year": "2021",
                    "make": "HYUNDAI", "tad": "FC-2,FD-3", "insurance_company": "PROGRESSIVE PREMIER INS CO OF",
                    "policy_number": "990320135", "defects": "0", "speed_limit": "65",
                    "towed_by": "TORAIN'S WRECKER SERVICE/TORAIN'S WRECKER SERVICE"},
        "ems_taken": "UNC HILLSBOROUGH,",
    }


def unit2():
    return {
        "number": 2, "column": "right",
        "driver": {"first": "SOBEYDA", "middle": "ABIGAIL", "last": "PUERTO", "address_1": "6330 NATURE WALK DR",
                   "city": "CHARLOTTE", "state": "NC", "zip": "282124562", "phone_area": "704", "phone": "299-5225",
                   "dob": "09/20/1990", "dl_number": "35194700", "dl_state": "NC", "alcohol_suspected": "0"},
        "owner": {"first": "SOBEYDA", "middle": "ABIGAIL", "last": "PUERTO", "address_1": "6330 NATURE WALK DR",
                  "city": "CHARLOTTE", "state": "NC", "zip": "282124562"},
        "vehicle": {"plate": "LHA1503", "plate_state": "NC", "vin": "3N1CN7AP0KL823202", "year": "2019",
                    "make": "NISSAN", "tad": "BC-3,BD-3", "insurance_company": "STATE FARM MUTUAL AUTOMOBILE",
                    "policy_number": "495 5372 B07 33", "defects": "0", "speed_limit": "65", "towed_by": "OWNER/OWNER"},
        "ems_taken": "",
    }


def occupants():
    row = lambda r, v, t, inj, **kw: {"row": r, "vehicle": v, "person_type": t, "protection": "2", "airbag": "2",
                                      "ejection": "1", "injury": inj, **kw}
    return [row("A", "1", "1", "4"), row("B", "2", "1", "4"),
            row("C", "1", "2", "4", name="CLINTON PHILEMON HENRY", dob="01/10/1990",
                address_line="5600 SYCAMORE GLEN RD,GREENSBORO,NC 27405")]


def make_form(*, supplemental, dob1="02/28/1993", with_charge=True, **over):
    d = {"form_rev": "1/2009", "form_number": 1, "form_total": 1, "supplemental": supplemental,
         "units_involved": 2, "local_use": "250105155DA/02", "crash_date": "01/05/2025", "crash_time": "20:28",
         "municipality": "HILLSBOROUGH", "on_road": "I 85", "from_road": "US 70",
         "latitude": "36.038730", "longitude": "-79.01086",
         "margin_boxes": [{"box": "3", "value": "1"}, {"box": "4", "value": "1"}],
         "units": [unit1(dob1), unit2()], "occupants": occupants(),
         "charges": [CHARGE] if with_charge else []}
    d.update(over)
    return ex.NCFormExtraction.model_validate(d)


def payload_of(forms):
    raw = ex.merge_forms(forms)
    ex.check_units(raw)
    return raw, nc.map_nc(raw, today=TODAY)


# ------------------------------------------------------------------ 1. apartment / unit goes to Address 2
@pytest.mark.parametrize("line,want", [
    ("2008 S MEBANE ST, APT,2022B", ("2008 S MEBANE ST", "APT,2022B")),      # the reported case, kept as printed
    ("123 MAIN ST APT B", ("123 MAIN ST", "APT B")),
    ("55 OAK AVE, UNIT 4C", ("55 OAK AVE", "UNIT 4C")),
    ("9 ELM RD STE 100", ("9 ELM RD", "STE 100")),
    ("77 PINE ST #12", ("77 PINE ST", "#12")),
    ("5 LAKE DR, LOT 12", ("5 LAKE DR", "LOT 12")),
    ("8 FIRST ST FL 2", ("8 FIRST ST", "FL 2")),
    ("40 BAY RD, APARTMENT 7", ("40 BAY RD", "APARTMENT 7")),
])
def test_unit_part_moves_to_address_2(line, want):
    assert nc.nc_split_unit(line) == want


@pytest.mark.parametrize("line", [
    "2008 S MEBANE ST", "12 LOT ST", "100 PARK FL", "UNITED DR 5", "10 MAIN ST, FL 33101", "APT 5", "", "ROUTE 7",
])
def test_streets_are_left_alone(line):
    assert nc.nc_split_unit(line) == (line, "")


def test_existing_address_2_is_never_overwritten():
    src = {"address_1": "1 MAIN ST APT 9", "address_2": "BLDG C", "city": "X", "state": "NC", "zip": "27401"}
    a = nc._nc_address(src, "t", [])
    assert (a["address_1"], a["address_2"]) == ("1 MAIN ST APT 9", "BLDG C")


def test_driver_and_owner_address_2_in_the_payload():
    _, p = payload_of([make_form(supplemental=True)])
    d, o = p["units"][0]["driver"], p["units"][0]["owner"]
    assert (d["address_1"], d["address_2"], d["city"], d["zip_code"]) == ("2008 S MEBANE ST", "APT,2022B", "BURLINGTON", "272157674")
    assert (o["address_1"], o["address_2"]) == ("2008 S MEBANE ST", "APT,2022B")
    assert p["units"][1]["driver"]["address_2"] == ""                              # no apartment: nothing invented


def test_apartment_in_a_one_line_address_and_in_witness_and_property_owner():
    f = make_form(supplemental=True, witnesses=[{"name": "TARA NICOLE THOMAS", "address_1": "110 ALEO 9TH AVE APT 3",
                                                 "city": "ROCKINGHAM", "state": "NC", "zip": "28379",
                                                 "phone_area": "910", "phone": "555-1212"}],
                  property_owners=[{"name": "STEVE WATKINS", "address_1": "127 ALEO NINTH AVE, STE 5",
                                    "city": "ROCKINGHAM", "state": "NC", "zip": "28379"}])
    _, p = payload_of([f])
    w = next(o for o in p["other_parties"] if o["role"] == "WITNESS")
    po = next(o for o in p["other_parties"] if o["role"] == "PROPERTY OWNER")
    assert (w["address_1"], w["address_2"]) == ("110 ALEO 9TH AVE", "APT 3")
    assert (po["address_1"], po["address_2"]) == ("127 ALEO NINTH AVE", "STE 5")
    assert w["phone"] == "910 555-1212"                                            # witness phone keeps its area code too


# ------------------------------------------------------------------ 3. phone keeps the area code
@pytest.mark.parametrize("number,area,want", [
    ("530-0635", "516", "516 530-0635"),                  # the reported case: area code was dropped
    ("(516) 530-0635", None, "516 530-0635"),
    ("516-530-0635", "", "516 530-0635"),
    ("5165300635", None, "516 530-0635"),
    ("1 516 530-0635", None, "516 530-0635"),
    ("516 530-0635", "516", "516 530-0635"),               # not doubled when the model already merged them
    ("530-0635", None, "530-0635"),                       # no area code on the report: nothing invented
    ("530-0635", "5", "530-0635"),                        # not a 3-digit area code
    ("", "516", ""), (None, None, ""),
    ("XXXXXXXXXX", "XXX", ""), ("null", "516", ""),       # redacted / null: blank
    ("516 530-0635 X12", None, "516 530-0635 X12"),        # not a plain phone number: kept as printed
])
def test_phone(number, area, want):
    assert nc.nc_phone(number, area) == want


def test_driver_phones_in_the_payload_and_note_when_no_area_code():
    _, p = payload_of([make_form(supplemental=True)])
    assert p["units"][0]["driver"]["phone"] == "516 530-0635"
    assert p["units"][1]["driver"]["phone"] == "704 299-5225"
    f = make_form(supplemental=True)
    f.units[0].driver.phone_area = None
    _, p2 = payload_of([f])
    assert p2["units"][0]["driver"]["phone"] == "530-0635"
    assert any("no area code" in n and "Unit 1 driver" in n for n in p2["notes"])


# ------------------------------------------------------------------ 4. several codes in one TAD box
@pytest.mark.parametrize("tad,want", [
    ("FC-2,FD-3", "Front"), ("BC-3,BD-3", "Rear"), ("FD-1,BD-2", "Multiple"), ("FD-1, BD-2", "Multiple"),
    ("FD-1;LD-2", "Multiple"), ("FC-2 FD-3", "Front"), ("FD - 2", "Front"), ("ND-0", ""), ("ND-0,FD-1", "Front"),
    ("ZZ-1,FD-2", "Front"), ("", ""), (None, ""),
])
def test_tad_with_several_codes(tad, want):
    assert nc.nc_impact_location(tad) == want


def test_tad_in_the_payload():
    _, p = payload_of([make_form(supplemental=True)])
    assert p["units"][0]["vehicle"]["impact_location"] == "Front"
    assert p["units"][1]["vehicle"]["impact_location"] == "Rear"
    assert not any("TAD" in n for n in p["notes"])
    f = make_form(supplemental=True)
    f.units[0].vehicle.tad = "QQ-1,ZZ-2"
    assert any("TAD 'QQ-1,ZZ-2'" in n for n in payload_of([f])[1]["notes"])


# ------------------------------------------------------------------ 2. Supplemental Report box ticked
@pytest.mark.parametrize("order", ["original_first", "supplemental_first"])
def test_only_the_supplemental_form_is_keyed(order):
    original = make_form(supplemental=False, dob1="01/01/1980", with_charge=False)      # different dob, no charge
    supplemental = make_form(supplemental=True)
    forms = [original, supplemental] if order == "original_first" else [supplemental, original]
    raw, p = payload_of(forms)
    assert raw["supplemental_only"] is True
    assert [u["number"] for u in raw["units"]] == [1, 2]                              # no duplicates
    assert p["units"][0]["driver"]["date_of_birth"] == "02/28/1993"                   # the supplemental reading
    assert p["units"][0]["driver"]["charge"] == "6812H27 - FAIL TO REDUCE SPEED."      # only on the supplemental form
    sup_pages, orig_pages = ("3-4", "1-2") if order == "original_first" else ("1-2", "3-4")
    note = next(n for n in p["notes"] if "Supplemental Report" in n)
    assert f"pages {sup_pages}" in note and f"pages {orig_pages}" in note and "disregarded" in note
    assert not any("appears on more than one form" in n for n in p["notes"])


def test_unchanged_when_no_form_or_every_form_is_supplemental():
    for flag in (False, True):
        raw = ex.merge_forms([make_form(supplemental=flag), make_form(supplemental=flag)])
        assert raw["supplemental_only"] is False and len(raw["units"]) == 2
        assert not any("Supplemental Report box" in n for n in raw["notes"])
        assert any("appears on more than one form" in n for n in raw["notes"])           # unchanged behaviour


def test_continuation_form_without_the_box_still_adds_units():
    f1 = make_form(supplemental=False, units_involved=3)
    u3 = unit2() | {"number": 3, "column": "left"}
    f2 = make_form(supplemental=False, units_involved=3, form_number=2, form_total=2, units=[u3], occupants=[], charges=[])
    raw, p = payload_of([f1, f2])
    assert sorted(u["party_number"] for u in p["units"]) == [1, 2, 3] and raw["supplemental_only"] is False


def test_supplemental_form_that_lacks_a_unit_cancels_instead_of_dropping_it():
    original = make_form(supplemental=False)                                          # has units 1 and 2
    supplemental = make_form(supplemental=True, units=[unit1()], occupants=[])        # unit 2 unreadable / missing
    raw = ex.merge_forms([original, supplemental])
    with pytest.raises(IncompleteExtractionError) as err:
        ex.check_units(raw)
    assert "[2]" in str(err.value) and "supplemental" in str(err.value).lower()


def test_prompt_and_schema_ask_for_what_the_rules_need():
    for needle in ("marked with an X", "Non-Reportable", "phone_area", "address_2", "APT,2022B", "FC-2,FD-3"):
        assert needle in ex.FORM_PROMPT, needle
    assert "phone_area" in ex.NCPerson.model_fields and "phone_area" in ex.NCParty.model_fields
