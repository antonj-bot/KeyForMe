"""PA browser test: fills the saved PA mock (mock/pa/index.html + pa_form.html) through the shared engine and
pa_extras, then reads the values back out of the page.

The mock is a static capture, so a small script (SIM below) imitates the three behaviours of the live site that the
filler depends on: the (+) link adds a violation row, the + button adds a tab, "Add Trailer" adds a tab whose owner
and driver are copied from the clicked unit (vehicle details empty), and ticking a violation type shows its text box.
Run only this file when you want the browser tests:   python -m pytest tests/test_pa_form.py -q
"""
import os
from pathlib import Path

import pytest

playwright_sync = pytest.importorskip("playwright.sync_api")

ROOT = Path(__file__).resolve().parents[1]
MOCK = ROOT / "mock" / "pa" / "index.html"
pytestmark = pytest.mark.skipif(not MOCK.is_file(), reason="copy the PA mock to mock/pa/ (index.html + pa_form.html)")

try:
    from tests.pa_fixtures import coded, sample_raw
except ImportError:
    from pa_fixtures import coded, sample_raw

from app.browser import pa_extras
from app.browser.engine import fill_form
from app.browser.pa_extras import fill_pa_extras
from app.browser.state_forms import get_form_spec
from app.keying.pa_rules import map_pa
from app.states.pa import to_engine_payload

SIM = r"""
(() => {
  const start = () => {
    if (!document.getElementById('formContainer') || window.__sim) return;
    window.__sim = true;
    const style = document.createElement('style');
    style.textContent = '.hide{display:none !important} .st-nav-add{display:inline-block;width:20px;height:20px;background:#ccc}';
    document.head.appendChild(style);
    let counter = 1000;
    const reindex = root => { const idx = counter++;
      root.querySelectorAll('[name]').forEach(e => { e.name = e.name.replace(/\[\d+\]/, '[' + idx + ']'); }); };
    const resetCitations = root => {
      root.querySelectorAll('td.citations').forEach(td => {
        td.querySelectorAll('div.item-content').forEach((it, i) => { if (i > 0) it.remove(); });
        const it = td.querySelector('div.item-content');
        if (it) { it.querySelector('.pa-citation').classList.remove('hide'); it.querySelector('.pa-violation').classList.add('hide'); }
      });
    };
    const addTab = (section, src, where, copyPeople) => {
      const ul = section.querySelector('ul');
      const panel = src.cloneNode(true);
      const id = 'tabs-x' + (counter++);
      panel.id = id; panel.style.display = 'none'; panel.setAttribute('aria-hidden', 'true');
      reindex(panel);
      panel.querySelectorAll('input[type=text], textarea').forEach(e => {
        if (/^Vehicle_/.test(e.id) || !copyPeople) e.value = ''; });
      panel.querySelectorAll('input[type=radio], input[type=checkbox]').forEach(e => { e.checked = e.hasAttribute('checked'); });
      resetCitations(panel);
      const unit = panel.querySelector('input[id^="Vehicle_UnitNumber-"]');
      if (unit) {
        const nums = Array.from(section.querySelectorAll('input[id^="Vehicle_UnitNumber-"]')).map(e => +e.value || 0);
        unit.value = String(Math.max(0, ...nums) + 1);
      }
      const li = document.createElement('li');
      li.setAttribute('role', 'tab'); li.className = 'ui-tabs-tab';
      const a = document.createElement('a');
      a.setAttribute('role', 'presentation'); a.className = 'ui-tabs-anchor'; a.setAttribute('href', '#' + id);
      li.appendChild(a);
      if (where === 'after') {
        src.after(panel);
        ul.querySelector('a[href="#' + src.id + '"]').closest('li').after(li);
      } else { section.appendChild(panel); ul.appendChild(li); }
      ul.querySelectorAll('a').forEach((x, i) => { x.textContent = String(i + 1); });
    };
    document.addEventListener('click', ev => {
      const add = ev.target.closest('td.citations a.add-item');
      if (add) {
        const item = add.closest('div.item-content');
        const clone = item.cloneNode(true);
        clone.querySelectorAll('input[type=text]').forEach(i => { i.value = ''; });
        clone.querySelectorAll('input[type=radio]').forEach(i => { i.checked = i.value === 'CITATION'; });
        clone.querySelector('.pa-citation').classList.remove('hide');
        clone.querySelector('.pa-violation').classList.add('hide');
        reindex(clone);
        item.after(clone);
        return;
      }
      const nav = ev.target.closest('.st-nav-add');
      if (nav) {
        const section = nav.closest('.formPageSection');
        const panels = section.querySelectorAll('[role=tabpanel]');
        addTab(section, panels[panels.length - 1], 'end', false);
        return;
      }
      const trailer = ev.target.closest('input[id^="Vehicle_AddTrailerGui-"]');
      if (trailer) {
        const panel = trailer.closest('[role=tabpanel]');
        addTab(panel.closest('.formPageSection'), panel, window.__trailerInsert || 'end', true);
      }
    });
    document.addEventListener('change', ev => {
      const r = ev.target.closest('input[id*="CitationOrViolation-"]');
      if (!r) return;
      const item = r.closest('div.item-content');
      item.querySelector('.pa-citation').classList.toggle('hide', r.value === 'VIOLATION');
      item.querySelector('.pa-violation').classList.toggle('hide', r.value !== 'VIOLATION');
    });
  };
  document.addEventListener('DOMContentLoaded', start);
})();
"""

