"""Tests for the shared HIT AND RUN driver rule (app/core/driver_rules.py + the engine hook).

Run:  python -m pytest tests/test_hit_and_run.py -q
The browser tests use the captured NJ form (mock/nj) and Chrome; they skip themselves if either is
missing. The rule itself is state-independent: any state whose payload sets a per-unit `hit_and_run`
flag gets it.
"""
import copy
import functools
import http.server
import os
import threading
from pathlib import Path

import pytest

from app.core.driver_rules import (HIT_AND_RUN_NAME, apply_hit_and_run_name, has_driver_name, is_flagged,
                                   unit_is_hit_and_run)

MOCK = Path(__file__).resolve().parent.parent / "mock" / "nj"


def payload(*units):
    return {"incident": {"incident_city": "X"}, "units": list(units), "other_parties": []}


def unit(number=1, flag=None, **driver):
    u = {"party_number": number, "driver": driver, "vehicle": {"make": "FORD"}, "owner": {}}
    if flag is not None:
        u["hit_and_run"] = flag
    return u


# ------------------------------------------------------------------ pure rule
@pytest.mark.parametrize("value,expected", [
    (True, True), (1, True), ("1", True), ("Y", True), ("yes", True), ("TRUE", True), ("x", True),
    (False, False), (0, False), ("0", False), ("NO", False), ("N", False), ("", False), (None, False), ("maybe", False),
])
def test_is_flagged(value, expected):
    assert is_flagged(value) is expected


@pytest.mark.parametrize("driver,expected", [
    ({"first_name": "BEN"}, True), ({"last_name": "POE"}, True), ({"middle_name": "T"}, True),
    ({"last_name": "UNKNOWN"}, True), ({"last_name": "0"}, True),
    ({}, False), (None, False), ({"first_name": "", "last_name": ""}, False),
    ({"first_name": "-", "middle_name": "--", "last_name": "***"}, False), ({"suffix": "JR"}, False),
])
def test_has_driver_name(driver, expected):
    assert has_driver_name(driver) is expected


def test_flag_is_read_from_the_unit_the_vehicle_or_the_driver():
    assert unit_is_hit_and_run({"hit_and_run": True})
    assert unit_is_hit_and_run({"vehicle": {"hit_and_run": "YES"}})
    assert unit_is_hit_and_run({"driver": {"hit_and_run": "1"}})
    assert not unit_is_hit_and_run({"vehicle": {"hit_and_run": ""}, "driver": {}})
    assert not unit_is_hit_and_run({}) and not unit_is_hit_and_run(None)


def test_no_names_on_a_flagged_unit_gets_hit_and_run_in_the_last_name():
    original = payload(unit(1, True), unit(2, True, first_name="BEN", last_name="POE"), unit(3))
    snapshot = copy.deepcopy(original)
    result, changed = apply_hit_and_run_name(original)
    assert changed == [1] and original == snapshot                          # the caller's payload is never modified
    assert result["units"][0]["driver"]["last_name"] == HIT_AND_RUN_NAME == "HIT AND RUN"
    assert result["units"][1]["driver"] == {"first_name": "BEN", "last_name": "POE"}      # printed names win
    assert result["units"][2]["driver"] == {}                                            # unflagged unit untouched


def test_without_a_flagged_unit_the_same_payload_object_comes_back():
    p = payload(unit(1), unit(2, False))
    result, changed = apply_hit_and_run_name(p)
    assert result is p and changed == []


def test_placeholders_in_the_name_fields_are_replaced_not_keyed():
    result, _ = apply_hit_and_run_name(payload(unit(1, True, first_name="-", middle_name="--", last_name="-", sex="M")))
    assert result["units"][0]["driver"] == {"first_name": "", "middle_name": "", "last_name": "HIT AND RUN", "sex": "M"}


def test_unknown_is_a_name_and_is_kept():
    result, changed = apply_hit_and_run_name(payload(unit(1, True, last_name="UNKNOWN")))
    assert changed == [] and result["units"][0]["driver"]["last_name"] == "UNKNOWN"


def test_missing_driver_dict_is_created():
    p = payload({"party_number": 4, "hit_and_run": True, "vehicle": {}})
    result, changed = apply_hit_and_run_name(p)
    assert changed == [4] and result["units"][0]["driver"] == {"last_name": "HIT AND RUN"}
    p2 = payload({"party_number": 1, "hit_and_run": True, "driver": None})
    assert apply_hit_and_run_name(p2)[0]["units"][0]["driver"]["last_name"] == "HIT AND RUN"


def test_applying_twice_changes_nothing_more():
    once, _ = apply_hit_and_run_name(payload(unit(1, True)))
    twice, changed = apply_hit_and_run_name(once)
    assert changed == [] and twice is once


