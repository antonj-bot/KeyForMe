"""NM supervised filler. Never saves or submits."""
import time

from playwright.sync_api import Page
from app.browser.nm_field_mapping import FRAME, UNIT_SECTION, INCIDENT, OWNER, DRIVER, VEHICLE



def _fill_control(control, value, label, warnings):
    if value is None or str(value) == "":
        return

    text = str(value)

    try:
        metadata = control.evaluate(
            """
            element => ({
                tag: element.tagName,
                options: element.tagName === "SELECT"
                    ? Array.from(element.options, option => ({
                        value: option.value,
                        label: option.textContent.trim()
                    }))
                    : []
            })
            """
        )

        is_select = metadata["tag"] == "SELECT"

        if is_select:
            wanted = text.casefold()

            match = next(
                (
                    option
                    for option in metadata["options"]
                    if wanted in (
                        option["value"].casefold(),
                        option["label"].casefold(),
                    )
                ),
                None,
            )

            if match is None:
                warnings.append(
                    f"{label}: no exact dropdown option; skipped"
                )
                return

            expected = match["value"]
            control.select_option(value=expected)
        else:
            expected = text
            control.fill(text, timeout=3000)
            control.press("Tab")

        actual = control.input_value()

        if is_select:
            retained = actual == expected
        else:
            retained = (
                actual.strip().casefold()
                == expected.strip().casefold()
            )

        if not retained:
            warnings.append(
                f"{label}: readback differs; review"
            )

    except Exception as exc:
        warnings.append(
            f"{label}: {type(exc).__name__}; review"
        )


def _fill(scope, selector, value, label, warnings):
    if value in (None, "") or not selector:
        return
    controls = scope.locator(selector)
    if controls.count() != 1:
        warnings.append(f"{label}: expected one field, found {controls.count()}")
        return
    _fill_control(controls.first, value, label, warnings)


def _fill_person(panel, mapping, data, role, warnings):
    for key, value in data.items():
        selector = mapping.get(key)

        if not selector or value in (None, ""):
            continue

        matches = panel.locator(selector)
        count = matches.count()

        if count == 2:
            # Owner first, Driver second within the active unit.
            index = 0 if role == "owner" else 1

        elif count == 1:
            # Shared Owner/Driver fields must not fall back
            # to the wrong person's only matching control.
            if key in OWNER:
                warnings.append(
                    f"{role}.{key}: expected separate Owner "
                    "and Driver fields; skipped"
                )
                continue

            # Driver-only field.
            index = 0

        else:
            warnings.append(
                f"{role}.{key}: expected one or two controls, "
                f"found {count}; skipped"
            )
            continue

        _fill_control(
            matches.nth(index),
            str(value),
            f"{role}.{key}",
            warnings,
        )

def _fill_vehicle_radio(panel, field_name, raw, warnings):
    """Select a verified NM vehicle radio within the active unit."""
    if raw is None:
        return

    value = str(raw).strip().upper()

    # Missing data must not be treated as an explicit NA selection.
    if not value:
        return

    choices = {
        "YES": "1",
        "Y": "1",
        "1": "1",
        "NO": "0",
        "N": "0",
        "0": "0",
        "NA": "",
        "N/A": "",
        "NOT APPLICABLE": "",
    }

    if value not in choices:
        warnings.append(
            f"{field_name}: unrecognized radio value; skipped"
        )
        return

    radio_value = choices[value]

    selector = (
        f"input[type='radio']"
        f"[id^='Vehicle_{field_name}-']"
        f"[value='{radio_value}']"
    )

    controls = panel.locator(selector)

    if controls.count() != 1:
        warnings.append(
            f"{field_name}: expected one radio, "
            f"found {controls.count()}; skipped"
        )
        return

    try:
        control = controls.first
        control.check(timeout=3000)

        if not control.is_checked():
            warnings.append(
                f"{field_name}: radio selection not retained"
            )

    except Exception as error:
        warnings.append(
            f"{field_name}: {type(error).__name__}; review"
        )
        
VIN_POPUP_OK = (
    "div.ui-dialog.ui-front.ui-dialog-buttons "
    "div.ui-dialog-buttonpane button:first-child"
)
YEAR_MAKE_MODEL = ("year", "make", "model")


def _click_vin_popup_ok(page: Page, timeout_s: float = 8.0) -> bool:
    """Find the VIN confirmation OK button across every open page/frame."""
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        for browser_page in page.context.pages:
            if browser_page.is_closed():
                continue
            for frame in browser_page.frames:
                try:
                    button = frame.locator(VIN_POPUP_OK).first
                    if button.count() and button.is_visible():
                        button.click(timeout=2000)
                        return True
                except Exception:
                    continue
        page.wait_for_timeout(200)
    return False


def _field_has_value(panel, selector: str, timeout_s: float = 3.0) -> bool:
    control = panel.locator(selector).first
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if control.count() and control.input_value().strip():
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


