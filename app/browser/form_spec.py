"""State-owned form configuration for the shared engine."""
from dataclasses import dataclass, field
from app.core.tabs import TabSpec

@dataclass(frozen=True)
class FormSpec:
    state: str
    frame: str
    unit_section: str
    incident: dict
    owner: dict
    driver: dict
    vehicle: dict
    tabs: TabSpec = field(default_factory=TabSpec)
    units_before_incident: bool = False
    person_order: tuple = ("owner", "driver")
    strict_person_pairs: bool = True
    tab_after_text: bool = True
    dropdown_prefix_codes: bool = False
    field_timeout_ms: int = 3000
    checkbox_fields: tuple = ()
    cited: bool = False
    radio_rows: dict = field(default_factory=dict)
    radio_fields: dict = field(default_factory=dict)
    radios_before_vin: bool = False
    popup_ok: str = "div.ui-dialog.ui-front.ui-dialog-buttons div.ui-dialog-buttonpane button:first-child"
    accept_native_dialogs: bool = False
    other_section: str = ""
    other: dict = field(default_factory=dict)
    other_keys: tuple = ()
    person_types: dict = field(default_factory=dict)
