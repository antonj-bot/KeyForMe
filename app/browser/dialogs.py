"""Let eCrash's own JavaScript dialogs reach the user.

Playwright silently dismisses every alert/confirm/prompt/beforeunload dialog
when no "dialog" listener is registered. For eCrash that means clicking
SAVE (#formSubmit) or EXIT (#formExit) by hand does nothing: the site's
"Save changes?" confirm is answered "Cancel" before you can see it.

This module registers a listener that leaves the dialog open so you answer it
yourself, exactly as on the normal site. While KeyForMe is extracting or
filling a form it keeps the previous behaviour (dismiss), so automation can
never stall on a dialog nobody is looking at.
"""
from __future__ import annotations

from contextlib import contextmanager

_automation_depth = 0


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


def handle_dialog(dialog, log=None) -> None:
    """Page 'dialog' listener. Never raises. Logs the type only, never the text."""
    kind = getattr(dialog, "type", "dialog")
    if _automation_depth:
        try:
            dialog.dismiss()
        except Exception:
            pass
        _say(log, f"Site dialog ({kind}) dismissed while KeyForMe was working", "warning")
        return
    # Manual use: do nothing. The browser keeps the dialog open for you to answer.
    _say(log, f"Site dialog ({kind}) is waiting for your answer")


def watch_dialogs(context, log=None) -> None:
    """Attach the listener to every current and future page and popup."""
    attached = []

    def attach(page) -> None:
        attached[:] = [known for known in attached if not _closed(known)]
        if any(page is known for known in attached):
            return
        attached.append(page)
        page.on("dialog", lambda dialog: handle_dialog(dialog, log))

    context.on("page", attach)
    for page in list(context.pages):
        attach(page)


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
