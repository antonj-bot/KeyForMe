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
    """
    Activate a tab using its position and actual linked panel.

    Wait for both panel visibility and selection state.
    Retry normal tab activation within one bounded timeout.
    Never click Add Unit here.
    """
    from playwright.sync_api import Error as PlaywrightError

    if number < 1:
        raise ValueError("Tab numbers start at one.")

    if spec.timeout_ms <= 0:
        raise ValueError("Tab activation timeout must be positive.")

    page = section.page
    deadline = time.monotonic() + spec.timeout_ms / 1000
    last_error = None
    next_click = 0.0
    click_attempted = False

    def remaining_ms():
        return max(
            1,
            int((deadline - time.monotonic()) * 1000),
        )

    while time.monotonic() < deadline:
        if page.is_closed():
            raise RuntimeError(
                f"{label} {number}: browser page was closed."
            )

        try:
            tabs = unit_tabs(section, spec)
            count = tabs.count()

            if number > count:
                last_error = RuntimeError(
                    f"Only {count} initialized tab(s) found."
                )
            else:
                # Re-resolve each time in case the form rebuilt its tabs.
                tab = tabs.nth(number - 1)
                panel = panel_for_tab(section, tab, number)

                selected = tab.locator(
                    "xpath=.."
                ).get_attribute(
                    "aria-selected",
                    timeout=remaining_ms(),
                )

                if selected is None:
                    selected = tab.get_attribute(
                        "aria-selected",
                        timeout=remaining_ms(),
                    )

                hidden = panel.get_attribute(
                    "aria-hidden",
                    timeout=remaining_ms(),
                )

                active = (
                    panel.is_visible()
                    and selected != "false"
                    and hidden != "true"
                )

                # Require at least one click to activate the requested tab.
                if click_attempted and active:
                    return panel

                if time.monotonic() >= next_click:
                    tab.click(timeout=remaining_ms())
                    click_attempted = True

                    # Give the form time to update before another click.
                    next_click = time.monotonic() + 0.75

                last_error = RuntimeError(
                    "Linked panel has not finished becoming active."
                )

        except (PlaywrightError, RuntimeError) as error:
            last_error = error

        remaining = deadline - time.monotonic()
        if remaining > 0:
            # Keep Playwright events running while waiting.
            page.wait_for_timeout(
                min(100, max(1, int(remaining * 1000)))
            )

    raise RuntimeError(
        f"{label} {number}: activation failed within "
        f"{spec.timeout_ms / 1000:g}s. Last issue: {last_error}"
    ) from last_error
