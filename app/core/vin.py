"""Shared VIN lookup policy. Never changes the printed VIN."""
from dataclasses import dataclass

@dataclass(frozen=True)
class VinPolicy:
    # Opt in only after confirming invalid-format errors do not block the form.
    skip_invalid_format: bool = False

# Safe default for forms whose rejection behavior is not verified.
DEFAULT_VIN_POLICY = VinPolicy(
    skip_invalid_format=False,
)

# Configure exceptions here, not inside individual fillers.
STATE_VIN_POLICIES = {
    "NM": VinPolicy(skip_invalid_format=True),
}


def get_vin_policy(state: str) -> VinPolicy:
    code = str(state or "").strip().upper()

    return STATE_VIN_POLICIES.get(
        code,
        DEFAULT_VIN_POLICY,
    )    

NONBLOCKING_FORMAT_ERRORS = VinPolicy(skip_invalid_format=True)

def should_attempt_vin_lookup(vin, *, policy=VinPolicy(), unit_number=None, warn=None):
    text = str(vin or "").strip()
    if not text:
        return False
    upper = text.upper()
    invalid = len(upper) != 17 or any(c in upper for c in "IOQ")
    if not invalid:
        return True
    prefix = f"Unit {unit_number}: " if unit_number is not None else ""
    message = prefix + "VIN keyed as printed; format requires review."
    if policy.skip_invalid_format:
        message += " Popup wait skipped; using report year/make/model."
    if warn:
        warn(message)
    return not policy.skip_invalid_format
