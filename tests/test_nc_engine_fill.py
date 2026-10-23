"""Run the REAL shared engine (app.browser.engine.fill_form) plus nc_extras against the captured NC form
(mock/nc/nc_form.html) and read every value back from the page.

What this proves: the NC selectors resolve exactly the way controls.fill_person / fill_field need (2 controls
for owner+driver fields, 1 for driver-only and vehicle fields), nothing leaks into neighbouring tabs, the radios
and checkboxes work, and the pipeline contract (registry) holds.
What it cannot prove: how the LIVE app reacts (autocomplete, multiselect widgets, the (+) charge button). The mock
is a static capture, so the (+) behaviour is SIMULATED below (a click clones the charge row). Do the live UAT check.
"""
import glob
import pathlib
import re
import sys
import types
from datetime import date

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from nc_fixtures import REFERENCE_ROWS, sample_raw  # noqa: E402
from app.keying import nc_rules as nc_rules  # noqa: E402

playwright = pytest.importorskip("playwright.sync_api")
ROOT = pathlib.Path(__file__).resolve().parents[1]
MOCK = (ROOT / "mock" / "nc" / "index.html").as_uri()
TODAY = date(2026, 10, 23)

try:
    from app.browser import nc_field_mapping as M
    from app.browser.engine import fill_form
    from app.browser.nc_extras import fill_nc_extras
    from app.browser.state_forms import get_form_spec
    from app.core.tabs import activate_tab
    from app.states import nc as nc_state
    get_form_spec("NC")
    IMPORT_ERROR = None
except Exception as error:                                   # NC not installed/registered in state_forms yet
    IMPORT_ERROR = error
pytestmark = pytest.mark.skipif(IMPORT_ERROR is not None, reason=f"NC engine wiring not importable: {IMPORT_ERROR}")

SIMULATE_ADD_CHARGE = """
document.addEventListener('click', e => {
  const a = e.target.closest('a.add-item'); if (!a) return;
  const item = a.closest('.item-content'); const clone = item.cloneNode(true);
  clone.querySelector('input[type=text]').value = ''; clone.querySelector('input[type=text]').id += 'x';
  item.parentNode.appendChild(clone);
});
"""


def _launch(p):
    for kwargs in ({}, {"channel": "chrome"}):
        try:
            return p.chromium.launch(headless=True, **kwargs)
        except Exception:
            pass
    for exe in glob.glob("/opt/pw-browsers/chromium-*/chrome-linux64/chrome"):
        return p.chromium.launch(executable_path=exe, headless=True, args=["--no-sandbox"])
    pytest.skip("no Chromium available")


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = _launch(p)
        yield b
        b.close()


@pytest.fixture()
def page(browser):
    pg = browser.new_page()
    pg.goto(MOCK)
    pg.frame_locator("#formIframe").locator("#formSubmit").wait_for(state="attached")
    frame = next(f for f in pg.frames if f.url.endswith("nc_form.html"))
    frame.add_script_tag(content=SIMULATE_ADD_CHARGE)
    yield pg
    pg.close()


def panels(page, section, n):
    spec = get_form_spec("NC")
    sec = page.frame_locator(spec.frame).locator(section)
    return activate_tab(sec, n, spec=spec.tabs, label="test")


def val(panel, selector, nth=0):
    return panel.locator(selector).nth(nth).input_value()


def checked(panel, selector, nth=0):
    return panel.locator(selector).nth(nth).is_checked()


def full_raw():
    """Sample (units 1-2, witness, property owner, hit & run, 2 charges) + the reference person table
    (A unit 1 driver, B unit 2 driver, C unit 1 passenger, D and E unit 2 passengers) + a third unit."""
    raw = sample_raw()
    names = {"C": "MARIA LOPEZ", "D": "JOSE RUIZ", "E": "ANA RUIZ"}
    raw["occupants"] = [{"row": r, "vehicle": v, "person_type": t, "name": names.get(r, ""), "address_line": "",
                         "protection": "2", "airbag": "1", "ejection": "1", "injury": "3" if r == "C" else "5"}
                        for r, v, t in REFERENCE_ROWS]
    raw["units"][0]["ems_taken"] = "Mission Hospital"          # no letter, one value -> the one injured person (C)
    u3 = {**raw["units"][1], "number": 3, "parked": False,
          "driver": {"first": "PAT", "middle": "", "last": "KIM", "address_1": "9 OAK ST", "city": "RALEIGH",
                     "state": "NC", "zip": "27601", "dob": "01/02/1990"}}
    raw["units"].append(u3)
    raw["units"][2]["vehicle"] = {**u3["vehicle"], "vin": "1HGCM82633A004352", "plate": "KIM123", "tad": "LD-3"}
    return raw


