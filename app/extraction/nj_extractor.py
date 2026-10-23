"""New Jersey NJTR-1 extraction.

Flow
  1. Free triage: drop blank pages and exact duplicate pages (app/extraction/nj_pages.py).
  2. Classify each remaining page as UNIT / NARRATIVE / OTHER (free text-layer check first,
     otherwise a small AI call on the page header). A failed classification stops the
     extraction rather than silently skipping a page.
  3. Every UNIT page is read twice, concurrently: a full extraction (header, up to two
     vehicle blocks, occupants A-D, field 135) and a tiny inventory of the printed vehicle
     numbers. Every NARRATIVE page is read for occupants E-J, "Other Descriptions",
     "Additional Citations" and insurance statements.
  4. Completeness gate: the vehicle numbers inventoried on a page must all appear in its
     extraction. Missing ones get ONE targeted recovery; still missing -> stop.
  5. Assemble one raw report dict. app/keying/nj_rules.py turns it into the keying payload.

The AI only transcribes. It never applies keying rules.
"""
from __future__ import annotations

import base64
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pymupdf

from app.core.completeness import IncompleteExtractionError
from app.extraction.nj_pages import usable_pages
from app.nj_models import (
    NJInventory,
    NJNarrativePage,
    NJPageKind,
    NJUnitPage,
    NJVehicleRaw,
)

KEY_WHAT_YOU_SEE = (
    "KEY WHAT YOU SEE. Transcribe values exactly as printed, including misspellings, "
    "capitalization, punctuation, leading zeros and VIN characters. Never correct, "
    "normalize, guess or invent a value. A dash, a row of dashes or a blank box means "
    "no value: return null (an empty list for lists). Do not copy values between "
    "vehicles or between people. Put anything unreadable or doubtful in warnings."
)

CLASSIFY_PROMPT = (
    "This is the top of one page of a New Jersey police report PDF. Return exactly one kind. "
    "UNIT = a 'New Jersey Police Crash Investigation Report' form page with the vehicle "
    "blocks (printed 'Veh. #' boxes, driver, owner and vehicle sections). "
    "NARRATIVE = a page that has the '145. Crash Description/Narrative' box, or a "
    "'Motor Vehicle Crash Description' continuation page of narrative text. "
    "OTHER = anything else: blank separator pages, diagram-only pages, cover sheets, "
    "photographs, attachments. Use the printed titles only."
)

INVENTORY_PROMPT = (
    "Read only the printed vehicle numbers on this NJTR-1 crash report page: the box "
    "'23. Veh. #' (left vehicle block) and the box '53. Veh. #' (right vehicle block). "
    "Return the distinct positive vehicle numbers of POPULATED blocks (a block with a "
    "vehicle number or any vehicle, VIN, plate or driver data). Ignore empty blocks full "
    "of dashes. Set uncertain=true if a number is unreadable, contradictory or a populated "
    "block has no number. Do not return names, addresses or any other value."
)

