"""Raw NJTR-1 extractions transcribed from the six sample reports (read by eye from the
page images / OCR text, not produced by the AI). They are realistic INPUT for map_nj():
they check the keying rules on real layouts, not the AI's reading accuracy.

Sample name  ->  fixture
  NJ standard.pdf                                      -> STANDARD
  NJ 3 units 1 property owner.pdf                      -> THREE_UNITS
  NJ unit 1 has violation and there is property owner  -> VIOLATION
  4 units, units 3 and 4 are parked.pdf                -> FOUR_UNITS
  NJ veh 2 parked.pdf                                  -> VEH2_PARKED
  Nj normal 2 units. no passenger.pdf                  -> NORMAL_2
"""

NO_REMOVAL = dict(driven=False, left_at_scene=False, towed_disabled=False,
                  towed_disabled_impounded=False, towed_impounded=False)


def driver(first="", middle="", last="", dob="", dl="", dl_state="", alcohol="No",
           a1="", city="", state="", zip=""):
    return dict(first=first, middle=middle, last=last, dob=dob, dl_number=dl, dl_state=dl_state,
                alcohol_given=alcohol, address_1=a1, address_2="", city=city, state=state, zip=zip)


def owner(name="", same=False, company=None, a1="", city="", state="", zip=""):
    return dict(same_as_driver=same, name=name, is_company=company, address_1=a1,
                city=city, state=state, zip=zip)


def vehicle(vin="", year="", make="", model="", plate="", plate_state=""):
    return dict(vin=vin, year=year, make=make, model=model, plate=plate, plate_state=plate_state)


def occ(row, veh, pos, ej, inj, age, avail, used, airbag, hospital="", name="", address=""):
    return dict(row=row, vehicle=veh, position=pos, ejection=ej, injury=inj, age=age,
                safety_available=avail, safety_used=used, airbag=airbag, hospital=hospital,
                name=name, address_line=address)


def veh(number, *, parked=False, hit_and_run=False, policy="", ins="", narr_ins="", driver_=None,
        owner_=None, vehicle_=None, removal=None, charges=(), damage_new="", damage_old="",
        new_form=True, contributing=()):
    return dict(number=number, parked=parked, hit_and_run=hit_and_run, policy_number=policy,
                ins_code=ins, narrative_insurance=narr_ins, narrative_policy="",
                driver=driver_ or driver(), owner=owner_ or owner(), vehicle=vehicle_ or vehicle(),
                removal={**NO_REMOVAL, **(removal or {})}, charges=list(charges),
                damage=dict(new=damage_new, old=damage_old, new_form=new_form),
                contributing=list(contributing))


# ------------------------------------------------------------------------------ NJ standard
STANDARD = dict(
    case_number="D040202602475C", police_dept="New Jersey State Police",
    crash_date="07/18/2026", crash_time="2058", road_name="Garden State Parkway", cross_road="",
    speed_limit="55", latitude="40.886591", longitude="-74.151818", weather_code="", road_condition_code="",
    vehicles=[
        veh(1, policy="3085845C0152F", ins="000", narr_ins="(NY) STATE FARM - Field 25",
            driver_=driver("JULIA", "", "HARRISON", "12/24/1989", "498908407", "NY", "No", "415 BUCHANAN RD", "UTICA", "NY", "13502"),
            owner_=owner("JULIA HARRISON", same=True, a1="415 BUCHANAN RD", city="UTICA", state="NY", zip="13502"),
            vehicle_=vehicle("1F9TEST05KT090000", "2025", "CHEVROLET", "TRAVERSE", "BADDDIE", "NY"),
            removal=dict(towed_disabled=True), damage_new="09", damage_old="09", contributing=["60", "-"]),
        veh(2, policy="3464371A0652", ins="000", narr_ins="(NY) STATE FARM - Field 55",
            driver_=driver("MICHEAL", "T", "PAINE", "12/25/1976", "456389033", "NY", "No", "156 TOWNLINE ROAD", "PEARL RIVER", "NY", "10965"),
            owner_=owner("MICHEAL T PAINE", same=True, a1="156 TOWNLINE ROAD", city="PEARL RIVER", state="NY", zip="10965"),
            vehicle_=vehicle("1F9TEST03KT000004", "2014", "MINI", "COOPER ROADSTER", "KYN5066", "NY"),
            removal=dict(driven=True), damage_new="09", damage_old="09", contributing=["25", "-"]),
    ],
    occupants=[
        occ("A", "01", "01", "01", "04", "36", "04", "04", "04", name="JULIA HARRISON", address="415 BUCHANAN RD UTICA NY 13502"),
        occ("B", "01", "03", "01", "03", "17", "04", "04", "04", name="JAYDEN T STAPLETON", address="415 BUCHANAN RD UTICA NJ 13502"),
        occ("C", "01", "07", "01", "05", "14", "04", "04", "", name="CAYSEN T STAPLETON", address="415 BUCHANAN RD UTICA NJ 13502"),
        occ("D", "02", "01", "01", "05", "49", "04", "04", "06", name="MICHEAL T PAINE", address="156 TOWNLINE ROAD PEARL RIVER NY 10965"),
    ],
    property_owners=[dict(name="NJTA", address_line="", is_company=True)],   # "NJTA : CONCRETE BARRIER"
)