VIN_NOTE = "VIN confirmation not found"


def split_vin_notes(warnings):
    """The static mock has no VIN decode popup, so the real vin_lookup warns once per unit that has a VIN
    ('Unit 1: VIN confirmation not found; using report year/make/model'). That is expected here and says
    nothing about NC. Every OTHER warning is a real problem, so only this exact note is set aside."""
    vin = [w for w in warnings if VIN_NOTE in w]
    return vin, [w for w in warnings if VIN_NOTE not in w]


def small_raw():
    """One unit with two charges and an assumed tow: enough for the tests that only need the pipeline, fast."""
    raw = sample_raw()
    raw["units"] = raw["units"][:1]
    raw["units"][0]["vehicle"]["towed_by"] = "KAR KARE/KAR KARE"            # not in the towing table -> a note
    raw["occupants"], raw["witnesses"], raw["property_owners"] = [], [], []
    return raw


# ------------------------------------------------------------------ the selectors, per panel
def test_selectors_resolve_with_the_counts_the_engine_needs(page):
    spec = get_form_spec("NC")
    frame = page.frame_locator(spec.frame)
    for key, sel in spec.incident.items():
        assert frame.locator(sel).count() == 1, key
    unit = panels(page, spec.unit_section, 4)                      # an untouched unit tab
    paired = {k for k in spec.driver if k in spec.owner or k in ("phone", "date_of_birth", "drivers_license",
                                                                  "drivers_license_state", "injury_code")}
    for key, sel in spec.driver.items():
        want = 2 if key in paired else 1
        assert unit.locator(sel).count() == want, (key, unit.locator(sel).count())
    for key, sel in spec.owner.items():
        assert unit.locator(sel).count() == 2, key
    for key, sel in spec.vehicle.items():
        assert unit.locator(sel).count() == 1, key
    other = panels(page, spec.other_section, 3)
    for key, sel in spec.other.items():
        assert other.locator(sel).count() == 1, key
    for key in spec.radio_fields.values():
        for v in ("1", "0", ""):
            assert unit.locator(f"input[type='radio'][id^='Vehicle_{key}-'][value='{v}']").count() == 1
    assert unit.locator(M.OWNER_SAME_AS_DRIVER_ADDRESS).count() == 1
    assert other.locator(M.OTHER_SAME_AS_DRIVER_ADDRESS).count() == 1 and other.locator(M.OTHER_SAME_AS_OWNER_ADDRESS).count() == 1
    assert unit.locator(M.CHARGE_ITEM).count() == 1 and unit.locator(M.CHARGE_ADD).count() == 1


def test_roles_all_have_a_party_type():
    payload = nc_rules.map_nc(full_raw(), today=TODAY)
    spec = get_form_spec("NC")
    for o in payload["other_parties"]:
        assert o["role"] in spec.person_types, o["role"]


