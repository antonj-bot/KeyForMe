from playwright.sync_api import Page, FrameLocator, expect
from app.browser.field_mapping import FRAME_SELECTOR, STRUCTURE, INCIDENT, OWNER, DRIVER, VEHICLE, RADIO_ROWS


def form(page: Page) -> FrameLocator:
    return page.frame_locator(FRAME_SELECTOR)


def fill_if_present(scope, selector: str, value, index: int = 0) -> None:
    if value in (None, ""):
        return
    control = scope.locator(selector).nth(index)
    if control.count():
        control.fill(str(value))


def check_if(scope, selector: str, enabled: bool, index: int = 0) -> None:
    control = scope.locator(selector).nth(index)
    if control.count():
        control.set_checked(bool(enabled))


def select_radio_row(scope, row_name: str, value: str) -> None:
    normalized = (value or "").upper()
    label = {"YES": "Yes", "NO": "No", "NA": "NA"}.get(normalized)
    if label:
        scope.get_by_role("row", name=row_name).get_by_label(label).check()


def add_units(page: Page, required: int) -> None:
    """The site's Add Trailer action clones Unit 1 into another unit.

    We use the clone only to create Unit 2/3, then overwrite every mapped field.
    """
    f = form(page)
    for _ in range(max(0, required - 1)):
        f.get_by_role("button", name="Add Trailer").click()


def activate_unit(page: Page, unit_number: int) -> None:
    form(page).get_by_role("link", name=str(unit_number), exact=True).click()


def fill_incident(page: Page, incident: dict) -> None:
    f = form(page)
    for key, value in incident.items():
        selector = INCIDENT.get(key)
        if selector:
            fill_if_present(f, selector, value)


def fill_person(scope, mapping: dict, data: dict, person_index: int) -> None:
    for key, value in data.items():
        selector = mapping.get(key)
        if not selector:
            continue
        if key in {"same_as_driver_address", "same_as_owner"}:
            check_if(scope, selector, bool(value), person_index)
        elif key == "cited":
            cited_selector = mapping.get("cited_yes" if value == "YES" else "cited_no" if value == "NO" else "")
            if cited_selector:
                check_if(scope, cited_selector, True)
        else:
            fill_if_present(scope, selector, value, person_index)


def fill_unit(page: Page, unit_number: int, unit: dict) -> None:
    activate_unit(page, unit_number)
    f = form(page)

    # Within an active unit, the first visible Person_* set is Owner and second is Driver.
    fill_person(f, OWNER, unit["owner"], person_index=0)
    fill_person(f, DRIVER, unit["driver"], person_index=1)

    for key, value in unit["vehicle"].items():
        if key == "vehicle_towed":
            select_radio_row(f, RADIO_ROWS["vehicle_towed"], value)
        elif key == "airbag_deployed":
            select_radio_row(f, RADIO_ROWS["airbag_deployed"], value)
        else:
            selector = VEHICLE.get(key)
            if selector:
                fill_if_present(f, selector, value)


def fill_keying_form(page: Page, payload: dict) -> None:
    """Fill the CA form. Deliberately does not save or submit."""
    fill_incident(page, payload["incident"])
    add_units(page, len(payload["units"]))
    for unit_number, unit in enumerate(payload["units"], start=1):
        fill_unit(page, unit_number, unit)
