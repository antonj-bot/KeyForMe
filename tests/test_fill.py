import sys

from playwright.sync_api import sync_playwright

from app.browser.engine import fill_form


def fake_unit(n: int) -> dict:
    return {
        "party_number": n,
        "owner": {
            "first_name": f"OWN{n}", "last_name": "TEST",
            "address_1": f"{n} OWNER ST", "same_as_driver_address": True,
        },
        "driver": {
            "first_name": f"DRV{n}", "last_name": "TEST",
            "address_1": f"{n} DRIVER ST",
            "charge": "VC 22350" if n == 1 else "",
            "cited": "NO" if n == 1 else "",
        },
        "vehicle": {
            "tag_number": f"TAG{n}", "vin": f"VIN{n}", "make": "TESTMAKE",
            "vehicle_towed": "YES", "airbag_deployed": "NO",
        },
    }


vehicles = int(sys.argv[1]) if len(sys.argv) > 1 else 3
payload = {
    "incident": {
        "report_identifier_1": "TEST-0001",
        "incident_city": "TESTCITY",
        "time_2400": "1605",
    },
    "units": [fake_unit(n) for n in range(1, vehicles + 1)],
    "other_parties": [],
}

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False, slow_mo=150)
    page = browser.new_page()
    page.goto("http://localhost:8000/index.html")
    fill_form(
        page,
        payload,
        state="CA",
    )
    print("Done. Check every unit tab, then close the Inspector.")
    page.pause()
