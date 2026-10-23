"""Always-on-top Report ID widget (ported from RIDtoDPT's ui_widget.py).

Every Tk object lives in the widget thread. The rest of the app talks to it
only through `ui_queue` and the thread-safe `hotkeys_enabled_event`.
"""
from __future__ import annotations

import queue
import tkinter as tk
from tkinter import messagebox

from . import sound_effects

WIDGET_WIDTH = 180
WIDGET_HEIGHT = 96

GRADIENT_ON_TOP = "#4b6cb7"
GRADIENT_ON_BOTTOM = "#182848"
GRADIENT_OFF_TOP = "#b74b4b"
GRADIENT_OFF_BOTTOM = "#481818"

FONT_NAME = "Segoe UI"
FONT_SIZE = 11
TEXT_COLOR = "white"
BORDER_COLOR = "#ffffff"
BORDER_WIDTH = 2

HELP_TEXT = (
    "Report ID -> Excel\n"
    "--------------------\n"
    "1. Click 📊 and pick the worksheet to write to.\n"
    "2. Click ⌨ to turn hotkeys ON (red = OFF, blue = ON).\n"
    "3. With an eCrash work item open:\n"
    "   • Press [ to write the Report ID to AutoExtracted (C10 down).\n"
    "   • Press ] to write the Report ID to Manual (I10 down).\n\n"
    "Each press fills the next empty row in that column.\n"
    "Hotkeys do nothing while OFF.\n\n"
    "Tips:\n"
    "• Click and drag the widget to move it.\n"
    "• 🔄 returns it to the top-right corner.\n"
    "• 🔊 / 🔇 toggles sounds.\n"
    "• If extraction fails, check the Report ID is visible on the page."
)