UNIT_PAGE_PROMPT = (
    "This is one page of a New Jersey Police Crash Investigation Report, form NJTR-1 "
    "(Rev. 01/22). The page holds up to TWO vehicles side by side: the LEFT vehicle block "
    "uses printed fields 23-52 ('23. Veh. #') and the RIGHT vehicle block uses fields 53-82 "
    "('53. Veh. #'). Return every POPULATED vehicle block as one entry in vehicles; an empty "
    "block full of dashes is not returned. "
    "INCIDENT HEADER (same on every page): case_number = field 1; police_dept = the name in "
    "field 2 'Police Dept. of' (not the Code box); crash_date = field 4; crash_time = field 6 "
    "(as printed, e.g. 2058 or '16 01'); road_name = field 10 'Crash Occurred On' road name; "
    "cross_road = field 17 'Cross Road Name/Route No.'; speed_limit = field 11; "
    "latitude = field 21; longitude = field 22. "
    "MARGIN CODES: the narrow columns on the left and right page edges hold small numbered "
    "boxes, each with a 1-2 digit code. weather_code = the code in margin box 103; "
    "road_condition_code = the code in margin box 102. For the LEFT vehicle: damage_new = box "
    "130, damage_old = box 131, contributing_codes = boxes 118a and 118b. For the RIGHT "
    "vehicle: damage_new = box 132, damage_old = box 133, contributing_codes = boxes 119a "
    "and 119b. Set form_shows_box_134 = true only if the right margin prints a box numbered "
    "134. Read each code from beside its own number; never take it from a neighbouring box. "
    "EACH VEHICLE: number = field 23/53; side = LEFT or RIGHT; parked and hit_and_run = true "
    "only if that vehicle's own checkbox has an X; policy_number = field 24/54; ins_code = "
    "'NJ Ins. Code' field 25/55 (an asterisk is returned as '*'). "
    "Driver: first, middle (the Initial box), last, dob (field 33/63), license number, "
    "license state, street (Number & Street), city, state, zip (read City, State and Zip "
    "separately; if one box holds 'City, ST 12345' return it in city), alcohol_given = "
    "No, Yes or Refused (whichever box has an X in field 48/78). "
    "Owner: owner_same_as_driver = true only if the 'Same As Driver' box has an X; "
    "owner_name = the owner name printed in the owner name area, first-initial-last in the "
    "printed order, even when 'Same As Driver' is marked (null if blank); "
    "owner_is_company = true when the printed name is a business, not a person; owner street, "
    "city, state, zip. "
    "Vehicle: vin, year, make, model, plate, plate_state exactly as printed (read the VIN "
    "character by character; never force 17 characters). "
    "Removal: set driven, left_at_scene, towed_disabled, towed_disabled_and_impounded and "
    "towed_impounded to true only for boxes with an X. "
    "Charges: the bottom rows 'Charge' (fields 136, 138, 140, 142) with the vehicle number in "
    "their 'Oper.' box; return each charge text exactly as printed (join a charge that wraps "
    "onto two lines; leave out the summons numbers) in charges of the vehicle named in Oper. "
    "OCCUPANTS: the table with columns 83-95 and rows A-D. Return one entry per row that has "
    "any value. Columns: 83 vehicle (a number, or P, B or O), 84 seating position, 85 "
    "ejection, 86 injury, 87 age, 92 safety equipment available, 93 safety equipment used, "
    "94 airbag, 95 hospital. name = the person's name only; address = the rest of the "
    "name-and-address cell. A person's name may be written 'LAST, FIRST M' - return it as printed. "
    "FIELD 135 'Damage To Other Property': return property_owners only when Yes is marked: "
    "one entry per owner named, with name and address as printed and no description words "
    "(mailbox, fence, transformer, lawn, barrier...). If only an address is given, return it "
    "with name null. Set is_company true for a business or agency. Do not return other "
    "vehicles that are already vehicle blocks of this report. "
    + KEY_WHAT_YOU_SEE
)

NARRATIVE_PROMPT = (
    "This is a narrative page of a New Jersey NJTR-1 crash report (it may also carry the "
    "continuation of the occupant table and a diagram). Return: "
    "occupants = rows E to J of the occupant table (columns 83-95, name and address) that "
    "have any value; skip rows of dashes. Columns: 83 vehicle (number, or P, B or O), 84 "
    "seating position, 85 ejection, 86 injury, 87 age, 92 safety equipment available, 93 "
    "safety equipment used, 94 airbag, 95 hospital; name = name only; address = the rest. "
    "other_descriptions = every line under '***Other Descriptions***' as vehicle (the leading "
    "number, e.g. 01 -> 1), text (the description without the leading number and without the "
    "trailing 'Field NN') and field (the NN). "
    "additional_citations = every line under '***Additional Citations***' as vehicle (the "
    "leading number) and text (the citation exactly as printed, without the summons number). "
    "insurance_statements = only sentences in the narrative that name the insurance company "
    "of a specific vehicle: vehicle number and the company name as written. "
    "Do not summarise the narrative and do not return anything else. " + KEY_WHAT_YOU_SEE
)

RECOVERY_SUFFIX = (
    " RECOVERY: a previous read of this page missed vehicle number(s) {missing}. Return ONLY "
    "the vehicle block(s) printed with those numbers (and their own occupant rows and "
    "charges); the incident header may be repeated. If a requested vehicle cannot be read, "
    "omit it and say why in warnings. Never create a vehicle to satisfy this request."
)

_TEXT_UNIT = ("23. VEH", "24. POLICY NO", "53 VEH")
_TEXT_NARRATIVE = ("CRASH DESCRIPTION", "145. CRASH")