# ------------------------------------------------------------------ the real engine on the capture
def test_engine_and_extras_fill_the_nc_form(page):
    payload = nc_rules.map_nc(full_raw(), today=TODAY)
    spec = get_form_spec("NC")
    warnings = fill_form(page, nc_state.to_engine_payload(payload), state="NC")
    warnings += fill_nc_extras(page, payload)
    vin_notes, other = split_vin_notes(warnings)
    assert other == [], other                                                      # no real warnings at all
    assert len(vin_notes) <= len(payload["units"])                                 # at most one VIN note per unit

    frame = page.frame_locator(spec.frame)
    inc = {k: frame.locator(v).input_value() for k, v in spec.incident.items()}
    assert inc["report_identifier_1"] == "260816025HA" and inc["incident_date"] == "08/16/2026"
    assert inc["incident_street"] == "1960" and inc["incident_cross_street"] == "1946"
    assert inc["weather"] == "1" and inc["road_condition"] == "2" and inc["incident_state"] == "NC"
    assert frame.locator(M.HIT_AND_RUN).is_checked()

    u1 = panels(page, spec.unit_section, 1)
    assert val(u1, spec.owner["last_name"], 0) == "GONZALEZ PEREZ" and val(u1, spec.owner["last_name"], 1) == "GONZALES PEREZ"
    assert val(u1, spec.driver["date_of_birth"], 1) == "09/22/1994" and val(u1, spec.driver["date_of_birth"], 0) == ""
    assert val(u1, spec.driver["injury_code"], 1) == "5" and val(u1, spec.driver["injury_code"], 0) == ""
    assert val(u1, spec.driver["alcohol_drugs"]) == "1" and val(u1, spec.driver["contributing"]) == "8"
    assert val(u1, spec.driver["protection"]) == "2" and val(u1, spec.driver["ejection"]) == "1"   # table row A
    assert val(u1, spec.driver["ems_to"]) == ""                                   # EMS went to passenger C
    assert val(u1, spec.vehicle["vin"]) == "1GNSCJE0XDR157820" and val(u1, spec.vehicle["impact_location"]) == "Front"
    assert val(u1, spec.vehicle["vehicle_defects"]) == "0" and val(u1, spec.vehicle["speed_limit"]) == "35"
    assert val(u1, M.VEHICLE["tag_state"]) == "SC" and val(u1, M.VEHICLE["policy_number"]) == "11408925685"
    assert u1.locator("input[type='radio'][id^='Vehicle_VehicleTowed-'][value='1']").is_checked()      # rotation tow
    assert u1.locator("input[type='radio'][id^='Vehicle_AirBagDeployed-'][value='0']").is_checked()    # not deployed
    charges = u1.locator(M.CHARGE_INPUT)                                          # first charge by the engine, second via (+)
    assert charges.count() == 2
    assert [charges.nth(i).input_value() for i in range(2)] == [
        "Y0335457-1 - DRIVING WHILE IMPAIRED", "HIT AND RUN/ NO OPERATOR'S LICENSE FAILURE TO"]
    assert not checked(u1, M.OWNER_SAME_AS_DRIVER_ADDRESS)                        # owner has its own address

    u2 = panels(page, spec.unit_section, 2)
    assert val(u2, spec.driver["last_name"], 1) == "PARKED" and val(u2, spec.owner["last_name"], 0) == "RAINWATER"
    assert val(u2, spec.driver["address_1"], 1) == ""
    assert u2.locator("input[type='radio'][id^='Vehicle_VehicleTowed-'][value='0']").is_checked()      # stayed on scene
    assert u2.locator("input[type='radio'][id^='Vehicle_AirBagDeployed-'][value='0']").is_checked()
    assert val(u2, spec.vehicle["impact_location"]) == "Right Rear" and val(u2, spec.vehicle["speed_limit"]) == "0"

    u3 = panels(page, spec.unit_section, 3)
    assert val(u3, spec.driver["last_name"], 1) == "KIM" and val(u3, spec.vehicle["vin"]) == "1HGCM82633A004352"
    assert val(u3, spec.vehicle["impact_location"]) == "Left Side"

    u4 = panels(page, spec.unit_section, 4)                                       # untouched tab: nothing leaked
    assert val(u4, spec.owner["last_name"], 0) == "" and val(u4, spec.vehicle["vin"]) == ""
    for n in (1, 2, 3):                                                           # Vehicle # follows the tab order
        assert val(panels(page, spec.unit_section, n), "input[id^='Vehicle_UnitNumber-']") == str(n)

    roles = [o["role"] for o in payload["other_parties"]]
    assert roles.count("PASSENGER") == 3 and "WITNESS" in roles and "PROPERTY OWNER" in roles
    for n, o in enumerate(payload["other_parties"], 1):
        p = panels(page, spec.other_section, n)
        assert val(p, spec.other["person_type"]) == spec.person_types[o["role"]]
        assert val(p, spec.other["last_name"]) == o["last_name"]
        assert val(p, spec.other["unit_number"]) == (o["party_number"] if o["role"] not in ("WITNESS",) else "")
        assert val(p, spec.other["ems_to"]) == o["ems_to"]
        assert checked(p, M.OTHER_SAME_AS_DRIVER_ADDRESS) == bool(o["same_as_driver_address"])
        assert checked(p, M.OTHER_SAME_AS_OWNER_ADDRESS) == bool(o["same_as_owner_address"])
    maria = next(n for n, o in enumerate(payload["other_parties"], 1) if o["first_name"] == "MARIA")
    pm = panels(page, spec.other_section, maria)
    assert val(pm, spec.other["ems_to"]) == "Mission Hospital" and val(pm, spec.other["injury_code"]) == "3"
    assert checked(pm, M.OTHER_SAME_AS_DRIVER_ADDRESS)                            # unit 1 driver has an address
    jose = next(n for n, o in enumerate(payload["other_parties"], 1) if o["first_name"] == "JOSE")
    assert checked(panels(page, spec.other_section, jose), M.OTHER_SAME_AS_OWNER_ADDRESS)   # unit 2: only the owner has one
    last = panels(page, spec.other_section, len(payload["other_parties"]) + 1)    # untouched other-party tab
    assert val(last, spec.other["last_name"]) == ""