# ------------------------------------------------------------------------------ NJ 3 units 1 property owner
THREE_UNITS = dict(
    case_number="2026-008200", police_dept="RIDGEFIELD", crash_date="08/08/26", crash_time="1259",
    road_name="BERGEN BLVD", cross_road="ELM AVENUE", speed_limit="35", latitude="40.8329", longitude="-73.9910",
    weather_code="01", road_condition_code="01",
    vehicles=[
        veh(1, policy="KBJR-F4T4-INS", ins="*", narr_ins="RentalCover.com",
            driver_=driver("TYRIK", "CHARLES", "JONES", "08/04/93", "971298010", "NY", "No", "399 BRISTOL ST, APT C", "BROOKLYN", "NY", "11212"),
            owner_=owner("ERIC M LOPEZ", a1="1 SPENCER PL, APT 2B", city="BROOKLYN", state="NY", zip="11216"),
            vehicle_=vehicle("1F9TEST05KT000005", "2014", "NISSAN", "SENTRA", "MEA3724", "NY"),
            removal=dict(towed_disabled=True), damage_new="12", damage_old="08", contributing=["14", "04"],
            charges=["39:4-88B FAILED TO MAINTAIN LANE", "39:3-10 UNLICENSED DRIVER", "39:4-82 FAILURE TO KEEP RIGHT",
                     "39:4-97.3 USE OF HAND-HELD WIRELESS DEVICE"]),
        veh(2, policy="TCA00002069599", ins="632",
            driver_=driver("MAYRA", "C", "BERMEO-ALTAMIRANO", "01/16/94", "B27145366351942", "NJ", "No", "309 ELM AVE", "BOGOTA", "NJ", "07603-1216"),
            owner_=owner("MAYRA C BERMEO-ALTAMIRANO", same=True, a1="309 ELM AVE", city="BOGOTA", state="NJ", zip="07603-1216"),
            vehicle_=vehicle("1F9TEST07KT000006", "2020", "JEEP", "WRA", "D93UNB", "NJ"),
            removal=dict(towed_disabled=True), damage_new="08", damage_old="04", contributing=["25", "-"]),
        veh(3, parked=True, policy="876068086", ins="134",
            driver_=driver(alcohol="No", dl="NONE"),
            owner_=owner("JAIME G PALOMEQUEPACHECO", a1="36 EUCLID AVE, APT 2", city="HACKENSACK", state="NJ", zip="07601-4510"),
            vehicle_=vehicle("1F9TEST09KT000007", "2009", "TOYOTA", "CAM", "A38YCR", "NJ"),
            removal=dict(left_at_scene=True), damage_new="01", damage_old="", contributing=["25", "01"]),
    ],
    occupants=[
        occ("A", "1", "01", "01", "03", "33", "04", "04", "04", ),
        occ("B", "1", "03", "01", "05", "31", "04", "04", "06", name="EMANUEL, JABARI SHAHKIR",
            address="346 JEFFERSON AVE, #2A, BROOKLYN, NY 11221"),
        occ("C", "2", "01", "01", "05", "32", "04", "04", "06"),
    ],
    property_owners=[dict(name="", address_line="746 BERGEN BLVD", is_company=None)],
)

