"""NM approved text-entry mappings. Unknown selections leave the field blank."""

def _normalize(raw):
    return " ".join(str(raw or "").upper().split())


def _options(text):
    return {_normalize(line): _normalize(line) for line in text.splitlines() if line.strip()}


WEATHER = _options("""
CLEAR
Blowing Sand, Soil, Dirt
Blowing Snow
Cloudy
Dust
Fog, Smog, Smoke
Freezing Rain or Freezing Drizzle
Other
Raining
Severe Crosswind
Sleet or Hail
Snowing
Wind
""")
FHE = _options("""
Collision w/ Motor Vehicle
Collision w/Other Non-Fixed Object
Collision w/ Person
Collision w/Animal
Collision w/Fixed Object
Non-Collision
Other
Other N-Col
Other Object
Other Vehicle
Overturned
Parked Vehicle
Pedalcyclist
Pedestrian
R.R. Train
Rollover
Vehicle on Other Rdwy
""")
LIGHTING = _options("""
Dark-Lighted
Dark-Not Lighted
Dark-Unknown Lighting
Dawn
Daylight
Dusk
Other
Other and not stated
Unknown or Not Reported
""")
INTERSECTION = _options("""
Five-Point or More
Four-Way
L Int
Not an Intersection
Roundabout
T Int
Traffic Circle
Y Int
""")
INJURY = {code: code for code in ("A", "B", "C", "K", "O")}
INJURY.update({
    "A SUSPECTED SERIOUS INJURY": "A",
    "B MINOR INJURY": "B",
    "C COMPLAINT OF INJURY (BUT NOT VISIBLE)": "C",
    "K KILLED": "K",
    "O NO APPARENT INJURY": "O",
})
# Only readable, previously transcribed seating entries; obscured entries omitted.
SEATING_LABELS = {
    "BA": "Baby In Arms", "BP": "Bus Passengers", "CF": "Center Front",
    "CM": "Camper Or Truck", "CR": "Center Rear", "CT": "Center Third Seat",
    "EX": "Riding on Motor Vehicle Exterior", "FC": "Center Fourth Seat",
    "FL": "Left Fourth Seat", "FR": "Right Fourth Seat", "FS": "Fourth In Seat",
    "FV": "Fell From Vehicle", "JP": "Jumped From Vehicle", "LF": "Left Front",
    "LR": "Left Rear", "LS": "Lap Sitter", "LT": "Left Third Seat",
    "MD": "Motorcycle Driver", "MH": "Motor home", "MP": "Motorcycle Passenger",
    "NA": "Not Applicable", "PC": "Pedal cyclist", "PD": "Pedestrian",
    "PP": "Pedalcyclist Passenger", "RF": "Right Front", "RR": "Right Rear",
    "RT": "Right Third Seat", "SS": "Semi Sleeper", "TB": "Truck Bed",
    "TD": "On Towed Device", "TO": "Trailer Occupants",
    "UN": "Unknown Seat Position", "VR": "Rear of Van",
}
SEATING = {}
for code, label in SEATING_LABELS.items():
    for alias in (code, label, f"{code} {label}"):
        SEATING[_normalize(alias)] = code

