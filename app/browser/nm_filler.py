"""NM supervised filler. Never saves or submits."""
import time

from playwright.sync_api import Page
from app.browser.nm_field_mapping import FRAME, UNIT_SECTION, INCIDENT, OWNER, DRIVER, VEHICLE


def _fill_control(control, value, label, warnings):
    if value is None or str(value) == "":
        return
    try:
        if control.evaluate("e => e.tagName") == "SELECT":
            opts = control.locator("option").evaluate_all(
                "os => os.map(o => ({value:o.value, label:o.textContent.trim()}))"
            )
            match = next((o for o in opts if str(value).casefold() in
                          (o["value"].casefold(), o["label"].casefold())), None)
            if match is None:
                warnings.append(f"{label}: no exact dropdown option; skipped")
                return
            control.select_option(value=match["value"])
        else:
            control.fill(str(value), timeout=3000)
            control.press("Tab")
        actual = control.input_value()
        if actual.strip().casefold() != str(value).strip().casefold() and not (
            control.evaluate("e => e.tagName") == "SELECT"
            and actual == match["value"]
        ):
            warnings.append(f"{label}: readback differs; review")
    except Exception as exc:
        warnings.append(f"{label}: {type(exc).__name__}; review")


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

        if len(vin.upper()) != 17 or any(char in vin.upper() for char in "IOQ"):
            warnings.append(f"Unit {unit_number}: VIN was keyed as printed but may be rejected; review it")

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


def ensure_nm_units(page, required: int, log=None) -> None:
    """Create missing NM vehicle-unit tabs before filling any fields."""
    from playwright.sync_api import expect

    if required < 1:
        raise ValueError("NM requires at least one extracted unit.")

    section = page.frame_locator(FRAME).locator(UNIT_SECTION)

    if section.count() != 1:
        raise RuntimeError(
            "NM vehicle-unit section missing or ambiguous."
        )

    tabs = section.locator(
        "a.ui-tabs-anchor[href^='#tabs-']"
    )

    current = tabs.count()

    if current < 1:
        raise RuntimeError(
            "No NM vehicle-unit tabs found; nothing filled."
        )

    if current >= required:
        return

    # Scoped to vehicle units, not Other Parties.
    add_button = section.locator(
        "div.st-nav-add:visible"
    )

    if add_button.count() != 1:
        raise RuntimeError(
            "NM vehicle Add Unit button missing or ambiguous; "
            "nothing filled."
        )

    while current < required:
        if log:
            log(f"Adding NM vehicle unit {current + 1}...")

        add_button.click(timeout=5000)

        try:
            # Wait for exactly one new tab before clicking again.
            expect(tabs).to_have_count(
                current + 1,
                timeout=10000,
            )
        except AssertionError as error:
            raise RuntimeError(
                "NM Add Unit did not create exactly one new tab. "
                "Review the form before retrying; "
                "no report fields were filled."
            ) from error

        current = tabs.count()

        if log:
            log(f"NM vehicle units available: {current}")

    # Verify the numbered tabs expected by the existing filler.
    for number in range(1, required + 1):
        link = section.locator(
            f"a.ui-tabs-anchor[href='#tabs-{number}']"
        )

        if link.count() != 1:
            raise RuntimeError(
                f"NM vehicle unit {number} is missing or ambiguous; "
                "nothing filled."
            )
               
def _activate_nm_unit(section, number: int) -> None:
    """Activate one exact NM unit tab and verify its panel is active."""
    href = f"#tabs-{number}"
    tab = section.locator(
        f"a.ui-tabs-anchor[href='{href}']"
    )
    panel = section.locator(href)

    if tab.count() != 1:
        raise RuntimeError(
            f"NM Unit {number} tab is missing or ambiguous."
        )

    if panel.count() != 1:
        raise RuntimeError(
            f"NM Unit {number} panel is missing or ambiguous."
        )

    try:
        tab.first.scroll_into_view_if_needed(timeout=3000)
        tab.first.click(timeout=5000)
    except Exception:
        # jQuery UI tabs can leave an overlay over the anchor after VIN lookup.
        # Dispatch a DOM click only on the already-verified exact unit anchor.
        tab.first.dispatch_event("click")

    try:
        panel.first.wait_for(state="visible", timeout=10000)
    except Exception as error:
        raise RuntimeError(
            f"NM Unit {number} did not become active after its tab was clicked."
        ) from error

    # Verify jQuery UI's active relationship when the attributes are present.
    selected = tab.first.get_attribute("aria-selected")
    hidden = panel.first.get_attribute("aria-hidden")

    if selected == "false" or hidden == "true":
        raise RuntimeError(
            f"NM Unit {number} panel remained inactive after tab selection."
        )


def fill_nm_form(page: Page, payload: dict) -> list[str]:
    warnings = []
    frame = page.frame_locator(FRAME)
    # Avoid filling the same incident input twice under different payload names.
    for key, value in payload.get("incident", {}).items():
        if key in INCIDENT:
            _fill(frame, INCIDENT[key], value, f"incident.{key}", warnings)
    section = frame.locator(UNIT_SECTION)
    if section.count() != 1:
        raise RuntimeError("NM unit section missing or ambiguous")
    units = payload.get("units", [])
    if section.locator("a.ui-tabs-anchor[href^='#tabs-']").count() < len(units):
        raise RuntimeError("Not enough captured NM unit tabs")
    for number, unit in enumerate(units, 1):
        _activate_nm_unit(section, number)
        panel = section.locator(f"#tabs-{number}").first
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
        decoded = _fill_nm_vin(page, panel, vehicle_data, number, warnings)

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
