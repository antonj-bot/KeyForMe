"""Offline tests for the NJ extraction layer: page triage, classification, completeness
and assembly. The AI call is replaced by a stub that answers from a plan, so these tests
check OUR logic (not the model's reading accuracy).

Run:  python -m pytest tests/test_nj_extractor.py -q
"""
import io
from datetime import date

import pymupdf
import pytest

PIL = pytest.importorskip("PIL", reason="Pillow is only needed to build the synthetic test PDFs")
from PIL import Image, ImageDraw  # noqa: E402

from app.core.completeness import IncompleteExtractionError
from app.extraction import nj_extractor as ex
from app.extraction import nj_pages
from app.keying import nj_rules
from app.nj_models import (NJInventory, NJNarrativeItem, NJNarrativePage, NJOccupantRaw,
                           NJPageKind, NJPropertyRaw, NJUnitPage, NJVehicleRaw)

W, H = 1224, 1584


# ------------------------------------------------------------------ synthetic scanned PDFs
def page_image(kind: str, label: str = "") -> bytes:
    img = Image.new("L", (W, H), 255)
    d = ImageDraw.Draw(img)
    if kind == "blank":
        for x, y in ((900, 400), (905, 420)):                    # dust specks
            d.point((x, y), fill=60)
    elif kind == "shadow":
        for x in range(0, 18):                                    # scanner shadow along the left edge
            d.line([(x, 0), (x, H)], fill=90 + x * 3)
        d.line([(0, H - 6), (W, H - 6)], fill=120, width=4)
    elif kind == "unit":
        d.rectangle([60, 60, W - 60, H - 60], outline=0, width=4)
        for i in range(60):
            d.text((90, 90 + i * 22), f"{label} FIELD {i}  VALUE {i * 7919 % 1000}", fill=0)
    elif kind == "narrative":
        for i in range(45):
            d.text((90, 90 + i * 26), f"{label} narrative line {i} the vehicle stated that", fill=0)
    elif kind == "diagram":
        d.rectangle([200, 300, W - 200, H - 300], outline=0, width=6)
        d.line([(200, 300), (W - 200, H - 300)], fill=0, width=6)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    return buf.getvalue()


def build_pdf(tmp_path, pages, name="r.pdf"):
    doc = pymupdf.open()
    for kind, label in pages:
        page = doc.new_page(width=612, height=792)
        if kind == "text-unit":
            page.insert_text((72, 100), "New Jersey Police Crash Investigation Report 23. Veh. # 24. Policy No. " + "x" * 40)
        else:
            page.insert_image(page.rect, stream=page_image(kind, label))
    path = tmp_path / name
    doc.save(path)
    doc.close()
    return path


# ------------------------------------------------------------------ plan-driven stub for the AI call
def vehicle(number, side="LEFT", **kw):
    base = dict(number=number, side=side, driver_first="F%d" % (number or 0), driver_last="L%d" % (number or 0),
                vin="VIN%03d" % (number or 0), plate="PL%d" % (number or 0), owner_name="OWNER %d" % (number or 0))
    base.update(kw)
    return NJVehicleRaw(**base)


def unit_page(*vehicles, **kw):
    data = dict(case_number="26-1", police_dept="TOWN", crash_date="06/15/26", crash_time="2041", road_name="MAIN ST")
    data.update(kw)
    return NJUnitPage(vehicles=list(vehicles), **data)


class Plan:
    def __init__(self, kinds, units=None, inventories=None, narratives=None, recovery=None, fail_classify=()):
        self.kinds = kinds                        # 1-based page -> UNIT/NARRATIVE/OTHER
        self.units = units or {}                  # page -> NJUnitPage
        self.inventories = inventories or {}      # page -> NJInventory (default: derived from the unit page)
        self.narratives = narratives or {}
        self.recovery = recovery or {}            # page -> NJUnitPage returned for the recovery prompt
        self.fail_classify = set(fail_classify)
        self.calls = []

    def __call__(self, model, prompt, schema, images, labels=None):
        page = int(labels[0].split()[-1].rstrip(":"))
        self.calls.append((schema.__name__, page, "RECOVERY" in prompt))
        if schema is NJPageKind:
            if page in self.fail_classify:
                raise TimeoutError("boom")
            return NJPageKind(kind=self.kinds[page])
        if schema is NJInventory:
            return self.inventories.get(page) or NJInventory(
                vehicle_numbers=[v.number for v in self.units[page].vehicles if v.number is not None])
        if schema is NJUnitPage:
            if "RECOVERY" in prompt:
                return self.recovery[page]
            return self.units[page]
        if schema is NJNarrativePage:
            return self.narratives.get(page, NJNarrativePage())
        raise AssertionError(schema)

    def count(self, name):
        return sum(1 for c in self.calls if c[0] == name)


