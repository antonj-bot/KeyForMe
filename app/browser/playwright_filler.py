
# KeyForMe shared-core migration v1
from app.core.tabs import unit_tabs, ensure_tabs, activate_tab as shared_activate_tab
from app.core.vin import (
    get_vin_policy,
    should_attempt_vin_lookup,
)
# CA format rejection must be verified before opting into the NM fast path.
CA_VIN_POLICY = VinPolicy(skip_invalid_format=False)

# KeyForMe fix5
import time

from playwright.sync_api import Page

from app.browser.field_mapping import (
    DRIVER, FRAME_SELECTOR, INCIDENT, OTHER, OTHER_SECTION, OWNER,
    PERSON_TYPE_CODES, RADIO_ROWS, STRUCTURE, UNIT_SECTION, VEHICLE, VIN_POPUP_OK
)

CHECKBOX_FIELDS = ("same_as_driver_address", "same_as_owner")
YEAR_MAKE_MODEL = ("year", "make", "model")

_dialog = {"seen": False}


# ---------------- basics

def form(page: Page):
    return page.frame_locator(FRAME_SELECTOR)


def unit_section(page: Page):
    return form(page).locator(UNIT_SECTION)


def other_section(page: Page):
    return form(page).locator(OTHER_SECTION)


def select_by_code(control, wanted: str) -> None:
    options = control.locator("option").evaluate_all(
        "os => os.map(o => ({v: o.value, t: o.textContent.trim()}))"
    )
    w = wanted.strip().upper()
    for o in options:
        if o["v"].upper() == w or o["t"].upper() == w:
            control.select_option(value=o["v"])
            return
    for o in options:
        t = o["t"].upper()
        if t.startswith(w + " ") or t.startswith(w + "-") or t.startswith(w + "."):
            control.select_option(value=o["v"])
            return
    raise ValueError(f"no dropdown option matches '{wanted}'")


def fill_control(control, value, selector: str) -> None:
    text = str(value)
    try:
        if control.evaluate("e => e.tagName") == "SELECT":
            select_by_code(control, text)
            actual = control.evaluate("e => e.options[e.selectedIndex]?.text || ''")
            if not actual.strip().upper().startswith(text.strip().upper()):
                print(f"  Note: picked '{actual}' for '{text}' in {selector}")
        else:
            control.fill(text)
            actual = control.input_value()
            if actual.strip().upper() != text.strip().upper():
                print(f"  Note: keyed '{text}' into {selector}, but the field shows '{actual}'")
    except Exception as error:
        print(f"  Note: could not key '{text}' into {selector}: {error}")


def fill_if_present(scope, selector: str, value, index: int = 0) -> None:
    if value in (None, ""):
        return
    control = scope.locator(selector).nth(index)
    if not control.count():
        print(f"  Note: field not found: {selector}")
        return
    fill_control(control, value, selector)


def fill_person_field(scope, selector: str, value, person: str) -> None:
    """Owner block is 1st in a unit, Driver 2nd. Driver-only fields have one match."""
    if value in (None, ""):
        return
    matches = scope.locator(selector)
    count = matches.count()
    if not count:
        print(f"  Note: field not found: {selector}")
        return
    index = 1 if person == "driver" and count > 1 else 0
    fill_control(matches.nth(index), value, selector)


def check_if(scope, selector: str, enabled: bool, index: int = 0) -> bool:
    control = scope.locator(selector).nth(index)
    if not control.count():
        return False
    try:
        if control.is_checked() != enabled:
            control.click()
            control.page.wait_for_timeout(300)
        return control.is_checked() == enabled
    except Exception:
        return False


