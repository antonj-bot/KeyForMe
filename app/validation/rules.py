import re
from app.models import CaliforniaCHP555

CRITICAL_ALWAYS = {"driver_license_number", "license_plate", "local_report_number"}
CRITICAL_IF_PRESENT = {"vin", "policy_number"}


def _walk(value, path=""):
    if isinstance(value, dict):
        if {"value", "confidence", "evidence"}.issubset(value):
            yield path, value
        for key, child in value.items():
            yield from _walk(child, f"{path}.{key}" if path else key)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from _walk(child, f"{path}[{index}]")


def validate(report: CaliforniaCHP555) -> list[str]:
    warnings = list(report.warnings)
    payload = report.model_dump()
    party_numbers = [p.party_number for p in report.parties]
    if len(party_numbers) != len(set(party_numbers)):
        warnings.append("Duplicate party numbers detected")
    for path, item in _walk(payload):
        name = path.split(".")[-1].split("[")[0]
        val = item["value"]
        if name in CRITICAL_ALWAYS and val is None:
            warnings.append(f"Missing critical field: {path}")
        if val is not None:
            threshold = 0.95 if name in CRITICAL_ALWAYS | CRITICAL_IF_PRESENT else 0.85
            if item["confidence"] < threshold:
                warnings.append(f"Review low-confidence field: {path} ({item['confidence']:.2f})")
    for party in report.parties:
        vin = party.vin.value
        if vin and (not isinstance(vin, str) or not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", vin.upper())):
            warnings.append(f"Party {party.party_number}: VIN is not a valid 17-character format")
    return sorted(set(warnings))