@pytest.fixture
def run(tmp_path, monkeypatch):
    def _run(pages, plan):
        monkeypatch.setattr(ex, "_parse", plan)
        return ex.extract_nj(build_pdf(tmp_path, pages), "stub-model")
    return _run


# ------------------------------------------------------------------ triage
def test_blank_shadow_and_duplicate_pages_are_dropped(tmp_path):
    path = build_pdf(tmp_path, [("unit", "A"), ("blank", ""), ("shadow", ""), ("unit", "A"), ("narrative", "N"), ("diagram", "")])
    with pymupdf.open(path) as doc:
        kept, dropped = nj_pages.usable_pages(doc)
    assert kept == [0, 4, 5]                                  # unit, narrative, diagram-only (the AI calls that OTHER)
    assert dropped == {1: "blank", 2: "blank", 3: "duplicate of page 1"}


def test_different_but_similar_pages_are_both_kept(tmp_path):
    path = build_pdf(tmp_path, [("unit", "UNITS 1 AND 2"), ("unit", "UNITS 3 AND 4")])
    with pymupdf.open(path) as doc:
        assert nj_pages.usable_pages(doc)[0] == [0, 1]


def test_pdf_without_embedded_images_uses_exact_pixel_digest(tmp_path):
    path = build_pdf(tmp_path, [("text-unit", ""), ("text-unit", "")])
    with pymupdf.open(path) as doc:
        kept, dropped = nj_pages.usable_pages(doc)
    assert kept == [0] and 1 in dropped


# ------------------------------------------------------------------ classification wording / crop
def test_classifier_treats_the_occupant_table_page_as_narrative():
    prompt = ex.CLASSIFY_PROMPT.upper()
    assert "OCCUPANTS" in prompt and "83 TO 95" in prompt and "ROW LETTERS" in prompt
    assert "WHEN UNSURE BETWEEN NARRATIVE AND OTHER, ANSWER NARRATIVE" in prompt


def test_header_crop_is_tall_enough_to_include_the_occupant_rows(tmp_path):
    import base64
    path = build_pdf(tmp_path, [("unit", "U")])
    with pymupdf.open(path) as doc:
        header = Image.open(io.BytesIO(base64.b64decode(ex._header_image(doc, 0).split(",", 1)[1])))
        full = doc.load_page(0).get_pixmap(dpi=160)
    assert 0.33 <= header.height / full.height <= 0.37


# ------------------------------------------------------------------ extraction flow
def standard_plan():
    left = vehicle(1, ins_code="000", policy_number="P1", charges=["39:4-88B A"], damage_new="09", contributing_codes=["60", "-"],
                   owner_same_as_driver=True)
    right = vehicle(2, side="RIGHT", ins_code="000", driven=True)
    occ = [NJOccupantRaw(row="A", vehicle="01", position="01", injury="04", age="36", name="F1 L1"),
           NJOccupantRaw(row="B", vehicle="01", position="03", injury="03", age="17", name="JAYDEN S", address="1 MAIN ST UTICA NJ 13502"),
           NJOccupantRaw(row="C", vehicle="-", position="-")]                      # a row of dashes is dropped
    narrative = NJNarrativePage(
        occupants=[NJOccupantRaw(row="E", vehicle="2", position="03", name="LATE PASSENGER")],
        other_descriptions=[NJNarrativeItem(vehicle=1, text="(NY) STATE FARM", field="25"),
                            NJNarrativeItem(vehicle=2, text="ABC-1", field="54"),
                            NJNarrativeItem(vehicle=1, text="Prior Accident in area", field="118a")],
        additional_citations=[NJNarrativeItem(vehicle=1, text="39:4-96 - Reckless Driving")],
        insurance_statements=[NJNarrativeItem(vehicle=2, text="GEICO")])
    return Plan({1: "UNIT", 2: "NARRATIVE", 3: "OTHER"},
                units={1: unit_page(left, right, occupants=occ, property_owners=[NJPropertyRaw(name="NJTA", is_company=True)])},
                narratives={2: narrative})


