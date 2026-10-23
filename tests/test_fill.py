"""Manual browser smoke test for the shared KeyForMe form-filling engine.

Pytest can safely collect this module because browser execution only happens in main().

Examples:
    python tests/test_fill.py 3 --state CA
    python tests/test_fill.py 3 --state NC
    python tests/test_fill.py 3 --state NC --url http://localhost:8000/mock/nc/index.html
"""
from __future__ import annotations

import argparse

from playwright.sync_api import sync_playwright

from app.browser.engine import fill_form


DEFAULT_URLS = {
    "CA": "http://localhost:8000/index.html",
    "NC": "http://localhost:8000/mock/nc/index.html",
}


def fake_unit(n: int, state: str) -> dict:
    unit = {
        "party_number": n,
        "owner": {
            "first_name": f"OWN{n}",
            "last_name": "TEST",
            "address_1": f"{n} OWNER ST",
            "same_as_driver_address": True,
        },
        "driver": {
            "first_name": f"DRV{n}",
            "last_name": "TEST",
            "address_1": f"{n} DRIVER ST",
            "charge": "VC 22350" if state == "CA" and n == 1 else "",
            "cited": "NO" if state == "CA" and n == 1 else "",
        },
        "vehicle": {
            "tag_number": f"TAG{n}",
            "vin": f"VIN{n}",
            "make": "TESTMAKE",
            "vehicle_towed": "YES",
            "airbag_deployed": "NO",
        },
    }

    if state == "NC":
        unit["driver"].update(
            {
                "injury_code": "5",
                "alcohol_drugs": "0",
                "contributing": "0",
                "protection": "2",
                "ejection": "1",
                "ems_to": "",
                "extra_charges": [],
            }
        )
        unit["vehicle"].update(
            {
                "impact_location": "Front" if n == 1 else "Rear",
                "vehicle_defects": "0",
                "speed_limit": "35",
            }
        )

    return unit


def fake_payload(vehicles: int, state: str) -> dict:
    return {
        "incident": {
            "report_identifier_1": "TEST-0001",
            "incident_state": state,
            "incident_city": "TESTCITY",
            "time_2400": "1605",
        },
        "units": [fake_unit(n, state) for n in range(1, vehicles + 1)],
        "other_parties": [],
        "notes": [],
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Manually smoke-test KeyForMe form filling.")
    parser.add_argument("vehicles", nargs="?", type=int, default=3)
    parser.add_argument("--state", choices=("CA", "NC"), default="CA")
    parser.add_argument("--url", help="Override the default local mock URL.")
    parser.add_argument("--headless", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.vehicles < 1:
        raise SystemExit("vehicles must be at least 1")

    state = args.state.upper()
    url = args.url or DEFAULT_URLS[state]
    payload = fake_payload(args.vehicles, state)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            headless=args.headless,
            slow_mo=0 if args.headless else 150,
        )
        try:
            page = browser.new_page()
            page.goto(url)

            if state == "NC":
                # Covers the shared engine plus NC extras.
                from app.states.nc import fill as fill_nc

                fill_nc(page, payload)
                warnings = []
            else:
                warnings = fill_form(page, payload, state=state) or []

            print(f"Filled {args.vehicles} synthetic {state} unit(s) at {url}")
            for warning in warnings:
                print(f"WARNING: {warning}")

            if not args.headless:
                print("Done. Check every unit tab, then close the Inspector.")
                page.pause()
        finally:
            browser.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