# ------------------------------------------------------------------ AI plumbing (patched in tests)
def _parse(model: str, prompt: str, schema, images: list[str], labels: list[str] | None = None):
    from app.ai.runtime import get_ai_client

    content = []
    for number, image in enumerate(images):
        if labels:
            content.append({"type": "input_text", "text": labels[number]})
        content.append({"type": "input_image", "image_url": image, "detail": "high"})
    return get_ai_client().parse(
        model=model, instructions=prompt, content=content, schema=schema, reasoning_effort="none")


def _jpeg(pix) -> str:
    return "data:image/jpeg;base64," + base64.b64encode(pix.tobytes("jpeg", jpg_quality=85)).decode()


def _page_image(doc, index: int, dpi: int = 200) -> str:
    return _jpeg(doc.load_page(index).get_pixmap(dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False))


def _header_image(doc, index: int) -> str:
    page = doc.load_page(index)
    clip = pymupdf.Rect(0, 0, page.rect.width, page.rect.height * 0.25)
    return _jpeg(page.get_pixmap(dpi=160, clip=clip, colorspace=pymupdf.csGRAY, alpha=False))


# ------------------------------------------------------------------ classification
def classify_pages(doc, kept: list[int], model: str) -> dict[int, str]:
    kinds: dict[int, str] = {}
    jobs: list[int] = []
    for index in kept:
        text = " ".join(doc.load_page(index).get_text().upper().split())
        if any(marker in text for marker in _TEXT_UNIT):
            kinds[index] = "UNIT"
        elif any(marker in text for marker in _TEXT_NARRATIVE):
            kinds[index] = "NARRATIVE"
        else:
            jobs.append(index)
    if jobs:
        with ThreadPoolExecutor(max_workers=min(len(jobs), 6)) as pool:
            futures = {
                i: pool.submit(_parse, model, CLASSIFY_PROMPT, NJPageKind,
                               [_header_image(doc, i)], [f"PDF PAGE {i + 1}:"])
                for i in jobs
            }
            for index, future in futures.items():
                try:
                    kinds[index] = future.result().kind
                except Exception as error:
                    raise RuntimeError(
                        f"Could not classify PDF page {index + 1}. "
                        "Extraction stopped to prevent missing report data."
                    ) from error
    return kinds


# ------------------------------------------------------------------ small helpers
def _clean(value):
    if value is None:
        return ""
    return " ".join(str(value).split())


def _vehicle_numbers(page: NJUnitPage) -> list[int]:
    return [v.number for v in page.vehicles if v.number is not None]


def _vehicle_dict(v: NJVehicleRaw, new_form: bool) -> dict:
    return {
        "number": v.number, "parked": v.parked, "hit_and_run": v.hit_and_run,
        "policy_number": _clean(v.policy_number), "ins_code": _clean(v.ins_code),
        "narrative_insurance": "", "narrative_policy": "",
        "driver": {
            "first": _clean(v.driver_first), "middle": _clean(v.driver_middle), "last": _clean(v.driver_last),
            "dob": _clean(v.driver_dob), "dl_number": _clean(v.driver_license_number),
            "dl_state": _clean(v.driver_license_state), "alcohol_given": _clean(v.alcohol_given),
            "address_1": _clean(v.driver_address_1), "address_2": "", "city": _clean(v.driver_city),
            "state": _clean(v.driver_state), "zip": _clean(v.driver_zip),
        },
        "owner": {
            "same_as_driver": v.owner_same_as_driver, "name": _clean(v.owner_name),
            "is_company": v.owner_is_company, "address_1": _clean(v.owner_address_1),
            "city": _clean(v.owner_city), "state": _clean(v.owner_state), "zip": _clean(v.owner_zip),
        },
        "vehicle": {
            "vin": _clean(v.vin), "year": _clean(v.year), "make": _clean(v.make), "model": _clean(v.model),
            "plate": _clean(v.plate), "plate_state": _clean(v.plate_state),
        },
        "removal": {
            "driven": v.driven, "left_at_scene": v.left_at_scene, "towed_disabled": v.towed_disabled,
            "towed_disabled_impounded": v.towed_disabled_and_impounded, "towed_impounded": v.towed_impounded,
        },
        "charges": [_clean(c) for c in v.charges if _clean(c)],
        "damage": {"new": _clean(v.damage_new), "old": _clean(v.damage_old), "new_form": new_form},
        "contributing": [_clean(c) for c in v.contributing_codes if _clean(c)],
    }


