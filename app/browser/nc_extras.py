"""What the shared engine cannot do for NC: Hit & Run, extra charges and the "Same As ... Address" boxes.

Runs AFTER engine.fill_form, so the driver's address is already keyed when "Same As Driver Address" is
ticked (the box copies it). Never saves or submits; every problem is returned as a warning to review.
"""
import time

from app.browser import nc_field_mapping as nc
from app.browser.controls import check_field, fill_control
from app.browser.state_forms import get_form_spec
from app.core.tabs import activate_tab


def _add_charges(panel, charges, label, spec, warnings, timeout_s=5.0):
    """Click (+) once per extra charge and key it into the row that appears."""
    items = panel.locator(nc.CHARGE_ITEM)
    for index, charge in enumerate(charges, start=1):
        before = items.count()
        if before < 1:
            warnings.append(f"{label}: no charge row found; extra charge '{charge}' not keyed")
            return
        try:
            panel.locator(nc.CHARGE_ADD).last.click(timeout=spec.field_timeout_ms)
        except Exception as error:
            warnings.append(f"{label}: (+) could not be clicked ({type(error).__name__}); charge '{charge}' not keyed")
            return
        deadline = time.monotonic() + timeout_s
        while items.count() <= before and time.monotonic() < deadline:
            panel.page.wait_for_timeout(100)
        if items.count() != before + 1:
            warnings.append(f"{label}: (+) did not add exactly one charge row; charge '{charge}' not keyed")
            return
        field = items.nth(before).locator(nc.CHARGE_INPUT)
        if field.count() != 1:
            warnings.append(f"{label}: new charge row has {field.count()} fields; charge '{charge}' not keyed")
            return
        fill_control(field.first, charge, f"{label}.charge{index + 1}", spec, warnings)


def fill_nc_extras(page, payload, *, log=None) -> list[str]:
    spec = get_form_spec("NC")
    warnings: list[str] = []
    frame = page.frame_locator(spec.frame)

    if (payload.get("incident") or {}).get("hit_and_run"):
        if log:
            log("Ticking Hit & Run...")
        check_field(frame, nc.HIT_AND_RUN, True, "incident.hit_and_run", spec, warnings)

    units = payload.get("units") or []
    if units:
        section = frame.locator(spec.unit_section)
        for number, unit in enumerate(units, 1):
            extra = (unit.get("driver") or {}).get("extra_charges") or []
            same = bool((unit.get("owner") or {}).get("same_as_driver_address"))
            if not (extra or same):
                continue
            panel = activate_tab(section, number, spec=spec.tabs, label="NC unit")
            if same:
                check_field(panel, nc.OWNER_SAME_AS_DRIVER_ADDRESS, True,
                            f"unit{number}.owner.same_as_driver_address", spec, warnings)
            if extra:
                if log:
                    log(f"Unit {number}: keying {len(extra)} extra charge(s)...")
                _add_charges(panel, extra, f"unit{number}.driver", spec, warnings)

    others = payload.get("other_parties") or []
    if others:
        section = frame.locator(spec.other_section)
        for number, other in enumerate(others, 1):
            extra = other.get("extra_charges") or []
            same_driver = bool(other.get("same_as_driver_address"))
            same_owner = bool(other.get("same_as_owner_address"))
            if not (extra or same_driver or same_owner):
                continue
            panel = activate_tab(section, number, spec=spec.tabs, label="NC other party")
            label = f"other{number}"
            if same_driver:
                check_field(panel, nc.OTHER_SAME_AS_DRIVER_ADDRESS, True, f"{label}.same_as_driver_address", spec, warnings)
            if same_owner:
                check_field(panel, nc.OTHER_SAME_AS_OWNER_ADDRESS, True, f"{label}.same_as_owner_address", spec, warnings)
            if extra:
                _add_charges(panel, extra, label, spec, warnings)
    return warnings
