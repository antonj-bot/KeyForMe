"""Tests for manual SAVE / EXIT dialogs and the clearer UI log line.

Run from the project root:   python -m pytest tests/test_dialogs.py -v
Set KEYFORME_TEST_CHROMIUM to a browser executable to avoid channel="chrome".
"""
import os

import pytest

from app.browser import dialogs

FORM = """<html><body>
<button id="formSubmit" onclick="window.saveAnswer = confirm('Save changes?')">SAVE</button>
<button id="formExit" onclick="window.exitAnswer = confirm('Exit without saving?')">Exit</button>
<button id="formNotes" onclick="window.noteAnswer = confirm('Notes?')">Notes</button>
<a id="row-12345" href="#" onclick="window.rowAnswer = confirm('Open?'); return false">REPORT 12345 JOHN DOE</a>
<button onclick="window.noIdAnswer = confirm('No id?')">x</button>
<button id="alertBtn" onclick="alert('Saved'); window.alertDone = true">alert</button>
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


@pytest.fixture(autouse=True)
def _reset_click():
    dialogs._last_click = None
    yield
    dialogs._last_click = None


@pytest.fixture
def session(browser):
    context = browser.new_context()
    logs, seen = [], []
    page = context.new_page()
    yield context, page, logs, seen
    context.close()


def load(page, context=None):
    page.set_content(wrap(FORM))
    page.wait_for_timeout(150)


def observe(page, seen):
    """Test-only observer: records dialogs and takes no action on them."""
    page.on("dialog", lambda dialog: seen.append(dialog))


def inner(page):
    return page.frames[1]


def click_async(frame, selector):
    # A real click event; Playwright's own click() would be blocked by the dialog.
    frame.evaluate(f"setTimeout(() => document.querySelector('{selector}').click(), 0)")


def log_to(logs):
    return lambda message, level="info": logs.append((level, message))


def start(session):
    context, page, logs, seen = session
    dialogs.watch_dialogs(context, log_to(logs))
    load(page)
    observe(page, seen)
    return context, page, logs, seen


# ---------------------------------------------------------------- behaviour from before
def test_root_cause_without_listener_dialog_is_auto_cancelled(session):
    _, page, _, _ = session
    load(page)
    click_async(inner(page), "#formSubmit")
    page.wait_for_timeout(300)
    assert inner(page).evaluate("window.saveAnswer") is False


def test_manual_save_dialog_waits_for_user_then_ok(session):
    _, page, logs, seen = start(session)
    click_async(inner(page), "#formSubmit")
    page.wait_for_timeout(300)
    assert len(seen) == 1 and seen[0].type == "confirm"
    seen[0].accept()
    page.wait_for_timeout(200)
    assert inner(page).evaluate("window.saveAnswer") is True
    assert any("waiting for your answer" in m for _, m in logs)


def test_manual_save_dialog_cancel_is_respected(session):
    _, page, logs, seen = start(session)
    click_async(inner(page), "#formSubmit")
    page.wait_for_timeout(300)
    seen[0].dismiss()
    page.wait_for_timeout(200)
    assert inner(page).evaluate("window.saveAnswer") is False


def test_dialogs_during_automation_are_dismissed(session):
    _, page, logs, seen = start(session)
    with dialogs.automation_running():
        assert dialogs.is_automation_running()
        click_async(inner(page), "#formSubmit")
        page.wait_for_timeout(300)
    assert inner(page).evaluate("window.saveAnswer") is False
    assert not dialogs.is_automation_running()
    assert any(level == "warning" and "dismissed" in m for level, m in logs)
    inner(page).evaluate("window.saveAnswer = undefined")
    dialogs._last_click = None
    click_async(inner(page), "#formSubmit")
    page.wait_for_timeout(300)
    assert len(seen) == 2
    seen[1].accept()
    page.wait_for_timeout(200)
    assert inner(page).evaluate("window.saveAnswer") is True


def test_popup_windows_get_the_listener(session):
    context, page, logs, seen = session
    dialogs.watch_dialogs(context, log_to(logs))
    page.set_content("<html><body>main</body></html>")
    with context.expect_page() as info:
        page.evaluate("window.open('about:blank')")
    popup = info.value
    load(popup)
    popup_seen = []
    observe(popup, popup_seen)
    click_async(popup.frames[1], "#formSubmit")
    popup.wait_for_timeout(300)
    assert len(popup_seen) == 1
    popup_seen[0].accept()
    popup.wait_for_timeout(200)
    assert popup.frames[1].evaluate("window.saveAnswer") is True
    assert any("after you clicked SAVE" in m for _, m in logs)          # the hook works in popups too


# ---------------------------------------------------------------- the clearer log line
def waiting(logs):
    return [m for _, m in logs if "waiting for your answer" in m]


def test_log_names_the_save_button(session):
    _, page, logs, seen = start(session)
    click_async(inner(page), "#formSubmit")
    page.wait_for_timeout(300)
    assert waiting(logs) == ["Site confirm dialog (after you clicked SAVE) is waiting for your answer in Chrome"]
    seen[0].accept()


def test_log_names_the_exit_button(session):
    _, page, logs, seen = start(session)
    click_async(inner(page), "#formExit")
    page.wait_for_timeout(300)
    assert waiting(logs) == ["Site confirm dialog (after you clicked EXIT) is waiting for your answer in Chrome"]
    seen[0].accept()


def test_log_names_an_alert_without_a_known_button(session):
    _, page, logs, seen = start(session)
    click_async(inner(page), "#alertBtn")                          # not a form* id: no label
    page.wait_for_timeout(300)
    assert waiting(logs) == ["Site alert is waiting for your answer in Chrome"]
    seen[0].accept()


def test_other_form_controls_show_their_id(session):
    _, page, logs, seen = start(session)
    click_async(inner(page), "#formNotes")
    page.wait_for_timeout(300)
    assert waiting(logs) == ["Site confirm dialog (after you clicked #formNotes) is waiting for your answer in Chrome"]
    seen[0].accept()


def test_unknown_or_data_like_ids_are_never_shown(session):
    _, page, logs, seen = start(session)
    click_async(inner(page), "#row-12345")                      # an id that could carry report data
    page.wait_for_timeout(300)
    seen[0].accept()
    click_async(inner(page), "button:not([id])")
    page.wait_for_timeout(300)
    seen[1].accept()
    messages = waiting(logs)
    assert messages == ["Site confirm dialog is waiting for your answer in Chrome"] * 2
    assert not any("12345" in m or "JOHN" in m for _, m in logs)


def test_old_click_is_not_blamed_for_a_later_dialog(session):
    _, page, logs, seen = start(session)
    click_async(inner(page), "#formExit")
    page.wait_for_timeout(300)
    seen[0].accept()
    dialogs._last_click = (dialogs._last_click[0] - 10, dialogs._last_click[1])   # pretend it was 10 s ago
    inner(page).evaluate("setTimeout(() => confirm('later'), 0)")
    page.wait_for_timeout(300)
    assert waiting(logs)[-1] == "Site confirm dialog is waiting for your answer in Chrome"
    seen[1].accept()


def test_log_never_contains_dialog_text(session):
    _, page, logs, seen = start(session)
    click_async(inner(page), "#formSubmit")
    page.wait_for_timeout(300)
    seen[0].accept()
    assert logs and not any("Save changes" in m for _, m in logs)


def test_page_that_loaded_before_watching_still_gets_the_hook(session):
    context, page, logs, seen = session
    load(page)                                                     # loaded BEFORE watch_dialogs
    dialogs.watch_dialogs(context, log_to(logs))
    observe(page, seen)
    click_async(inner(page), "#formSubmit")
    page.wait_for_timeout(300)
    assert any("after you clicked SAVE" in m for m in waiting(logs))
    seen[0].accept()


# ---------------------------------------------------------------- pure unit tests (no browser)
class FakeDialog:
    type = "confirm"

    def __init__(self, kind="confirm", fail=False):
        self.type, self.dismissed, self.fail = kind, 0, fail

    def dismiss(self):
        if self.fail:
            raise RuntimeError("already handled")
        self.dismissed += 1


class FakeMessage:
    def __init__(self, text):
        self.text = text


def test_label_rules():
    assert dialogs.label_for_control("formSubmit") == "SAVE" and dialogs.label_for_control("formExit") == "EXIT"
    assert dialogs.label_for_control("formReject") == "#formReject"
    for hidden in ("", None, "row-12345", "case_12345", "formABC-12345", "form1", "x" * 60):
        assert dialogs.label_for_control(hidden) == ""


def test_recent_click_window():
    dialogs.record_click("formSubmit", now=100.0)
    assert dialogs.recent_click_label(now=102.9) == "SAVE"
    assert dialogs.recent_click_label(now=103.5) == ""
    assert dialogs.recent_click_label(now=99.0) == ""                 # a click "from the future" is ignored
    dialogs._last_click = None
    assert dialogs.recent_click_label() == ""


def test_describe_dialog_wording():
    assert dialogs.describe_dialog("confirm", "SAVE") == "Site confirm dialog (after you clicked SAVE) is waiting for your answer in Chrome"
    assert dialogs.describe_dialog("alert", "") == "Site alert is waiting for your answer in Chrome"
    assert dialogs.describe_dialog("prompt", "EXIT") == "Site prompt (after you clicked EXIT) is waiting for your answer in Chrome"
    assert "leave this page" in dialogs.describe_dialog("beforeunload", "")


def test_console_handler_only_reads_its_own_messages_and_never_raises():
    dialogs.handle_console_message(FakeMessage("some site log"))
    dialogs.handle_console_message(FakeMessage(dialogs.CLICK_PREFIX + "{not json"))
    dialogs.handle_console_message(object())
    assert dialogs._last_click is None
    dialogs.handle_console_message(FakeMessage(dialogs.CLICK_PREFIX + '{"id": "formSubmit"}'))
    assert dialogs.recent_click_label() == "SAVE"


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
        dialogs.handle_dialog(FakeDialog(fail=True))
        dialogs.handle_dialog(FakeDialog(), lambda *a: 1 / 0)


def test_idle_handler_does_not_touch_dialog():
    dialog = FakeDialog()
    dialogs.handle_dialog(dialog)
    assert dialog.dismissed == 0
