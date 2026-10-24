"""Shared PA test data. Names, numbers and addresses are the sample values printed in the PA training deck."""
import copy


def coded(text=None, code=None):
    return {"code": code, "text": text}


def sample_raw() -> dict:
    """A two-vehicle crash: unit 1 has a passenger, two violations and a trailer; unit 2 left the scene."""
    return copy.deepcopy({
        "incident_number": "202607025541", "report_number": None, "cad_case_number": None,
        "investigation_date": "07/23/2026", "crash_date": "07/19/2026", "crash_time": "09:30",
        "municipality": "PHILADELPHIA CITY",
        "house_number": None, "street_name": "ROOSEVELT", "street_ending": "BOULEVARD", "route_number": None,
        "cross_street_name": "GRANT", "cross_street_ending": "AVENUE", "not_in_intersection": None,
        "latitude": "40:04:53.610", "longitude": "-75:01:42.170",
        "units_involved": 2,
        "weather": [coded("CLOUDY"), coded("CLOUDY")], "road_surface": [coded("DRY")],
        "speed_limit": "30 MPH", "hit_and_run_crash": True,
        "units": [
            {"number": 1, "unit_type": "AUTOMOBILE", "hit_and_run": False, "owner_is_driver": False,
             "driver": {"first": "BRITNEY", "middle": None, "last": "CABAN", "suffix": None,
                        "address_1": "2225 NORTH LAWRENCE STREET", "city": "PHILADELPHIA", "state": "PA",
                        "zip": "19133", "phone": "(000) 000-0000", "dob": "09/06/1990",
                        "dl_number": "29649264", "dl_state": "PA",
                        "alcohol_drugs": [coded("UNKNOWN")],
                        "driver_actions": [coded("DRIVING TOO FAST FOR CONDITIONS"), coded(code="23")],
                        "helmet": [],
                        "violations": [{"text": "75 3361 SPEED", "charged": "YES", "primary": True},
                                       {"text": "75 3714 CARELESS", "charged": "Warning", "primary": False}]},
             "owner": {"first": "BRITNEY", "middle": None, "last": "CABAN", "suffix": None,
                       "address_1": "2225 NORTH LAWRENCE STREET", "city": "PHILADELPHIA", "state": "PA",
                       "zip": "19133", "phone": "(000) 000-0000"},
             "vehicle": {"plate": "NFL7193", "plate_state": "pa", "vin": "1HGCM56715A042022", "year": "2005",
                         "make": "HONDA", "model": "Accord", "insurance_company": "UNKNOWN",
                         "policy_number": None, "policy_expiration": None, "towed": "YES", "towed_by": "ABC TOWING",
                         "impact_point": ["12"], "vehicle_failures": [coded(code="1")]},
             "passenger_helmet": [],
             "trailers": [{"plate": "TRL1234", "plate_state": "PA", "vin": None, "year": None, "tag_year": "2026",
                           "make": "UTILITY"}]},
            {"number": 2, "unit_type": "AUTOMOBILE", "hit_and_run": True, "owner_is_driver": False,
             "driver": {"first": None, "last": None, "violations": []},
             "owner": {"first": "ANDY", "last": "PERDOMO", "address_1": "137 OLEY ST", "city": "READING",
                       "state": "PA", "zip": "19601"},
             "vehicle": {"plate": "JYM3740", "plate_state": "PA", "vin": "JN8AT2MV9LW101587", "year": "2020",
                         "make": "NISSAN", "model": "ROGUE", "towed": None, "towed_by": None,
                         "impact_point": ["6"], "vehicle_failures": []},
             "trailers": []},
        ],
        "occupants": [
            {"unit": "1", "person_no": "1", "person_type": coded("DRIVER"), "first": "BRITNEY", "last": "CABAN",
             "injury": [coded(code="0")], "safety_equipment": [coded(code="3")], "ejection": [coded(code="1")],
             "airbag": "Front", "medical_facility": "NONE"},
            {"unit": "1", "person_no": "2", "person_type": coded("PASSENGER"), "first": "NAHZYRA", "last": "EUTSEY",
             "address_1": "1228 VETERANS HWY APT H5", "city": "PHILADELPHIA", "state": "PA", "zip": "19056",
             "phone": "(215) 796-3958", "dob": "99/99/9999",
             "injury": [coded(code="4")], "safety_equipment": [coded(text="Lap and Shoulder Belt Used")],
             "ejection": [coded(code="1")], "airbag": "Not Deployed", "medical_facility": "TEMPLE"},
        ],
        "witnesses": [{"first": "JOHN", "last": "WITNESS", "address_1": "5 MAIN ST", "city": "PHILADELPHIA",
                       "state": "PA", "zip": "19107", "phone": "(215) 555-0100"}],
        "property_owners": [],
        "notes": [],
    })
