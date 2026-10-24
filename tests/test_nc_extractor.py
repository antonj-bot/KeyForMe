"""NC extractor plumbing, run WITHOUT the AI: the model call is replaced by canned results, so this tests
page pairing, merging, the unit-count gate, and that the extractor schema feeds map_nc without key drift.
The PDFs used for pairing are generated here (image-only pages, like the scanned NC reports)."""
import copy
import os
import sys
import types
from datetime import date
from pathlib import Path

import pymupdf
import pytest

from app.core.completeness import IncompleteExtractionError
from app.extraction import nc_extractor as ex
from app.keying import nc_rules as nc

sys.path.insert(0, str(Path(__file__).resolve().parent))
from nc_fixtures import sample_raw  # noqa: E402

TODAY = date(2026, 10, 23)
SAMPLES = Path(os.environ.get("NC_SAMPLES_DIR", "samples/nc"))      # folder holding the real NC sample PDFs
needs_samples = pytest.mark.skipif(not SAMPLES.exists(), reason="set NC_SAMPLES_DIR to the folder with the NC sample PDFs")


def as_form(raw: dict, **over) -> ex.NCFormExtraction:
    d = copy.deepcopy(raw)
    d["margin_boxes"] = [{"box": k, "value": v} for k, v in d["margin_boxes"].items()]
    d.pop("notes", None)
    d.update({"form_rev": "1/2009", "form_number": 1, "form_total": 1, "units_involved": 2,
              "witnesses": [{"name": "TESTFOUR MIDDLED SAMPLEFOUR", "address_1": "400 SAMPLE 9TH AVE", "city": "ROCKINGHAM",
                             "state": "NC", "zip": "28379"}],
              "property_owners": [{"name": "TESTFIVE SAMPLEFIVE", "description": "FENCE/HOUSE",
                                   "address_1": "500 SAMPLE NINTH AVE", "city": "ROCKINGHAM", "state": "NC", "zip": "28379"}]})
    d.update(over)
    return ex.NCFormExtraction.model_validate(d)


def blank_pdf(path: Path, pages: int) -> Path:
    doc = pymupdf.open()
    for _ in range(pages):
        doc.new_page(width=612, height=792)
    doc.save(path)
    doc.close()
    return path


def test_extractor_schema_feeds_map_nc_without_drift():
    raw = ex.merge_forms([as_form(sample_raw())])
    ex.check_units(raw)
    p = nc.map_nc(raw, today=TODAY)
    q = nc.map_nc(sample_raw(), today=TODAY)
    assert p["incident"] == q["incident"]
    assert p["units"] == q["units"]
    assert {o["role"] for o in p["other_parties"]} == {"WITNESS", "PROPERTY OWNER"}
    assert next(o for o in p["other_parties"] if o["role"] == "PROPERTY OWNER")["last_name"] == "SAMPLEFIVE"


def test_unit_count_gate():
    raw = ex.merge_forms([as_form(sample_raw(), units_involved=3)])
    with pytest.raises(IncompleteExtractionError):
        ex.check_units(raw)
    ex.check_units(ex.merge_forms([as_form(sample_raw(), units_involved=2)]))          # ok
    with pytest.raises(ValueError):
        ex.check_units(ex.merge_forms([as_form({**sample_raw(), "units": []})]))


def test_two_forms_keep_letters_and_margin_boxes_apart():
    r1 = sample_raw()
    r2 = copy.deepcopy(sample_raw())
    r2["units"] = [{**r2["units"][0], "number": 3, "column": "left", "hit_and_run": False,
                    "ems_taken": "B - REFUSED"},
                   {**r2["units"][1], "number": 4, "column": "right"}]
    r2["occupants"] = [{"row": "A", "vehicle": "3", "person_type": "1", "injury": "5", "protection": "1",
                        "airbag": "1", "ejection": "1"},
                       {"row": "B", "vehicle": "3", "person_type": "2", "name": "AMY LEE", "injury": "4",
                        "protection": "1", "airbag": "1", "ejection": "1"}]
    r2["margin_boxes"] = {"14": "20"}
    r2["charges"], r2["witnesses"], r2["property_owners"] = [], [], []
    f2 = as_form(r2, supplemental=False, form_number=2, form_total=2, units_involved=4, witnesses=[], property_owners=[])
    raw = ex.merge_forms([as_form(r1, units_involved=4), f2])
    ex.check_units(raw)
    p = nc.map_nc(raw, today=TODAY)
    by = {u["party_number"]: u for u in p["units"]}
    assert sorted(by) == [1, 2, 3, 4]
    assert by[1]["driver"]["contributing"] == "8" and by[3]["driver"]["contributing"] == "20"   # per-form margin boxes
    amy = next(o for o in p["other_parties"] if o["first_name"] == "AMY")
    assert amy["ems_to"] == "REFUSED" and amy["vehicle_number"] == "3"        # row B of form 2, not form 1
    assert by[1]["driver"]["ems_to"] == ""


