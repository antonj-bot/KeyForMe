import re

from app.keying.ca_mapper import has_vehicle_data
from app.models import CaliforniaCHP555

REQUIRED_PARTY_FIELDS = ("driver_license_number", "license_plate")


def validate(report: CaliforniaCHP555) -> list[str]:
    warnings = list(report.warnings)

    if not report.report.local_report_number:
        warnings.append("Missing report number")

    numbers = [p.party_number for p in report.parties]
    if len(numbers) != len(set(numbers)):
        warnings.append("Duplicate party numbers detected")

    for party in report.parties:
        if not has_vehicle_data(party):
            continue  # blank party block, not a vehicle
        for field in REQUIRED_PARTY_FIELDS:
            if not getattr(party, field):
                warnings.append(f"Party {party.party_number}: missing {field}")

        vin = party.vin
        if vin and not re.fullmatch(r"[A-HJ-NPR-Z0-9]{17}", str(vin).upper()):
            warnings.append(f"Party {party.party_number}: VIN format looks wrong ({vin})")

    return warnings
