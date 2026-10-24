"""Tests for the Report ID -> Excel feature.

Run from the project root:   python -m pytest tests/test_rid_export.py -v

Browser tests use Chrome (channel="chrome"); set KEYFORME_TEST_CHROMIUM to a
browser executable path to use another one. They are skipped if no browser starts.
"""
import importlib
import os
import sys
import threading
import time
import types
from unittest.mock import MagicMock

import pytest

from app.rid_export import config, excel_writer, sound_effects as sounds
from app.rid_export.controller import RidExportController
from app.rid_export.excel_writer import ExcelTarget, ExcelWriter, write_next_empty
from app.rid_export.finder import find_text_in_all_pages
from app.rid_export.text_utils import clean_rid_text

RID_HTML = '<div id="formStatus"><div>Report Id: 9000000001</div><div>x</div></div>'
TARGET = ExcelTarget("Book1.xlsx", "Sheet1")


# ---------------------------------------------------------------- fakes
class FakeCell:
    def __init__(self):
        self.Value = None


class FakeSheet:
    def __init__(self, Name="Sheet1", Visible=-1, filled=()):
        self.Name, self.Visible = Name, Visible
        self.cells, self.Parent = {}, None
        for (r, c), v in dict(filled).items():
            self.Cells(r, c).Value = v

    def Cells(self, row, col):
        return self.cells.setdefault((row, col), FakeCell())


class FakeBook:
    def __init__(self, Name, sheets, Path="C:\\x"):
        self.Name, self.Path, self.saves = Name, Path, 0
        self.sheets = {s.Name.lower(): s for s in sheets}
        self.Worksheets = _Sheets(sheets, self)

    def Save(self):
        self.saves += 1


class _Sheets(list):
    def __init__(self, sheets, book):
        super().__init__(sheets)
        self.by_name = {s.Name: s for s in sheets}
        for s in sheets:
            s.Parent = book

    def __call__(self, name):
        return self.by_name[name]


class FakeExcel:
    def __init__(self, books):
        self.Workbooks = books


class FakeKeyboard:
    def __init__(self):
        self.pressed = set()

    def is_pressed(self, key):
        return key in self.pressed


class FakeWidget:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def run(self):
        return


class Recorder:
    def __init__(self, monkeypatch):
        self.events = []
        monkeypatch.setattr(sounds, "play_success", lambda: self.events.append("ok"))
        monkeypatch.setattr(sounds, "play_fail", lambda: self.events.append("fail"))


class FakeWriter:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def write(self, target, cell, text):
        if self.fail:
            raise RuntimeError("boom")
        self.calls.append((target, cell, text))
        return 10


def make_controller(context=None, writer=None, finder=None, kb=None, logs=None):
    logs = logs if logs is not None else []
    kwargs = {}
    if finder is not None:
        kwargs["finder"] = finder
    controller = RidExportController(
        context, log=lambda m, level="info": logs.append((level, m)),
        writer=writer or FakeWriter(), keyboard_module=kb or FakeKeyboard(),
        widget_factory=FakeWidget, list_worksheets=lambda: [], **kwargs)
    controller.start()
    return controller