def test_standard_report_is_assembled(run):
    plan = standard_plan()
    raw = run([("unit", "U"), ("narrative", "N"), ("diagram", "")], plan)
    assert [v["number"] for v in raw["vehicles"]] == [1, 2]
    v1, v2 = raw["vehicles"]
    assert v1["narrative_insurance"] == "(NY) STATE FARM"                      # Field 25 line
    assert v2["narrative_policy"] == "ABC-1" and v2["narrative_insurance"] == "GEICO"   # Field 54 line + insurance sentence
    assert v1["charges"] == ["39:4-88B A", "39:4-96 - Reckless Driving"]        # additional citation appended
    assert [o["row"] for o in raw["occupants"]] == ["A", "B", "E"]
    assert raw["property_owners"] == [{"name": "NJTA", "address_line": "", "is_company": True}]
    assert raw["case_number"] == "26-1" and raw["crash_time"] == "2041"
    assert plan.count("NJPageKind") == 3 and plan.count("NJUnitPage") == 1 and plan.count("NJInventory") == 1 \
        and plan.count("NJNarrativePage") == 1
    assert not raw["notes"]


def test_blank_and_duplicate_pages_cost_no_api_calls(run):
    plan = standard_plan()
    plan.kinds = {1: "UNIT", 4: "NARRATIVE", 5: "OTHER"}
    plan.units = {1: plan.units[1]}
    plan.narratives = {4: plan.narratives[2]}
    run([("unit", "U"), ("blank", ""), ("shadow", ""), ("narrative", "N"), ("diagram", ""), ("unit", "U"), ("narrative", "N")], plan)
    assert plan.count("NJPageKind") == 3                                        # pages 1, 4, 5 only
    assert plan.count("NJUnitPage") == 1 and plan.count("NJNarrativePage") == 1


def test_text_layer_pages_are_classified_for_free(run):
    plan = standard_plan()
    plan.kinds = {}
    plan.units = {1: plan.units[1]}
    run([("text-unit", "")], plan)
    assert plan.count("NJPageKind") == 0


def test_four_units_across_two_unit_pages(run):
    plan = Plan({1: "UNIT", 2: "UNIT", 3: "NARRATIVE"},
                units={1: unit_page(vehicle(1), vehicle(2, "RIGHT")), 2: unit_page(vehicle(3, parked=True), vehicle(4, "RIGHT", parked=True))})
    raw = run([("unit", "P1"), ("unit", "P2"), ("narrative", "N")], plan)
    assert [v["number"] for v in raw["vehicles"]] == [1, 2, 3, 4]
    assert raw["vehicles"][2]["parked"] and plan.count("NJUnitPage") == 2 and plan.count("NJInventory") == 2


def test_missing_vehicle_is_recovered_once(run):
    plan = Plan({1: "UNIT"}, units={1: unit_page(vehicle(1))},
                inventories={1: NJInventory(vehicle_numbers=[1, 2])},
                recovery={1: unit_page(vehicle(2, "RIGHT"), occupants=[NJOccupantRaw(row="B", vehicle="2", position="01", name="X Y")])})
    raw = run([("unit", "P1")], plan)
    assert [v["number"] for v in raw["vehicles"]] == [1, 2]
    assert [o["name"] for o in raw["occupants"]] == ["X Y"]
    assert plan.calls.count(("NJUnitPage", 1, True)) == 1                       # exactly one recovery call


def test_recovery_that_still_misses_a_vehicle_stops(run):
    plan = Plan({1: "UNIT"}, units={1: unit_page(vehicle(1))},
                inventories={1: NJInventory(vehicle_numbers=[1, 2, 3])},
                recovery={1: unit_page(vehicle(2, "RIGHT"))})
    with pytest.raises(IncompleteExtractionError, match=r"\[3\]"):
        run([("unit", "P1")], plan)


def test_recovery_cannot_invent_unrequested_vehicles(run):
    plan = Plan({1: "UNIT"}, units={1: unit_page(vehicle(1))},
                inventories={1: NJInventory(vehicle_numbers=[1, 2])},
                recovery={1: unit_page(vehicle(2, "RIGHT"), vehicle(9, "LEFT"))})
    raw = run([("unit", "P1")], plan)
    assert [v["number"] for v in raw["vehicles"]] == [1, 2]                     # 9 was not requested and is ignored


def test_uncertain_inventory_stops(run):
    plan = Plan({1: "UNIT"}, units={1: unit_page(vehicle(1))}, inventories={1: NJInventory(vehicle_numbers=[1], uncertain=True)})
    with pytest.raises(IncompleteExtractionError, match="uncertain"):
        run([("unit", "P1")], plan)


