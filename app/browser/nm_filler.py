"""NM mock filler; no Save/Submit or automatic VIN popup acceptance."""
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
        link = section.locator(f"a.ui-tabs-anchor[href='#tabs-{number}']")
        if link.count() != 1:
            raise RuntimeError(f"Unit {number} tab missing")
        link.click()
        panel = section.locator(f"#tabs-{number}")
        panel.wait_for(state="visible", timeout=5000)
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
        for key, value in vehicle_data.items():
            if key in VEHICLE:
                _fill(panel, VEHICLE[key], value, f"unit{number}.vehicle.{key}", warnings)
        if vehicle_data.get("vin"):
            warnings.append(f"Unit {number}: VIN popup must be reviewed manually on live form")
    return warnings
