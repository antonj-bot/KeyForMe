"""Shared NC fixture: the 'Witness, property owner and unit 1 citation' sample (form 1 of 2), values read
from the page images. Margin boxes are synthetic (the sample's margin digits were not read cell by cell)."""


def sample_raw() -> dict:
    return {
        "form_rev": "1/2009", "local_use": "260816025HA/02", "crash_date": "08/16/2026",
        "crash_time": "03:49", "municipality": "ROCKINGHAM", "on_road": "SR 1960", "from_road": "SR 1946",
        "latitude": "34.919383", "longitude": "-79.76735",
        "margin_boxes": {"3": "2", "4": "1", "5": "", "14": "8", "15": "-", "16": "", "17": "", "18": "", "19": ""},
        "units": [
            {"number": 1, "column": "left", "hit_and_run": True, "parked": False, "pedestrian": False,
             "driver": {"first": "LESVIN", "middle": "GEOVANY", "last": "GONZALES PEREZ", "suffix": "",
                        "address_1": "161 MORROW STREET", "city": "ROCKINGHAM", "state": "NC", "zip": "28379",
                        "phone": "(910) 995-7963", "dob": "09/22/1994", "dl_number": "", "dl_state": "",
                        "alcohol_suspected": "1"},
             "owner": {"first": "LESVIN", "middle": "GEOVANY", "last": "GONZALEZ PEREZ", "suffix": "",
                       "same_as_driver": False, "address_1": "161 MORROW STREET", "city": "ROCKINGHAM",
                       "state": "NC", "zip": "28379"},
             "vehicle": {"plate": "XXA169", "plate_state": "SC", "vin": "1GNSCJE0XDR157820", "year": "2027",
                         "make": "CHEV", "tad": "FD-2", "insurance_company": "AMERICAN",
                         "policy_number": "11408925685", "towed_by": "WATSON'S/ ROTATION/WATSON'S/ ROTATION",
                         "defects": "0", "speed_limit": "35"},
             "ems_taken": "N/A,"},
            {"number": 2, "column": "right", "hit_and_run": False, "parked": True, "pedestrian": False,
             "driver": {"first": "", "middle": "", "last": "", "address_1": "null"},
             "owner": {"first": "LEE", "middle": "GERALD", "last": "RAINWATER", "same_as_driver": False,
                       "address_1": "155 ENTWISTLE THIRD ST", "city": "ROCKINGHAM", "state": "NC",
                       "zip": "283794771"},
             "vehicle": {"plate": "NZJ7202", "plate_state": "NC", "vin": "5TBBT44121S154498", "year": "2001",
                         "make": "TOYT", "tad": "BR-1", "insurance_company": "INTEGON PREFERRED INSURANCE COMPANY",
                         "policy_number": "2034780977", "towed_by": "STAYED ON SCENE/STAYED ON SCENE",
                         "defects": "0", "speed_limit": "0"},
             "ems_taken": ""},
        ],
        "occupants": [
            {"row": "A", "vehicle": "1", "person_type": "1", "name": "", "address_line": "",
             "protection": "0", "airbag": "2", "ejection": "1", "injury": "5"},
        ],
        "charges": [
            {"name": "LESVIN GEOVANY GONZALES PEREZ", "charge": "Y0335457-1 - DRIVING WHILE IMPAIRED"},
            {"name": "LESVIN GEOVANY GONZALES PEREZ", "charge": "HIT AND RUN/ NO OPERATOR'S LICENSE FAILURE TO"},
        ],
        "witnesses": [{"name": "TARA NICOLE THOMAS", "address_line": "110 ALEO 9TH AVE, ROCKINGHAM, NC 28379"}],
        "property_owners": [{"name": "STEVE WATKINS", "address_1": "127 ALEO NINTH AVE", "city": "ROCKINGHAM",
                             "state": "NC", "zip": "28379"}],
    }


# The person-table reference the user sent: columns 21 (vehicle) and 22 (type, 1 = driver, 2 = passenger).
REFERENCE_ROWS = [("A", "1", "1"), ("B", "2", "1"), ("C", "1", "2"), ("D", "2", "2"), ("E", "2", "2")]
