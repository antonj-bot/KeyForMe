# KeyForMe fix2
from app.browser.playwright_filler import fill_keying_form
from app.extraction.openai_extractor import extract_chp555_fast
from app.keying.ca_mapper import map_ca_keying
from app.validation.rules import validate

NAME = "California CHP 555"


def extract(pdf_path, model: str) -> dict:
    result = extract_chp555_fast(pdf_path, model)
    warnings = validate(result)
    print(f"Parties found: {len(result.parties)} | Warnings: {len(warnings)}")
    for warning in warnings:
        print(f"  - {warning}")
    payload = map_ca_keying(result)
    for note in payload["notes"]:
        print(f"  NOTE: {note}")
    return payload


def fill(page, payload: dict) -> None:
    fill_keying_form(page, payload)
