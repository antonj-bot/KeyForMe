"""Tests for app/states/nj.py: the extract/fill entry points the app calls."""
import copy
import sys
import types
from datetime import date

import pytest

from app.keying import nj_rules
from app.states import nj
import nj_fixtures as fx


@pytest.fixture
def payload():
    out = nj_rules.map_nj(fx.VIOLATION, today=date(2026, 10, 23))
    out["other_parties"][0]["same_as_driver_address"] = True
    return out


def test_extract_runs_the_extractor_then_the_rules(monkeypatch):
    monkeypatch.setattr(nj, "extract_nj", lambda path, model: copy.deepcopy(fx.STANDARD))
    out = nj.extract("x.pdf", "stub")
    assert out["incident"]["report_identifier_1"] == "D040202602475C" and len(out["units"]) == 2


def test_engine_payload_drops_only_what_the_engine_cannot_drive(payload):
    before = copy.deepcopy(payload)
    engine = nj.to_engine_payload(payload)
    assert payload == before                                              # the original is untouched
    assert "hit_and_run" not in engine["incident"] and engine["incident"]["incident_city"]
    assert all("extra_charges" not in u["driver"] for u in engine["units"])
    assert engine["units"][0]["driver"]["charge"] == "39:4-97 - Careless Driving"      # first charge stays
    for party in engine["other_parties"]:
        assert "same_as_driver_address" not in party and "same_as_owner_address" not in party
        assert party["role"] and "person_type" in party


class FakeUI:
    def __init__(self):
        self.logs, self.updates = [], []

    def log(self, message, level="info"):
        self.logs.append((level, message))

    def update(self, **kw):
        self.updates.append(kw)


@pytest.fixture
def wiring(monkeypatch):
    ui, calls = FakeUI(), {}
    engine = types.ModuleType("app.browser.engine")
    engine.fill_form = lambda page, payload, state, log: calls.update(engine=(page, payload, state)) or ["engine warning"]
    extras = types.ModuleType("app.browser.nj_extras")
    extras.fill_nj_extras = lambda page, payload, log=None: calls.update(extras=(page, payload)) or ["extras warning"]
    server = types.ModuleType("app.ui.server")
    server.log, server.update = ui.log, ui.update
    pkg = types.ModuleType("app.ui")
    pkg.server = server
    for name, mod in (("app.browser.engine", engine), ("app.browser.nj_extras", extras), ("app.ui", pkg), ("app.ui.server", server)):
        monkeypatch.setitem(sys.modules, name, mod)
    return ui, calls


def test_fill_runs_engine_then_extras_and_reports_warnings(wiring, payload):
    ui, calls = wiring
    nj.fill("PAGE", payload)
    page, engine_payload, state = calls["engine"]
    assert page == "PAGE" and state == "NJ" and "hit_and_run" not in engine_payload["incident"]
    assert calls["extras"][1] is payload                                   # extras get the full payload
    assert ui.updates == [{"warnings": 2}]
    assert [m for lvl, m in ui.logs if m in ("engine warning", "extras warning")] == ["engine warning", "extras warning"]


def test_notes_are_shown_but_never_block_filling(wiring, payload):
    ui, calls = wiring
    payload["notes"] = ["Unit 1: something to review"]
    nj.fill("PAGE", payload)
    assert ("warning", "Unit 1: something to review") in ui.logs and "engine" in calls


def test_fill_refuses_a_payload_without_units(wiring):
    ui, calls = wiring
    with pytest.raises(ValueError, match="No NJ units"):
        nj.fill("PAGE", {"units": [], "incident": {}})
    assert calls == {}                                                      # the form was never touched
