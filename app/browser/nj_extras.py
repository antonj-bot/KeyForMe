"""NJ form controls the shared engine does not drive: Hit & Run checkbox, extra charges
(the "(+)" button), the other-party "Same As Driver/Owner Address" boxes, and a check that
Impact Location holds EXACTLY the intended option.

Everything here is best effort and never raises: a control that cannot be driven becomes a
warning so the keyer finishes it by hand. The functions use only Playwright and the NJ
selectors, so they can be moved into the shared engine later without changes.
"""
from __future__ import annotations

import time

from app.browser import nj_field_mapping as m

TAB_TIMEOUT_MS = 8000
FIELD_TIMEOUT_MS = 3000
# Impact Location uses the suggestion list, so every step is time-boxed. Playwright's own default for a
# step is 30 s; with a slow or stuck page that turned ONE field into minutes of silent waiting.
STEP_TIMEOUT_MS = 3000        # longest any single click / key press / fill may take
FIELD_BUDGET_S = 12.0         # longest ONE Impact Location field may take in total
TOTAL_BUDGET_S = 60.0         # longest ALL Impact Location checks together may take
SLOW_LOG_S = 5.0              # a check slower than this is mentioned in the UI log
BLANK_TIMEOUT_MS = 1500       # clearing a field after a failure (best effort)


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


# ---------------------------------------------------------------- exact option selection
# Impact Location is a text box with a suggestion list. Typing "Rear" and pressing Tab takes the
# FIRST suggestion that CONTAINS the text, which can be "Left Rear" or "Front & Rear" instead of
# "Rear" (the same goes for "Front"). The shared engine cannot tell, so after filling we read the
# field back and, if it is not exactly what the report says, pick the exact suggestion.
SUGGESTION_ITEMS = (
    "ul.ui-autocomplete:visible li, .ui-menu-item:visible, [role='option']:visible, "
    ".autocomplete-suggestion:visible, .tt-suggestion:visible"
)
MAX_ARROW_PRESSES = 25


def _norm(value) -> str:
    return " ".join(str(value or "").upper().split())


def _type_text(field, text: str, timeout_ms: int) -> None:
    try:
        field.press_sequentially(text, delay=25, timeout=timeout_ms)
    except AttributeError:                       # older Playwright
        field.type(text, delay=25, timeout=timeout_ms)


def _blank(field) -> bool:
    """Best-effort: leave the box empty. True if it worked."""
    try:
        field.fill("", timeout=BLANK_TIMEOUT_MS)
        field.press("Tab", timeout=BLANK_TIMEOUT_MS)
        return True
    except Exception:
        return False


def select_exact_option(page, field, expected: str, budget_s: float = FIELD_BUDGET_S) -> bool:
    """Make `field` hold exactly `expected` (ignoring case and spacing). Returns True on success.

    Every step has an explicit timeout and the whole attempt has a time budget, so a slow or stuck page
    costs seconds, never minutes. On failure the field is left BLANK (never a different value than the
    report says) and False is returned. If the page is so stuck that even clearing the field fails, the
    original error is raised so the caller can tell the keyer to check it by hand."""
    want = _norm(expected)
    deadline = time.monotonic() + budget_s

    def step_ms() -> int:
        left = int((deadline - time.monotonic()) * 1000)
        if left <= 0:
            raise TimeoutError("Impact Location time budget used up")
        return min(STEP_TIMEOUT_MS, left)

    try:
        if _norm(field.input_value(timeout=step_ms())) == want:
            return True
        frame = page.frame_locator(m.FRAME)
        field.click(timeout=step_ms())
        field.fill("", timeout=step_ms())
        _type_text(field, expected, step_ms())
        page.wait_for_timeout(300)

        # 1) click the suggestion whose text is exactly the wanted option
        suggestions = frame.locator(SUGGESTION_ITEMS)
        texts = suggestions.all_inner_texts()
        for index, shown in enumerate(texts):
            if _norm(shown) == want:
                suggestions.nth(index).click(timeout=step_ms())
                page.wait_for_timeout(150)
                if _norm(field.input_value(timeout=step_ms())) == want:
                    return True
                break

        # 2) walk the suggestion list with the arrow keys, reading the box after every press
        for _ in range(min(max(len(texts), 1) + 2, MAX_ARROW_PRESSES)):
            field.press("ArrowDown", timeout=step_ms())
            if _norm(field.input_value(timeout=step_ms())) == want:
                field.press("Tab", timeout=step_ms())
                page.wait_for_timeout(150)
                if _norm(field.input_value(timeout=step_ms())) == want:
                    return True
                break
    except Exception:
        if _blank(field):
            return False                          # blank beats wrong
        raise                                     # the page is stuck: the caller warns "check it by hand"

    # 3) could not select it: leave the box blank rather than keyed wrongly
    if _blank(field):
        return False
    raise RuntimeError("could not clear the field")


def fix_impact_locations(page, payload, log=None) -> list[str]:
    warnings: list[str] = []
    section = page.frame_locator(m.FRAME).locator(m.UNIT_SECTION)
    started = time.monotonic()
    for index, unit in enumerate(payload.get("units") or [], start=1):
        expected = ((unit.get("vehicle") or {}).get("impact_location") or "").strip()
        if not expected:
            continue
        label = f"Unit {unit.get('party_number') or index}"
        if time.monotonic() - started > TOTAL_BUDGET_S:
            warnings.append(f"{label}: Impact Location not verified (time budget used up); check it by hand")
            continue
        began = time.monotonic()
        try:
            field = _panel(section, index).locator(m.VEHICLE["impact_location"]).first
            before = field.input_value(timeout=FIELD_TIMEOUT_MS)
            if select_exact_option(page, field, expected):
                if _norm(before) != _norm(expected) and log:
                    log(f"{label}: Impact Location set to {expected}")
            else:
                warnings.append(f"{label}: Impact Location '{expected}' could not be selected exactly; "
                                "the field was left blank, key it by hand")
        except Exception as error:
            warnings.append(f"{label}: Impact Location not verified ({type(error).__name__}); check it by hand")
        took = time.monotonic() - began
        if log and took > SLOW_LOG_S:
            log(f"{label}: Impact Location check was slow ({took:.0f}s); the browser is responding slowly")
    return warnings


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
    warnings = fix_impact_locations(page, payload, log)
    warnings += tick_hit_and_run(page, payload)
    warnings += add_extra_charges(page, payload, log)
    warnings += tick_same_as_address(page, payload)
    return warnings
