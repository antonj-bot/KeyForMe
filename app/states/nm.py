"""NM extraction entrypoint. Browser filling intentionally disabled until validated."""
from pathlib import Path
from app.extraction.nm_extractor import extract_nm
from app.keying.nm_mapper import map_nm

NAME = "New Mexico SH 10074"


def extract(pdf_path: Path, model: str) -> dict:
    report = extract_nm(pdf_path, model)
    return map_nm(report)


def fill(page, payload: dict) -> None:
    raise NotImplementedError(
        "NM form filling is not enabled yet. Validate the NM payload and selectors first."
    )
