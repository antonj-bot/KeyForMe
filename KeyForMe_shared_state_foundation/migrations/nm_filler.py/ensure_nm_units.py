def ensure_nm_units(page, required: int, log=None) -> None:
    if required < 1:
        raise ValueError("NM requires at least one extracted unit.")
    section = page.frame_locator(FRAME).locator(UNIT_SECTION)
    ensure_tabs(page, section, required, spec=NM_TABS, log=log, label="NM vehicle unit")
