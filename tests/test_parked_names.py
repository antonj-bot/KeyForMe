"""PARKED / HIT AND RUN in the driver last name (NJ, NM and the shared rule).
Run: python -m pytest tests/test_parked_names.py -q"""
import pytest

from app.core import driver_rules as dr


# ------------------------------------------------------------------ shared rule
@pytest.mark.parametrize("driver,parked,har,expected", [
    ({}, True, True, "PARKED"),                                  # PARKED has priority
    ({}, True, False, "PARKED"),
    ({}, False, True, "HIT AND RUN"),
    ({}, False, False, ""),
    ({"first_name": "-", "last_name": "--"}, True, False, "PARKED"),   # dashes are no name
    ({"last_name": "SMITH"}, True, True, ""),                    # a written name always wins
    ({"first_name": "BEN"}, False, True, ""),
    ({"last_name": "UNKNOWN"}, True, False, ""),                 # UNKNOWN is a written name
])
def test_placeholder_last_name(driver, parked, har, expected):
    assert dr.placeholder_last_name(driver, parked, har) == expected


def test_apply_placeholder_name_clears_leftover_dashes_and_keeps_other_keys():
    driver = {"first_name": "-", "middle_name": "--", "last_name": "", "sex": "M"}
    assert dr.apply_placeholder_name(driver, True, False) == "PARKED"
    assert driver == {"first_name": "", "middle_name": "", "last_name": "PARKED", "sex": "M"}


def test_apply_placeholder_name_leaves_a_written_name_alone():
    driver = {"first_name": "ANA", "last_name": "ROE"}
    assert dr.apply_placeholder_name(driver, True, True) == ""
    assert driver == {"first_name": "ANA", "last_name": "ROE"}


# ------------------------------------------------------------------ NJ
def _nj(**vehicle):
    from app.keying import nj_rules
    base = {"number": 1, "parked": False, "hit_and_run": False, "driver": {}, "owner": {}, "vehicle": {}}
    base.update(vehicle)
    return nj_rules.map_nj({"vehicles": [base], "occupants": [], "property_owners": []})


def _nj_driver(payload):
    return payload["units"][0]["driver"]


def test_nj_parked_box_and_blank_name_keys_parked():
    d = _nj_driver(_nj(parked=True))
    assert d["last_name"] == "PARKED" and d["first_name"] == ""


def test_nj_parked_wins_over_hit_and_run():
    payload = _nj(parked=True, hit_and_run=True)
    assert _nj_driver(payload)["last_name"] == "PARKED"
    assert not any("both Parked" in n for n in payload["notes"])


def test_nj_hit_and_run_only():
    assert _nj_driver(_nj(hit_and_run=True))["last_name"] == "HIT AND RUN"


def test_nj_no_marks_stays_blank():
    d = _nj_driver(_nj())
    assert d["last_name"] == "" and d["first_name"] == ""


def test_nj_dashes_in_the_name_boxes_count_as_blank():
    d = _nj_driver(_nj(parked=True, driver={"first": "-", "middle": "", "last": "-"}))
    assert d["last_name"] == "PARKED" and d["first_name"] == ""


def test_nj_a_written_name_wins_over_both_marks():
    d = _nj_driver(_nj(parked=True, hit_and_run=True, driver={"first": "JULIA", "last": "HARRISON"}))
    assert (d["first_name"], d["last_name"]) == ("JULIA", "HARRISON")


def test_nj_prompt_names_the_checkbox_row():
    pytest.importorskip("pymupdf")
    from app.extraction import nj_extractor
    assert "Resp. to Emergency" in nj_extractor.UNIT_PAGE_PROMPT and "Parked" in nj_extractor.UNIT_PAGE_PROMPT


# ------------------------------------------------------------------ NM
class _Blank:
    """An NM report/unit whose every attribute that was not given is None."""
    def __init__(self, **values):
        self.__dict__.update(values)

    def __getattr__(self, name):
        return None


def _nm(**unit):
    from app.keying import nm_mapper
    report = _Blank(incident=_Blank(), units=[_Blank(unit_number=1, **unit)], warnings=[])
    return nm_mapper.map_nm(report)


def test_nm_parked_mark_and_blank_name_keys_parked():
    payload = _nm(parked_vehicle=True)
    d = payload["units"][0]["driver"]
    assert d["last_name"] == "PARKED" and d["first_name"] == ""
    assert payload["notes"] == []                      # a note would cancel the NM fill


def test_nm_parked_wins_over_hit_and_run():
    assert _nm(parked_vehicle=True, hit_and_run=True)["units"][0]["driver"]["last_name"] == "PARKED"


def test_nm_hit_and_run_only():
    assert _nm(hit_and_run=True)["units"][0]["driver"]["last_name"] == "HIT AND RUN"


def test_nm_no_marks_stays_blank():
    d = _nm()["units"][0]["driver"]
    assert d["last_name"] == "" and d["first_name"] == ""


def test_nm_written_name_wins():
    d = _nm(parked_vehicle=True, hit_and_run=True, driver_first_name="ANA", driver_last_name="ROE")["units"][0]["driver"]
    assert (d["first_name"], d["last_name"]) == ("ANA", "ROE")


def test_nm_model_and_prompts_read_the_marks():
    pytest.importorskip("pymupdf")
    from app.extraction import nm_extractor
    from app.nm_models import NMUnit
    assert "parked_vehicle" in NMUnit.model_fields and "hit_and_run" in NMUnit.model_fields
    for prompt in (nm_extractor.PAGE_1_PROMPT, nm_extractor.PAGES_2_AND_3_PROMPT):
        assert "parked_vehicle" in prompt and "hit_and_run" in prompt