# ------------------------------------------------------------------------------ NJ unit 1 has violation + property owners
VIOLATION = dict(
    case_number="26-002311", police_dept="Berkeley Township Police Department", crash_date="07/31/2026",
    crash_time="0040", road_name="Buena VIsa Drive", cross_road="Tapola Road", speed_limit="25",
    latitude="39.954336", longitude="-74.241293", weather_code="", road_condition_code="",
    vehicles=[
        veh(1, hit_and_run=True, policy="UNKNOWN", ins="000",
            driver_=driver("Jonathan", "", "Rosado", "02/25/1993", "R66854090002936", "NJ", "No", "33 Innsbruck Dr", "Berkeley Township", "NJ", "08757"),
            owner_=owner("Ean Holdings LLC", a1="14002 E 21st St", city="Tulsa", state="OK", zip="74134"),
            vehicle_=vehicle("1F9TEST00KT000008", "2026", "KIA", "K4", "MGH5227", "NY"),
            removal=dict(towed_disabled_impounded=True), damage_new="15", damage_old="05", contributing=["02", "-"],
            charges=["39:4-97 - Careless Driving", "39:3-40 - License or Registration Suspended", "39:4-96 - Reckless Driving",
                     "39:4-88a", "39:4-49.1", "39:4-129d", "39:4-130 - Failure to Report an Accident"]),
        veh(2, parked=True, policy="876667817", ins="000",
            driver_=driver(alcohol=""),
            owner_=owner("Richard B McKelvey III", a1="34 Buena Visa Dr", city="Berkeley Township", state="NJ", zip="08757"),
            vehicle_=vehicle("1F9TEST02KT000009", "2012", "FORD", "EXPLORER", "G40LXS", "NJ"),
            removal=dict(left_at_scene=True), damage_new="05", damage_old="05", contributing=["25", "25"]),
    ],
    occupants=[occ("A", "01", "01", "00", "04", "33", "04", "00", "04", hospital="6501", name="Jonathan Rosado",
                   address="33 Innsbruck Dr Berkeley Township NJ 08757")],
    property_owners=[dict(name="Karen Odonnell", address_line="", is_company=None),
                     dict(name="Jersey Central Power & Light", address_line="", is_company=True)],
)

# ------------------------------------------------------------------------------ 4 units, 3 and 4 parked (units 3-4 on a second page)
FOUR_UNITS = dict(
    case_number="26-0047400", police_dept="EAST ORANGE", crash_date="06/15/26", crash_time="2041",
    road_name="WASHINGTON ST", cross_road="HILLYER ST", speed_limit="25", latitude="40.7730", longitude="-74.2202",
    weather_code="01", road_condition_code="01",
    vehicles=[
        veh(1, policy="6242-74-86-52", ins="365",
            driver_=driver("RAYNA", "M", "MENDEZ", "05/13/06", "M25136447455062", "NJ", "No", "57 STATE ST", "EAST ORANGE", "NJ", "07017-1117"),
            owner_=owner("RAYNA M MENDEZ", same=True, a1="57 STATE ST", city="EAST ORANGE", state="NJ", zip="07017-1117"),
            vehicle_=vehicle("1F9TEST09KT000010", "2019", "HONDA", "CIV", "Z81WYP", "NJ"),
            removal=dict(towed_disabled_impounded=True), damage_new="12", damage_old="02", contributing=["04", "-"],
            charges=["39:3-4", "39:3-10"]),
        veh(2, policy="ABP6300245193", ins="169",
            driver_=driver("CHRISTIAN", "A", "JENKINS", "03/04/91", "J25461246103912", "NJ", "No", "63 ELMWOOD AVE, 2ND FL", "MONTCLAIR", "NJ", "07042-4533"),
            owner_=owner("CHRISTIAN A JENKINS", same=True, a1="63 ELMWOOD AVE, 2ND FL", city="MONTCLAIR", state="NJ", zip="07042-4533"),
            vehicle_=vehicle("1F9TEST00KT000011", "2011", "KIA MOT", "SOUL", "P43UDW", "NJ"),
            removal=dict(towed_disabled_impounded=True), damage_new="02", damage_old="02", contributing=["25", "-"]),
        veh(3, parked=True, policy="822525521-0", ins="945",
            driver_=driver(alcohol="No", dl="NONE"),
            owner_=owner("SAMPLEFOUR MERRITT", a1="95 WASHINGTON ST, APT. 4A", city="EAST ORANGE", state="NJ", zip="07017-1014"),
            vehicle_=vehicle("1F9TEST02KT000012", "2015", "DODGE", "DUR", "U65UUD", "NJ"),
            removal=dict(left_at_scene=True), damage_new="10", damage_old="05", contributing=["25", "25"]),
        veh(4, parked=True, policy="871920204", ins="134",
            driver_=driver(alcohol="No"),
            owner_=owner("MARC E EXANTUS", a1="212 ELMWOOD AVE", city="IRVINGTON", state="NJ", zip="07111-1315"),
            vehicle_=vehicle("1F9TEST04KT000013", "2015", "HONDA", "ACC", "C75WVX", "NJ"),
            removal=dict(driven=True), damage_new="05", damage_old="03", contributing=["25", "-"]),
    ],
    occupants=[
        occ("A", "01", "01", "01", "03", "20", "04", "04", "04", hospital="5707", name="MENDEZ, RAYNA M",
            address="57 STATE ST, EAST ORANGE, NJ 07017-1117"),
        occ("B", "02", "01", "01", "04", "35", "04", "04", "02", hospital="5707", name="JENKINS, CHRISTIAN A",
            address="63 ELMWOOD AVE, 2ND FL, MONTCLAIR, NJ 07042-4533"),
    ],
    property_owners=[],   # field 135 only names the two parked vehicles that are already units 3 and 4
)