def select_radio_row(scope, row_text: str, value: str) -> None:
    label = {"YES": "Yes", "NO": "No", "NA": "NA"}.get((value or "").upper())
    if not label:
        return
    row = scope.locator(f"tr:visible:has-text('{row_text}')").last
    try:
        if not row.count():
            print(f"  Note: '{row_text}' row not found; set {label} manually.")
            return
        radio = row.get_by_label(label, exact=True)
        if not radio.count():
            radio = row.locator(f"input[type=radio][value='{label}' i]")
        if radio.count():
            radio.first.check(timeout=3_000)
        else:
            print(f"  Note: no '{label}' radio in '{row_text}' row.")
    except Exception as error:
        print(f"  Note: could not set '{row_text}' = {label}: {error}")


# ---------------- tabs (units and other parties work the same way)

def count_tabs(section) -> int:
    return unit_tabs(section).count()


def add_tabs(page: Page, section, add_selector: str, required: int, label: str) -> None:
    add_control = form(page).locator(add_selector)
    ensure_tabs(page, section, required, add_control=add_control, log=print, label=label)


def activate_tab(section, number: int, label: str):
    return shared_activate_tab(section, number, label=label)


# ---------------- people

def fill_person(scope, mapping: dict, data: dict, person: str) -> None:
    person_index = 1 if person == "driver" else 0
    for key, value in data.items():
        selector = mapping.get(key)
        if not selector or key in CHECKBOX_FIELDS or key == "cited":
            continue
        fill_person_field(scope, selector, value, person)

    cited = data.get("cited")
    if cited in ("YES", "NO"):
        selector = mapping.get("cited_yes" if cited == "YES" else "cited_no")
        if not selector or not check_if(scope, selector, True):
            print(f"  Note: could not tick Cited {cited}; set it manually.")

    for key in CHECKBOX_FIELDS:
        if data.get(key) and mapping.get(key):
            if not check_if(scope, mapping[key], True, person_index):
                print(f"  Note: could not tick '{key}'; the address was typed in instead.")


# ---------------- vehicle + VIN popup
def debug_vin_popup(page: Page):
    print("\n===== VIN POPUP DEBUG =====")

    for browser_page in page.context.pages:

        if browser_page.is_closed():
            continue

        print(f"PAGE: {browser_page.url}")

        for frame in browser_page.frames:

            try:
                dialogs = frame.locator(
                    "div.ui-dialog"
                )

                buttons = frame.locator(
                    "button"
                )

                print(
                    f"FRAME: {frame.url}"
                )

                print(
                    f"Dialogs: {dialogs.count()}"
                )

                print(
                    f"Buttons: {buttons.count()}"
                )

                for button in buttons.all():

                    if not button.is_visible():
                        continue

                    print({
                        "text": button.inner_text(),
                        "id": button.get_attribute("id"),
                        "class": button.get_attribute("class"),
                    })

            except Exception:
                continue
            
        
def click_popup_ok(page: Page, timeout_s: float = 8.0) -> bool:
    """
    Find the VIN popup OK button across all browser frames.

    Handles:
    - Main webpage
    - #formIframe
    - Nested iframes
    - Other frames in the same browser context
    """

    deadline = time.monotonic() + timeout_s

    while time.monotonic() < deadline:

        for browser_page in page.context.pages:

            if browser_page.is_closed():
                continue

            for frame in browser_page.frames:

                try:
                    button = frame.locator(
                        VIN_POPUP_OK
                    ).first

                    if not button.count():
                        continue

                    if not button.is_visible():
                        continue

                    button.click(timeout=2000)

                    print(
                        f"VIN popup OK clicked in frame: "
                        f"{frame.url}"
                    )

                    return True

                except Exception:
                    continue

        page.wait_for_timeout(200)

    print("WARNING: VIN popup OK button not found.")
    return False