TRIM_JS = """(_, keep) => {
  for (const id of ['section-page-base-owner-02', 'section-page-base-passenger-03']) {
    const s = document.getElementById(id);
    const panels = Array.from(s.querySelectorAll('[role=tabpanel]'));
    const lis = Array.from(s.querySelectorAll('ul > li'));
    panels.forEach((p, i) => { if (i >= keep) p.remove(); });
    lis.forEach((l, i) => { if (i >= keep) l.remove(); });
  }
}"""

DUMP_JS = """(section) => Array.from(section.querySelectorAll('[role=tabpanel]')).map(p => {
  const vals = sel => Array.from(p.querySelectorAll(sel)).map(e => e.value);
  const checked = sel => { const e = p.querySelector(sel + ':checked'); return e ? e.value : null; };
  return {
    unit: vals('input[id^="Vehicle_UnitNumber-"]')[0],
    first: vals('input[id^="Person_FirstName-"]'), last: vals('input[id^="Person_LastName-"]'),
    address: vals('textarea[id^="Person_Address-"]:not([id^="Person_Address2-"])'), address2: vals('textarea[id^="Person_Address2-"]'), zip: vals('input[id^="Person_ZipCode-"]'),
    phone: vals('input[id^="Person_HomePhone-"]'), dob: vals('input[id^="Person_DateOfBirth-"]'),
    dl: vals('input[id^="Person_DriversLicenseNumber-"]'), injury: vals('input[id^="Person_InjuryStatus-"]'),
    alcohol: vals('input[id^="Person_AlcoholDrugUse-"]')[0], actions: vals('input[id^="Person_DriverActionsAtTimeOfCrash-"]')[0],
    safety: vals('input[id^="Person_SafetyEquipmentRestraint-"]')[0], ejection: vals('input[id^="Person_Ejection-"]')[0],
    ems: vals('input[id^="Person_TransportedTo-"]')[0],
    ptype: vals('input[id^="Person_PersonType-"]')[0], pvehicle: vals('input[id^="Person_VehicleUnitNumber-"]')[0],
    tag: vals('input[id^="Vehicle_LicensePlate-"]')[0], tagstate: vals('input[id^="Vehicle_RegistrationState-"]')[0],
    vin: vals('input[id^="Vehicle_Vin-"]')[0], year: vals('input[id^="Vehicle_ModelYear-"]')[0],
    make: vals('input[id^="Vehicle_Make-"]')[0], model: vals('input[id^="Vehicle_Model-"]')[0],
    carrier: vals('input[id^="Vehicle_InsuranceCompany-"]')[0], impact: vals('input[id^="Vehicle_DamagedAreas-"]')[0],
    failures: vals('input[id^="Vehicle_ContributingCircumstancesVehicle-"]')[0],
    towed: checked('input[id*="VehicleTowed-"]'), airbag: checked('input[id*="AirBagDeployed-"]'),
    violations: Array.from(p.querySelectorAll('td.citations div.item-content')).map(it => {
      const g = sel => { const e = it.querySelector(sel); return e ? e.value : ''; };
      const c = it.querySelector('input[id*="CitationOrViolation-"]:checked');
      const ch = it.querySelector('input[id*="CitationIssued-"]:checked');
      return {kind: c ? c.value : null, text: g('input[id^="Citations_CitationDetail-"]'),
              primary: g('input[id^="Citations_ViolationCode-"]'), charged: ch ? ch.value : null};
    }),
  };
})"""


