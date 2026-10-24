"""What the shared engine cannot do for PA: Hit & Run, violation rows (type, text, Charged?) and trailers.

Runs AFTER engine.fill_form. Never saves or submits; every problem is returned as a warning to review.
Trailers are added LAST and from the highest unit down, because "Add Trailer" creates a new tab.
"""
import time

from app.browser import pa_field_mapping as pa
from app.browser.controls import check_field, fill_control, fill_field
from app.browser.state_forms import get_form_spec
from app.browser.vin_lookup import fill_vin
from app.core.tabs import activate_tab


def _violations(panel, violations, label, spec, warnings, timeout_s=5.0):
    """Key every violation row of one person; click (+) once per extra row."""
    items = panel.locator(pa.CITATION_ITEM)
    for index, v in enumerate(violations):
        if index:
            before = items.count()
            if before < 1:
                warnings.append(f"{label}: no violation row found; violation {index + 1} not keyed")
                return
            try:
                panel.locator(pa.CITATION_ADD).last.click(timeout=spec.field_timeout_ms)
            except Exception as error:
                warnings.append(f"{label}: (+) could not be clicked ({type(error).__name__}); violation {index + 1} not keyed")
                return
            deadline = time.monotonic() + timeout_s
            while items.count() <= before and time.monotonic() < deadline:
                panel.page.wait_for_timeout(100)
            if items.count() != before + 1:
                warnings.append(f"{label}: (+) did not add exactly one row; violation {index + 1} not keyed")
                return
        if items.count() <= index:
            warnings.append(f"{label}: violation row {index + 1} missing; not keyed")
            return
        item, kind, tag = items.nth(index), v["kind"], f"{label}.violation{index + 1}"
        check_field(item, pa.CITATION_KIND[kind], True, f"{tag}.type", spec, warnings)
        field = item.locator(pa.CITATION_TEXT[kind])
        if field.count() != 1:
            warnings.append(f"{tag}: expected one text field, found {field.count()}; text not keyed")
        else:
            fill_control(field.first, v["text"], f"{tag}.text", spec, warnings)
        if v.get("charged"):
            check_field(item, pa.CITATION_CHARGED[v["charged"]], True, f"{tag}.charged", spec, warnings)


def _tab_unit_numbers(section) -> list[str]:
    return [v.strip() for v in section.locator(pa.UNIT_NUMBER).evaluate_all("els => els.map(e => e.value)")]


def _add_trailer(page, section, unit_tab, trailer, label, spec, warnings, timeout_s=5.0):
    panel = activate_tab(section, unit_tab, spec=spec.tabs, label="PA unit")
    button = panel.locator(pa.ADD_TRAILER)
    if button.count() != 1:
        warnings.append(f"{label}: expected one Add Trailer button, found {button.count()}; trailer not keyed")
        return
    before_numbers = _tab_unit_numbers(section)
    tabs = section.locator(spec.tabs.anchors)
    before = tabs.count()
    try:
        button.first.click(timeout=spec.field_timeout_ms)
    except Exception as error:
        warnings.append(f"{label}: Add Trailer could not be clicked ({type(error).__name__}); trailer not keyed")
        return
    deadline = time.monotonic() + timeout_s
    while tabs.count() <= before and time.monotonic() < deadline:
        page.wait_for_timeout(100)
    if tabs.count() != before + 1:
        warnings.append(f"{label}: Add Trailer did not add exactly one tab; trailer not keyed")
        return
    after_numbers = _tab_unit_numbers(section)
    new = [i for i, n in enumerate(after_numbers, 1) if n not in before_numbers]
    new_tab = new[0] if len(new) == 1 else tabs.count()          # normally the new unit number identifies it
    if len(new) != 1:
        warnings.append(f"{label}: could not tell which tab is the new trailer; assumed the last one, review")
    tpanel = activate_tab(section, new_tab, spec=spec.tabs, label="PA trailer")
    tag = tpanel.locator(pa.VEHICLE["tag_number"])
    if tag.count() == 1 and tag.first.input_value().strip():
        warnings.append(f"{label}: the new trailer tab already has a tag number; not overwritten, review")
        return
    vehicle = {k: trailer.get(k) for k in ("vin", "year", "make", "tag_number", "tag_state")}
    decoded = fill_vin(page, tpanel, vehicle, new_tab, spec, warnings)
    for key, value in vehicle.items():
        if key == "vin" or (decoded and key in ("year", "make")):
            continue
        fill_field(tpanel, spec.vehicle.get(key), value, f"{label}.{key}", spec, warnings)


def fill_pa_extras(page, payload, *, log=None) -> list[str]:
    spec = get_form_spec("PA")
    warnings: list[str] = []
    frame = page.frame_locator(spec.frame)
    if (payload.get("incident") or {}).get("hit_and_run"):
        if log:
            log("Ticking Hit & Run...")
        check_field(frame, pa.HIT_AND_RUN, True, "incident.hit_and_run", spec, warnings)

    units = payload.get("units") or []
    section = frame.locator(spec.unit_section)
    for number, unit in enumerate(units, 1):
        rows = (unit.get("driver") or {}).get("violations") or []
        if rows:
            if log:
                log(f"Unit {number}: keying {len(rows)} violation(s)...")
            panel = activate_tab(section, number, spec=spec.tabs, label="PA unit")
            _violations(panel, rows, f"unit{number}.driver", spec, warnings)

    others = payload.get("other_parties") or []
    if others:
        other_section = frame.locator(spec.other_section)
        for number, other in enumerate(others, 1):
            rows = other.get("violations") or []
            if rows:
                panel = activate_tab(other_section, number, spec=spec.tabs, label="PA other party")
                _violations(panel, rows, f"other{number}", spec, warnings)

    for number in range(len(units), 0, -1):                       # trailers last, highest unit first
        for t_i, trailer in enumerate(units[number - 1].get("trailers") or [], 1):
            if log:
                log(f"Unit {number}: adding trailer {t_i}...")
            _add_trailer(page, section, number, trailer, f"unit{number}.trailer{t_i}", spec, warnings)
    return warnings
