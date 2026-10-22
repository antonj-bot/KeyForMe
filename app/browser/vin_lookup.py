"""Shared VIN interaction. Format policy remains in app.core.vin."""
import time
from app.core.vin import get_vin_policy, should_attempt_vin_lookup

def click_popup_ok(page, selector, timeout_s=8.0):
    deadline=time.monotonic()+timeout_s
    while time.monotonic()<deadline:
        for browser_page in page.context.pages:
            if browser_page.is_closed():
                continue
            for frame in browser_page.frames:
                try:
                    button=frame.locator(selector).first
                    if button.count() and button.is_visible():
                        button.click(timeout=2000)
                        return True
                except Exception:
                    continue
        page.wait_for_timeout(200)
    return False

def field_has_value(page,panel,selector,timeout_s=3.0):
    control=panel.locator(selector).first
    deadline=time.monotonic()+timeout_s
    while time.monotonic()<deadline:
        try:
            if control.count() and control.input_value().strip():
                return True
        except Exception:
            pass
        page.wait_for_timeout(200)
    return False

def fill_vin(page,panel,vehicle,number,spec,warnings):
    vin=str(vehicle.get("vin") or "").strip()
    if not vin:
        return False
    vin_selector=spec.vehicle.get("vin")
    year_selector=spec.vehicle.get("year")
    if not vin_selector or not year_selector:
        warnings.append(f"Unit {number}: VIN/Year selectors not configured")
        return False
    controls=panel.locator(vin_selector)
    if controls.count()!=1:
        warnings.append(f"Unit {number}: VIN field missing or ambiguous")
        return False
    try:
        controls.first.fill(vin,timeout=spec.field_timeout_ms)
        controls.first.press("Tab",timeout=spec.field_timeout_ms)
        if not should_attempt_vin_lookup(vin,policy=get_vin_policy(spec.state),
                                         unit_number=number,warn=warnings.append):
            return False
        if not click_popup_ok(page,spec.popup_ok):
            warnings.append(f"Unit {number}: VIN confirmation not found; using report year/make/model")
            return False
        decoded=field_has_value(page,panel,year_selector)
        if not decoded:
            warnings.append(f"Unit {number}: VIN confirmed but Year blank; using report year/make/model")
        return decoded
    except Exception as error:
        warnings.append(f"Unit {number}: VIN handling {type(error).__name__}; using report year/make/model")
        return False