def field_has_value(section, selector: str, timeout_s: float = 3.0) -> bool:
    control = section.locator(selector).first
    end = time.monotonic() + timeout_s
    while time.monotonic() < end:
        try:
            if control.count() and control.input_value().strip():
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def fill_vehicle(page: Page, section, vehicle: dict) -> None:
    decoded = False
    vin = vehicle.get("vin")
    vin_box = section.locator(VEHICLE["vin"]).first
    if vin and vin_box.count():
        _dialog["seen"] = False
        vin_box.fill(str(vin))
        vin_box.press("Tab")
        if should_attempt_vin_lookup(
            vin, policy=get_vin_policy("CA"),
            warn=lambda message: print("  NOTE: " + message),
        ):
            if click_popup_ok(page):
                decoded = field_has_value(
                    section,
                    VEHICLE["year"],
                )

                print(
                    "  VIN popup: OK clicked"
                    + ("" if decoded else ", but year stayed blank")
                )

            else:
                print("  WARNING: VIN popup OK button not found.")

                # Show all frames and visible buttons for debugging.
                debug_vin_popup(page)

                print(
                    "  Continuing with year, make, and model "
                    "from the police report."
                )


    for key, value in vehicle.items():
        if key == "vin" or (decoded and key in YEAR_MAKE_MODEL):
            continue
        if key in RADIO_ROWS:
            select_radio_row(section, RADIO_ROWS[key], value)
        elif VEHICLE.get(key):
            fill_if_present(section, VEHICLE[key], value)


# ---------------- other parties

OTHER_KEYS = ("first_name", "middle_name", "last_name", "suffix", "sex",
              "address_1", "address_2", "state", "city", "zip_code",
              "home_phone", "date_of_birth", "injury_code", "safety_equipment",
              "ejected", "taken_to")


def fill_other_party(page: Page, number: int, other: dict) -> None:
    section = other_section(page)
    activate_tab(section, number, "other party")

    role = other.get("role", "")
    type_code = PERSON_TYPE_CODES.get(role, "")
    if type_code:
        fill_if_present(section, OTHER["person_type"], type_code)
    else:
        print(f"  Note: no Person Type code set for {role}; pick it manually.")

    # Witnesses and pedalcyclists do not receive a Vehicle #.
    if role not in {"WITNESS", "BICYCLIST", "PEDALCYCLIST"}:
        fill_if_present(
            section,
            OTHER["unit_number"],
            other.get("party_number"),
        )
    for key in OTHER_KEYS:
        if role == "WITNESS" and key in ("injury_code", "safety_equipment", "ejected", "taken_to"):
            continue
        fill_if_present(section, OTHER[key], other.get(key))


def fill_other_parties(page: Page, others: list) -> None:
    if not others:
        return
    section = other_section(page)
    add_tabs(page, section, STRUCTURE["add_other_button"], len(others), "other party")
    for number, other in enumerate(others, start=1):
        name = " ".join(x for x in (other["first_name"], other["last_name"]) if x)
        print(f"Keying other party {number} ({other['role']} {name})...")
        fill_other_party(page, number, other)


# ---------------- whole form

def fill_incident(page: Page, incident: dict) -> None:
    f = form(page)
    for key, value in incident.items():
        if INCIDENT.get(key):
            fill_if_present(f, INCIDENT[key], value)


def fill_unit(page: Page, unit_number: int, unit: dict) -> None:
    section = unit_section(page)
    activate_tab(section, unit_number, "unit")
    fill_person(section, DRIVER, unit["driver"], "driver")
    fill_person(section, OWNER, unit["owner"], "owner")
    fill_vehicle(page, section, unit["vehicle"])


def fill_keying_form(page: Page, payload: dict) -> None:
    """Fill the form. Never saves or submits."""
    def on_dialog(dialog):
        _dialog["seen"] = True
        dialog.accept()

    page.on("dialog", on_dialog)
    try:
        fill_incident(page, payload["incident"])
        add_tabs(page, unit_section(page), STRUCTURE["add_unit_button"],
                 len(payload["units"]), "unit")
        for unit_number, unit in enumerate(payload["units"], start=1):
            print(f"Keying unit {unit_number}...")
            fill_unit(page, unit_number, unit)
        fill_other_parties(page, payload.get("other_parties", []))
    finally:
        page.remove_listener("dialog", on_dialog)
    for note in payload.get("notes", []):
        print(f"  NOTE: {note}")