def _shorten(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + "…"


class RidWidget:
    def __init__(self, hotkeys_enabled_event, ui_queue, list_worksheets,
                 on_target, enable_blocker):
        self.hotkeys_enabled_event = hotkeys_enabled_event
        self.ui_queue = ui_queue
        self.list_worksheets = list_worksheets
        self.on_target = on_target
        self.enable_blocker = enable_blocker  # () -> str | None (reason not to enable)
        self.width = WIDGET_WIDTH
        self.height = WIDGET_HEIGHT

        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        self.canvas = tk.Canvas(self.root, width=self.width, height=self.height,
                                highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.draw_gradient(GRADIENT_OFF_TOP, GRADIENT_OFF_BOTTOM)
        self.canvas.create_rectangle(0, 0, self.width, self.height,
                                     outline=BORDER_COLOR, width=BORDER_WIDTH)

        self.target_id = self.canvas.create_text(
            self.width // 2, 40, text="No worksheet selected",
            font=(FONT_NAME, 8), fill=TEXT_COLOR, justify="center")
        self.text_id = self.canvas.create_text(
            self.width // 2, 70, text="Last pasted:\n(none)",
            font=(FONT_NAME, FONT_SIZE, "bold"), fill=TEXT_COLOR, justify="center")

        self.offset_x = 0
        self.offset_y = 0
        self.canvas.bind("<Button-1>", self.start_move)
        self.canvas.bind("<B1-Motion>", self.do_move)

        self.pick_button = self._button("📊", self.pick_worksheet, 5, 24, font=10)
        self.hotkeys_button = tk.Button(
            self.root, text="⌨ OFF", font=(FONT_NAME, 8, "bold"),
            command=self.toggle_hotkeys, bg="#ffdddd", fg="#000000",
            relief="flat", bd=0)
        self.hotkeys_button.place(x=33, y=5, width=45, height=20)
        self.help_button = self._button("?", self.show_help, 82, 20, bold=True)
        self.mute_button = self._button("🔊", self.toggle_mute, 106, 20)
        self.reset_button = self._button("🔄", self.place_top_right, 130, 20)

        self.place_top_right()
        self.root.after(100, self.process_ui_queue)

    def _button(self, text, command, x, width, font=10, bold=False):
        button = tk.Button(
            self.root, text=text, command=command, bg="#ffffff", fg="#000000",
            relief="flat", bd=0,
            font=(FONT_NAME, font, "bold") if bold else (FONT_NAME, font))
        button.place(x=x, y=5, width=width, height=20)
        return button

    # ---- queue from the rest of the app ----
    def process_ui_queue(self):
        try:
            while True:
                action = self.ui_queue.get_nowait()
                if action[0] == "text":
                    self.update_text(action[1])
                elif action[0] == "close":
                    self.root.destroy()
                    return
        except queue.Empty:
            pass
        try:
            self.root.after(100, self.process_ui_queue)
        except Exception:
            pass

    # ---- worksheet picker ----
    def set_target_label(self, label):
        self.canvas.itemconfig(
            self.target_id, text=_shorten(label, 30) if label else "No worksheet selected")

    def pick_worksheet(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Pick worksheet")
        dialog.attributes("-topmost", True)
        dialog.resizable(False, False)
        x = max(0, self.root.winfo_x() - 300)
        y = self.root.winfo_y() + self.height + 10
        dialog.geometry(f"+{x}+{y}")

        tk.Label(dialog, text="Open worksheets in Excel:",
                 font=(FONT_NAME, 10, "bold")).pack(anchor="w", padx=10, pady=(10, 4))
        listbox = tk.Listbox(dialog, width=52, height=10, exportselection=False,
                             font=(FONT_NAME, 10))
        listbox.pack(padx=10)
        status = tk.Label(dialog, text="", fg="#b00020", font=(FONT_NAME, 9))
        status.pack(anchor="w", padx=10, pady=(4, 0))
        items = []

        def refresh():
            try:
                found = list(self.list_worksheets())
                message = "" if found else "No open worksheets found. Open a workbook, then Refresh."
            except Exception as error:
                found = []
                message = f"Could not read Excel ({type(error).__name__})."
            items[:] = found
            listbox.delete(0, "end")
            for item in found:
                listbox.insert("end", item.label)
            status.config(text=message)

        def choose(_event=None):
            selection = listbox.curselection()
            if not selection:
                return
            target = items[selection[0]]
            self.on_target(target)
            self.set_target_label(target.label)
            dialog.destroy()

        row = tk.Frame(dialog)
        row.pack(fill="x", padx=10, pady=10)
        tk.Button(row, text="Refresh", command=refresh).pack(side="left")
        tk.Button(row, text="Cancel", command=dialog.destroy).pack(side="right")
        tk.Button(row, text="Select", command=choose).pack(side="right", padx=6)
        listbox.bind("<Double-Button-1>", choose)

        refresh()
        dialog.transient(self.root)
        dialog.grab_set()
        self.root.wait_window(dialog)

    # ---- hotkey toggle ----
    def toggle_hotkeys(self):
        event = self.hotkeys_enabled_event
        if event.is_set():
            event.clear()
            self.hotkeys_button.config(text="⌨ OFF", bg="#ffdddd")
            self.draw_gradient(GRADIENT_OFF_TOP, GRADIENT_OFF_BOTTOM)
            return
        reason = self.enable_blocker()
        if reason:
            messagebox.showinfo("Report ID → Excel", reason, parent=self.root)
            return
        event.set()
        self.hotkeys_button.config(text="⌨ ON", bg="#ddffdd")
        self.draw_gradient(GRADIENT_ON_TOP, GRADIENT_ON_BOTTOM)

    def show_help(self):
        messagebox.showinfo("Help", HELP_TEXT, parent=self.root)

    def toggle_mute(self):
        self.mute_button.config(text="🔇" if sound_effects.toggle_muted() else "🔊")

    # ---- drawing ----
    def draw_gradient(self, top_color, bottom_color):
        self.canvas.delete("gradient")
        r1, g1, b1 = self.hex_to_rgb(top_color)
        r2, g2, b2 = self.hex_to_rgb(bottom_color)
        for i in range(self.height):
            r = int(r1 + (r2 - r1) * i / self.height)
            g = int(g1 + (g2 - g1) * i / self.height)
            b = int(b1 + (b2 - b1) * i / self.height)
            self.canvas.create_line(0, i, self.width, i,
                                    fill=f"#{r:02x}{g:02x}{b:02x}", tags="gradient")
        self.canvas.lower("gradient")

    @staticmethod
    def hex_to_rgb(hex_color):
        hex_color = hex_color.lstrip("#")
        return tuple(int(hex_color[i:i + 2], 16) for i in (0, 2, 4))

    def start_move(self, event):
        self.offset_x = event.x
        self.offset_y = event.y

    def do_move(self, event):
        x = self.root.winfo_x() + (event.x - self.offset_x)
        y = self.root.winfo_y() + (event.y - self.offset_y)
        self.root.geometry(f"+{x}+{y}")

    def place_top_right(self):
        self.root.update_idletasks()
        x = self.root.winfo_screenwidth() - self.width - 20
        self.root.geometry(f"{self.width}x{self.height}+{x}+20")

    def update_text(self, text):
        text = text or "(none)"
        if len(text) > 70:
            text = text[:70] + "..."
        self.canvas.itemconfig(self.text_id, text=f"Last pasted:\n{text}")

    def run(self):
        self.root.mainloop()