FACTORS = _options("""
Animal(s) in roadway
Avoid no contact - other
Avoid no contact - vehicle
Backup - prior to crash
Backup - prior to incident
Cell Phone
Coupling device (hitch, chains)
Debris
Defective Steering
Defective Tires
Disregarded traffic signal
Driver distracted by other activity
Driver distracted by passenger
Driver distracted by talking on cell phone
Driver distracted by talking on hand free device
Driver distracted by texting
Driver inattention
Driverless moving vehicle
Drove left of center
Excessive Speed
Exhaust System
Failed to yield - emergency veh(s)
Failed to yield - police vehicle(s)
Failed to yield right-of-way
Following too closely
High speed pursuit
Improper Lane change
Improper backing
Improper overtaking
Inadequate brakes
Lights (head, signal, tail)
Low Visibility due to glare
Low Visibility due to smoke
Made improper turn
Mirrors
None
Obstruction in road
Other No driver error
Other improper driving
Other mech. Defect
Other visual obstruction(s)
Passed stop sign
Pedestrian error
Road defect
Road surface condition
Speed too fast for conditions
Suspension
Texting
Traffic Congestion
Traffic control not functioning
Under influence of alcohol
Under the influence of drugs or medication
Vehicle Skidded Before Brake
Weather conditions
Wheels
Windows/Windshield
Wipers
""")
WEATHER["00 CLEAR"] = "CLEAR"
FHE.update({"COLLISION W/MOTOR VEHICLE": "COLLISION W/ MOTOR VEHICLE", "COLLISION W/PERSON": "COLLISION W/ PERSON"})
INTERSECTION.update({
    "FIVE POINT OR MORE": "FIVE-POINT OR MORE",
    "5 POINT OR MORE": "FIVE-POINT OR MORE",
    "FOUR WAY": "FOUR-WAY", "FOUR-WAY INTERSECTION": "FOUR-WAY",
    "4 WAY INTERSECTION": "FOUR-WAY",
    "L-INTERSECTION": "L INT", "L INTERSECTION": "L INT",
    "T-INTERSECTION": "T INT", "T INTERSECTION": "T INT",
    "Y-INTERSECTION": "Y INT", "Y INTERSECTION": "Y INT",
})
FACTORS["NO DRIVER ERROR"] = "OTHER NO DRIVER ERROR"
NM_DROPDOWNS = {
    "weather": WEATHER, "first_harmful_event": FHE, "lighting": LIGHTING,
    "intersection_type": INTERSECTION, "injury_code": INJURY,
    "seating_position": SEATING, "apparent_contributing_factors": FACTORS,
}


def nm_dropdown_value(field, raw, warnings=None):
    """Map exact approved values. Semicolons separate selections, never commas.

    If any nonblank selection is unknown, return blank for the whole field.
    """
    if raw is None:
        return ""
    items = raw if isinstance(raw, (list, tuple)) else [raw]
    parts = [_normalize(part) for item in items if item is not None
             for part in str(item).split(";") if _normalize(part)]
    if not parts:
        return ""
    mapping = NM_DROPDOWNS.get(field, {})
    result = []
    for part in parts:
        if part not in mapping:
            if warnings is not None:
                warnings.append(f"NM {field}: unrecognized option; entire field left blank.")
            return ""
        if mapping[part] not in result:
            result.append(mapping[part])
    return ";".join(result)


def nm_intersection_type(raw):
    return nm_dropdown_value("intersection_type", raw)


def apply_nm_dropdowns(payload):
    """Apply once, at the end of map_nm(), before returning the payload."""
    notes = payload.setdefault("notes", [])
    incident = payload["incident"]
    for field in ("weather", "first_harmful_event", "lighting", "intersection_type"):
        incident[field] = nm_dropdown_value(field, incident.get(field), notes)
    for unit in payload.get("units", []):
        driver = unit["driver"]
        for field in ("injury_code", "seating_position"):
            driver[field] = nm_dropdown_value(field, driver.get(field), notes)
        vehicle = unit["vehicle"]
        field = "apparent_contributing_factors"
        vehicle[field] = nm_dropdown_value(field, vehicle.get(field), notes)
    return payload


def _self_test():
    assert nm_dropdown_value("weather", "00 Clear") == "CLEAR"
    assert nm_dropdown_value("weather", ["CLOUDY", "WIND"]) == "CLOUDY;WIND"
    assert nm_dropdown_value("weather", "FOG, SMOG, SMOKE") == "FOG, SMOG, SMOKE"
    assert nm_intersection_type("T-INTERSECTION") == "T INT"
    assert nm_dropdown_value("injury_code", "O") == "O"
    assert nm_dropdown_value("injury_code", "0") == ""
    assert nm_dropdown_value("seating_position", "LF Left Front") == "LF"
    assert nm_dropdown_value("apparent_contributing_factors", "NO DRIVER ERROR") == "OTHER NO DRIVER ERROR"
    assert nm_dropdown_value("first_harmful_event", "ROLLOVER") == "ROLLOVER"
    assert nm_dropdown_value("first_harmful_event", "OVERTURNED") == "OVERTURNED"
    warnings = []
    assert nm_dropdown_value("weather", "CLOUDY;UNRECOGNIZED", warnings) == ""
    assert warnings
    print("All NM text-entry helper tests passed.")


if __name__ == "__main__":
    _self_test()
