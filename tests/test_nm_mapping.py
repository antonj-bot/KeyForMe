from app.nm_models import NMIncident, NMPageExtraction, NMUnit
from app.extraction.nm_extractor import merge_pages
from app.keying.nm_mapper import map_nm


def test_split_unit_across_pages_and_owner_phone():
    first = NMPageExtraction(
        incident=NMIncident(crash_date="09/28/2026", crash_time="0804"),
        units=[NMUnit(unit_number=1, owner_phone="(505) 353-7699"),
               NMUnit(unit_number=2, driver_first_name="TEST", driver_city="RIO RANCHO")],
    )
    second = NMPageExtraction(units=[NMUnit(
        unit_number=2, owner_first_name="OWNER", owner_phone="(760) 221-5512",
        insurance_carrier="USAA", vin="WAUAUGFF7LA040097",
    )])
    payload = map_nm(merge_pages([first, second]))
    assert payload["incident"]["time_2400"] == "08:04"
    assert len(payload["units"]) == 2
    assert payload["units"][0]["owner"]["home_phone"] == "505 353-7699"
    assert payload["units"][1]["owner"]["home_phone"] == "760 221-5512"
    assert payload["units"][1]["driver"]["city"] == "RIO RANCHO"
    assert payload["units"][1]["vehicle"]["vin"] == "WAUAUGFF7LA040097"


def test_conflicts_are_flagged_not_overwritten():
    report = merge_pages([
        NMPageExtraction(units=[NMUnit(unit_number=1, vin="ORIGINAL")]),
        NMPageExtraction(units=[NMUnit(unit_number=1, vin="DIFFERENT")]),
    ])
    assert report.units[0].vin == "ORIGINAL"
    assert any("conflicting readings for vin" in w for w in report.warnings)
