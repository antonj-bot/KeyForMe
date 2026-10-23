"""Excel access: list open worksheets and append values (pywin32, Windows)."""
from __future__ import annotations

import time
from dataclasses import dataclass

_HIDDEN_BOOKS = {"PERSONAL.XLSB"}


@dataclass(frozen=True)
class ExcelTarget:
    workbook: str
    sheet: str

    @property
    def label(self) -> str:
        return f"{self.workbook}  ›  {self.sheet}"


# ---------- pure helpers (no COM; unit-tested) ----------
def get_col_row(cell: str):
    col = "".join(ch for ch in cell if ch.isalpha())
    row = "".join(ch for ch in cell if ch.isdigit())
    return col, int(row)


def col_to_num(col: str) -> int:
    num = 0
    for ch in col:
        num = num * 26 + (ord(ch.upper()) - ord("A") + 1)
    return num


def write_next_empty(ws, start_cell: str, text) -> int:
    """Write text to the first empty cell at/below start_cell. Returns the row."""
    col, row = get_col_row(start_cell)
    col_num = col_to_num(col)
    while ws.Cells(row, col_num).Value not in (None, ""):
        row += 1
    ws.Cells(row, col_num).Value = text
    return row


# ---------- COM ----------
def _excel_app():
    import win32com.client

    return win32com.client.GetActiveObject("Excel.Application")


def list_open_worksheets():
    """Visible worksheets of every workbook open in the running Excel."""
    import pythoncom

    pythoncom.CoInitialize()
    try:
        excel = _excel_app()
    except Exception:
        return []  # Excel is not running
    found = []
    for wb in excel.Workbooks:
        name = str(wb.Name)
        if name.upper() in _HIDDEN_BOOKS:
            continue
        for ws in wb.Worksheets:
            try:
                if ws.Visible != -1:  # xlSheetVisible
                    continue
            except Exception:
                pass
            found.append(ExcelTarget(name, str(ws.Name)))
    return found


class ExcelWriter:
    """Used from ONE worker thread only (COM objects are cached per thread)."""

    SAVE_EVERY = 10

    def __init__(self):
        self._cache = {}
        self._writes = 0

    def _sheet(self, target: ExcelTarget):
        cached = self._cache.get(target)
        if cached is not None:
            wb, ws = cached
            wb.Name  # raises if the workbook was closed
            return wb, ws
        excel = _excel_app()
        for book in excel.Workbooks:
            if str(book.Name).lower() == target.workbook.lower():
                ws = book.Worksheets(target.sheet)
                self._cache[target] = (book, ws)
                return book, ws
        raise FileNotFoundError("Workbook is no longer open")

    def write(self, target: ExcelTarget, cell: str, text) -> int:
        last_error = None
        for attempt in range(3):
            try:
                wb, ws = self._sheet(target)
                row = write_next_empty(ws, cell, text)
                self._writes += 1
                if self._writes % self.SAVE_EVERY == 0:
                    try:
                        if str(wb.Path):  # never open Save As for an unsaved book
                            wb.Save()
                    except Exception:
                        pass
                return row
            except Exception as error:  # e.g. Excel busy editing a cell
                last_error = error
                self._cache.pop(target, None)
                time.sleep(0.3)
        raise last_error
