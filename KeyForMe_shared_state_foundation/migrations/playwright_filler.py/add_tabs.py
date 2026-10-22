def add_tabs(page: Page, section, add_selector: str, required: int, label: str) -> None:
    add_control = form(page).locator(add_selector)
    ensure_tabs(page, section, required, add_control=add_control, log=print, label=label)