# ------------------------------------------------------------------------------ NJ veh 2 parked
VEH2_PARKED = dict(
    case_number="26-008542", police_dept="Trenton Police Department", crash_date="08/10/2026", crash_time="0950",
    road_name="635 S TESTTHREE AVE TRENTON NJ 08611", cross_road="", speed_limit="10",
    latitude="40.210912", longitude="-74.754208", weather_code="", road_condition_code="",
    vehicles=[
        veh(1, policy="5055658C2638B", ins="000", narr_ins="State Farm Mutual Automobile Insurance Company - Field 25",
            driver_=driver("Ebenezer", "", "Goodlin", "12/16/1950", "30356166", "PA", "No", "28 Teaberry Ln", "Levittown", "PA", "19054"),
            owner_=owner("Ebenezer Goodlin", same=True, a1="28 Teaberry Ln", city="Levittown", state="PA", zip="19054"),
            vehicle_=vehicle("1F9TEST06KT000014", "2005", "FORD", "RANGER", "ZVR7077", "PA"),
            removal=dict(left_at_scene=True), damage_new="12", damage_old="06", contributing=["04", "-"]),
        veh(2, parked=True, policy="871866005", ins="134",
            driver_=driver(alcohol=""),
            owner_=owner("Peace Blewuadah", a1="353 Elm Avenue", city="Trenton", state="NJ", zip="08016"),
            vehicle_=vehicle("1F9TEST08KT000015", "2014", "TOYOTA", "4RUNNER", "P92JGG", "NJ"),
            removal=dict(left_at_scene=True), damage_new="06", damage_old="02", contributing=["25", "-"]),
    ],
    occupants=[occ("A", "01", "01", "01", "05", "75", "04", "04", "06", name="Ebenezer Goodlin",
                   address="28 Teaberry Ln Levittown PA 19054")],
    property_owners=[],
)

# ------------------------------------------------------------------------------ Nj normal 2 units. no passenger
NORMAL_2 = dict(
    case_number="26-40623", police_dept="Passaic", crash_date="06 09 26", crash_time="16 01",
    road_name="Jefferson Street", cross_road="Columbia Avenue", speed_limit="25", latitude="", longitude="",
    weather_code="01", road_condition_code="01",
    vehicles=[
        veh(1, policy="2501632-E01-30", ins="962",
            driver_=driver("Felix", "", "Rodriguez", "04 30 61", "R6094 25900 04611", "NJ", "No", "110 Jefferson St", "Passaic, NJ 07055-5114", "", ""),
            owner_=owner("Felix Rodriguez", same=True, a1="110 Jefferson St", city="Passaic, NJ 07055-5114"),
            vehicle_=vehicle("1F9TEST0XKT000016", "08", "Jeep", "WRA", "M70SMF", "NJ"),
            removal=dict(driven=True), damage_new="02", damage_old="", contributing=["04", "-"]),
        veh(2, policy="F10753226-9", ins="426",
            driver_=driver("Ausencia", "", "Mejia", "12 18 70", "M2326 06800 62702", "NJ", "No", "119 Jefferson St Apt 2", "Passaic, NJ 07055-5102", "", ""),
            owner_=owner("Eusebio Mejia", a1="119 Jefferson St", city="Passaic, NJ 07055-5102"),
            vehicle_=vehicle("1F9TEST01KT000017", "17", "Nissan", "ROG", "Z84LMG", "NJ"),
            removal=dict(driven=True), damage_new="02", damage_old="", contributing=["25", "-"]),
    ],
    occupants=[
        occ("A", "1", "01", "01", "05", "65", "02", "02", "06", name="Rodriguez, Felix",
            address="110 Jefferson St, Passaic, NJ 07055-5114"),
        occ("B", "2", "01", "01", "05", "55", "02", "02", "06", name="Mejia, Ausencia",
            address="119 Jefferson St Apt 2, Passaic, NJ 07055-5102"),
    ],
    property_owners=[],
)

ALL = dict(STANDARD=STANDARD, THREE_UNITS=THREE_UNITS, VIOLATION=VIOLATION, FOUR_UNITS=FOUR_UNITS,
           VEH2_PARKED=VEH2_PARKED, NORMAL_2=NORMAL_2)
