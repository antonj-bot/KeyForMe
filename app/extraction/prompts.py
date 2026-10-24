"""Prompt text shared by every state extractor.

KEY WHAT YOU SEE applies to ALL states. A state may add an exception only when that state's guide or SOP
defines one, and it goes in STATE_EXCEPTIONS below, so every exception is visible in one place.

    from app.extraction.prompts import key_what_you_see
    KEY_WHAT_YOU_SEE = key_what_you_see("NC")
"""
from __future__ import annotations

CORE = (
    'KEY WHAT YOU SEE. '
    'Transcribe every value exactly as printed, including misspellings, abbreviations, capitalization, punctuation, periods, ellipses, leading zeros, identifiers and VIN characters. '
    'Never correct, normalize, translate, guess or invent a value. '
    'Read each field from its own printed label and physical location. '
    'Return null for a blank or unreadable value (an empty list for a list). '
    'Never copy a value from one unit, vehicle, party or person to another. '
    'Put anything unreadable or doubtful in warnings.'
)

STATE_EXCEPTIONS = {
    # California CHP 555
    "CA": (
        "For checkboxes, use only visibly marked selections. "
        "Dates: MM/DD/YYYY. Times: HH:MM."
    ),
    # North Carolina DMV-349
    "NC": (
        "Exception: the literal word null or a series of X is a printed value, not a blank: "
        "transcribe it as printed."
    ),
    # New Jersey NJTR-1
    "NJ": (
        "Exception: a dash, a row of dashes or a blank box means no value: return null."
    ),
    # Pennsylvania AA-500 family
    "PA": (
        "For every coded or dropdown-like box return each printed value as {code, text}: the number as "
        "printed in code and the words as printed in text (either may be null); several printed values "
        "are several entries."
    ),
    # New Mexico SH 10074
    "NM": "",
}


def key_what_you_see(state: str | None = None) -> str:
    """CORE plus the exception for `state` (KeyError for a state that is not listed)."""
    if not state:
        return CORE
    extra = STATE_EXCEPTIONS[state.upper()]
    return CORE + (" " + extra if extra else "")


# kept for the NM extractor, which imports this name
KEY_WHAT_YOU_SEE = key_what_you_see("NM")
