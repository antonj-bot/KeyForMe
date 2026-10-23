"""Let eCrash's own JavaScript dialogs reach the user, and say clearly what is waiting.

Playwright silently dismisses every alert/confirm/prompt/beforeunload dialog when no
"dialog" listener is registered. For eCrash that means clicking SAVE (#formSubmit) or
EXIT (#formExit) by hand does nothing: the site's "Save changes?" confirm is answered
"Cancel" before you can see it.

This module registers a listener that leaves the dialog open so you answer it yourself,
exactly as on the normal site. While KeyForMe is extracting or filling a form it keeps the
previous behaviour (dismiss), so automation can never stall on a dialog nobody is looking at.

The UI log line names the button that opened the dialog ("after you clicked SAVE"). That works
through a tiny click hook injected into every page and iframe; it reports only the id of a
known form button, never page text, so no report data reaches the log.
"""
from __future__ import annotations

import json
import re
import time
from contextlib import contextmanager

_automation_depth = 0

CLICK_PREFIX = "__kfm_click__:"
CLICK_WINDOW_SECONDS = 3.0
# Control ids that are safe and useful to show. Anything else is reported generically.
_BUTTON_LABELS = {"formSubmit": "SAVE", "formExit": "EXIT"}
_CONTROL_ID = re.compile(r"^form[A-Za-z]{2,30}$")

CLICK_SCRIPT = """
(() => {
  if (window.__kfmClickHook) return;
  window.__kfmClickHook = true;
  document.addEventListener('click', event => {
    try {
      const el = event.target.closest('button, input[type=button], input[type=submit], a, [role=button]');
      if (el && el.id) console.debug('__kfm_click__:' + JSON.stringify({ id: String(el.id).slice(0, 40) }));
    } catch (_) {}
  }, true);
})();
"""

_last_click: tuple[float, str] | None = None

_KIND_TEXT = {
    "confirm": "confirm dialog",
    "alert": "alert",
    "prompt": "prompt",
    "beforeunload": "'leave this page?' prompt",
}


@contextmanager
def automation_running():
    """Dialogs raised inside this block are dismissed automatically."""
    global _automation_depth
    _automation_depth += 1
    try:
        yield
    finally:
        _automation_depth -= 1


def is_automation_running() -> bool:
    return _automation_depth > 0


# ---------------------------------------------------------------- which button was clicked
def label_for_control(control_id: str) -> str:
    """Display label for a clicked control id, or "" when it should not be shown."""
    control_id = str(control_id or "")
    if control_id in _BUTTON_LABELS:
        return _BUTTON_LABELS[control_id]
    return f"#{control_id}" if _CONTROL_ID.fullmatch(control_id) else ""


def record_click(control_id: str, now: float | None = None) -> None:
    global _last_click
    _last_click = (time.monotonic() if now is None else now, str(control_id or ""))


def recent_click_label(now: float | None = None) -> str:
    """Label of the control clicked within the last few seconds, else ""."""
    if _last_click is None:
        return ""
    when, control_id = _last_click
    now = time.monotonic() if now is None else now
    if not 0 <= now - when <= CLICK_WINDOW_SECONDS:
        return ""
    return label_for_control(control_id)


def handle_console_message(message) -> None:
    """Page 'console' listener: remember the click reported by CLICK_SCRIPT. Never raises."""
    try:
        text = message.text
        if not text.startswith(CLICK_PREFIX):
            return
        record_click(json.loads(text[len(CLICK_PREFIX):]).get("id", ""))
    except Exception:
        pass


# ---------------------------------------------------------------- the dialog listener
def describe_dialog(kind: str, label: str) -> str:
    what = _KIND_TEXT.get(kind, f"{kind} dialog")
    origin = f" (after you clicked {label})" if label else ""
    return f"Site {what}{origin} is waiting for your answer in Chrome"


def handle_dialog(dialog, log=None) -> None:
    """Page 'dialog' listener. Never raises. Logs the type and button only, never the text."""
    kind = getattr(dialog, "type", "dialog")
    if _automation_depth:
        try:
            dialog.dismiss()
        except Exception:
            pass
        _say(log, f"Site {_KIND_TEXT.get(kind, kind)} dismissed while KeyForMe was working", "warning")
        return
    # Manual use: do nothing. The browser keeps the dialog open for you to answer.
    _say(log, describe_dialog(kind, recent_click_label()))


def watch_dialogs(context, log=None) -> None:
    """Attach the listeners to every current and future page and popup."""
    attached = []

    def attach(page) -> None:
        attached[:] = [known for known in attached if not _closed(known)]
        if any(page is known for known in attached):
            return
        attached.append(page)
        page.on("dialog", lambda dialog: handle_dialog(dialog, log))
        page.on("console", lambda message: handle_console_message(message))

    try:
        context.add_init_script(CLICK_SCRIPT)               # every frame of every page loaded from now on
    except Exception:
        pass                                                # without it the message is just less specific
    context.on("page", attach)
    for page in list(context.pages):
        attach(page)
        for frame in list(page.frames):                     # pages that are already loaded
            try:
                frame.evaluate(CLICK_SCRIPT)
            except Exception:
                pass


def _closed(page) -> bool:
    try:
        return page.is_closed()
    except Exception:
        return True


def _say(log, message, level="info") -> None:
    if log is None:
        return
    try:
        log(message, level)
    except Exception:
        pass
