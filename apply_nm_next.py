"""Safe, repeatable NM-only schema and mapper upgrade.
Run from KeyForMe root: python apply_nm_next.py
Does not modify CA files or enable NM live filling.
"""
from pathlib import Path
import ast
import shutil

root = Path.cwd()
model = root / 'app/nm_models.py'
mapper = root / 'app/keying/nm_mapper.py'
for p in (model, mapper):
    if not p.is_file():
        raise SystemExit(f'Missing {p}; run from KeyForMe project root')

incident_fields = '''    first_harmful_event: str | None = None
    district: str | None = None
'''
unit_fields = '''    driver_sex: str | None = None
    driver_physical_condition: str | None = None
    driver_seating_position: str | None = None
    driver_op_code: str | None = None
    airbag_code: str | None = None
    body_style: str | None = None
    unit_road_condition: str | None = None
    unit_traffic_control: str | None = None
    road_design: str | None = None
    apparent_contributing_factors: str | None = None
    sequence_first: str | None = None
    sequence_second: str | None = None
    sequence_third: str | None = None
    sequence_fourth: str | None = None
'''

m = model.read_text(encoding='utf-8')
if 'first_harmful_event:' not in m:
    assert 'class NMUnit(BaseModel):' in m
    m = m.replace('class NMUnit(BaseModel):', incident_fields + '\nclass NMUnit(BaseModel):', 1)
if 'driver_physical_condition:' not in m:
    assert 'class NMPageExtraction(BaseModel):' in m
    m = m.replace('class NMPageExtraction(BaseModel):', unit_fields + '\nclass NMPageExtraction(BaseModel):', 1)
ast.parse(m)

s = mapper.read_text(encoding='utf-8')
helpers = '''

def nm_driver_license(raw: str | None) -> str:
    """Non-numeric placeholders such as ---- are not keyable."""
    t = (raw or "").strip()
    return t if re.search(r"\\d", t) else ""


def nm_dob(raw: str | None) -> str:
    """Do not reconstruct incomplete birth dates."""
    from datetime import datetime
    t = date(raw)
    if not re.fullmatch(r"\\d{2}/\\d{2}/\\d{4}", t):
        return ""
    try:
        datetime.strptime(t, "%m/%d/%Y")
    except ValueError:
        return ""
    return t


def nm_airbag(raw: str | None) -> str:
    t = (raw or "").strip().upper()
    if not t:
        return ""
    if t in {"N", "NA", "N/A"}:
        return "NO"
    return "YES" if t.isalpha() else ""
'''
if 'def nm_driver_license(' not in s:
    assert 'def map_nm(report: NMReport)' in s
    s = s.replace('def map_nm(report: NMReport)', helpers + '\n\ndef map_nm(report: NMReport)', 1)

replacements = {
    '"report_identifier_1": incident.crash_report_number or "",': '"report_identifier_1": incident.case_number or "",',
    '"report_identifier_2": incident.case_number or "",': '"report_identifier_2": incident.crash_report_number or "",',
    '"date_of_birth": date(u.driver_dob),': '"date_of_birth": nm_dob(u.driver_dob),',
    '"drivers_license": u.driver_license or "",': '"drivers_license": nm_driver_license(u.driver_license),',
}
for before, after in replacements.items():
    if before in s:
        s = s.replace(before, after, 1)

additions = {
    '"officer_id": incident.officer_id or "",': '''"officer_id": incident.officer_id or "",
            "first_harmful_event": incident.first_harmful_event or "",
            "district": incident.district or incident.reporting_district or "",
            "intersection_type": incident.intersection_type or "",''',
    '"driver_actions": u.driver_actions or "",': '''"driver_actions": u.driver_actions or "",
                "sex": u.driver_sex or "",
                "physical_condition": u.driver_physical_condition or "",
                "seating_position": u.driver_seating_position or "",
                "op_code": u.driver_op_code or "",''',
    '"damage_extent": u.damage_severity or "",': '''"damage_extent": u.damage_severity or "",
                "airbag_deployed": nm_airbag(u.airbag_code),
                "body_style": u.body_style or "",
                "road_condition": u.unit_road_condition or "",
                "traffic_control": u.unit_traffic_control or "",
                "road_design": u.road_design or "",
                "apparent_contributing_factors": u.apparent_contributing_factors or "",
                "sequence_first": u.sequence_first or "",
                "sequence_second": u.sequence_second or "",
                "sequence_third": u.sequence_third or "",
                "sequence_fourth": u.sequence_fourth or "",''',
}
for anchor, block in additions.items():
    marker = block.split('\n')[1].strip().split(':')[0]
    if marker not in s:
        if anchor not in s:
            raise SystemExit(f'Mapper structure changed: could not find {anchor}. No files changed.')
        s = s.replace(anchor, block, 1)
ast.parse(s)

for p in (model, mapper):
    backup = p.with_suffix('.py.bak')
    if not backup.exists():
        shutil.copy2(p, backup)
model.write_text(m, encoding='utf-8')
mapper.write_text(s, encoding='utf-8')
print('NM models and mapper updated; CA unchanged.')
print('Backups are *.py.bak (if not already present).')
