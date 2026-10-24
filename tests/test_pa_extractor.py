"""PA extraction plumbing: page merge, unit-count guard and PDF rendering. The model itself is never called."""
import pymupdf
import pytest

from app.core.completeness import IncompleteExtractionError
from app.extraction import pa_extractor as ex
from app.extraction.pa_extractor import PAOccupant, PAPage, PAParty, PAUnit, check_units, merge_pages


def unit(n, last="DOE"):
    return PAUnit(number=n, driver={"last": last}, vehicle={"plate": f"TAG{n}"})


def page(**kw):
    return PAPage(**kw)


def test_crash_data_comes_from_the_first_page_that_has_it_and_units_are_merged():
    pages = [
        page(incident_number="202607025541", crash_date="07/19/2026", municipality="PHILADELPHIA CITY",
             units_involved=2, weather=[{"text": "CLOUDY"}], hit_and_run_crash=False),
        page(incident_number="202607025541", units=[unit(1)]),
        page(incident_number="202607025541", units=[unit(2)], crash_date="01/01/1999"),
        page(incident_number="202607025541", occupants=[PAOccupant(unit="1", person_no="1", first="A", last="B")]),
    ]
    raw = merge_pages(pages)
    assert raw["crash_date"] == "07/19/2026" and raw["municipality"] == "PHILADELPHIA CITY"
    assert raw["weather"] == [{"code": None, "text": "CLOUDY"}]
    assert [u["number"] for u in raw["units"]] == [1, 2]
    assert len(raw["occupants"]) == 1
    check_units(raw)                                           # 2 expected, 2 read


def test_pages_of_another_incident_or_another_form_are_ignored():
    pages = [
        page(incident_number="AAA-1", crash_date="07/19/2026", units=[unit(1)]),
        page(incident_number="BBB-2", units=[unit(2)]),                 # different incident
        page(is_pa_crash_report=False, units=[unit(3)]),                # e.g. an auto-theft form
        page(incident_number=None, units=[unit(4)]),                    # no number printed: accepted
    ]
    raw = merge_pages(pages)
    assert [u["number"] for u in raw["units"]] == [1, 4]
    assert any("BBB-2" in n for n in raw["notes"]) and any("Page 3 is not part" in n for n in raw["notes"])


def test_incident_number_comparison_ignores_punctuation_and_case():
    pages = [page(incident_number="43-26-05679", crash_date="07/11/2026", units=[unit(1)]),
             page(incident_number="43 26 05679", units=[unit(2)])]
    assert [u["number"] for u in merge_pages(pages)["units"]] == [1, 2]


def test_duplicate_units_and_people_are_kept_once():
    occ = PAOccupant(unit="1", person_no="1", first="A", last="B")
    pages = [page(incident_number="X1", crash_date="07/19/2026", units=[unit(1, "FIRST")], occupants=[occ],
                  witnesses=[PAParty(first="W", last="ONE", address_1="1 ST")]),
             page(incident_number="X1", units=[unit(1, "SECOND")], occupants=[occ],
                  witnesses=[PAParty(first="w", last="one", address_1="1 st")])]
    raw = merge_pages(pages)
    assert len(raw["units"]) == 1 and raw["units"][0]["driver"]["last"] == "FIRST"
    assert len(raw["occupants"]) == 1 and len(raw["witnesses"]) == 1
    assert any("first reading kept" in n for n in raw["notes"])


def test_crash_level_hit_and_run_is_kept_from_any_page():
    raw = merge_pages([page(incident_number="X", crash_date="07/19/2026", units=[unit(1)]),
                       page(incident_number="X", hit_and_run_crash=True)])
    assert raw["hit_and_run_crash"] is True


def test_no_pa_pages_at_all_is_an_error():
    with pytest.raises(ValueError, match="No PA crash report pages"):
        merge_pages([page(is_pa_crash_report=False)])


def test_missing_unit_cancels_filling():
    raw = merge_pages([page(incident_number="X", crash_date="07/19/2026", units_involved=3, units=[unit(1), unit(3)])])
    with pytest.raises(IncompleteExtractionError, match=r"\[2\]"):
        check_units(raw)


def test_unreadable_unit_count_is_a_note_not_an_error():
    raw = merge_pages([page(incident_number="X", crash_date="07/19/2026", units=[unit(1)])])
    check_units(raw)
    assert any("unit count not verified" in n for n in raw["notes"])


def test_no_units_is_an_error():
    raw = merge_pages([page(incident_number="X", crash_date="07/19/2026")])
    with pytest.raises(ValueError, match="No PA units"):
        check_units(raw)


def make_pdf(tmp_path, pages, name="pa.pdf"):
    doc = pymupdf.open()
    for i in range(pages):
        p = doc.new_page()
        p.insert_text((72, 72), f"page {i + 1}")             # a text page; scanned pages work the same way
    path = tmp_path / name
    doc.save(path)
    doc.close()
    return path


def test_extract_pa_reads_every_page_as_an_image_and_merges(tmp_path, monkeypatch):
    calls = []

    def fake(image, number, model, schema=PAPage):
        calls.append((number, model, image[:23]))
        if number == 1:
            return page(incident_number="X9", crash_date="07/19/2026", units_involved=1)
        if number == 2:
            return page(incident_number="X9", units=[unit(1)])
        return page(is_pa_crash_report=False)

    monkeypatch.setattr(ex, "_extract_page", fake)
    raw = ex.extract_pa(make_pdf(tmp_path, 3), "test-model")
    assert sorted(c[0] for c in calls) == [1, 2, 3]
    assert all(c[1] == "test-model" and c[2] == "data:image/jpeg;base64," for c in calls)
    assert [u["number"] for u in raw["units"]] == [1]


def test_extract_payload_goes_through_the_rules(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "_extract_page", lambda image, number, model, schema=PAPage: page(
        incident_number="X9", crash_date="07/19/2026", crash_time="09:30", units_involved=1, units=[unit(1)]))
    payload = ex.extract_payload(make_pdf(tmp_path, 1), "m")
    assert payload["incident"]["report_identifier_1"] == "X9" and len(payload["units"]) == 1


def test_page_limit(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "MAX_PAGES", 2)
    with pytest.raises(ValueError, match="1-2 pages"):
        ex.extract_pa(make_pdf(tmp_path, 3), "m")


def test_schema_round_trips():
    p = PAPage.model_validate({"units": [{"number": 1, "trailers": [{"plate": "T"}],
                                          "driver": {"violations": [{"text": "x", "charged": "Y", "primary": True}]}}]})
    assert p.units[0].driver.violations[0].primary is True
    assert "units" in PAPage.model_json_schema()["properties"]
