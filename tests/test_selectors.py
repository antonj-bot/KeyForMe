"""The shared selector helpers and the mappings that use them. Run: python -m pytest tests/test_selectors.py -q"""
from app.browser import selectors


def test_person_and_vehicle_selectors():
    assert selectors.person("FirstName") == "[id^='Person_FirstName-']:visible"
    assert selectors.vehicle("Vin") == "[id^='Vehicle_Vin-']:visible"


def test_mappings_build_the_same_selectors():
    from app.browser import nj_field_mapping as nj
    from app.browser import nm_field_mapping as nm
    for module in (nj, nm):
        assert module.person("LastName") == selectors.person("LastName")
        assert module.vehicle("Make") == selectors.vehicle("Make")
