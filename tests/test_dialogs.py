"""Tests for manual SAVE / EXIT dialogs.

Run from the project root:   python -m pytest tests/test_dialogs.py -v
Set KEYFORME_TEST_CHROMIUM to a browser executable to avoid channel="chrome".
"""
import os

import pytest

from app.browser import dialogs

FORM = """<html><body>
<button id="formSubmit" onclick="window.saveAnswer = confirm('Save changes?')">SAVE</button>
<button id="formExit" onclick="window.exitAnswer = confirm('Exit without saving?')">Exit</button>
</body></html>"""


def wrap(html):
    inner = html.replace("&", "&amp;").replace('"', "&quot;")
    return f'<html><body><iframe id="formIframe" srcdoc="{inner}"></iframe></body></html>'


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        exe = os.environ.get("KEYFORME_TEST_CHROMIUM")
        try:
            b = p.chromium.launch(executable_path=exe) if exe else p.chromium.launch(channel="chrome")
        except Exception as error:
            pytest.skip(f"no browser available ({type(error).__name__})")
        yield b
        b.close()


@pytest.fixture
def session(browser):
    context = browser.new_context()
    logs, seen = [], []
    page = context.new_page()
    page.set_content(wrap(FORM))
    page.wait_for_timeout(100)
    yield context, page, logs, seen
    context.close()


def observe(page, seen):
    """Test-only observer: records dialogs and takes no action on them."""
    page.on("dialog", lambda dialog: seen.append(dialog))


def inner(page):
    return page.frames[1]


def click_async(frame, selector):
    # A real mouse click is not blocked by dialogs; Playwright's click() would be.
    frame.evaluate(f"setTimeout(() => document.querySelector('{selector}').click(), 0)")


def log_to(logs):
    return lambda message, level="info": logs.append((level, message))


def test_root_cause_without_listener_dialog_is_auto_cancelled(session):
    _, page, _, _ = session
    click_async(inner(page), "#formSubmit")
    page.wait_for_timeout(300)
    assert inner(page).evaluate("window.saveAnswer") is False


def test_manual_save_dialog_waits_for_user_then_ok(session):
    context, page, logs, seen = session
    dialogs.watch_dialogs(context, log_to(logs))
    observe(page, seen)
    click_async(inner(page), "#formSubmit")
    page.wait_for_timeout(300)
    assert len(seen) == 1 and seen[0].type == "confirm"
    seen[0].accept()                          # the user presses OK
    page.wait_for_timeout(200)
    assert inner(page).evaluate("window.saveAnswer") is True     # proves it was not auto-cancelled
    assert any("waiting for your answer" in m for _, m in logs)


def test_manual_save_dialog_cancel_is_respected(session):
    context, page, logs, seen = session
    dialogs.watch_dialogs(context, log_to(logs))
    observe(page, seen)
    click_async(inner(page), "#formSubmit")
    page.wait_for_timeout(300)
    seen[0].dismiss()                         # the user presses Cancel
    page.wait_for_timeout(200)
    assert inner(page).evaluate("window.saveAnswer") is False


def test_manual_exit_dialog_waits_for_user(session):
    context, page, logs, seen = session
    dialogs.watch_dialogs(context, log_to(logs))
    observe(page, seen)
    click_async(inner(page), "#formExit")
    page.wait_for_timeout(300)
    assert len(seen) == 1
    seen[0].accept()
    page.wait_for_timeout(200)
    assert inner(page).evaluate("window.exitAnswer") is True


def test_dialogs_during_automation_are_dismissed(session):
    context, page, logs, seen = session
    dialogs.watch_dialogs(context, log_to(logs))
    observe(page, seen)
    with dialogs.automation_running():
        assert dialogs.is_automation_running()
        click_async(inner(page), "#formSubmit")
        page.wait_for_timeout(300)           # nobody answers; it must not stall
    assert inner(page).evaluate("window.saveAnswer") is False
    assert not dialogs.is_automation_running()
    assert any(level == "warning" and "dismissed" in m for level, m in logs)
    inner(page).evaluate("window.saveAnswer = undefined")
    click_async(inner(page), "#formSubmit")  # after automation: manual behaviour is back
    page.wait_for_timeout(300)
    assert len(seen) == 2
    seen[1].accept()
    page.wait_for_timeout(200)
    assert inner(page).evaluate("window.saveAnswer") is True


def test_popup_windows_get_the_listener(session):
    context, page, logs, seen = session
    dialogs.watch_dialogs(context, log_to(logs))
    observe(page, seen)
    with context.expect_page() as info:
        page.evaluate("window.open('about:blank')")
    popup = info.value
    popup.set_content(wrap(FORM))
    popup.wait_for_timeout(100)
    popup_seen = []
    observe(popup, popup_seen)
    click_async(popup.frames[1], "#formSubmit")
    popup.wait_for_timeout(300)
    assert len(popup_seen) == 1
    popup_seen[0].accept()
    popup.wait_for_timeout(200)
    assert popup.frames[1].evaluate("window.saveAnswer") is True


def test_log_never_contains_dialog_text(session):
    context, page, logs, seen = session
    dialogs.watch_dialogs(context, log_to(logs))
    observe(page, seen)
    click_async(inner(page), "#formSubmit")
    page.wait_for_timeout(300)
    seen[0].accept()
    assert logs and not any("Save changes" in m for _, m in logs)


# ---------------- pure unit tests (no browser) ----------------
class FakeDialog:
    type = "confirm"

    def __init__(self, fail=False):
        self.dismissed, self.fail = 0, fail

    def dismiss(self):
        if self.fail:
            raise RuntimeError("already handled")
        self.dismissed += 1


def test_nested_automation_depth():
    with dialogs.automation_running():
        with dialogs.automation_running():
            assert dialogs.is_automation_running()
        assert dialogs.is_automation_running()
    assert not dialogs.is_automation_running()


def test_automation_depth_restored_after_error():
    with pytest.raises(ValueError):
        with dialogs.automation_running():
            raise ValueError
    assert not dialogs.is_automation_running()


def test_handler_never_raises():
    dialogs.handle_dialog(FakeDialog())
    with dialogs.automation_running():
        dialogs.handle_dialog(FakeDialog(fail=True))             # dismiss() blows up
        dialogs.handle_dialog(FakeDialog(), lambda *a: 1 / 0)    # logger blows up


def test_idle_handler_does_not_touch_dialog():
    dialog = FakeDialog()
    dialogs.handle_dialog(dialog)
    assert dialog.dismissed == 0