def _occupant_dict(o) -> dict:
    return {
        "row": _clean(o.row), "vehicle": _clean(o.vehicle), "position": _clean(o.position),
        "ejection": _clean(o.ejection), "injury": _clean(o.injury), "age": _clean(o.age),
        "safety_available": _clean(o.safety_available), "safety_used": _clean(o.safety_used),
        "airbag": _clean(o.airbag), "hospital": _clean(o.hospital),
        "name": _clean(o.name), "address_line": _clean(o.address),
    }


def _occupant_has_data(d: dict) -> bool:
    keys = ("vehicle", "position", "ejection", "injury", "age", "safety_available",
            "safety_used", "airbag", "hospital", "name", "address_line")
    return any(re.search(r"[A-Za-z0-9]", d[k]) for k in keys)


# ------------------------------------------------------------------ assembly
def assemble(unit_pages: list[tuple[int, NJUnitPage]], narrative_pages: list[tuple[int, NJNarrativePage]]) -> dict:
    notes: list[str] = []
    raw: dict = {k: "" for k in (
        "case_number", "police_dept", "crash_date", "crash_time", "road_name", "cross_road",
        "speed_limit", "latitude", "longitude", "weather_code", "road_condition_code")}

    for index, page in unit_pages:                         # incident header: first value wins, conflicts are noted
        for key in raw:
            new = _clean(getattr(page, key))
            if not new:
                continue
            if not raw[key]:
                raw[key] = new
            elif raw[key].upper() != new.upper():
                notes.append(f"Page {index + 1}: {key} reads '{new}' but an earlier page read '{raw[key]}'; kept the first")
        notes.extend(f"Page {index + 1}: {w}" for w in page.warnings)

    vehicles: dict[int, dict] = {}
    order: list[int] = []
    next_free = 1
    for index, page in unit_pages:
        for v in page.vehicles:
            number = v.number
            if number is None:                              # General SOP: key units in the order presented
                while next_free in vehicles:
                    next_free += 1
                number = next_free
                notes.append(f"Page {index + 1}: a vehicle block has no printed number; keyed as unit {number}")
            data = _vehicle_dict(v, page.form_shows_box_134)
            data["number"] = number
            if number in vehicles:
                if vehicles[number]["vehicle"]["vin"] != data["vehicle"]["vin"] or \
                        vehicles[number]["driver"]["last"] != data["driver"]["last"]:
                    notes.append(f"Page {index + 1}: vehicle {number} appears twice with different data; kept the first")
                continue
            vehicles[number] = data
            order.append(number)

    occupants, seen = [], set()
    for index, page in unit_pages:
        for o in page.occupants:
            d = _occupant_dict(o)
            key = (d["vehicle"], d["position"], d["name"].upper(), d["row"])
            if _occupant_has_data(d) and key not in seen:
                seen.add(key)
                occupants.append(d)
    properties, prop_seen = [], set()
    for index, page in unit_pages:
        for p in page.property_owners:
            name, address = _clean(p.name), _clean(p.address)
            if (name or address) and (name.upper(), address.upper()) not in prop_seen:
                prop_seen.add((name.upper(), address.upper()))
                properties.append({"name": name, "address_line": address, "is_company": p.is_company})

    for index, page in narrative_pages:                     # rows E-J, citations, narrative values
        notes.extend(f"Page {index + 1}: {w}" for w in page.warnings)
        for o in page.occupants:
            d = _occupant_dict(o)
            key = (d["vehicle"], d["position"], d["name"].upper(), d["row"])
            if _occupant_has_data(d) and key not in seen:
                seen.add(key)
                occupants.append(d)
        for item in page.other_descriptions:
            target = vehicles.get(item.vehicle) if item.vehicle is not None else None
            field = re.sub(r"\D", "", item.field or "")
            if target is None or not _clean(item.text):
                if _clean(item.text):
                    notes.append(f"Page {index + 1}: description '{_clean(item.text)}' (field {field or '?'}) could not be tied to a vehicle")
                continue
            if field in ("25", "55") and not target["narrative_insurance"]:
                target["narrative_insurance"] = _clean(item.text)
            elif field in ("24", "54") and not target["narrative_policy"]:
                target["narrative_policy"] = _clean(item.text)
        for item in page.additional_citations:
            target = vehicles.get(item.vehicle) if item.vehicle is not None else None
            if target is None:
                if _clean(item.text):
                    notes.append(f"Page {index + 1}: citation '{_clean(item.text)}' could not be tied to a vehicle")
                continue
            if _clean(item.text) and _clean(item.text) not in target["charges"]:
                target["charges"].append(_clean(item.text))
        for item in page.insurance_statements:
            target = vehicles.get(item.vehicle) if item.vehicle is not None else None
            if target is not None and _clean(item.text) and not target["narrative_insurance"]:
                target["narrative_insurance"] = _clean(item.text)

    numbers = set(vehicles)
    for d in occupants:
        v = d["vehicle"]
        if v.isdigit() and int(v) not in numbers:
            notes.append(f"Occupant row {d['row'] or '?'} refers to vehicle {int(v)}, which has no vehicle block")

    raw.update(vehicles=[vehicles[n] for n in order], occupants=occupants,
               property_owners=properties, notes=notes)
    return raw