def _fill_nm_vin(page: Page, panel, vehicle_data: dict, unit_number: int, warnings) -> bool:
    """Key VIN, confirm lookup across frames, and report whether decode populated Year."""
    vin = str(vehicle_data.get("vin") or "").strip()
    if not vin:
        return False

    vin_selector = VEHICLE.get("vin")
    year_selector = VEHICLE.get("year")
    if not vin_selector or not year_selector:
        warnings.append(f"Unit {unit_number}: VIN or Year selector is not configured")
        return False

    vin_boxes = panel.locator(vin_selector)
    if vin_boxes.count() != 1:
        warnings.append(f"Unit {unit_number}: expected one VIN field, found {vin_boxes.count()}")
        return False

    try:
        vin_box = vin_boxes.first
        vin_box.fill(vin, timeout=3000)
        vin_box.press("Tab")

        vin_upper = vin.upper()
        invalid_format = (
            len(vin_upper) != 17
            or any(char in vin_upper for char in "IOQ")
        )

        if invalid_format:
            warnings.append(
                f"Unit {unit_number}: VIN keyed exactly as printed; "
                "format requires review. Popup wait skipped; "
                "continuing with year/make/model from the report."
            )
            return False

        if not _click_vin_popup_ok(page):
            warnings.append(
                f"Unit {unit_number}: VIN popup OK button was not found; "
                "year/make/model were keyed from the report"
            )
            return False

        decoded = _field_has_value(panel, year_selector)
        if not decoded:
            warnings.append(
                f"Unit {unit_number}: VIN popup was confirmed but Year stayed blank; "
                "year/make/model were keyed from the report"
            )
        return decoded
    except Exception as error:
        warnings.append(
            f"Unit {unit_number}: VIN handling failed ({type(error).__name__}); "
            "year/make/model were keyed from the report"
        )
        return False


def _nm_unit_tabs(section):
    """
    Return initialized NM vehicle-unit tabs.

    The anchor's ui-id is dynamically generated, so unit identity
    comes from tab order and the href-linked panel.
    """
    return section.locator(
        "li[role='tab'] > a.ui-tabs-anchor[role='presentation']"
    )


def _nm_tab_panel(section, tab, unit_number: int):
    """
    Resolve a unit tab to the actual panel referenced by its href.
    """
    href = (tab.get_attribute("href") or "").strip()

    if not href.startswith("#"):
        raise RuntimeError(
            f"NM Unit {unit_number} tab has an invalid "
            f"panel reference: {href!r}"
        )

    panel = section.locator(href)

    if panel.count() != 1:
        raise RuntimeError(
            f"NM Unit {unit_number} panel {href!r} "
            f"is missing or ambiguous."
        )

    return panel


def ensure_nm_units(page, required: int, log=None) -> None:
    """
    Create missing NM vehicle-unit tabs using the same count-and-wait
    method as CA, while allowing dynamically generated NM tab IDs.
    """
    if required < 1:
        raise ValueError("NM requires at least one extracted unit.")

    section = page.frame_locator(FRAME).locator(UNIT_SECTION)

    if section.count() != 1:
        raise RuntimeError(
            "NM vehicle-unit section missing or ambiguous."
        )

    tabs = _nm_unit_tabs(section)
    current = tabs.count()

    if current < 1:
        raise RuntimeError(
            "No NM vehicle-unit tabs found; nothing filled."
        )

    
    # The NM form's actual clickable control is the visible (+) anchor.
    # No Add Unit control is needed when enough units already exist.
    if current >= required:
        return

    # Search the vehicle SECTION, not the tab-navigation <ul>.
    # Do not use a.add-item: it may add a nested vehicle detail.
    add_button = section.locator("div.st-nav-add:visible")

    matches = add_button.count()

    if matches != 1:
        raise RuntimeError(
            "NM vehicle Add Unit control: "
            f"expected 1 visible div.st-nav-add inside "
            f"{UNIT_SECTION}, found {matches}. "
            "No Add Unit click was attempted."
        )

    while current < required:
        before = current

        if log:
            log(f"Adding NM vehicle unit {before + 1}...")

        if not add_button.is_visible():
            raise RuntimeError(
                f"NM form has {before} vehicle unit(s), "
                f"but requires {required}, and the Add Unit "
                "button is not visible."
            )

        
        add_button.scroll_into_view_if_needed(timeout=3000)
        add_button.click(timeout=5000)

        expected = before + 1

        # Same approach as CA: wait until the unit count increases.
        for _ in range(50):
            page.wait_for_timeout(200)
            current = tabs.count()
            if current > before:
                break
        else:
            raise RuntimeError(
                f"Clicked the NM Add Unit button, but Unit "
                f"{before + 1} did not appear."
            )

        # Small stabilization delay for the NM form's jQuery event handlers.
        page.wait_for_timeout(300)
        # Same approach as CA: wait until the unit count increases.
        for _ in range(50):
            page.wait_for_timeout(200)
            current = tabs.count()

            if current > before:
                break
        else:
            raise RuntimeError(
                f"Clicked the NM Add Unit button, but Unit "
                f"{before + 1} did not appear."
            )

        # One click must create exactly one vehicle unit.
        if current != before + 1:
            raise RuntimeError(
                "NM Add Unit created an unexpected number of tabs. "
                f"Before: {before}; after: {current}."
            )

        if log:
            log(f"NM vehicle unit {current} added.")

    # Validate the first required tabs and their actual linked panels.
    seen_panels = set()

    for index in range(required):
        unit_number = index + 1
        tab = tabs.nth(index)

        href = (tab.get_attribute("href") or "").strip()

        if not href.startswith("#"):
            raise RuntimeError(
                f"NM Unit {unit_number} tab has an invalid "
                f"panel reference: {href!r}"
            )

        if href in seen_panels:
            raise RuntimeError(
                f"NM Unit {unit_number} reuses panel {href!r}."
            )

        _nm_tab_panel(
            section,
            tab,
            unit_number,
        )

        seen_panels.add(href)


