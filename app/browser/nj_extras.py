"""NJ form controls the shared engine does not drive: Hit & Run checkbox, extra charges
(the "(+)" button) and the other-party "Same As Driver/Owner Address" boxes.

Everything here is best effort and never raises: a control that cannot be driven becomes a
warning so the keyer finishes it by hand. The functions use only Playwright and the NJ
selectors, so they can be moved into the shared engine later without changes.
"""
from __future__ import annotations

from app.browser import nj_field_mapping as m

TAB_TIMEOUT_MS = 8000
FIELD_TIMEOUT_MS = 3000


def _panel(section, number: int):
    anchors = section.locator(m.TAB_ANCHORS)
    if anchors.count() < number:
        raise RuntimeError(f"only {anchors.count()} tab(s) exist")
    tab = anchors.nth(number - 1)
    target = (tab.get_attribute("href", timeout=FIELD_TIMEOUT_MS) or "").lstrip("#")
    if not target:
        raise RuntimeError("tab has no linked panel")
    tab.click(timeout=FIELD_TIMEOUT_MS)
    panel = section.locator(f'[id="{target}"]')
    panel.wait_for(state="visible", timeout=TAB_TIMEOUT_MS)
    return panel


def tick_hit_and_run(page, payload) -> list[str]:
    if not (payload.get("incident") or {}).get("hit_and_run"):
        return []
    try:
        box = page.frame_locator(m.FRAME).locator(m.HIT_AND_RUN)
        box.check(timeout=FIELD_TIMEOUT_MS)
        if not box.is_checked():
            raise RuntimeError("box stayed unchecked")
        return []
    except Exception as error:
        return [f"Incident Hit & Run: could not tick the box ({type(error).__name__}); tick it by hand"]


def add_extra_charges(page, payload, log=None) -> list[str]:
    warnings: list[str] = []
    frame = page.frame_locator(m.FRAME)
    section = frame.locator(m.UNIT_SECTION)
    for index, unit in enumerate(payload.get("units") or [], start=1):
        extra = [c for c in (unit.get("driver") or {}).get("extra_charges") or [] if str(c).strip()]
        if not extra:
            continue
        label = f"Unit {unit.get('party_number') or index}"
        try:
            panel = _panel(section, index)
            for charge in extra:
                inputs = panel.locator(m.CHARGE)
                before = inputs.count()
                if before < 1:
                    raise RuntimeError("charge field not found")
                plus = panel.locator(".citations a.add-item:visible").last
                plus.click(timeout=FIELD_TIMEOUT_MS)
                for _ in range(20):                                   # wait for the new Charge box
                    if panel.locator(m.CHARGE).count() > before:
                        break
                    page.wait_for_timeout(150)
                else:
                    raise RuntimeError("(+) did not add a charge box")
                panel.locator(m.CHARGE).last.fill(str(charge), timeout=FIELD_TIMEOUT_MS)
            if log:
                log(f"{label}: {len(extra)} extra charge(s) keyed")
        except Exception as error:
            warnings.append(f"{label}: extra charges not keyed ({type(error).__name__}); key the remaining charges by hand")
    return warnings


def tick_same_as_address(page, payload) -> list[str]:
    warnings: list[str] = []
    frame = page.frame_locator(m.FRAME)
    section = frame.locator(m.OTHER_SECTION)
    for index, party in enumerate(payload.get("other_parties") or [], start=1):
        wanted = []
        if party.get("same_as_driver_address"):
            wanted.append((m.OTHER["same_as_driver_address"], "Same As Driver Address"))
        if party.get("same_as_owner_address"):
            wanted.append((m.OTHER["same_as_owner_address"], "Same As Owner Address"))
        if not wanted:
            continue
        label = f"Other party {index}"
        try:
            panel = _panel(section, index)
            last = (party.get("last_name") or "").strip()
            if last:                                                  # make sure this tab really is this person
                shown = panel.locator(m.OTHER["last_name"]).first.input_value(timeout=FIELD_TIMEOUT_MS).strip()
                if shown.upper() != last.upper():
                    raise RuntimeError("tab does not hold the expected person")
            for selector, name in wanted:
                box = panel.locator(selector).first
                box.check(timeout=FIELD_TIMEOUT_MS)
                if not box.is_checked():
                    raise RuntimeError(f"{name} stayed unchecked")
        except Exception as error:
            warnings.append(f"{label}: Same As address box not ticked ({type(error).__name__}); tick it by hand")
    return warnings


def fill_nj_extras(page, payload, log=None) -> list[str]:
    warnings = tick_hit_and_run(page, payload)
    warnings += add_extra_charges(page, payload, log)
    warnings += tick_same_as_address(page, payload)
    return warnings
