"""Browser tests against the captured NJ keying form (mock/nj/index.html) in real Chrome.

Run:  python -m pytest tests/test_nj_form.py -q
Set KEYFORME_TEST_CHROMIUM to a browser executable to avoid channel="chrome".
Skipped automatically when mock/nj/ or a browser is missing.

The mock is a static capture: the site's own scripts are removed, so the (+) charge button
does nothing there. The tests add a tiny script that imitates it (clone the Charge row).
That checks our CLICK-AND-WAIT logic; the site's real (+) behaviour must be confirmed on UAT.
"""
import functools
import http.server
import os
import threading
from pathlib import Path

import pytest

from app.browser import nj_extras as extras
from app.browser import nj_field_mapping as m

MOCK = Path(__file__).resolve().parent.parent / "mock" / "nj"

# jQuery UI marks the active <li aria-selected="true">; the capture shim only switches panels.
TAB_FIX = """() => { document.addEventListener('click', e => {
  const a = e.target.closest('a.ui-tabs-anchor'); if (!a) return; const li = a.closest('li');
  li.parentElement.querySelectorAll('li').forEach(x => x.setAttribute('aria-selected', x === li ? 'true' : 'false'));
}, true); }"""

# imitates the real (+): append a new Charge row after the clicked one
PLUS_SHIM = """() => { document.addEventListener('click', e => {
  const plus = e.target.closest('.citations a.add-item'); if (!plus) return;
  const row = plus.closest('.item-content'); const copy = row.cloneNode(true);
  const input = copy.querySelector("input[type=text]"); input.value = "";
  input.id = input.id + '-' + (document.querySelectorAll("[id^='Citations_CitationDetail-']").length + 1);
  row.parentElement.appendChild(copy);
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
def page(browser):
    b, url = browser
    pg = b.new_page()
    pg.goto(url)
    pg.wait_for_timeout(300)
    inner = pg.frames[1]
    inner.evaluate(TAB_FIX)
    inner.evaluate(PLUS_SHIM)
    yield pg
    pg.close()


def frame(pg):
    return pg.frame_locator(m.FRAME)


def open_tab(pg, section, number):
    return extras._panel(frame(pg).locator(section), number)


# ------------------------------------------------------------------ selectors
def test_incident_selectors_match_exactly_one_field(page):
    for key, selector in m.INCIDENT.items():
        assert frame(page).locator(selector).count() == 1, key
    assert frame(page).locator(m.HIT_AND_RUN).count() == 1


def test_unit_panel_selectors(page):
    panel = open_tab(page, m.UNIT_SECTION, 1)
    for key, selector in m.OWNER.items():
        assert panel.locator(selector).count() == 2, f"owner/driver pair: {key}"      # owner first, driver second
    for key in ("alcohol_test", "charge", "safety_available", "ejection", "hospital", "safety_used"):
        assert panel.locator(m.DRIVER[key]).count() == 1, key
    for key, selector in m.VEHICLE.items():
        assert panel.locator(selector).count() == 1, key
    for radio in m.RADIO_FIELDS.values():
        assert panel.locator(f"[id^='Vehicle_{radio}-']").count() >= 2, radio          # YES / NO radios


def test_other_party_panel_selectors(page):
    panel = open_tab(page, m.OTHER_SECTION, 1)
    for key, selector in m.OTHER.items():
        assert panel.locator(selector).count() == 1, key


def test_tabs_exist_for_a_four_unit_report_and_nine_other_parties(page):
    assert frame(page).locator(m.UNIT_SECTION).locator(m.TAB_ANCHORS).count() >= 4
    assert frame(page).locator(m.OTHER_SECTION).locator(m.TAB_ANCHORS).count() >= 9


# ------------------------------------------------------------------ Hit & Run
def test_hit_and_run_is_ticked_only_when_flagged(page):
    assert extras.tick_hit_and_run(page, {"incident": {"hit_and_run": ""}}) == []
    assert not frame(page).locator(m.HIT_AND_RUN).is_checked()
    assert extras.tick_hit_and_run(page, {"incident": {"hit_and_run": "1"}}) == []
    assert frame(page).locator(m.HIT_AND_RUN).is_checked()


def test_hit_and_run_failure_is_a_warning_not_an_exception(page):
    page.frames[1].evaluate("document.querySelector('#Incident_IncidentHitAndRun-v1').remove()")
    warnings = extras.tick_hit_and_run(page, {"incident": {"hit_and_run": "1"}})
    assert len(warnings) == 1 and "tick it by hand" in warnings[0]


# ------------------------------------------------------------------ extra charges
def charge_values(page, unit):
    panel = open_tab(page, m.UNIT_SECTION, unit)
    return [panel.locator(m.CHARGE).nth(i).input_value() for i in range(panel.locator(m.CHARGE).count())]


def test_extra_charges_use_the_plus_button_in_order(page):
    payload = {"units": [{"party_number": 1, "driver": {"extra_charges": ["39:3-10 UNLICENSED", "39:4-82 KEEP RIGHT", "39:4-97.3 HANDHELD"]}},
                         {"party_number": 2, "driver": {"extra_charges": []}}]}
    open_tab(page, m.UNIT_SECTION, 1).locator(m.CHARGE).first.fill("39:4-88B FIRST")        # the engine keys the first charge
    logs = []
    assert extras.add_extra_charges(page, payload, logs.append) == []
    assert charge_values(page, 1) == ["39:4-88B FIRST", "39:3-10 UNLICENSED", "39:4-82 KEEP RIGHT", "39:4-97.3 HANDHELD"]
    assert charge_values(page, 2) == [""]                                                    # unit 2 untouched
    assert logs == ["Unit 1: 3 extra charge(s) keyed"]


def test_units_without_extra_charges_are_not_touched(page):
    assert extras.add_extra_charges(page, {"units": [{"party_number": 1, "driver": {"charge": "X", "extra_charges": []}}]}) == []
    assert charge_values(page, 1) == [""]


def test_missing_plus_button_warns_and_leaves_the_rest(page):
    page.frames[1].evaluate("document.querySelectorAll('.citations a.add-item').forEach(a => a.remove())")
    warnings = extras.add_extra_charges(page, {"units": [{"party_number": 1, "driver": {"extra_charges": ["A", "B"]}}]})
    assert len(warnings) == 1 and "Unit 1" in warnings[0] and "by hand" in warnings[0]


def test_plus_button_that_adds_nothing_warns(browser):
    b, url = browser
    bare = b.new_page()                                    # no (+) script at all: the click changes nothing
    bare.goto(url)
    bare.wait_for_timeout(300)
    bare.frames[1].evaluate(TAB_FIX)
    try:
        warnings = extras.add_extra_charges(bare, {"units": [{"party_number": 1, "driver": {"extra_charges": ["A"]}}]})
        assert len(warnings) == 1 and "Unit 1" in warnings[0]
    finally:
        bare.close()


def test_unit_tab_that_does_not_exist_warns(page):
    warnings = extras.add_extra_charges(page, {"units": [{"party_number": 99, "driver": {"extra_charges": ["A"]}}] * 20})
    assert warnings and all("by hand" in w for w in warnings)


# ------------------------------------------------------------------ Same As address boxes
def set_other_last_name(page, number, name):
    open_tab(page, m.OTHER_SECTION, number).locator(m.OTHER["last_name"]).fill(name)


def test_same_as_driver_box_is_ticked_when_flagged(page):
    set_other_last_name(page, 1, "STAPLETON")
    payload = {"other_parties": [{"last_name": "STAPLETON", "same_as_driver_address": True, "same_as_owner_address": False}]}
    assert extras.tick_same_as_address(page, payload) == []
    panel = open_tab(page, m.OTHER_SECTION, 1)
    assert panel.locator(m.OTHER["same_as_driver_address"]).is_checked()
    assert not panel.locator(m.OTHER["same_as_owner_address"]).is_checked()


def test_same_as_owner_box(page):
    set_other_last_name(page, 1, "KAY")
    extras.tick_same_as_address(page, {"other_parties": [{"last_name": "KAY", "same_as_driver_address": False, "same_as_owner_address": True}]})
    panel = open_tab(page, m.OTHER_SECTION, 1)
    assert panel.locator(m.OTHER["same_as_owner_address"]).is_checked()
    assert not panel.locator(m.OTHER["same_as_driver_address"]).is_checked()


def test_nothing_ticked_when_an_address_was_keyed(page):
    set_other_last_name(page, 1, "JAY")
    assert extras.tick_same_as_address(page, {"other_parties": [{"last_name": "JAY", "same_as_driver_address": False, "same_as_owner_address": False}]}) == []
    assert not open_tab(page, m.OTHER_SECTION, 1).locator(m.OTHER["same_as_driver_address"]).is_checked()


def test_wrong_person_in_the_tab_is_never_ticked(page):
    set_other_last_name(page, 1, "SOMEONE ELSE")
    warnings = extras.tick_same_as_address(page, {"other_parties": [{"last_name": "STAPLETON", "same_as_driver_address": True}]})
    assert len(warnings) == 1 and "by hand" in warnings[0]
    assert not open_tab(page, m.OTHER_SECTION, 1).locator(m.OTHER["same_as_driver_address"]).is_checked()


def test_party_without_a_name_is_ticked_without_the_name_check(page):
    assert extras.tick_same_as_address(page, {"other_parties": [{"last_name": "", "same_as_driver_address": True}]}) == []
    assert open_tab(page, m.OTHER_SECTION, 1).locator(m.OTHER["same_as_driver_address"]).is_checked()


def test_fill_nj_extras_runs_everything_and_never_raises(page):
    set_other_last_name(page, 1, "KAY")
    payload = {"incident": {"hit_and_run": "1"},
               "units": [{"party_number": 1, "driver": {"extra_charges": ["B"]}}],
               "other_parties": [{"last_name": "KAY", "same_as_driver_address": True}]}
    assert extras.fill_nj_extras(page, payload) == []
    assert frame(page).locator(m.HIT_AND_RUN).is_checked() and charge_values(page, 1)[-1] == "B"
    assert extras.fill_nj_extras(page, {}) == []                                       # empty payload is fine