def test_extra_charges_fail_loudly_when_plus_does_nothing(browser):
    """If the (+) link does not add a row (e.g. the live page changed), the charge is reported, not lost silently."""
    pg = browser.new_page()
    pg.goto(MOCK)                                                                  # no simulation script injected
    pg.frame_locator("#formIframe").locator("#formSubmit").wait_for(state="attached")
    payload = nc_rules.map_nc(small_raw(), today=TODAY)
    fill_form(pg, nc_state.to_engine_payload(payload), state="NC")
    warnings = fill_nc_extras(pg, payload)
    pg.close()
    assert any("did not add exactly one charge row" in w for w in warnings), warnings


# ------------------------------------------------------------------ the registry contract
def _load_registry():
    """Load the project's registry.py (the module with extend_pipelines) by FILE, wherever it lives
    (app/registry.py, app/core/registry.py, ...). Backup folders are ignored."""
    import importlib.util
    for p in sorted(ROOT.rglob("registry.py")):
        rel = p.relative_to(ROOT).parts
        if any(part.startswith(".") or part in ("venv", "site-packages") for part in rel):
            continue
        if "extend_pipelines" not in p.read_text(encoding="utf-8", errors="ignore"):
            continue
        spec = importlib.util.spec_from_file_location("kfm_registry_under_test", p)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    pytest.skip("registry.py with extend_pipelines not found in the project")


def test_nc_pipeline_passes_the_registry_contract(monkeypatch):
    registry = _load_registry()
    plugins = types.ModuleType("app.state_plugins")
    plugins.PLUGINS = {"NC": nc_state}
    monkeypatch.setitem(sys.modules, "app.state_plugins", plugins)
    result = registry.extend_pipelines({"CA": object()})
    assert result["NC"] is nc_state and callable(nc_state.extract) and callable(nc_state.fill)
    assert nc_state.ENABLED is True


def test_nc_is_registered_in_the_real_state_plugins():
    """The installer's edit to app/state_plugins.py: NC is in PLUGINS and the registry accepts it."""
    registry = _load_registry()
    from app.state_plugins import PLUGINS
    assert PLUGINS.get("NC") is nc_state
    assert registry.extend_pipelines({}).get("NC") is nc_state


def test_to_engine_payload_removes_what_the_engine_cannot_do():
    payload = nc_rules.map_nc(full_raw(), today=TODAY)
    data = nc_state.to_engine_payload(payload)
    assert "hit_and_run" not in data["incident"] and "extra_charges" not in data["units"][0]["driver"]
    assert "same_as_driver_address" not in data["units"][0]["owner"]
    assert all("same_as_driver_address" not in p and "extra_charges" not in p for p in data["other_parties"])
    assert payload["incident"]["hit_and_run"] == "1" and payload["units"][0]["driver"]["extra_charges"]     # original untouched


def test_pipeline_fill_logs_notes_and_never_saves(page, monkeypatch):
    log, updates = [], []
    ui = types.ModuleType("app.ui.server")
    ui.log = lambda message, level="info": log.append((level, str(message)))
    ui.update = lambda **kw: updates.append(kw)
    monkeypatch.setitem(sys.modules, "app.ui.server", ui)
    monkeypatch.setitem(sys.modules, "app.ui", types.SimpleNamespace(server=ui))
    payload = nc_rules.map_nc(small_raw(), today=TODAY)
    nc_state.fill(page, payload)
    logged = [m for lvl, m in log if lvl == "warning"]
    assert [m for m in logged if VIN_NOTE not in m and "towing table" not in m and "NC supervised" not in m
            and "NC filler finished" not in m] == []                               # nothing unexpected was logged
    assert len(updates) == 1 and updates[0]["warnings"] == sum(VIN_NOTE in m for m in logged)
    assert any("NC filler finished" in m for _, m in log)
    assert any("towing table" in m for _, m in log)                               # advisory notes are shown, not blocking
    with pytest.raises(ValueError):
        nc_state.fill(page, {"incident": {}, "units": []})
