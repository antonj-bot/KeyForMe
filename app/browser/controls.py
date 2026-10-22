"""Shared controls. Matching and blur behavior are explicit form settings."""
def fill_control(control, value, label, spec, warnings):
    if value is None or str(value) == "":
        return
    text = str(value)
    try:
        metadata = control.evaluate("""e => ({tag:e.tagName, options:e.tagName==='SELECT'
            ? Array.from(e.options,o=>({value:o.value,label:o.textContent.trim()})):[]})""")
        if metadata["tag"] == "SELECT":
            wanted = text.strip().upper()
            options = metadata["options"]
            match = next((o for o in options if wanted in
                          (o["value"].upper(), o["label"].upper())), None)
            if match is None and spec.dropdown_prefix_codes:
                match = next((o for o in options if any(o["label"].upper().startswith(wanted+s)
                              for s in (" ", "-", "."))), None)
            if match is None:
                warnings.append(f"{label}: no approved dropdown match; skipped")
                return
            control.select_option(value=match["value"], timeout=spec.field_timeout_ms)
            retained = control.input_value() == match["value"]
        else:
            control.fill(text, timeout=spec.field_timeout_ms)
            if spec.tab_after_text:
                control.press("Tab", timeout=spec.field_timeout_ms)
            retained = control.input_value().strip().casefold() == text.strip().casefold()
        if not retained:
            warnings.append(f"{label}: readback differs; review")
    except Exception as error:
        warnings.append(f"{label}: {type(error).__name__}; review")

def fill_field(scope, selector, value, label, spec, warnings):
    if not selector or value in (None, ""):
        return
    controls = scope.locator(selector)
    if controls.count() != 1:
        warnings.append(f"{label}: expected one field, found {controls.count()}; skipped")
        return
    fill_control(controls.first, value, label, spec, warnings)

def check_field(scope, selector, enabled, label, spec, warnings, index=0):
    if not selector:
        warnings.append(f"{label}: checkbox selector not configured")
        return
    control = scope.locator(selector).nth(index)
    try:
        if not control.count():
            raise RuntimeError("Checkbox missing")
        if control.is_checked() != enabled:
            control.click(timeout=spec.field_timeout_ms)
            control.page.wait_for_timeout(300)
        if control.is_checked() != enabled:
            raise RuntimeError("Checkbox did not retain value")
    except Exception as error:
        warnings.append(f"{label}: {type(error).__name__}; review")

def fill_person(panel, mapping, data, role, spec, warnings):
    for key, value in data.items():
        selector = mapping.get(key)
        if not selector or value in (None, "") or key in spec.checkbox_fields or key == "cited":
            continue
        controls = panel.locator(selector)
        count = controls.count()
        if spec.strict_person_pairs:
            if count == 2:
                index = 0 if role == "owner" else 1
            elif count == 1 and key not in spec.owner:
                index = 0
            else:
                warnings.append(f"{role}.{key}: separate person controls missing or ambiguous; skipped")
                continue
        else:
            if count == 0:
                warnings.append(f"{role}.{key}: field missing; skipped")
                continue
            index = 1 if role == "driver" and count > 1 else 0
        fill_control(controls.nth(index), value, f"{role}.{key}", spec, warnings)
    if spec.cited and data.get("cited") in ("YES", "NO"):
        key = "cited_yes" if data["cited"] == "YES" else "cited_no"
        check_field(panel,mapping.get(key),True,f"{role}.cited",spec,warnings)
    for key in spec.checkbox_fields:
        if data.get(key) and mapping.get(key):
            check_field(panel,mapping[key],True,f"{role}.{key}",spec,warnings,
                        index=1 if role == "driver" else 0)

def fill_radio(panel, key, raw, spec, warnings):
    if raw is None or not str(raw).strip():
        return
    value = str(raw).strip().upper()
    try:
        if key in spec.radio_fields:
            choices={"YES":"1","Y":"1","1":"1","NO":"0","N":"0","0":"0",
                     "NA":"","N/A":"","NOT APPLICABLE":""}
            if value not in choices:
                raise ValueError("Unknown radio value")
            name=spec.radio_fields[key]
            controls=panel.locator(f"input[type='radio'][id^='Vehicle_{name}-'][value='{choices[value]}']")
            if controls.count()!=1:
                raise RuntimeError("Radio missing or ambiguous")
            control=controls.first
        else:
            label={"YES":"Yes","NO":"No","NA":"NA"}.get(value)
            if not label:
                return
            row=panel.locator(f"tr:visible:has-text('{spec.radio_rows[key]}')").last
            controls=row.get_by_label(label,exact=True)
            if not controls.count():
                controls=row.locator(f"input[type=radio][value='{label}' i]")
            if not controls.count():
                raise RuntimeError("Radio missing")
            control=controls.first
        control.check(timeout=3000)
        if not control.is_checked():
            raise RuntimeError("Radio not retained")
    except Exception as error:
        warnings.append(f"vehicle.{key}: {type(error).__name__}; review")
