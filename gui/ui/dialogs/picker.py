import tkinter as tk
from datetime import date as _date
from tkinter import ttk

import i18n
from ui.dialogs.base import _center_dialog


class DatePickerDialog(tk.Toplevel):
    """Compact month/year picker."""

    def __init__(self, parent, initial_date: _date):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("date_picker_title"))
        self.resizable(False, False)

        self.result = None
        self._month_var = tk.StringVar(value=i18n.MONTHS[initial_date.month])
        self._year_var = tk.IntVar(value=initial_date.year)

        self._build_ui()
        _center_dialog(self, parent)

    def _build_ui(self):
        # Small arrow button style — only needs to be configured once
        s = ttk.Style()
        s.configure("Arrow.TButton", padding=(3, 1), font=("Cantarell", 7))

        frame = ttk.Frame(self)
        frame.pack(padx=16, pady=12)

        ttk.Label(frame, text=i18n._("date_picker_month")).grid(
            row=0, column=0, sticky="e", padx=(0, 6), pady=4)
        self._month_box = ttk.Combobox(
            frame,
            values=i18n.MONTHS[1:],
            textvariable=self._month_var,
            state="readonly",
            width=10,
        )
        self._month_box.grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(frame, text=i18n._("date_picker_year")).grid(
            row=1, column=0, sticky="e", padx=(0, 6), pady=4)

        year_row = ttk.Frame(frame)
        year_row.grid(row=1, column=1, sticky="w", pady=4)

        self._year_entry = ttk.Entry(year_row, textvariable=self._year_var, width=5)
        self._year_entry.grid(row=0, column=0, sticky="ns")
        self._year_entry.bind("<Return>", lambda _e: self._confirm())
        self._year_entry.bind("<Up>",     lambda _e: self._year_step(+1))
        self._year_entry.bind("<Down>",   lambda _e: self._year_step(-1))

        arrow_col = ttk.Frame(year_row)
        arrow_col.grid(row=0, column=1, padx=(3, 0), sticky="ns")
        arrow_col.rowconfigure(0, weight=1)
        arrow_col.rowconfigure(1, weight=1)
        ttk.Button(arrow_col, text="▲", style="Arrow.TButton",
                   command=lambda: self._year_step(+1)).grid(
            row=0, column=0, sticky="nsew")
        ttk.Button(arrow_col, text="▼", style="Arrow.TButton",
                   command=lambda: self._year_step(-1)).grid(
            row=1, column=0, sticky="nsew", pady=(1, 0))

        btns = ttk.Frame(self)
        btns.pack(pady=(4, 12))
        ttk.Button(btns, text=i18n._("btn_today"),
                   command=self._jump_to_today, width=8).pack(side="left", padx=3)
        ttk.Button(btns, text=i18n._("btn_ok"),
                   command=self._confirm, width=8).pack(side="left", padx=3)
        ttk.Button(btns, text=i18n._("btn_cancel"),
                   command=self.destroy, width=8).pack(side="left", padx=3)

    def _year_step(self, delta: int):
        try:
            self._year_var.set(int(self._year_var.get()) + delta)
        except (ValueError, tk.TclError):
            pass

    def _jump_to_today(self):
        today = _date.today()
        self._month_var.set(i18n.MONTHS[today.month])
        self._year_var.set(today.year)

    def _confirm(self):
        try:
            month = i18n.MONTHS.index(self._month_var.get())
        except ValueError:
            month = 1
        try:
            year = int(self._year_var.get())
        except (ValueError, tk.TclError):
            year = _date.today().year
        self.result = _date(year, month, 1)
        self.destroy()