@pytest.fixture(scope="module")
def browser():
    """Playwright's own Chromium; or the browser named in PA_TEST_BROWSER (a chrome.exe path); or installed Chrome."""
    attempts = []
    if os.environ.get("PA_TEST_BROWSER"):
        attempts.append({"executable_path": os.environ["PA_TEST_BROWSER"]})
    attempts += [{}, {"channel": "chrome"}]
    with playwright_sync.sync_playwright() as p:
        b, last = None, None
        for kw in attempts:
            try:
                b = p.chromium.launch(headless=True, **kw)
                break
            except Exception as error:
                last = error
        if b is None:                                                    # no browser available on this machine
            pytest.skip(f"no browser could be started ({type(last).__name__}); set PA_TEST_BROWSER to a chrome.exe path")
        yield b
        b.close()


def open_mock(browser, *, simulate=True, trailer_insert=None, keep=1):
    page = browser.new_page()
    if simulate:
        page.add_init_script(SIM)
    if trailer_insert:
        page.add_init_script(f"window.__trailerInsert = '{trailer_insert}';")
    page.goto(MOCK.as_uri())
    frame = page.frame_locator("#formIframe")
    frame.locator("#formContainer").wait_for(state="attached")
    frame.locator("#section-page-base-owner-02").evaluate(TRIM_JS, keep)
    return page, frame


def fill_all(page, payload):
    warnings = list(fill_form(page, to_engine_payload(payload), state="PA") or [])
    warnings += fill_pa_extras(page, payload)
    return warnings


def panels(frame, section="#section-page-base-owner-02"):
    return frame.locator(section).evaluate(DUMP_JS)


def value(frame, selector):
    return frame.locator(selector).input_value()


def slim(raw, units=(0,), occupants=()):
    """Keep the browser tests quick: only the units / people a test is about."""
    raw["units"] = [raw["units"][i] for i in units]
    raw["occupants"] = [raw["occupants"][i] for i in occupants]
    raw["witnesses"] = []
    raw["hit_and_run_crash"] = False
    return raw


@pytest.fixture()
def payload():
    return map_pa(sample_raw())