def test_units_without_party_numbers_are_reported_by_position():
    _, changed = apply_hit_and_run_name(payload({"hit_and_run": True}, {"hit_and_run": True, "driver": {"last_name": "A"}}, {"hit_and_run": True}))
    assert changed == [1, 3]


@pytest.mark.parametrize("bad", [None, {}, {"units": None}, {"units": [None, "x", 3]}, {"units": []}])
def test_odd_payloads_never_raise(bad):
    result, changed = apply_hit_and_run_name(bad)
    assert changed == []


def test_other_parties_and_other_units_are_never_touched():
    p = payload(unit(1, True))
    p["other_parties"] = [{"role": "PASSENGER", "last_name": ""}]
    result, _ = apply_hit_and_run_name(p)
    assert result["other_parties"] == [{"role": "PASSENGER", "last_name": ""}]


# ------------------------------------------------------------------ engine integration (real Chrome, NJ mock)
TAB_FIX = """() => { document.addEventListener('click', e => {
  const a = e.target.closest('a.ui-tabs-anchor'); if (!a) return; const li = a.closest('li');
  li.parentElement.querySelectorAll('li').forEach(x => x.setAttribute('aria-selected', x === li ? 'true' : 'false'));
}, true); }"""


@pytest.fixture(scope="module")
def browser():
    if not (MOCK / "index.html").exists():
        pytest.skip("mock/nj/index.html not found")
    sync_api = pytest.importorskip("playwright.sync_api")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(MOCK))
    handler.log_message = lambda *a: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_api.sync_playwright() as p:
        exe = os.environ.get("KEYFORME_TEST_CHROMIUM")
        try:
            b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch(channel="chrome")
        except Exception as error:
            pytest.skip(f"no browser available ({type(error).__name__})")
        yield b, f"http://127.0.0.1:{server.server_address[1]}/index.html"
        b.close()
    server.shutdown()


@pytest.fixture
def page(browser, monkeypatch):
    from app.browser import vin_lookup
    monkeypatch.setattr(vin_lookup, "click_popup_ok", lambda *a, **k: False)     # the mock has no VIN pop-up
    b, url = browser
    pg = b.new_page()
    pg.goto(url)
    pg.wait_for_timeout(300)
    pg.frames[1].evaluate(TAB_FIX)
    yield pg
    pg.close()


def open_unit(pg, number):
    from app.browser import nj_field_mapping as m
    sec = pg.frame_locator(m.FRAME).locator(m.UNIT_SECTION)
    anchors = sec.locator(m.TAB_ANCHORS)
    href = anchors.nth(number - 1).get_attribute("href").lstrip("#")
    anchors.nth(number - 1).click()
    panel = sec.locator(f'[id="{href}"]')
    panel.wait_for(state="visible", timeout=8000)
    return panel


def driver_names(pg, number):
    from app.browser import nj_field_mapping as m
    panel = open_unit(pg, number)
    box = lambda key: panel.locator(m.DRIVER[key]).nth(1).input_value()           # owner is the 1st match, driver the 2nd
    return box("first_name"), box("middle_name"), box("last_name")


def test_engine_keys_hit_and_run_when_the_flag_is_set_and_there_is_no_name(page):
    from app.browser.engine import fill_form
    p = payload(unit(1, True), unit(2, True, first_name="BEN", last_name="POE"), unit(3, False))
    logs = []
    warnings = fill_form(page, p, state="NJ", log=logs.append)
    assert driver_names(page, 1) == ("", "", "HIT AND RUN")
    assert driver_names(page, 2) == ("BEN", "", "POE")
    assert driver_names(page, 3) == ("", "", "")
    assert warnings == [] or not any("last_name" in w for w in warnings)
    assert "Unit 1: no driver name on a hit-and-run vehicle; keying HIT AND RUN as the last name" in logs
    assert not any(l.startswith("Unit 2:") and "hit-and-run" in l for l in logs)
    assert p["units"][0]["driver"] == {}                                           # the caller's payload is unchanged


def test_engine_logs_never_contain_names(page):
    from app.browser.engine import fill_form
    logs = []
    fill_form(page, payload(unit(1, True, last_name="UNKNOWN")), state="NJ", log=logs.append)
    assert not any("HIT AND RUN" in l for l in logs) and driver_names(page, 1)[2] == "UNKNOWN"


def test_a_payload_without_the_flag_fills_exactly_as_before(page):
    from app.browser.engine import fill_form
    fill_form(page, payload(unit(1, None), unit(2, False)), state="NJ")
    assert driver_names(page, 1) == ("", "", "") and driver_names(page, 2) == ("", "", "")
