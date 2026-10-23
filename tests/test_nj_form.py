"""Browser tests against the captured NJ keying form (mock/nj/index.html) in real Chrome.

Run:  python -m pytest tests/test_nj_form.py -q
Browser: these tests use Playwright's OWN Chromium by default (install it once with
`python -m playwright install chromium`). On the dev machine, key presses in the installed Chrome
(channel="chrome") randomly stalled for seconds (see tools/diagnose_impact_location.py output), which
made these tests slow and flaky, while Playwright's Chromium was consistently fast. The app itself is
still checked in real Chrome on UAT. To run the tests in your installed Chrome anyway:
    $env:KEYFORME_TEST_BROWSER = "chrome"
To use any other browser executable:  $env:KEYFORME_TEST_CHROMIUM = "C:\\path\\to\\browser.exe"
Skipped automatically when mock/nj/ or a browser is missing.

Speed: the captured form holds 15 unit tabs and 10 other-party tabs (about 1300 fields), far more than a real
report. Every test page is trimmed to 4 + 4 tabs (about 400 fields, like a real 4-vehicle report) and every
Playwright call has a 10 s default timeout, so a stuck step fails in seconds, not minutes.

The mock is a static capture: the site's own scripts are removed, so the (+) charge button
does nothing there. The tests add a tiny script that imitates it (clone the Charge row).
That checks our CLICK-AND-WAIT logic; the site's real (+) behaviour must be confirmed on UAT.
"""
import functools
import http.server
import os
import re
import threading
import time
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


# Keep only the first `units` unit tabs and `others` other-party tabs (removes the extra panels from the DOM).
TRIM_JS = """(cfg) => {
  const trim = (id, keep) => {
    const s = document.getElementById(id); if (!s) return 0;
    const anchors = Array.from(s.querySelectorAll('ul.ui-tabs-nav > li > a.ui-tabs-anchor'));
    anchors.slice(keep).forEach(a => {
      const pid = a.getAttribute('href').slice(1);
      const panel = Array.from(s.querySelectorAll('[role="tabpanel"]')).find(p => p.id === pid);
      if (panel) panel.remove();
      a.closest('li').remove();
    });
    return anchors.length;
  };
  return [trim('section-page-base-owner-02', cfg.units), trim('section-page-base-passenger-03', cfg.others)];
}"""
KEEP_UNITS, KEEP_OTHERS = 4, 4


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):          # no request lines in the test output
        pass


def launch_test_browser(playwright):
    """KEYFORME_TEST_CHROMIUM=<exe> wins; KEYFORME_TEST_BROWSER=chrome uses the installed Chrome;
    otherwise Playwright's own Chromium."""
    exe = os.environ.get("KEYFORME_TEST_CHROMIUM")
    if exe:
        return playwright.chromium.launch(executable_path=exe)
    if os.environ.get("KEYFORME_TEST_BROWSER", "").strip().lower() == "chrome":
        return playwright.chromium.launch(channel="chrome")
    return playwright.chromium.launch()