def test_pairs_pages_and_rejects_odd_page_counts(monkeypatch, tmp_path):
    seen = []

    def fake(images, prompt, model, schema=ex.NCFormExtraction):
        seen.append(len(images))
        return as_form(sample_raw(), units_involved=2)

    monkeypatch.setattr(ex, "_extract_images", fake)
    assert ex.extract_nc(blank_pdf(tmp_path / "four.pdf", 4))["units"] and seen == [2, 2]   # 4 pages -> 2 forms
    seen.clear()
    ex.extract_nc(blank_pdf(tmp_path / "two.pdf", 2))
    assert seen == [2]
    for pages in (1, 3):
        with pytest.raises(ValueError):
            ex.extract_nc(blank_pdf(tmp_path / f"odd{pages}.pdf", pages))


@needs_samples
@pytest.mark.parametrize("name,pages", [("NC normal 2 units.pdf", 2), ("NC 3 units, redacted.pdf", 4),
                                        ("Witness, property owner and unit 1 citation.pdf", 4),
                                        ("NC unit 2 christopher first name owner.pdf", 2)])
def test_sample_pdfs_are_image_only_even_page_counts(name, pages):
    with pymupdf.open(SAMPLES / name) as pdf:
        assert len(pdf) == pages
        assert all(len(pg.get_text().strip()) < 50 for pg in pdf)        # no text layer: vision is required
        assert ex._image(pdf[0]).startswith("data:image/jpeg;base64,")


def test_prompt_mentions_every_hard_rule():
    for needle in ("HIT & RUN", "PEDESTRIAN", "Parked", "Veh# n Towed To/By", "margin_boxes", "column 32",
                   "Municipality", "KEY WHAT YOU SEE", "A - Mission Hospital"):
        assert needle in ex.FORM_PROMPT, needle


# ------------------------------------------------------------------ detect.py patch
def _find_detect() -> Path:
    """The live detect.py. Backup folders (.nj-backups, .provider-backups, .nc-backups...) are ignored: they hold
    OLD copies of the file."""
    root = Path(__file__).resolve().parents[1]
    candidates = []
    for p in sorted(root.rglob("detect.py")):
        rel = p.relative_to(root).parts
        if any(part.startswith(".") or part in ("venv", "site-packages") for part in rel):
            continue
        if "FORM_SIGNATURES" in p.read_text(encoding="utf-8", errors="ignore"):
            candidates.append(p)
    if not candidates:
        pytest.skip("detect.py not found")
    return next((p for p in candidates if p.parts[-2] == "states"), candidates[0])


@pytest.fixture()
def detect_mod(monkeypatch):
    import importlib.util
    runtime = types.ModuleType("app.ai.runtime")                      # stub: no real AI client in tests
    runtime.get_ai_client = lambda: None
    monkeypatch.setitem(sys.modules, "app.ai", types.ModuleType("app.ai"))
    monkeypatch.setitem(sys.modules, "app.ai.runtime", runtime)
    spec = importlib.util.spec_from_file_location("kfm_detect_under_test", _find_detect())
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_detect_maps_dmv349_to_nc(detect_mod):
    d = detect_mod
    if not hasattr(d, "state_from_form_name"):
        pytest.skip("detect.py is not patched yet: run install_nc_state.py")
    assert d.state_from_form_name("DMV-349 (Rev. 1/2009)") == "NC"
    assert d.state_from_form_name("DMV 349") == "NC" and d.state_from_form_name("CHP 555") == "CA"
    assert d.state_from_form_name("NJTR-1") == "NJ" and d.state_from_form_name("") is None


def test_detect_from_image_fills_state_from_form_name(detect_mod, monkeypatch, tmp_path):
    d = detect_mod
    if not hasattr(d, "state_from_form_name"):
        pytest.skip("detect.py is not patched yet: run install_nc_state.py")
    page = pymupdf.open(blank_pdf(tmp_path / "p.pdf", 1))[0]
    client = types.SimpleNamespace(parse=lambda **kw: d.ReportID(state=None, form_name="DMV-349 (Rev. 1/2009)", agency=None))
    monkeypatch.setattr(d, "get_ai_client", lambda: client)
    rid = d.detect_from_image(page, "gpt-6-luna")
    assert rid.state == "NC" and rid.form_name.startswith("DMV-349")
    client2 = types.SimpleNamespace(parse=lambda **kw: d.ReportID(state="CA", form_name="CHP 555", agency=None))
    monkeypatch.setattr(d, "get_ai_client", lambda: client2)
    assert d.detect_from_image(page, "m").state == "CA"                # a printed state is never overridden