def test_full_report_lands_in_the_right_fields(browser, payload):
    page, frame = open_mock(browser)
    try:
        warnings = fill_all(page, payload)
        assert value(frame, "#Incident_CaseIdentifier") == "202607025541"
        assert value(frame, "#Incident_CrashDate") == "07/19/2026" and value(frame, "#Incident_CrashTime") == "09:30"
        assert value(frame, "#Incident_CrashCity") == "PHILADELPHIA CITY"
        assert value(frame, "#Incident_LossStreet") == "ROOSEVELT BOULEVARD"
        assert value(frame, "#Incident_LossCrossStreet") == "GRANT AVENUE"
        assert value(frame, "#Incident_Latitude") == "400453.610" and value(frame, "#Incident_Longitude") == "-750142.170"
        assert value(frame, "#Incident_WeatherCondition") == "1" and value(frame, "#Incident_RoadSurfaceCondition") == "0"
        assert value(frame, "#Incident_LossCrossStreetSpeedLimitDropDown") == "30"
        assert frame.locator("#Incident_IncidentHitAndRun-v1").is_checked()

        unit1, unit2, trailer = panels(frame)
        assert unit1["unit"] == "1" and unit1["first"] == ["BRITNEY", "BRITNEY"] and unit1["last"] == ["CABAN", "CABAN"]
        assert unit1["address"] == ["2225 NORTH LAWRENCE STREET"] * 2 and unit1["zip"] == ["19133", "19133"]
        assert unit1["dob"][1] == "09/06/1990" and unit1["dl"][1] == "29649264" and unit1["injury"][1] == "0"
        assert unit1["alcohol"] == "Unknown" and unit1["actions"] == "24;23"
        assert unit1["safety"] == "03" and unit1["ejection"] == "1" and unit1["ems"] == "NONE"
        assert (unit1["tag"], unit1["tagstate"], unit1["vin"], unit1["year"], unit1["make"], unit1["model"]) == \
            ("NFL7193", "PA", "1HGCM56715A042022", "2005", "HONDA", "Accord")
        assert unit1["impact"] == "Front" and unit1["failures"] == "01"
        assert unit1["towed"] == "1" and unit1["airbag"] == "1"
        assert unit1["violations"] == [
            {"kind": "VIOLATION", "text": "", "primary": "75 3361 SPEED", "charged": "YES"},
            {"kind": "CITATION", "text": "75 3714 CARELESS", "primary": "", "charged": "WARNING"}]

        assert unit2["unit"] == "2" and unit2["last"][1] == "HIT AND RUN" and unit2["last"][0] == "PERDOMO"
        assert unit2["tag"] == "JYM3740" and unit2["impact"] == "Rear" and unit2["towed"] == "" and unit2["airbag"] == ""
        assert unit2["violations"][0]["kind"] == "CITATION" and unit2["violations"][0]["text"] == ""

        assert trailer["unit"] == "3"                                          # created by Add Trailer
        assert (trailer["tag"], trailer["tagstate"], trailer["make"]) == ("TRL1234", "PA", "UTILITY")
        assert trailer["vin"] == "" and trailer["year"] == ""                  # Tag Year is not a vehicle year
        assert trailer["last"] == ["CABAN", "CABAN"]                           # people copied by the site, untouched

        others = panels(frame, "#section-page-base-passenger-03")
        assert [o["ptype"] for o in others] == ["Passenger", "Witness"]
        pax = others[0]
        assert (pax["first"][0], pax["last"][0], pax["pvehicle"]) == ("NAHZYRA", "EUTSEY", "1")
        assert pax["address"][0] == "1228 VETERANS HWY"
        assert pax["address2"][0] == "APT H5"
        assert pax["dob"][0] == ""
        assert pax["injury"][0] == "4" and pax["safety"] == "03" and pax["ems"] == "TEMPLE"
        assert others[1]["last"][0] == "WITNESS" and others[1]["phone"][0] == "215 555-0100"
        assert not [w for w in warnings if "Party Type" in w and "skipped" in w]
    finally:
        page.close()


def test_every_violation_row_keeps_its_type_text_and_charged(browser):
    raw = sample_raw()
    raw["units"][0]["driver"]["violations"] = [
        {"text": "V-ONE", "charged": "NO", "primary": False},
        {"text": "V-TWO", "charged": "YES", "primary": True},
        {"text": "V-THREE", "charged": "Warning", "primary": False},
        {"text": "V-FOUR", "charged": None, "primary": False},
    ]
    raw["units"][0]["trailers"] = []
    page, frame = open_mock(browser)
    try:
        warnings = fill_all(page, map_pa(slim(raw)))
        rows = panels(frame)[0]["violations"]
        assert rows == [
            {"kind": "CITATION", "text": "V-ONE", "primary": "", "charged": "NO"},
            {"kind": "VIOLATION", "text": "", "primary": "V-TWO", "charged": "YES"},
            {"kind": "CITATION", "text": "V-THREE", "primary": "", "charged": "WARNING"},
            {"kind": "CITATION", "text": "V-FOUR", "primary": "", "charged": None}]
        assert not [w for w in warnings if "violation" in w.lower()]
    finally:
        page.close()