@pytest.fixture(scope="module")
def browser():
    if not (MOCK / "index.html").exists():
        pytest.skip("mock/nj/index.html not found")
    sync_api = pytest.importorskip("playwright.sync_api")
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(QuietHandler, directory=str(MOCK)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    with sync_api.sync_playwright() as p:
        try:
            b = launch_test_browser(p)
        except Exception as error:
            pytest.skip(f"no browser available ({type(error).__name__}); run: python -m playwright install chromium")
        yield b, f"http://127.0.0.1:{server.server_address[1]}/index.html"
        b.close()
    server.shutdown()
    server.server_close()


def open_page(browser, plus=True):
    b, url = browser
    pg = b.new_page()
    pg.set_default_timeout(10_000)                       # no step may hide for 30 s
    pg.goto(url)
    pg.wait_for_timeout(300)
    inner = pg.frames[1]
    inner.evaluate(TRIM_JS, {"units": KEEP_UNITS, "others": KEEP_OTHERS})
    inner.evaluate(TAB_FIX)
    if plus:
        inner.evaluate(PLUS_SHIM)
    return pg


@pytest.fixture
def page(browser):
    pg = open_page(browser)
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


def test_the_capture_has_enough_tabs_for_a_four_unit_report_and_nine_other_parties():
    html = (MOCK / "nj_form.html").read_text(encoding="utf-8")
    owner, other = html.split('id="section-page-base-passenger-03"', 1)
    assert len(re.findall(r'class="ui-tabs-anchor"', owner)) >= 4
    assert len(re.findall(r'class="ui-tabs-anchor"', other)) >= 9


def test_the_test_page_is_trimmed_to_a_realistic_size(page):
    assert frame(page).locator(m.UNIT_SECTION).locator(m.TAB_ANCHORS).count() == KEEP_UNITS
    assert frame(page).locator(m.OTHER_SECTION).locator(m.TAB_ANCHORS).count() == KEEP_OTHERS


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
    bare = open_page(browser, plus=False)                  # no (+) script at all: the click changes nothing
    try:
        warnings = extras.add_extra_charges(bare, {"units": [{"party_number": 1, "driver": {"extra_charges": ["A"]}}]})
        assert len(warnings) == 1 and "Unit 1" in warnings[0]
    finally:
        bare.close()


def test_unit_tab_that_does_not_exist_warns(page):
    units = [{"party_number": n, "driver": {"extra_charges": []}} for n in range(1, KEEP_UNITS + 1)]
    units.append({"party_number": KEEP_UNITS + 1, "driver": {"extra_charges": ["A"]}})          # no 5th tab exists
    warnings = extras.add_extra_charges(page, {"units": units})
    assert len(warnings) == 1 and f"Unit {KEEP_UNITS + 1}" in warnings[0] and "by hand" in warnings[0]


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


# ------------------------------------------------------------------ Impact Location: exact option
OPTIONS = ["Front", "Front & Rear", "Left Front", "Left Rear", "Left Side", "Multiple", "NA",
           "Rear", "Right Front", "Right Rear", "Right Side"]

# A stand-in suggestion list: shows options that CONTAIN the typed text, Tab takes the FIRST one
# (the behaviour that turns "Rear" into "Front & Rear"), ArrowDown fills the box like jQuery UI.
FAKE_SUGGEST = """(cfg) => {
  const OPTIONS = cfg.options, ODD = cfg.mode === 'odd';
  const menu = document.createElement(ODD ? 'div' : 'ul');
  menu.className = ODD ? 'zzz-list' : 'ui-autocomplete ui-front ui-menu';
  menu.style.cssText = 'display:none;position:absolute;z-index:99;background:#fff;border:1px solid #888';
  document.body.appendChild(menu);
  let active = -1, shown = [], input = null;
  window.__events = 0;
  const close = () => { menu.style.display = 'none'; shown = []; active = -1; };
  const render = () => {
    menu.innerHTML = '';
    shown.forEach((text, i) => {
      const item = document.createElement(ODD ? 'span' : 'li');
      if (!ODD) item.className = 'ui-menu-item';
      item.textContent = text; if (ODD) item.style.display = 'block';
      item.addEventListener('click', () => { input.value = shown[i]; close(); });
      menu.appendChild(item);
    });
    menu.style.display = shown.length ? 'block' : 'none';
  };
  document.querySelectorAll("[id^='Vehicle_DamagedAreas-']").forEach(el => {
    el.addEventListener('input', () => {
      window.__events++; input = el; const v = el.value.toUpperCase();
      shown = v ? OPTIONS.filter(o => o.toUpperCase().includes(v)) : []; active = -1; render();
      const r = el.getBoundingClientRect(); menu.style.left = r.left + 'px'; menu.style.top = (r.bottom + window.scrollY) + 'px';
    });
    el.addEventListener('keydown', e => {
      input = el;
      if (e.key === 'ArrowDown' && shown.length) { e.preventDefault(); active = Math.min(active + 1, shown.length - 1); el.value = shown[active]; }
      else if (e.key === 'Tab' && shown.length) { el.value = shown[active >= 0 ? active : 0]; close(); }
      else if (e.key === 'Enter' && active >= 0) { e.preventDefault(); close(); }
    });
  });
}"""


def install_suggest(page, mode="standard", options=OPTIONS):
    page.frames[1].evaluate(FAKE_SUGGEST, {"options": options, "mode": mode})


def engine_style_fill(page, unit, text):
    """What the shared engine does: type the text, press Tab."""
    field = open_tab(page, m.UNIT_SECTION, unit).locator(m.VEHICLE["impact_location"]).first
    field.click()
    field.press_sequentially(text, delay=20)
    field.press("Tab")
    page.wait_for_timeout(150)
    return field


def impact(page, unit):
    return open_tab(page, m.UNIT_SECTION, unit).locator(m.VEHICLE["impact_location"]).first.input_value()


def units(*locations):
    return {"units": [{"party_number": i, "vehicle": {"impact_location": loc}} for i, loc in enumerate(locations, 1)]}


def test_the_bug_typing_rear_and_tab_picks_the_wrong_suggestion(page):
    install_suggest(page)
    assert engine_style_fill(page, 1, "Rear").input_value() == "Front & Rear"      # why 06 came out wrong


def test_rear_is_corrected_after_the_engine_picked_the_wrong_suggestion(page):
    install_suggest(page)
    engine_style_fill(page, 1, "Rear")
    logs = []
    assert extras.fix_impact_locations(page, units("Rear"), logs.append) == []
    assert impact(page, 1) == "Rear" and logs == ["Unit 1: Impact Location set to Rear"]


def test_front_and_other_ambiguous_values_are_exact(page):
    install_suggest(page)
    for unit, text in ((1, "Front"), (2, "Rear"), (3, "Left Rear")):
        engine_style_fill(page, unit, text)
    assert extras.fix_impact_locations(page, units("Front", "Rear", "Left Rear")) == []
    assert [impact(page, n) for n in (1, 2, 3)] == ["Front", "Rear", "Left Rear"]


def test_a_value_that_is_already_exact_is_not_touched(page):
    install_suggest(page)
    engine_style_fill(page, 1, "Left Rear")
    page.frames[1].evaluate("window.__events = 0")
    logs = []
    assert extras.fix_impact_locations(page, units("Left Rear"), logs.append) == []
    assert page.frames[1].evaluate("window.__events") == 0 and logs == []          # no typing, no log line


def test_case_and_spacing_differences_count_as_exact(page):
    install_suggest(page)
    open_tab(page, m.UNIT_SECTION, 1).locator(m.VEHICLE["impact_location"]).first.fill("  REAR ")
    assert extras.fix_impact_locations(page, units("Rear")) == []
    assert impact(page, 1) == "  REAR "


def test_menu_without_known_markup_is_handled_with_the_arrow_keys(page):
    install_suggest(page, mode="odd")
    engine_style_fill(page, 1, "Rear")
    assert extras.fix_impact_locations(page, units("Rear")) == []
    assert impact(page, 1) == "Rear"


def test_when_the_exact_option_does_not_exist_the_field_is_blanked_and_a_warning_given(page):
    install_suggest(page, options=[o for o in OPTIONS if o != "Rear"])
    engine_style_fill(page, 1, "Rear")
    assert impact(page, 1) != ""                                                      # engine left a wrong value
    warnings = extras.fix_impact_locations(page, units("Rear"))
    assert len(warnings) == 1 and "Unit 1" in warnings[0] and "left blank" in warnings[0]
    assert impact(page, 1) == ""


def test_units_without_an_impact_location_are_skipped(page):
    install_suggest(page)
    assert extras.fix_impact_locations(page, units("", "Rear")) == []
    assert impact(page, 1) == "" and impact(page, 2) == "Rear"


def test_a_missing_unit_tab_is_a_warning_not_an_exception(page):
    install_suggest(page)
    units = [{"party_number": n, "vehicle": {"impact_location": ""}} for n in range(1, KEEP_UNITS + 1)]
    units.append({"party_number": KEEP_UNITS + 1, "vehicle": {"impact_location": "Rear"}})      # no 5th tab exists
    warnings = extras.fix_impact_locations(page, {"units": units})
    assert len(warnings) == 1 and f"Unit {KEEP_UNITS + 1}" in warnings[0] and "check it by hand" in warnings[0]


def test_fill_nj_extras_runs_the_impact_check_first(page):
    install_suggest(page)
    engine_style_fill(page, 1, "Rear")
    payload = {"incident": {"hit_and_run": ""}, "units": [{"party_number": 1, "driver": {"extra_charges": []},
                                                            "vehicle": {"impact_location": "Rear"}}]}
    assert extras.fill_nj_extras(page, payload) == []
    assert impact(page, 1) == "Rear"


# ------------------------------------------------------------------ a slow or stuck page costs seconds, never minutes
def disable_impact_field(pg, number=1):
    open_tab(pg, m.UNIT_SECTION, number)
    pg.frames[1].evaluate("document.querySelector(\"[id^='Vehicle_DamagedAreas-t%d']\").disabled = true" % number)


def test_a_stuck_field_gives_a_warning_within_seconds(page, monkeypatch):
    install_suggest(page)
    monkeypatch.setattr(extras, "STEP_TIMEOUT_MS", 600)
    monkeypatch.setattr(extras, "BLANK_TIMEOUT_MS", 400)
    disable_impact_field(page)                              # clicks and typing now wait for an enabled field
    started = time.monotonic()
    warnings = extras.fix_impact_locations(page, units("Rear"))
    assert time.monotonic() - started < 8
    assert len(warnings) == 1 and "Unit 1" in warnings[0] and "by hand" in warnings[0]


def test_the_time_budget_stops_a_field_and_leaves_it_blank(page):
    install_suggest(page)
    field = engine_style_fill(page, 1, "Rear")
    assert field.input_value() == "Front & Rear"
    started = time.monotonic()
    assert extras.select_exact_option(page, field, "Rear", budget_s=0.001) is False
    assert time.monotonic() - started < 5
    assert impact(page, 1) == ""                            # blank beats wrong


def test_total_budget_skips_the_remaining_units_with_a_warning(page, monkeypatch):
    install_suggest(page)
    monkeypatch.setattr(extras, "TOTAL_BUDGET_S", -1)       # already used up
    warnings = extras.fix_impact_locations(page, units("Rear", "Front"))
    assert len(warnings) == 2 and all("time budget used up" in w and "by hand" in w for w in warnings)


def test_a_slow_check_is_mentioned_in_the_log(page, monkeypatch):
    install_suggest(page)
    monkeypatch.setattr(extras, "SLOW_LOG_S", 0.0)          # anything counts as slow
    engine_style_fill(page, 1, "Rear")
    logs = []
    assert extras.fix_impact_locations(page, units("Rear"), logs.append) == []
    assert any("was slow" in line and "responding slowly" in line for line in logs)
    assert not any("Rear" in line and "was slow" in line for line in logs)              # the report value is never logged


def test_every_playwright_step_in_select_exact_option_has_a_timeout():
    """Guards against the 30 s default sneaking back in: each page/field call in the function names a timeout."""
    import inspect
    source = inspect.getsource(extras.select_exact_option) + inspect.getsource(extras._type_text) + inspect.getsource(extras._blank)
    calls = re.findall(r"\.(input_value|click|fill|press|press_sequentially|type)\(([^)]*)\)", source)
    assert calls and all("timeout" in args for _, args in calls), [c for c in calls if "timeout" not in c[1]]


# ------------------------------------------------------------------ which browser the tests use
class _FakeChromium:
    def __init__(self):
        self.calls = []

    def launch(self, **kwargs):
        self.calls.append(kwargs)
        return kwargs


class _FakePlaywright:
    def __init__(self):
        self.chromium = _FakeChromium()


def test_browser_choice_defaults_to_playwrights_own_chromium(monkeypatch):
    for name in ("KEYFORME_TEST_CHROMIUM", "KEYFORME_TEST_BROWSER"):
        monkeypatch.delenv(name, raising=False)
    fake = _FakePlaywright()
    launch_test_browser(fake)
    assert fake.chromium.calls == [{}]                                   # no channel, no path: the bundled build


def test_browser_choice_can_use_installed_chrome_or_a_given_executable(monkeypatch):
    monkeypatch.delenv("KEYFORME_TEST_CHROMIUM", raising=False)
    monkeypatch.setenv("KEYFORME_TEST_BROWSER", " Chrome ")
    fake = _FakePlaywright()
    launch_test_browser(fake)
    assert fake.chromium.calls == [{"channel": "chrome"}]
    monkeypatch.setenv("KEYFORME_TEST_CHROMIUM", "X:\\b.exe")
    fake = _FakePlaywright()
    launch_test_browser(fake)
    assert fake.chromium.calls == [{"executable_path": "X:\\b.exe"}]            # an explicit path beats everything