# ------------------------------------------------------------------ main entry
def extract_nj(pdf_path: Path, model: str = "gpt-6-luna") -> dict:
    with pymupdf.open(pdf_path) as doc:
        kept, dropped = usable_pages(doc)
        for index, reason in dropped.items():
            print(f"  NJ page {index + 1} skipped: {reason}")
        if not kept:
            raise ValueError("The NJ report has no usable pages.")
        kinds = classify_pages(doc, kept, model)
        print("  NJ pages: " + ", ".join(f"{i + 1}={kinds[i]}" for i in kept))
        unit_idx = [i for i in kept if kinds[i] == "UNIT"]
        narr_idx = [i for i in kept if kinds[i] == "NARRATIVE"]
        if not unit_idx:
            raise ValueError("No NJTR-1 vehicle page found; nothing should be keyed.")
        images = {i: _page_image(doc, i) for i in unit_idx}
        narr_images = {i: _page_image(doc, i, dpi=170) for i in narr_idx}

    with ThreadPoolExecutor(max_workers=min(2 * len(unit_idx) + len(narr_idx), 8)) as pool:
        unit_f = {i: pool.submit(_parse, model, UNIT_PAGE_PROMPT, NJUnitPage, [images[i]], [f"PDF PAGE {i + 1}:"])
                  for i in unit_idx}
        inv_f = {i: pool.submit(_parse, model, INVENTORY_PROMPT, NJInventory, [images[i]], [f"PDF PAGE {i + 1}:"])
                 for i in unit_idx}
        narr_f = {i: pool.submit(_parse, model, NARRATIVE_PROMPT, NJNarrativePage, [narr_images[i]], [f"PDF PAGE {i + 1}:"])
                  for i in narr_idx}
        unit_pages = {i: f.result() for i, f in unit_f.items()}
        inventories = {i: f.result() for i, f in inv_f.items()}
        narrative = {i: f.result() for i, f in narr_f.items()}

    for i in unit_idx:                                      # completeness gate, one recovery per page
        inventory = inventories[i]
        if inventory.uncertain:
            raise IncompleteExtractionError(f"NJ page {i + 1}: vehicle numbers are uncertain; filling cancelled for review.")
        expected = set(inventory.vehicle_numbers)
        missing = expected - set(_vehicle_numbers(unit_pages[i]))
        if not missing:
            continue
        print(f"NJ completeness: page {i + 1} is missing vehicle(s) {sorted(missing)}; targeted recovery started.")
        prompt = UNIT_PAGE_PROMPT + RECOVERY_SUFFIX.format(missing=", ".join(str(n) for n in sorted(missing)))
        recovery = _parse(model, prompt, NJUnitPage, [images[i]], [f"PDF PAGE {i + 1}:"])
        got = {v.number: v for v in recovery.vehicles if v.number in missing}
        if len(got) != len([v for v in recovery.vehicles if v.number in missing]):
            raise IncompleteExtractionError(f"NJ page {i + 1}: recovery returned duplicate vehicles; filling cancelled.")
        if set(missing) - set(got):
            raise IncompleteExtractionError(
                f"NJ page {i + 1}: vehicle(s) {sorted(set(missing) - set(got))} still missing after one recovery; filling cancelled.")
        page = unit_pages[i]
        page.vehicles = list(page.vehicles) + list(got.values())
        known = {(o.row, o.vehicle, o.name) for o in page.occupants}
        page.occupants = list(page.occupants) + [o for o in recovery.occupants if (o.row, o.vehicle, o.name) not in known]
        print(f"NJ completeness: page {i + 1} recovered vehicle(s) {sorted(got)}.")

    return assemble([(i, unit_pages[i]) for i in unit_idx], [(i, narrative[i]) for i in narr_idx])
