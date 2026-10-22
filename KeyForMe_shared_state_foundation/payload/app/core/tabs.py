"""One scoped tab engine, with state-specific selectors supplied as configuration."""
from dataclasses import dataclass
import json
import time

@dataclass(frozen=True)
class TabSpec:
    anchors: str = "a.ui-tabs-anchor[href^='#']"
    add: str = "div.st-nav-add:visible"
    timeout_ms: int = 12000
    settle_ms: int = 0

def unit_tabs(section, spec=TabSpec()):
    return section.locator(spec.anchors)

def panel_for_tab(section, tab, number):
    href = (tab.get_attribute("href") or "").strip()
    if not href.startswith("#") or len(href) == 1:
        raise RuntimeError(f"Unit {number}: no local panel reference.")
    panel = section.locator("[id=" + json.dumps(href[1:]) + "]")
    if panel.count() != 1:
        raise RuntimeError(f"Unit {number}: linked panel missing or ambiguous.")
    return panel

def validate_tabs(section, required, spec=TabSpec()):
    tabs = unit_tabs(section, spec)
    if tabs.count() < required:
        raise RuntimeError("Not enough initialized unit tabs.")
    seen = set()
    for index in range(required):
        tab = tabs.nth(index)
        href = tab.get_attribute("href")
        if href in seen:
            raise RuntimeError("Multiple unit tabs reference the same panel.")
        panel_for_tab(section, tab, index + 1)
        seen.add(href)

def ensure_tabs(page, section, required, *, spec=TabSpec(), add_control=None, log=None, label="unit"):
    if required < 0:
        raise ValueError("Required tab count cannot be negative.")
    if section.count() != 1:
        raise RuntimeError(f"{label}: section missing or ambiguous.")
    tabs = unit_tabs(section, spec)
    current = tabs.count()
    if required and current < 1:
        raise RuntimeError(f"{label}: no initialized starting tab.")
    while current < required:
        button = add_control if add_control is not None else section.locator(spec.add)
        if button.count() != 1:
            raise RuntimeError(f"{label}: expected one Add control, found {button.count()}.")
        expected = current + 1
        if log:
            log(f"Adding {label} {expected}...")
        button.scroll_into_view_if_needed(timeout=3000)
        # One normal click only. Never dispatch or force a second click.
        button.click(timeout=5000)
        deadline = time.monotonic() + spec.timeout_ms / 1000
        while True:
            count = tabs.count()
            if count > expected:
                raise RuntimeError(f"{label}: one Add click created multiple tabs; review the form.")
            ready = False
            if count == expected:
                try:
                    tab = tabs.nth(expected - 1)
                    panel_for_tab(section, tab, expected)
                    ready = tab.is_visible()
                except RuntimeError:
                    pass
            if ready:
                break
            if time.monotonic() >= deadline:
                raise RuntimeError(f"{label} {expected}: tab/panel not ready after Add; no second click attempted.")
            page.wait_for_timeout(100)
        if spec.settle_ms:
            page.wait_for_timeout(spec.settle_ms)
        current = tabs.count()
        if current != expected:
            raise RuntimeError(f"{label}: unexpected tab count after Add.")
        if log:
            log(f"{label.capitalize()} {current} added.")
    validate_tabs(section, required, spec)

def activate_tab(section, number, *, spec=TabSpec(), label="unit"):
    if number < 1:
        raise ValueError("Tab numbers start at one.")
    tab = unit_tabs(section, spec).nth(number - 1)
    tab.wait_for(state="visible", timeout=spec.timeout_ms)
    panel = panel_for_tab(section, tab, number)
    tab.click(timeout=spec.timeout_ms)
    panel.wait_for(state="visible", timeout=spec.timeout_ms)
    selected = tab.locator("xpath=..").get_attribute("aria-selected")
    if selected is None:
        selected = tab.get_attribute("aria-selected")
    if selected == "false" or panel.get_attribute("aria-hidden") == "true":
        raise RuntimeError(f"{label} {number}: panel remained inactive.")
    return panel
