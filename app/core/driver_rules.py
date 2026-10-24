"""Driver-name rules shared by every state (General SOP).

HIT AND RUN: when a vehicle is marked hit-and-run and the report gives NO driver name (first,
middle and last name are all blank), key HIT AND RUN in the driver's LAST NAME. A name that is
printed always wins, and "UNKNOWN" counts as a printed name (key what you see).

The rule needs one thing from the state's extraction: a per-vehicle flag. Set `hit_and_run` to a
truthy value on the unit (payload["units"][n]["hit_and_run"]); the same key is also read from the
unit's "vehicle" or "driver" dict. The shared engine applies the rule before it fills anything, so
a state only has to supply the flag, and every state that does gets the rule for free.

Pure functions: no I/O, no browser. The payload passed in is never modified.
"""
from __future__ import annotations

import copy
import re

HIT_AND_RUN_NAME = "HIT AND RUN"
NAME_KEYS = ("first_name", "middle_name", "last_name")

_TRUE = {"1", "Y", "YES", "TRUE", "X"}


def is_flagged(value) -> bool:
    """True for a ticked/flagged value: True, 1, Y, YES, TRUE or X (any case)."""
    if value in (None, "", False, 0):
        return False
    return str(value).strip().upper() in _TRUE


def has_driver_name(driver) -> bool:
    """True when first, middle or last name holds a letter or digit. A lone dash is no name."""
    if not isinstance(driver, dict):
        return False
    return any(re.search(r"[A-Za-z0-9]", str(driver.get(key) or "")) for key in NAME_KEYS)


def unit_is_hit_and_run(unit) -> bool:
    if not isinstance(unit, dict):
        return False
    sources = (unit, unit.get("vehicle"), unit.get("driver"))
    return any(is_flagged(src.get("hit_and_run")) for src in sources if isinstance(src, dict))


def apply_hit_and_run_name(payload):
    """Returns (payload, unit numbers changed). Without changes the SAME payload object comes back;
    with changes a deep copy is returned, so the caller's data is never touched."""
    units = (payload or {}).get("units") or []
    todo = [i for i, unit in enumerate(units)
            if unit_is_hit_and_run(unit) and not has_driver_name((unit or {}).get("driver"))]
    if not todo:
        return payload, []
    result = copy.deepcopy(payload)
    changed = []
    for i in todo:
        unit = result["units"][i]
        driver = unit.get("driver")
        if not isinstance(driver, dict):
            driver = unit["driver"] = {}
        for key in ("first_name", "middle_name"):
            if key in driver:
                driver[key] = ""                      # a leftover "-" placeholder must not be keyed
        driver["last_name"] = HIT_AND_RUN_NAME
        changed.append(unit.get("party_number") or i + 1)
    return result, changed


PARKED_NAME = "PARKED"


def placeholder_last_name(driver, parked=False, hit_and_run=False) -> str:
    """The placeholder to key in the driver's LAST name, or "" when none applies.
    A printed name always wins (key what you see). With first, middle and last name all blank:
    the parked-vehicle mark has priority (PARKED), then the hit-and-run mark (HIT AND RUN)."""
    if has_driver_name(driver):
        return ""
    if is_flagged(parked):
        return PARKED_NAME
    if is_flagged(hit_and_run):
        return HIT_AND_RUN_NAME
    return ""


def apply_placeholder_name(driver, parked=False, hit_and_run=False) -> str:
    """Key the placeholder into `driver` (a dict, changed in place). Returns the word keyed, or "".
    A leftover "-" in first / middle name is cleared; a printed name is never touched."""
    word = placeholder_last_name(driver, parked, hit_and_run)
    if word and isinstance(driver, dict):
        for key in ("first_name", "middle_name"):
            if key in driver:
                driver[key] = ""
        driver["last_name"] = word
    return word