def _activate_nm_unit(section, number: int):
    """
    Activate an NM unit by tab order and return its linked panel.
    Retries briefly because added jQuery UI tabs initialize asynchronously.
    """
    deadline = time.monotonic() + 8.0
    last_error = None

    while time.monotonic() < deadline:
        try:
            tabs = _nm_unit_tabs(section)
            count = tabs.count()

            if number > count:
                raise RuntimeError(
                    f"only {count} NM vehicle tab(s) are currently initialized"
                )

            tab = tabs.nth(number - 1)
            href = (tab.get_attribute("href") or "").strip()

            if not href.startswith("#"):
                raise RuntimeError(
                    f"NM Unit {number} tab has no valid href yet"
                )

            panel = section.locator(href)

            if panel.count() != 1:
                raise RuntimeError(
                    f"NM Unit {number} panel {href!r} is not ready"
                )

            tab.scroll_into_view_if_needed(timeout=1000)
            tab.click(timeout=2000)
            panel.wait_for(state="visible", timeout=2000)

            selected = tab.get_attribute("aria-selected")
            hidden = panel.get_attribute("aria-hidden")

            if selected == "false" or hidden == "true":
                raise RuntimeError(
                    f"NM Unit {number} has not become active yet"
                )

            return panel

        except Exception as error:
            last_error = error
            time.sleep(0.2)

    raise RuntimeError(
        f"NM Unit {number} could not be activated after 8 seconds: "
        f"{last_error}"
    )



def fill_nm_form(
    page: Page,
    payload: dict,
    log=None,
) -> list[str]:
    warnings = []
    frame = page.frame_locator(FRAME)
    units = payload.get("units", [])

    ensure_nm_units(
        page,
        len(units),
        log=log,
    )

    # Avoid filling the same incident input twice under different payload names.
    for key, value in payload.get("incident", {}).items():
        if key in INCIDENT:
            _fill(
                frame,
                INCIDENT[key],
                value,
                f"incident.{key}",
                warnings,
            )

    section = frame.locator(UNIT_SECTION)
    
    if section.count() != 1:
        raise RuntimeError("NM unit section missing or ambiguous")

    available = _nm_unit_tabs(section).count()

    if available < len(units):
        raise RuntimeError(
            f"NM form has {available} vehicle unit tab(s), "
            f"but the report requires {len(units)}."
        )
        
    for number, unit in enumerate(units, 1):
        if log:
            log(f"Keying NM vehicle unit {number}...")

        panel = _activate_nm_unit(section, number)
        
        _fill_person(panel, OWNER, unit.get("owner", {}), "owner", warnings)
        _fill_person(panel, DRIVER, unit.get("driver", {}), "driver", warnings)
        vehicle_data = unit.get("vehicle", {})
        _fill_vehicle_radio(
            panel,
            "VehicleTowed",
            vehicle_data.get("vehicle_towed"),
            warnings,
        )
        _fill_vehicle_radio(
            panel,
            "AirBagDeployed",
            vehicle_data.get("airbag_deployed"),
            warnings,
        )

        # VIN is handled first because confirmation may populate Year/Make/Model.
        vin_start = time.perf_counter()

        decoded = _fill_nm_vin(
            page,
            panel,
            vehicle_data,
            number,
            warnings,
        )

        if log:
            log(
                f"NM Unit {number} VIN handling: "
                f"{time.perf_counter() - vin_start:.2f}s"
            )

        for key, value in vehicle_data.items():
            if key == "vin":
                continue
            if decoded and key in YEAR_MAKE_MODEL:
                continue
            if key in VEHICLE:
                _fill(
                    panel,
                    VEHICLE[key],
                    value,
                    f"unit{number}.vehicle.{key}",
                    warnings,
                )
    return warnings
