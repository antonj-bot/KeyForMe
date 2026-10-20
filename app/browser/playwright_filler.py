from playwright.sync_api import Page, FrameLocator, expect
from app.browser.field_mapping import (
    FRAME_SELECTOR, UNIT_SECTION, STRUCTURE,
    INCIDENT, OWNER, DRIVER, VEHICLE, RADIO_ROWS,
)


def form(page: Page) -> FrameLocator:
    return page.frame_locator(FRAME_SELECTOR)


def fill_if_present(scope, selector: str, value, index: int = 0) -> None:
    if value in (None, ""):
        return
    control = scope.locator(selector).nth(index)
    if control.count():
        control.fill(str(value))


def check_if(scope, selector: str, enabled: bool, index: int = 0) -> bool:
    """Try to set a checkbox. Returns False instead of crashing if the site rejects it."""
    control = scope.locator(selector).nth(index)
    if not control.count():
        return False
    try:
        if control.is_checked() != enabled:
            control.click()
            control.page.wait_for_timeout(300)  # let the site's JS react
        return control.is_checked() == enabled
    except Exception:
        return False


def select_radio_row(scope, row_name: str, value: str) -> None:
    normalized = (value or "").upper()
    label = {"YES": "Yes", "NO": "No", "NA": "NA"}.get(normalized)
    if label:
        scope.get_by_role("row", name=row_name).get_by_label(label).check()



def fill_incident(page: Page, incident: dict) -> None:
    f = form(page)
    for key, value in incident.items():
        selector = INCIDENT.get(key)
        if selector:
            fill_if_present(f, selector, value)


CHECKBOX_FIELDS = {"same_as_driver_address", "same_as_owner"}


def fill_person(scope, mapping: dict, data: dict, person_index: int) -> None:
    # Text fields first, so the address exists before any "same as" checkbox.
    for key, value in data.items():
        selector = mapping.get(key)
        if not selector or key in CHECKBOX_FIELDS or key == "cited":
            continue
        fill_if_present(scope, selector, value, person_index)

    # Citation radio (driver only)
    cited = data.get("cited")
    if cited in ("YES", "NO"):
        cited_selector = mapping.get("cited_yes" if cited == "YES" else "cited_no")
        if cited_selector:
            check_if(scope, cited_selector, True)

    # "Same as" checkboxes last. The address is already typed, so a rejected click is harmless.
    for key in CHECKBOX_FIELDS:
        if data.get(key) and mapping.get(key):
            if not check_if(scope, mapping[key], True, person_index):
                print(f"  Note: could not tick '{key}'; the address was typed in instead.")





def fill_keying_form(page: Page, payload: dict) -> None:
    """Fill the CA form. Deliberately does not save or submit."""
    fill_incident(page, payload["incident"])
    add_units(page, len(payload["units"]))
    for unit_number, unit in enumerate(payload["units"], start=1):
        fill_unit(page, unit_number, unit)

def unit_section(page: Page):
    return form(page).locator(UNIT_SECTION)


def count_unit_tabs(section) -> int:
    hrefs = section.locator("a.ui-tabs-anchor").evaluate_all(
        "els => els.map(e => e.getAttribute('href'))"
    )
    return len({h for h in hrefs if h})


def add_units(page: Page, required: int) -> None:
    section = unit_section(page)
    add_button = form(page).locator(STRUCTURE["add_unit_button"]).first

    while count_unit_tabs(section) < required:
        before = count_unit_tabs(section)
        add_button.click()
        for _ in range(50):
            if count_unit_tabs(section) > before:
                break
            page.wait_for_timeout(200)
        else:
            raise RuntimeError(f"Clicked + but no new unit appeared (still {before}).")
        print(f"Unit {before + 1} added.")


def activate_unit(page: Page, unit_number: int) -> None:
    section = unit_section(page)
    tab = section.locator(f"a.ui-tabs-anchor[href='#tabs-{unit_number}']").first
    if not tab.count():
        found = section.locator("a.ui-tabs-anchor").evaluate_all(
            "els => els.map(e => `${e.getAttribute('href')} [${e.textContent.trim()}]`)"
        )
        raise RuntimeError(f"Unit {unit_number} tab not found. Unit tabs: {found}")
    tab.click()
    section.locator(f"#tabs-{unit_number}").first.wait_for(
        state="visible", timeout=10_000
    )


def fill_unit(page: Page, unit_number: int, unit: dict) -> None:
    activate_unit(page, unit_number)
    section = unit_section(page)

    # Search only the vehicle-unit section so Passenger fields aren't matched.
    fill_person(section, DRIVER, unit["driver"], person_index=1)
    fill_person(section, OWNER, unit["owner"], person_index=0)

    for key, value in unit["vehicle"].items():
        if key in RADIO_ROWS:
            select_radio_row(section, RADIO_ROWS[key], value)
        else:
            selector = VEHICLE.get(key)
            if selector:
                fill_if_present(section, selector, value)