def test_other_party_violations(browser):
    raw = sample_raw()
    raw["units"][0]["trailers"] = []
    raw["occupants"][1]["violations"] = [{"text": "P-ONE", "charged": "YES"}, {"text": "P-TWO", "charged": "NO"}]
    page, frame = open_mock(browser)
    try:
        fill_all(page, map_pa(slim(raw, occupants=(1,))))
        rows = panels(frame, "#section-page-base-passenger-03")[0]["violations"]
        assert [(r["text"], r["charged"]) for r in rows] == [("P-ONE", "YES"), ("P-TWO", "NO")]
    finally:
        page.close()


def test_trailer_tabs_inserted_next_to_their_unit_are_found_by_unit_number(browser):
    """If the live site puts the new tab right after the clicked unit (instead of at the end), every trailer must
    still land in the tab that was created for it."""
    raw = sample_raw()
    raw["units"][1]["trailers"] = [{"plate": "TRL-B", "plate_state": "NJ", "make": "BOX"}]
    page, frame = open_mock(browser, trailer_insert="after")
    try:
        warnings = fill_all(page, map_pa(slim(raw, units=(0, 1))))
        tabs = panels(frame)
        assert len(tabs) == 4
        by_tag = {t["tag"]: t for t in tabs}
        a, b = by_tag["TRL1234"], by_tag["TRL-B"]
        assert a["last"] == ["CABAN", "CABAN"] and a["make"] == "UTILITY" and a["tagstate"] == "PA"
        assert b["last"][0] == "PERDOMO" and b["make"] == "BOX" and b["tagstate"] == "NJ"
        assert {by_tag["NFL7193"]["unit"], by_tag["JYM3740"]["unit"]} == {"1", "2"}
        assert not [w for w in warnings if "trailer" in w.lower()]
    finally:
        page.close()


def test_two_trailers_on_one_unit(browser):
    raw = sample_raw()
    raw["units"][0]["trailers"].append({"plate": "TRL-2", "plate_state": "PA", "make": "SECOND"})
    page, frame = open_mock(browser)
    try:
        fill_all(page, map_pa(slim(raw)))
        tabs = panels(frame)
        assert sorted(t["tag"] for t in tabs[1:]) == ["TRL-2", "TRL1234"] and len(tabs) == 3
    finally:
        page.close()


def test_missing_add_trailer_behaviour_is_a_warning_not_a_crash(browser):
    page, frame = open_mock(browser, simulate=False, keep=2)
    try:
        warnings = []
        spec = get_form_spec("PA")
        section = frame.locator(spec.unit_section)
        pa_extras._add_trailer(page, section, 1, {"tag_number": "T"}, "unit1.trailer1", spec, warnings, timeout_s=0.4)
        assert warnings == ["unit1.trailer1: Add Trailer did not add exactly one tab; trailer not keyed"]
    finally:
        page.close()


def test_missing_plus_link_is_a_warning_not_a_crash(browser):
    page, frame = open_mock(browser, simulate=False, keep=2)
    try:
        warnings = []
        spec = get_form_spec("PA")
        panel = frame.locator(spec.unit_section).locator("#tabs-2")
        frame.locator(spec.unit_section).locator(spec.tabs.anchors).nth(1).click()
        rows = [{"kind": "violation", "text": "A", "charged": "YES"}, {"kind": "violation", "text": "B", "charged": ""}]
        pa_extras._violations(panel, rows, "unit2.driver", spec, warnings, timeout_s=0.4)
        assert warnings == ["unit2.driver: (+) did not add exactly one row; violation 2 not keyed"]
        assert panels(frame)[1]["violations"][0]["text"] == "A"
    finally:
        page.close()


def test_to_engine_payload_removes_what_the_extras_handle(payload):
    engine = to_engine_payload(payload)
    assert "hit_and_run" not in engine["incident"]
    assert all("violations" not in u["driver"] and "trailers" not in u for u in engine["units"])
    assert all("violations" not in o for o in engine["other_parties"])
    assert payload["units"][0]["driver"]["violations"] and payload["units"][0]["trailers"]     # original untouched


def test_the_form_spec_is_registered():
    spec = get_form_spec("PA")
    assert spec.state == "PA" and spec.frame == "#formIframe" and spec.units_before_incident
    assert spec.person_types["PASSENGER"] == "Passenger"
