"""Single filling workflow for verified state adapters. Never Save or Submit."""
import time
from app.core.tabs import ensure_tabs, activate_tab
from app.browser.controls import fill_field, fill_person, fill_radio
from app.browser.vin_lookup import fill_vin
from app.browser.state_forms import get_form_spec
from app.core.driver_rules import apply_hit_and_run_name

YEAR_MAKE_MODEL=("year","make","model")

def fill_form(page,payload,*,state,log=None):
    spec=get_form_spec(state)
    warnings=[]
    # General SOP, all states: a hit-and-run vehicle with no driver name gets HIT AND RUN as the last name.
    payload,hit_and_run_units=apply_hit_and_run_name(payload)
    if log:
        for number in hit_and_run_units:
            log(f"Unit {number}: no driver name on a hit-and-run vehicle; keying HIT AND RUN as the last name")
    units=payload.get("units",[])
    if not units:
        raise ValueError("No vehicle units available to fill.")
    # NM's notes gate remains in app.states.nm.fill, before this engine is called.
    others=payload.get("other_parties",[])
    if others and not spec.other_section:
        raise ValueError(f"{spec.state}: Other Parties filling is not configured; nothing filled.")
    frame=page.frame_locator(spec.frame)
    section=frame.locator(spec.unit_section)
    def on_dialog(dialog):
        # Preserve the existing CA native-dialog behavior. No new states opt in implicitly.
        dialog.accept()
    if spec.accept_native_dialogs:
        page.on("dialog",on_dialog)
    try:
        # Retain NM's preflight-before-incident and CA's incident-first order.
        if spec.units_before_incident:
            ensure_tabs(page,section,len(units),spec=spec.tabs,log=log,label=f"{spec.state} vehicle unit")
        for key,value in payload.get("incident",{}).items():
            fill_field(frame,spec.incident.get(key),value,f"incident.{key}",spec,warnings)
        if not spec.units_before_incident:
            ensure_tabs(page,section,len(units),spec=spec.tabs,log=log,label=f"{spec.state} vehicle unit")
        for number,unit in enumerate(units,1):
            if log:
                log(f"Keying {spec.state} vehicle unit {number}...")
            panel=activate_tab(section,number,spec=spec.tabs,label=f"{spec.state} unit")
            for role in spec.person_order:
                fill_person(panel,getattr(spec,role),unit.get(role,{}),role,spec,warnings)
            vehicle=unit.get("vehicle",{})
            if spec.radios_before_vin:
                for key in spec.radio_fields:
                    fill_radio(panel,key,vehicle.get(key),spec,warnings)
            started=time.perf_counter()
            decoded=fill_vin(page,panel,vehicle,number,spec,warnings)
            if log:
                log(f"{spec.state} Unit {number} VIN handling: {time.perf_counter()-started:.2f}s")
            for key,value in vehicle.items():
                if key=="vin" or (decoded and key in YEAR_MAKE_MODEL):
                    continue
                if key in spec.radio_rows or key in spec.radio_fields:
                    if not spec.radios_before_vin:
                        fill_radio(panel,key,value,spec,warnings)
                else:
                    fill_field(panel,spec.vehicle.get(key),value,f"unit{number}.vehicle.{key}",spec,warnings)
        if others:
            other_section=frame.locator(spec.other_section)
            ensure_tabs(page,other_section,len(others),spec=spec.tabs,log=log,label="other party")
            for number,other in enumerate(others,1):
                panel=activate_tab(other_section,number,spec=spec.tabs,label="other party")
                role=other.get("role","")
                type_code=spec.person_types.get(role,"")
                if type_code:
                    fill_field(panel,spec.other.get("person_type"),type_code,"other.person_type",spec,warnings)
                else:
                    warnings.append("other.person_type: no configured role mapping; review")
                if role not in {"WITNESS","BICYCLIST","PEDALCYCLIST"}:
                    fill_field(panel,spec.other.get("unit_number"),other.get("party_number"),"other.unit_number",spec,warnings)
                for key in spec.other_keys:
                    if role=="WITNESS" and key in ("injury_code","safety_equipment","ejected","taken_to"):
                        continue
                    fill_field(panel,spec.other.get(key),other.get(key),f"other.{key}",spec,warnings)
    finally:
        if spec.accept_native_dialogs:
            page.remove_listener("dialog",on_dialog)
    return warnings
