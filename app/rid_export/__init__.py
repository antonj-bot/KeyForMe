"""Report ID -> Excel feature (ported from RIDtoDPT).

Hotkeys read the Report ID from the open eCrash page and write it into the
worksheet picked in the floating widget. Importing this package does not load
tkinter, keyboard or pywin32; those are loaded only when the feature starts.
"""
from .controller import RidExportController

__all__ = ["RidExportController"]
