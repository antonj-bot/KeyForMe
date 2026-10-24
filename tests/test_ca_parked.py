"""CA: PARKED / HIT AND RUN placeholders in the driver last name.
Run: python -m pytest tests/test_ca_parked.py -q"""
import pytest

from app.extraction import ca_extractor
from app.keying import ca_mapper as m
from app.models import CaliforniaCHP555, CodingFields, Party, PartyPage1, ReportFields


def _blank(model, **over):
    data = {}
    for name, field in model.model_fields.items():
        if name in over or not field.is_required():
            continue
        data[name] = [] if "list" in str(field.annotation) else None
    data.update(over)
    return model(**data)


def _party(number, name=None, parked=None, plate="ABC123", **over):
    extra = {} if parked is None else {"parked_vehicle": parked}
    return _blank(Party, party_number=number, driver_name=name, license_plate=plate, **extra, **over)


def _report(*parties, hit_and_run=None):
    return CaliforniaCHP555(
        report=_blank(ReportFields, felony_hit_and_run=hit_and_run),
        parties=list(parties), coding=_blank(CodingFields))


def _driver(payload, number):
    return next(u for u in payload["units"] if u["party_number"] == number)["driver"]


def test_blank_name_and_parked_box_keys_parked():
    d = _driver(m.map_ca_keying(_report(_party(1, parked=True))), 1)
    assert d["last_name"] == "PARKED" and d["first_name"] == ""


def test_parked_has_priority_over_hit_and_run():
    payload = m.map_ca_keying(_report(_party(1, parked=True), hit_and_run="X"))
    assert _driver(payload, 1)["last_name"] == "PARKED"
    assert any("PARKED" in n for n in payload["notes"])


def test_the_reported_bug_hit_and_run_driver_and_the_parked_car_it_hit():
    payload = m.map_ca_keying(_report(_party(1, plate="RUN1"), _party(2, parked=True, plate="PARK2"), hit_and_run="X"))
    assert _driver(payload, 1)["last_name"] == "HIT AND RUN"
    assert _driver(payload, 2)["last_name"] == "PARKED"


def test_blank_name_hit_and_run_without_parked_box():
    assert _driver(m.map_ca_keying(_report(_party(1), hit_and_run="X")), 1)["last_name"] == "HIT AND RUN"


def test_blank_name_no_marks_stays_blank():
    d = _driver(m.map_ca_keying(_report(_party(1))), 1)
    assert d["last_name"] == "" and d["first_name"] == ""


@pytest.mark.parametrize("mark", ["NO", "N", "0", "", "false", "None"])
def test_a_no_is_not_a_hit_and_run(mark):
    assert _driver(m.map_ca_keying(_report(_party(1), hit_and_run=mark)), 1)["last_name"] == ""


def test_a_written_name_wins_over_both_placeholders():
    payload = m.map_ca_keying(_report(_party(1, name="JOHN Q PUBLIC", parked=True), hit_and_run="X"))
    d = _driver(payload, 1)
    assert (d["first_name"], d["middle_name"], d["last_name"]) == ("JOHN", "Q", "PUBLIC")
    assert not any("PARKED" in n for n in payload["notes"])


@pytest.mark.parametrize("written", ["PARKED", "parked", "PARKED VEHICLE", "Parked Veh."])
def test_a_printed_parked_is_keyed_in_last_name(written):
    d = _driver(m.map_ca_keying(_report(_party(1, name=written))), 1)
    assert d["first_name"] == "" and d["last_name"] == " ".join(written.split())


def test_printed_hit_and_run_is_keyed_in_last_name():
    d = _driver(m.map_ca_keying(_report(_party(1, name="HIT AND RUN"))), 1)
    assert d["first_name"] == "" and d["last_name"] == "HIT AND RUN"


def test_other_words_are_keyed_as_written():
    d = _driver(m.map_ca_keying(_report(_party(1, name="PARKED CITED"))), 1)
    assert (d["first_name"], d["last_name"]) == ("PARKED", "CITED")


def test_parked_mark_alone_still_makes_a_unit():
    party = _blank(Party, party_number=3, parked_vehicle=True)
    payload = m.map_ca_keying(_report(party))
    assert [u["party_number"] for u in payload["units"]] == [3]
    assert _driver(payload, 3)["last_name"] == "PARKED"


def test_unmarked_empty_party_is_still_skipped():
    assert m.map_ca_keying(_report(_blank(Party, party_number=3)))["units"] == []


def test_model_and_prompt_read_the_parked_box():
    assert PartyPage1.model_fields["parked_vehicle"].default is False
    assert "PARKED VEHICLE" in ca_extractor.PAGE1_PROMPT and "parked_vehicle" in ca_extractor.PAGE1_PROMPT
