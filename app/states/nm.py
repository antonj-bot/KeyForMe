"""NM extraction entrypoint. Browser filling intentionally disabled until validated."""
from pathlib import Path
from app.extraction.nm_extractor import extract_nm
from app.keying.nm_mapper import map_nm

NAME = "New Mexico SH 10074"


def extract(pdf_path: Path, model: str) -> dict:
    report = extract_nm(pdf_path, model)

    print("\n===== RAW INCIDENT VALUES =====")
    print("Weather:", repr(report.incident.weather))
    print("Lighting:", repr(report.incident.lighting))

    payload = map_nm(report)

    print("\n===== MAPPED INCIDENT VALUES =====")
    print("Weather:", repr(payload["incident"].get("weather")))
    print("Lighting:", repr(payload["incident"].get("lighting")))

    return payload


def fill(page, payload: dict) -> None:
    raise NotImplementedError(
        "NM form filling is not enabled yet. Validate the NM payload and selectors first."
    )