def test_no_unit_page_raises(run):
    with pytest.raises(ValueError, match="No NJTR-1 vehicle page"):
        run([("narrative", "N")], Plan({1: "NARRATIVE"}))


def test_only_blank_pages_raises(run):
    with pytest.raises(ValueError, match="no usable pages"):
        run([("blank", ""), ("shadow", "")], Plan({}))


def test_classification_failure_stops_instead_of_skipping(run):
    plan = Plan({1: "UNIT", 2: "UNIT"}, units={1: unit_page(vehicle(1))}, fail_classify={2})
    with pytest.raises(RuntimeError, match="Could not classify PDF page 2"):
        run([("unit", "A"), ("unit", "B")], plan)


# ------------------------------------------------------------------ assembly edge cases
def test_unnumbered_vehicles_are_keyed_in_order_presented(run):
    plan = Plan({1: "UNIT"}, units={1: unit_page(vehicle(None), vehicle(None, "RIGHT"))},
                inventories={1: NJInventory(vehicle_numbers=[])})
    raw = run([("unit", "P1")], plan)
    assert [v["number"] for v in raw["vehicles"]] == [1, 2]
    assert sum("no printed number" in n for n in raw["notes"]) == 2


def test_header_conflicts_and_duplicate_vehicle_conflicts_are_noted(run):
    p1 = unit_page(vehicle(1), vehicle(2, "RIGHT"))
    p2 = unit_page(vehicle(2, "LEFT", vin="DIFFERENT"), vehicle(3, "RIGHT"), crash_date="06/16/26", case_number="26-1")
    plan = Plan({1: "UNIT", 2: "UNIT"}, units={1: p1, 2: p2})
    raw = run([("unit", "P1"), ("unit", "P2")], plan)
    assert raw["crash_date"] == "06/15/26"
    assert any("crash_date reads '06/16/26'" in n for n in raw["notes"])
    assert any("vehicle 2 appears twice" in n for n in raw["notes"])
    assert [v["number"] for v in raw["vehicles"]] == [1, 2, 3]


def test_occupant_for_unknown_vehicle_is_noted(run):
    plan = Plan({1: "UNIT"}, units={1: unit_page(vehicle(1), occupants=[NJOccupantRaw(row="A", vehicle="5", position="03", name="Z Z")])})
    assert any("refers to vehicle 5" in n for n in run([("unit", "P1")], plan)["notes"])


def test_unattached_narrative_lines_are_noted_not_guessed(run):
    plan = Plan({1: "UNIT", 2: "NARRATIVE"}, units={1: unit_page(vehicle(1))},
                narratives={2: NJNarrativePage(other_descriptions=[NJNarrativeItem(vehicle=None, text="STATE FARM", field="25")],
                                               additional_citations=[NJNarrativeItem(vehicle=7, text="39:4-1")])})
    raw = run([("unit", "P1"), ("narrative", "N")], plan)
    assert raw["vehicles"][0]["narrative_insurance"] == "" and raw["vehicles"][0]["charges"] == []
    assert sum("could not be tied" in n for n in raw["notes"]) == 2


def test_model_warnings_are_carried_into_notes(run):
    plan = Plan({1: "UNIT"}, units={1: unit_page(vehicle(1), warnings=["VIN digit unclear"])})
    assert any("VIN digit unclear" in n for n in run([("unit", "P1")], plan)["notes"])


def test_whitespace_is_collapsed_and_none_becomes_empty(run):
    plan = Plan({1: "UNIT"}, units={1: unit_page(vehicle(1, driver_last="  DE   LA  CRUZ ", vin=None))})
    v = run([("unit", "P1")], plan)["vehicles"][0]
    assert v["driver"]["last"] == "DE LA CRUZ" and v["vehicle"]["vin"] == ""


# ------------------------------------------------------------------ whole chain: extractor -> rules
def test_extractor_output_feeds_the_rules_without_changes(run):
    raw = run([("unit", "U"), ("narrative", "N"), ("diagram", "")], standard_plan())
    out = nj_rules.map_nj(raw, today=date(2026, 10, 23))
    assert [u["party_number"] for u in out["units"]] == [1, 2]
    assert out["units"][0]["vehicle"]["insurance_carrier"] == "000"
    assert out["units"][0]["driver"]["extra_charges"] == ["39:4-96 - Reckless Driving"]
    names = [(p["person_type"], p["first_name"], p["last_name"]) for p in out["other_parties"]]
    assert ("Passenger", "JAYDEN", "S") in names and ("Passenger", "LATE", "PASSENGER") in names
    assert ("Property Owner", "", "NJTA") in names