def wait_for(predicate, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if predicate():
            return True
        time.sleep(0.02)
    return False


# ---------------------------------------------------------------- pure logic
@pytest.mark.parametrize("raw,expected", [
    ("Report Id: 9000000001", "9000000001"),
    ("report id:9000000001", "9000000001"),
    ("  REPORT   ID:   55  ", "55"),
    ("9000000001", "9000000001"),
    ("", ""), (None, ""),
])
def test_clean_rid_text(raw, expected):
    assert clean_rid_text(raw) == expected


def test_config_matches_ridtodpt():
    assert (config.HOTKEY_LEFT, config.HOTKEY_RIGHT) == ("[", "]")
    assert (config.LEFT_CELL, config.RIGHT_CELL) == ("C10", "I10")
    assert config.RID_SELECTOR == "#formStatus > div:nth-child(1)"


def test_col_row_helpers():
    assert excel_writer.get_col_row("C10") == ("C", 10)
    assert [excel_writer.col_to_num(c) for c in ("A", "C", "I", "Z", "AA")] == [1, 3, 9, 26, 27]


def test_write_next_empty_row():
    ws = FakeSheet(filled={(10, 3): "a", (11, 3): "b", (13, 3): "later"})
    assert write_next_empty(ws, "C10", "new") == 12
    assert ws.Cells(12, 3).Value == "new"
    assert write_next_empty(ws, "C10", "newer") == 14   # skips the gap-filled row 13
    assert write_next_empty(ws, "I10", "m") == 10       # other column is independent


def test_empty_string_counts_as_empty():
    ws = FakeSheet(filled={(10, 3): ""})
    assert write_next_empty(ws, "C10", "x") == 10


def test_target_label():
    assert ExcelTarget("B.xlsx", "S").label == "B.xlsx  ›  S"


# ---------------------------------------------------------------- Excel COM layer (faked)
def test_list_open_worksheets(monkeypatch):
    books = [
        FakeBook("Book1.xlsx", [FakeSheet("Sheet1"), FakeSheet("Hidden", Visible=0)]),
        FakeBook("PERSONAL.XLSB", [FakeSheet("Sheet1")]),
        FakeBook("Other.xlsx", [FakeSheet("Data")]),
    ]
    monkeypatch.setitem(sys.modules, "pythoncom", types.SimpleNamespace(CoInitialize=lambda: None))
    monkeypatch.setattr(excel_writer, "_excel_app", lambda: FakeExcel(books))
    assert excel_writer.list_open_worksheets() == [
        ExcelTarget("Book1.xlsx", "Sheet1"), ExcelTarget("Other.xlsx", "Data")]


def test_list_open_worksheets_excel_not_running(monkeypatch):
    def boom():
        raise OSError("no excel")
    monkeypatch.setitem(sys.modules, "pythoncom", types.SimpleNamespace(CoInitialize=lambda: None))
    monkeypatch.setattr(excel_writer, "_excel_app", boom)
    assert excel_writer.list_open_worksheets() == []


def test_writer_writes_and_caches(monkeypatch):
    book = FakeBook("Book1.xlsx", [FakeSheet("Sheet1")])
    monkeypatch.setattr(excel_writer, "_excel_app", lambda: FakeExcel([book]))
    writer = ExcelWriter()
    assert writer.write(TARGET, "C10", "111") == 10
    assert writer.write(TARGET, "C10", "222") == 11
    assert book.Worksheets("Sheet1").Cells(11, 3).Value == "222"


def test_writer_saves_every_10_but_not_unsaved(monkeypatch):
    saved = FakeBook("Book1.xlsx", [FakeSheet("Sheet1")])
    unsaved = FakeBook("New.xlsx", [FakeSheet("Sheet1")], Path="")
    monkeypatch.setattr(excel_writer, "_excel_app", lambda: FakeExcel([saved, unsaved]))
    writer = ExcelWriter()
    for i in range(10):
        writer.write(TARGET, "C10", str(i))
    assert saved.saves == 1
    writer2 = ExcelWriter()
    for i in range(10):
        writer2.write(ExcelTarget("New.xlsx", "Sheet1"), "C10", str(i))
    assert unsaved.saves == 0


def test_writer_workbook_closed_raises(monkeypatch):
    monkeypatch.setattr(excel_writer, "_excel_app", lambda: FakeExcel([]))
    monkeypatch.setattr(excel_writer.time, "sleep", lambda s: None)
    with pytest.raises(FileNotFoundError):
        ExcelWriter().write(TARGET, "C10", "1")


def test_writer_retries_when_excel_busy(monkeypatch):
    book = FakeBook("Book1.xlsx", [FakeSheet("Sheet1")])
    attempts = {"n": 0}

    def flaky():
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise OSError("Call was rejected by callee")
        return FakeExcel([book])

    monkeypatch.setattr(excel_writer, "_excel_app", flaky)
    monkeypatch.setattr(excel_writer.time, "sleep", lambda s: None)
    assert ExcelWriter().write(TARGET, "C10", "1") == 10
    assert attempts["n"] == 3


# ---------------------------------------------------------------- controller (no browser)
def test_hotkeys_off_does_nothing(monkeypatch):
    rec = Recorder(monkeypatch)
    calls = []
    kb = FakeKeyboard()
    kb.pressed = {"[", "]"}
    c = make_controller(finder=lambda *a: calls.append(a) or ("1", None), kb=kb)
    c.target = TARGET
    c.tick()
    c.process_hotkey("C10", "LEFT")      # even a direct call is ignored while OFF
    assert calls == [] and rec.events == []
    c.close()


def test_no_worksheet_gives_fail_sound(monkeypatch):
    rec = Recorder(monkeypatch)
    logs = []
    c = make_controller(logs=logs)
    c.hotkeys_enabled.set()
    c.process_hotkey("C10", "LEFT")
    assert rec.events == ["fail"] and any("Pick a worksheet" in m for _, m in logs)
    c.close()


def test_enable_blocker_messages():
    c = make_controller()
    assert "Pick a worksheet" in c._enable_blocker()
    c.target = TARGET
    assert c._enable_blocker() is None
    c._keyboard = None
    assert "keyboard" in c._enable_blocker()
    c.close()


def test_left_and_right_hotkeys_fire_once_per_press(monkeypatch):
    rec = Recorder(monkeypatch)
    writer, kb = FakeWriter(), FakeKeyboard()
    c = make_controller(writer=writer, kb=kb, finder=lambda *a: ("Report Id: 42", None))
    c.target = TARGET
    c.hotkeys_enabled.set()
    kb.pressed = {"["}
    for _ in range(5):                    # key held for 5 ticks
        c.tick()
    kb.pressed = set()
    c.tick()
    kb.pressed = {"]"}
    c.tick()
    assert wait_for(lambda: len(writer.calls) == 2)
    assert writer.calls == [(TARGET, "C10", "42"), (TARGET, "I10", "42")]
    assert rec.events == ["ok", "ok"]
    kb.pressed = {"["}                    # second separate press fires again
    c.tick()
    assert wait_for(lambda: len(writer.calls) == 3)
    c.close()


@pytest.mark.parametrize("text", ["[", "]", "{", "}", "", "Report Id:"])
def test_junk_values_fail(monkeypatch, text):
    rec = Recorder(monkeypatch)
    writer = FakeWriter()
    c = make_controller(writer=writer, finder=lambda *a: (text, None))
    c.target = TARGET
    c.hotkeys_enabled.set()
    c.process_hotkey("C10", "LEFT")
    time.sleep(0.1)
    assert rec.events == ["fail"] and writer.calls == []
    c.close()


def test_finder_error_gives_fail_sound(monkeypatch):
    rec = Recorder(monkeypatch)

    def nope(*a):
        raise LookupError("none")

    c = make_controller(finder=nope)
    c.target = TARGET
    c.hotkeys_enabled.set()
    c.process_hotkey("C10", "LEFT")
    assert rec.events == ["fail"]
    c.close()


def test_excel_failure_gives_fail_sound_and_no_ui_text(monkeypatch):
    rec = Recorder(monkeypatch)
    logs = []
    c = make_controller(writer=FakeWriter(fail=True), logs=logs,
                        finder=lambda *a: ("Report Id: 9", None))
    c.target = TARGET
    c.hotkeys_enabled.set()
    c.process_hotkey("C10", "LEFT")
    assert wait_for(lambda: "fail" in rec.events)
    assert c._ui.empty() or c._ui.get_nowait()[0] != "text"
    c.close()


def test_success_updates_widget_text_and_logs_no_rid_value(monkeypatch):
    Recorder(monkeypatch)
    logs = []
    c = make_controller(logs=logs, finder=lambda *a: ("Report Id: 777", None))
    c.target = TARGET
    c.hotkeys_enabled.set()
    c.process_hotkey("C10", "LEFT")
    assert wait_for(lambda: not c._ui.empty())
    assert c._ui.get_nowait() == ("text", "777")
    assert not any("777" in m for _, m in logs)      # report data stays out of the UI log
    c.close()


def test_tick_never_raises():
    class Broken:
        def is_pressed(self, key):
            raise RuntimeError("hook failed")
    logs = []
    c = make_controller(kb=Broken(), logs=logs)
    c.hotkeys_enabled.set()
    c.tick(); c.tick()
    assert sum("hotkey check failed" in m for _, m in logs) == 1   # logged once
    c.close()


def test_close_is_idempotent_and_clears_hotkeys():
    c = make_controller()
    c.hotkeys_enabled.set()
    c.close(); c.close()
    assert not c.hotkeys_enabled.is_set()


def test_widget_failure_does_not_crash_app():
    def bad_factory(**kw):
        raise RuntimeError("no display")
    logs = []
    c = RidExportController(None, log=lambda m, l="info": logs.append(m),
                            writer=FakeWriter(), keyboard_module=FakeKeyboard(),
                            widget_factory=bad_factory)
    c.start()
    assert c.widget_error == "RuntimeError"
    assert any("could not start" in m for m in logs)
    c.tick(); c.close()


# ---------------------------------------------------------------- widget (tkinter faked)
@pytest.fixture
def widget_module(monkeypatch):
    fake_tk = MagicMock(name="tkinter")
    fake_tk.TclError = Exception
    fake_tk.Tk.return_value.winfo_screenwidth.return_value = 1920
    fake_tk.Tk.return_value.winfo_x.return_value = 1000
    fake_tk.Tk.return_value.winfo_y.return_value = 20
    monkeypatch.setitem(sys.modules, "tkinter", fake_tk)
    sys.modules.pop("app.rid_export.widget", None)
    module = importlib.import_module("app.rid_export.widget")
    yield module, fake_tk
    sys.modules.pop("app.rid_export.widget", None)


def make_widget(module, targets=(), blocker=lambda: None):
    import queue as q
    picked = []
    event = threading.Event()
    widget = module.RidWidget(event, q.Queue(), lambda: list(targets), picked.append, blocker)
    return widget, event, picked


def test_widget_starts_with_hotkeys_off(widget_module):
    module, _ = widget_module
    widget, event, _ = make_widget(module)
    assert not event.is_set()


def test_widget_toggle_on_off_and_blocked(widget_module):
    module, tk = widget_module
    widget, event, _ = make_widget(module, blocker=lambda: "Pick a worksheet first")
    widget.toggle_hotkeys()
    assert not event.is_set()
    tk.messagebox.showinfo.assert_called_once()
    widget.enable_blocker = lambda: None
    widget.toggle_hotkeys()
    assert event.is_set()
    widget.toggle_hotkeys()
    assert not event.is_set()


def test_widget_queue_text_and_close(widget_module):
    module, _ = widget_module
    widget, _, _ = make_widget(module)
    widget.ui_queue.put(("text", "123"))
    widget.process_ui_queue()
    widget.canvas.itemconfig.assert_any_call(widget.text_id, text="Last pasted:\n123")
    widget.ui_queue.put(("close",))
    widget.process_ui_queue()
    widget.root.destroy.assert_called_once()


def test_widget_long_text_truncated(widget_module):
    module, _ = widget_module
    widget, _, _ = make_widget(module)
    widget.update_text("x" * 100)
    text = widget.canvas.itemconfig.call_args.kwargs["text"]
    assert text.endswith("...") and len(text) < 90


def test_widget_pick_worksheet_selects_listed_item(widget_module):
    module, tk = widget_module
    targets = [ExcelTarget("A.xlsx", "S1"), ExcelTarget("B.xlsx", "S2")]
    buttons = {}
    tk.Button.side_effect = lambda *a, **kw: buttons.setdefault(kw.get("text"), kw) and MagicMock()
    tk.Listbox.return_value.curselection.return_value = (1,)
    widget, _, picked = make_widget(module, targets)
    buttons.clear()
    widget.pick_worksheet()
    listbox = tk.Listbox.return_value
    assert [c.args[1] for c in listbox.insert.call_args_list] == [t.label for t in targets]
    buttons["Select"]["command"]()
    assert picked == [targets[1]]


def test_widget_pick_worksheet_excel_error_shows_message(widget_module):
    module, tk = widget_module
    widget, _, picked = make_widget(module)
    widget.list_worksheets = lambda: (_ for _ in ()).throw(OSError("x"))
    widget.pick_worksheet()
    messages = [c.kwargs.get("text") for c in tk.Label.return_value.config.call_args_list]
    assert any("Could not read Excel" in (m or "") for m in messages) and picked == []


def test_widget_mute_button(widget_module):
    module, _ = widget_module
    sounds.set_muted(False)
    widget, _, _ = make_widget(module)
    widget.toggle_mute()
    assert sounds.is_muted()
    widget.toggle_mute()
    assert not sounds.is_muted()


# ---------------------------------------------------------------- real browser
@pytest.fixture(scope="module")
def browser_context():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as p:
        exe = os.environ.get("KEYFORME_TEST_CHROMIUM")
        try:
            browser = (p.chromium.launch(executable_path=exe) if exe
                       else p.chromium.launch(channel="chrome"))
        except Exception as error:
            pytest.skip(f"no browser available ({type(error).__name__})")
        context = browser.new_context()
        yield context
        browser.close()


def _attr(html):
    return html.replace("&", "&amp;").replace('"', "&quot;")


def nested(html):
    """Report ID two iframes deep."""
    middle = f'<iframe srcdoc="{_attr(html)}"></iframe>'
    return f'<html><body><iframe srcdoc="{_attr(middle)}"></iframe></body></html>'


def test_finder_main_page(browser_context):
    page = browser_context.new_page()
    page.set_content(f"<html><body>{RID_HTML}</body></html>")
    text, found = find_text_in_all_pages(browser_context, config.RID_SELECTOR)
    assert text == "Report Id: 9000000001" and found is page
    page.close()


def test_finder_inside_nested_iframes(browser_context):
    page = browser_context.new_page()
    page.set_content(nested(RID_HTML))
    text, found = find_text_in_all_pages(browser_context, config.RID_SELECTOR)
    assert clean_rid_text(text) == "9000000001" and found is page
    page.close()


def test_finder_popup_and_skip_page(browser_context):
    main = browser_context.new_page()
    main.set_content("<html><body>Dashboard</body></html>")
    with browser_context.expect_page() as info:
        main.evaluate("window.open('about:blank')")
    popup = info.value
    popup.set_content(f"<html><body>{RID_HTML}</body></html>")
    _, found = find_text_in_all_pages(browser_context, config.RID_SELECTOR)
    assert found is popup
    with pytest.raises(LookupError):
        find_text_in_all_pages(browser_context, config.RID_SELECTOR, 300,
                               skip_page=lambda p: p is popup)
    popup.close(); main.close()


def test_finder_not_found_and_hidden(browser_context):
    page = browser_context.new_page()
    page.set_content('<html><body><div id="formStatus" style="display:none"><div>Report Id: 1</div></div></body></html>')
    with pytest.raises(LookupError):
        find_text_in_all_pages(browser_context, config.RID_SELECTOR, 300)
    page.close()


def test_end_to_end_hotkeys_to_excel(browser_context, monkeypatch):
    """Real Chrome page + real controller; only keyboard and Excel are faked."""
    rec = Recorder(monkeypatch)
    page = browser_context.new_page()
    page.set_content(nested(RID_HTML))
    book = FakeBook("Book1.xlsx", [FakeSheet("Sheet1", filled={(10, 3): "old"})])
    monkeypatch.setattr(excel_writer, "_excel_app", lambda: FakeExcel([book]))
    kb = FakeKeyboard()
    c = RidExportController(browser_context, log=lambda *a: None, writer=ExcelWriter(),
                            keyboard_module=kb, widget_factory=FakeWidget,
                            list_worksheets=lambda: [])
    c.start()
    c.target = TARGET

    kb.pressed = {"["}
    c.tick()                                   # OFF: nothing happens
    time.sleep(0.2)
    sheet = book.Worksheets("Sheet1")
    assert sheet.Cells(11, 3).Value is None and rec.events == []

    kb.pressed = set(); c.tick()
    c.hotkeys_enabled.set()
    kb.pressed = {"["}; c.tick()               # ON: left -> C, below the existing value
    assert wait_for(lambda: sheet.Cells(11, 3).Value == "9000000001")
    kb.pressed = set(); c.tick()
    kb.pressed = {"]"}; c.tick()               # right -> I10
    assert wait_for(lambda: sheet.Cells(10, 9).Value == "9000000001")
    assert rec.events == ["ok", "ok"]
    c.close()
    page.close()
