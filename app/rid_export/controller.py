"""Hotkey -> Report ID -> Excel controller.

Threads:
  * main thread    : tick() polls the hotkeys and runs the Playwright lookup
                     (same thread that owns Playwright; no cross-thread calls)
  * widget thread  : owns every Tk object
  * Excel worker   : owns every Excel COM object it writes through
"""
from __future__ import annotations

import queue
import threading

from . import config, sound_effects
from .excel_writer import ExcelWriter, list_open_worksheets
from .finder import find_text_in_all_pages
from .text_utils import clean_rid_text

_JUNK = ("[", "]", "{", "}")


class RidExportController:
    def __init__(self, context, log=None, skip_page=None, *, writer=None,
                 keyboard_module=None, widget_factory=None, list_worksheets=None,
                 finder=find_text_in_all_pages):
        self.context = context
        self._log_fn = log
        self.skip_page = skip_page
        self.writer = writer if writer is not None else ExcelWriter()
        self._keyboard = keyboard_module
        self._widget_factory = widget_factory
        self.list_worksheets = list_worksheets or list_open_worksheets
        self.finder = finder

        self.hotkeys_enabled = threading.Event()   # OFF until the user turns it on
        self.target = None                         # ExcelTarget picked in the widget
        self._tasks = queue.Queue()
        self._ui = queue.Queue()
        self._held = {"LEFT": False, "RIGHT": False}
        self._hotkey_error_logged = False
        self._closed = False
        self._widget_thread = None
        self._worker_thread = None
        self._ready = threading.Event()
        self.widget_error = None

    # ---------------- lifecycle ----------------
    def start(self):
        if self._keyboard is None:
            try:
                import keyboard
                self._keyboard = keyboard
            except Exception:
                self._log("Report ID hotkeys unavailable: 'keyboard' package missing", "warning")

        self._worker_thread = threading.Thread(
            target=self._excel_worker, name="KeyForMe-RID-Excel", daemon=True)
        self._worker_thread.start()
        self._widget_thread = threading.Thread(
            target=self._widget_main, name="KeyForMe-RID-Widget", daemon=True)
        self._widget_thread.start()
        self._ready.wait(5)
        if self.widget_error:
            self._log(f"Report ID widget could not start ({self.widget_error})", "warning")
        else:
            self._log("Report ID widget ready. Pick a worksheet, then turn hotkeys ON.")

    def close(self):
        if self._closed:
            return
        self._closed = True
        self.hotkeys_enabled.clear()
        self._ui.put(("close",))
        self._tasks.put(None)
        if self._widget_thread is not None:
            self._widget_thread.join(timeout=2)

    # ---------------- widget thread ----------------
    def _widget_main(self):
        try:
            _co_initialize()
            factory = self._widget_factory
            if factory is None:
                from .widget import RidWidget
                factory = RidWidget
            widget = factory(
                hotkeys_enabled_event=self.hotkeys_enabled,
                ui_queue=self._ui,
                list_worksheets=self.list_worksheets,
                on_target=self._set_target,
                enable_blocker=self._enable_blocker,
            )
        except Exception as error:
            self.widget_error = type(error).__name__
            self._ready.set()
            return
        self._ready.set()
        widget.run()

    def _set_target(self, target):
        self.target = target
        self._log(f"Report ID target: {target.label}")

    def _enable_blocker(self):
        if self._keyboard is None:
            return "The 'keyboard' package is not installed, so hotkeys are unavailable."
        if self.target is None:
            return "Pick a worksheet first (click the 📊 button)."
        return None

    # ---------------- Excel worker thread ----------------
    def _excel_worker(self):
        _co_initialize()
        while True:
            item = self._tasks.get()
            if item is None:
                return
            target, cell, text, side = item
            try:
                self.writer.write(target, cell, text)
                self._ui.put(("text", text))
                self._log(f"Report ID written to Excel ({side})", "success")
            except Exception as error:
                sound_effects.play_fail()
                self._log(f"Excel write failed ({type(error).__name__}) — is the workbook open?", "warning")

    # ---------------- main thread ----------------
    def tick(self):
        """Call often from the main loop. Never raises."""
        try:
            self._poll_hotkeys()
        except Exception as error:
            if not self._hotkey_error_logged:
                self._hotkey_error_logged = True
                self._log(f"Report ID hotkey check failed ({type(error).__name__})", "warning")

    def _poll_hotkeys(self):
        enabled = self.hotkeys_enabled.is_set() and self._keyboard is not None
        for side, key, cell in (("LEFT", config.HOTKEY_LEFT, config.LEFT_CELL),
                                ("RIGHT", config.HOTKEY_RIGHT, config.RIGHT_CELL)):
            down = bool(enabled and self._keyboard.is_pressed(key))
            if down and not self._held[side]:
                self._held[side] = True      # fire once per key press
                self.process_hotkey(cell, side)
            elif not down:
                self._held[side] = False

    def process_hotkey(self, cell, side):
        if not self.hotkeys_enabled.is_set():
            return                            # OFF: no extraction, no paste, no sound
        target = self.target
        if target is None:
            sound_effects.play_fail()
            self._log("Pick a worksheet first (📊 button)", "warning")
            return
        try:
            raw, _page = self.finder(self.context, config.RID_SELECTOR,
                                     config.SCAN_TIMEOUT_MS, self.skip_page)
            rid = clean_rid_text(raw)
            if rid and rid not in _JUNK:
                sound_effects.play_success()
                self._tasks.put((target, cell, rid, side))
            else:
                sound_effects.play_fail()
                self._log("Report ID was empty", "warning")
        except Exception as error:
            sound_effects.play_fail()
            self._log(f"Report ID not found on the open page ({type(error).__name__})", "warning")

    # ---------------- helpers ----------------
    def _log(self, message, level="info"):
        if self._log_fn is not None:
            try:
                self._log_fn(message, level)
            except Exception:
                pass


def _co_initialize():
    try:
        import pythoncom
        pythoncom.CoInitialize()
    except Exception:
        pass  # not on Windows / pywin32 missing (tests)
