import tkinter as tk
from tkinter import ttk
from datetime import datetime

import i18n
import theme

from ui.dialogs.base import _PAD, _PALETTE, _center_dialog, show_error

# Internal weekday codes (stored in calendar data — do NOT translate)
_WD_CODES = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]


def _recurrence_summary(r: dict | None) -> str:
    if not r:
        return i18n._("rec_none")
    freq = r.get("freq", "none")
    n = r.get("interval", 1)
    if freq == "daily":
        return i18n._("rec_daily") if n == 1 else i18n._("rec_every_n_days").format(n=n)
    if freq == "weekly":
        days = r.get("weekdays", [])
        base = i18n._("rec_weekly") if n == 1 else i18n._("rec_every_n_weeks").format(n=n)
        return f"{base} ({', '.join(days)})" if days else base
    if freq == "monthly":
        base = i18n._("rec_monthly") if n == 1 else i18n._("rec_every_n_months").format(n=n)
        mode = r.get("month_mode", "monthday")
        if mode == "monthday":
            return f"{base}, {i18n._('rec_on_day').format(day=r.get('month_day', '?'))}"
        pos_map = dict(i18n.POS_OPTS)
        pos = pos_map.get(str(r.get("month_pos", "1")), "?")
        wd = r.get("month_weekday", "")
        wd_long = i18n.WD_LONG[_WD_CODES.index(wd)] if wd in _WD_CODES else wd
        return f"{base}, {pos} {wd_long}"
    if freq == "yearly":
        return i18n._("rec_yearly") if n == 1 else i18n._("rec_every_n_years").format(n=n)
    return i18n._("rec_none")


class AddEntryDialog(tk.Toplevel):
    """Dialog to create or edit a calendar entry.

    Pass *entry* (a decrypted entry dict) to open in edit mode with pre-filled fields.
    result is a 6-tuple: (title, date_str, time_str, comments, color_or_None, recurrence_or_None)
    """

    def __init__(self, parent, entry: dict | None = None):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("edit_entry_title") if entry else i18n._("add_entry_title"))
        self.resizable(False, False)

        self.result = None  # (title, date_str, time_str, comments, color, recurrence)
        self._color      = entry.get("color")      if entry else None
        self._recurrence = entry.get("recurrence") if entry else None

        pad = _PAD

        ttk.Label(self, text=i18n._("lbl_title")).grid(row=0, column=0, sticky="e", **pad)
        self._title = ttk.Entry(self, width=30)
        self._title.grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(self, text=i18n._("lbl_date")).grid(row=1, column=0, sticky="e", **pad)
        self._date = ttk.Entry(self, width=14)
        self._date.grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(self, text=i18n._("lbl_time")).grid(row=2, column=0, sticky="e", **pad)
        self._time = ttk.Entry(self, width=14)
        self._time.grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(self, text=i18n._("lbl_comments")).grid(row=3, column=0, sticky="ne", padx=10, pady=4)
        self._comments = tk.Text(self, width=28, height=5)
        self._comments.grid(row=3, column=1, sticky="w", padx=10, pady=4)
        ttk.Label(self, text=i18n._("lbl_one_per_line"), foreground=theme.FG_DIM).grid(
            row=4, column=1, sticky="w", padx=10)

        # Color picker — 12 swatches in two rows of 6
        ttk.Label(self, text=i18n._("lbl_color")).grid(row=5, column=0, sticky="ne", padx=10, pady=6)
        color_frame = tk.Frame(self)
        color_frame.grid(row=5, column=1, sticky="w", padx=10, pady=4)
        self._swatch_btns: dict[str, tk.Button] = {}
        for i, c in enumerate(_PALETTE):
            row_i, col_i = divmod(i, 6)
            btn = tk.Button(color_frame, bg=c, width=2, height=1,
                            relief="flat", borderwidth=2,
                            command=lambda col=c: self._set_color(col))
            btn.grid(row=row_i, column=col_i, padx=2, pady=2)
            self._swatch_btns[c] = btn
        # "None" button in top-right corner
        self._none_btn = tk.Button(color_frame, text="✕", width=2, height=1,
                                   relief="flat", borderwidth=2,
                                   command=self._clear_color)
        self._none_btn.grid(row=0, column=6, padx=(6, 2), pady=2)
        if self._color and self._color in self._swatch_btns:
            self._swatch_btns[self._color].config(relief="sunken")

        # Recurrence row
        ttk.Label(self, text=i18n._("lbl_recurrence")).grid(row=6, column=0, sticky="e", **pad)
        rec_frame = ttk.Frame(self)
        rec_frame.grid(row=6, column=1, sticky="w", **pad)
        self._rec_lbl = ttk.Label(rec_frame,
                                   text=_recurrence_summary(self._recurrence),
                                   foreground=theme.FG_DIM)
        self._rec_lbl.pack(side="left")
        ttk.Button(rec_frame, text=i18n._("btn_edit_recurrence"),
                   command=self._open_recurrence).pack(side="left", padx=(10, 0))

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=10)
        btn_label = i18n._("btn_save") if entry else i18n._("btn_add")
        ttk.Button(btn_frame, text=btn_label, command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text=i18n._("btn_cancel"), command=self.destroy).pack(side="left", padx=6)

        if entry:
            self._title.insert(0, entry.get("title", ""))
            self._date.insert(0, entry.get("date", ""))
            self._time.insert(0, entry.get("time", "all-day"))
            comments_text = "\n".join(entry.get("comments", []))
            if comments_text:
                self._comments.insert("1.0", comments_text)
        else:
            self._time.insert(0, "all-day")

        self._title.focus_set()
        _center_dialog(self, parent)

    def _set_color(self, color: str):
        self._color = color
        for c, btn in self._swatch_btns.items():
            btn.config(relief="sunken" if c == color else "flat")
        self._none_btn.config(relief="flat")

    def _clear_color(self):
        self._color = None
        for btn in self._swatch_btns.values():
            btn.config(relief="flat")
        self._none_btn.config(relief="sunken")

    def _open_recurrence(self):
        dlg = RecurrenceDialog(self, self._recurrence)
        self.wait_window(dlg)
        self.grab_set()  # restore grab after child dialog closes
        if dlg.result is None:
            return  # cancelled
        self._recurrence = dlg.result or None  # {} (none) → None
        self._rec_lbl.config(text=_recurrence_summary(self._recurrence))
        self.update_idletasks()

    def _confirm(self):
        title = self._title.get().strip()
        if not title:
            show_error(self, i18n._("err_title"), i18n._("err_title_empty"))
            return

        date_str = self._date.get().strip()
        try:
            datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            show_error(self, i18n._("err_title"), i18n._("err_date_invalid"))
            return

        time_str = self._time.get().strip().lower()
        if time_str not in ("all-day", "unknown"):
            try:
                datetime.strptime(time_str, "%H:%M")
            except ValueError:
                show_error(self, i18n._("err_title"), i18n._("err_time_invalid"))
                return

        raw_comments = self._comments.get("1.0", "end").strip()
        comments = [c.strip() for c in raw_comments.splitlines() if c.strip()]

        self.result = (title, date_str, time_str, comments, self._color, self._recurrence)
        self.destroy()


class RecurrenceDialog(tk.Toplevel):
    """Popup to configure a recurrence rule.

    result = None  → cancelled (no change)
    result = {}    → confirmed with 'none' (remove recurrence)
    result = dict  → confirmed recurrence rule
    """

    def __init__(self, parent, recurrence: dict | None = None):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("recurrence_title"))
        self.resizable(False, False)

        self.result = None
        r = recurrence or {}

        self._freq     = tk.StringVar(value=r.get("freq", "none"))
        self._interval = tk.StringVar(value=str(r.get("interval", 1)))

        wd_set = set(r.get("weekdays", []))
        self._wd_vars = {c: tk.BooleanVar(value=c in wd_set) for c in _WD_CODES}

        self._month_mode = tk.StringVar(value=r.get("month_mode", "monthday"))
        self._month_day  = tk.StringVar(value=str(r.get("month_day", 1)))
        self._month_pos  = tk.StringVar(value=str(r.get("month_pos", "1")))
        self._month_wd   = tk.StringVar(value=r.get("month_weekday", _WD_CODES[0]))

        self._end_mode = tk.StringVar(value=r.get("end_mode", "never"))
        self._until    = tk.StringVar(value=r.get("until", ""))
        self._count    = tk.StringVar(value=str(r.get("count", 10)))

        self._build_ui()

        # Measure the dialog at its largest layout (monthly + interval both visible)
        # so the window size can be fixed — avoiding X11 expose-event timing issues
        # that cause widgets to only repaint on mouse hover after a resize.
        self._interval_frame.pack(before=self._sep, fill="x", padx=10, pady=3)
        self._monthly_frame.pack(before=self._sep, fill="x", padx=10, pady=3)
        self.update_idletasks()
        _fixed_w = self.winfo_reqwidth()
        _fixed_h = self.winfo_reqheight()
        self._interval_frame.pack_forget()
        self._monthly_frame.pack_forget()
        self.minsize(_fixed_w, _fixed_h)
        self.maxsize(_fixed_w, _fixed_h)

        self._update_ui()
        self._freq.trace_add("write", lambda *_: self.after(0, self._update_ui))
        _center_dialog(self, parent)

    def _build_ui(self):
        px = 10

        row0 = ttk.Frame(self)
        row0.pack(fill="x", padx=px, pady=(12, 3))
        ttk.Label(row0, text=i18n._("lbl_frequency")).pack(side="left")
        self._freq_cb = ttk.Combobox(
            row0, values=[l for l, _ in i18n.FREQ_OPTS], state="readonly", width=20)
        self._freq_cb.set(
            next((l for l, v in i18n.FREQ_OPTS if v == self._freq.get()),
                 i18n.FREQ_OPTS[0][0]))
        self._freq_cb.pack(side="left", padx=8)
        self._freq_cb.bind("<<ComboboxSelected>>",
                           lambda _: self._freq.set(
                               i18n.FREQ_OPTS[self._freq_cb.current()][1]))

        self._interval_frame = ttk.Frame(self)
        ttk.Label(self._interval_frame, text=i18n._("lbl_every")).pack(side="left")
        ttk.Entry(self._interval_frame, textvariable=self._interval,
                  width=4).pack(side="left", padx=4)
        self._unit_lbl = ttk.Label(self._interval_frame, text="")
        self._unit_lbl.pack(side="left")

        self._weekly_frame = ttk.Frame(self)
        ttk.Label(self._weekly_frame, text=i18n._("lbl_on_weekdays")).pack(side="left")
        for code, short in zip(_WD_CODES, i18n.WD_SHORT):
            ttk.Checkbutton(self._weekly_frame, text=short,
                            variable=self._wd_vars[code]).pack(side="left", padx=1)

        self._monthly_frame = ttk.Frame(self)
        r1 = ttk.Frame(self._monthly_frame)
        r1.pack(fill="x", pady=1)
        ttk.Radiobutton(r1, text=i18n._("lbl_on_day"), variable=self._month_mode,
                         value="monthday").pack(side="left")
        ttk.Entry(r1, textvariable=self._month_day, width=4).pack(side="left", padx=4)
        ttk.Label(r1, text=i18n._("lbl_of_month")).pack(side="left")

        r2 = ttk.Frame(self._monthly_frame)
        r2.pack(fill="x", pady=1)
        ttk.Radiobutton(r2, text=i18n._("lbl_on_the"), variable=self._month_mode,
                         value="weekday").pack(side="left")
        pos_vals = [v for _, v in i18n.POS_OPTS]
        self._pos_cb = ttk.Combobox(r2, values=[l for l, _ in i18n.POS_OPTS],
                                     state="readonly", width=8)
        self._pos_cb.set(
            next((l for l, v in i18n.POS_OPTS if v == self._month_pos.get()),
                 i18n.POS_OPTS[0][0]))
        self._pos_cb.pack(side="left", padx=4)
        self._pos_cb.bind("<<ComboboxSelected>>",
                           lambda _: self._month_pos.set(
                               pos_vals[self._pos_cb.current()]))
        self._wd_cb = ttk.Combobox(r2, values=i18n.WD_LONG, state="readonly", width=12)
        try:
            self._wd_cb.set(i18n.WD_LONG[_WD_CODES.index(self._month_wd.get())])
        except ValueError:
            self._wd_cb.set(i18n.WD_LONG[0])
        self._wd_cb.pack(side="left", padx=4)
        self._wd_cb.bind("<<ComboboxSelected>>",
                          lambda _: self._month_wd.set(
                              _WD_CODES[self._wd_cb.current()]))
        ttk.Label(r2, text=i18n._("lbl_of_month")).pack(side="left")

        self._sep = ttk.Separator(self, orient="horizontal")
        self._sep.pack(fill="x", padx=px, pady=8)

        end = ttk.LabelFrame(self, text=i18n._("end_label"))
        end.pack(fill="x", padx=px, pady=(0, 6))
        ttk.Radiobutton(end, text=i18n._("end_never"),
                         variable=self._end_mode, value="never").grid(
            row=0, column=0, sticky="w", padx=8, pady=2)
        ttk.Radiobutton(end, text=i18n._("end_on"),
                         variable=self._end_mode, value="until").grid(
            row=1, column=0, sticky="w", padx=8, pady=2)
        ttk.Entry(end, textvariable=self._until, width=12).grid(
            row=1, column=1, sticky="w", padx=4)
        ttk.Label(end, text=i18n._("end_date_format")).grid(row=1, column=2, sticky="w")
        ttk.Radiobutton(end, text=i18n._("end_after"),
                         variable=self._end_mode, value="count").grid(
            row=2, column=0, sticky="w", padx=8, pady=2)
        ttk.Entry(end, textvariable=self._count, width=6).grid(
            row=2, column=1, sticky="w", padx=4)
        ttk.Label(end, text=i18n._("end_repetitions")).grid(row=2, column=2, sticky="w")

        btns = ttk.Frame(self)
        btns.pack(pady=(0, 10))
        ttk.Button(btns, text=i18n._("btn_ok"), command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btns, text=i18n._("btn_cancel"), command=self.destroy).pack(side="left", padx=6)

    def _update_ui(self):
        freq = self._freq.get()
        for f in (self._interval_frame, self._weekly_frame, self._monthly_frame):
            f.pack_forget()
        if freq == "none":
            return
        self._unit_lbl.config(text=i18n.FREQ_UNITS.get(freq, ""))
        self._interval_frame.pack(before=self._sep, fill="x", padx=10, pady=3)
        if freq == "weekly":
            self._weekly_frame.pack(before=self._sep, fill="x", padx=10, pady=3)
        elif freq == "monthly":
            self._monthly_frame.pack(before=self._sep, fill="x", padx=10, pady=3)

    def _confirm(self):
        freq = self._freq.get()
        if freq == "none":
            self.result = {}
            self.destroy()
            return

        try:
            interval = int(self._interval.get())
            assert interval >= 1
        except (ValueError, AssertionError):
            show_error(self, i18n._("err_title"), i18n._("err_interval_invalid"))
            return

        rule = {"freq": freq, "interval": interval}

        if freq == "weekly":
            days = [c for c in _WD_CODES if self._wd_vars[c].get()]
            if not days:
                show_error(self, i18n._("err_title"), i18n._("err_no_weekday"))
                return
            rule["weekdays"] = days

        elif freq == "monthly":
            mode = self._month_mode.get()
            rule["month_mode"] = mode
            if mode == "monthday":
                try:
                    day = int(self._month_day.get())
                    assert 1 <= day <= 31
                except (ValueError, AssertionError):
                    show_error(self, i18n._("err_title"), i18n._("err_day_invalid"))
                    return
                rule["month_day"] = day
            else:
                rule["month_pos"]     = [v for _, v in i18n.POS_OPTS][self._pos_cb.current()]
                rule["month_weekday"] = _WD_CODES[self._wd_cb.current()]

        end_mode = self._end_mode.get()
        rule["end_mode"] = end_mode
        if end_mode == "until":
            until = self._until.get().strip()
            try:
                datetime.strptime(until, "%d.%m.%Y")
            except ValueError:
                show_error(self, i18n._("err_title"), i18n._("err_end_date_invalid"))
                return
            rule["until"] = until
        elif end_mode == "count":
            try:
                count = int(self._count.get())
                assert count >= 1
            except (ValueError, AssertionError):
                show_error(self, i18n._("err_title"), i18n._("err_count_invalid"))
                return
            rule["count"] = count

        self.result = rule
        self.destroy()


class ViewEntryDialog(tk.Toplevel):
    """Read-only view of a single entry."""

    def __init__(self, parent, entry: dict):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("view_entry_title"))
        self.resizable(False, False)

        pad = {"padx": 12, "pady": 3}

        fields = [
            (i18n._("lbl_id"),                entry.get("id", "")),
            (i18n._("lbl_entry_title_field"),  entry.get("title", "")),
            (i18n._("lbl_date_plain"),         entry.get("date", "")),
            (i18n._("lbl_time_plain"),         entry.get("time", "")),
        ]
        self._vars = []  # keep references to prevent garbage collection
        for row, (label, value) in enumerate(fields):
            ttk.Label(self, text=f"{label}:", font=("", 9, "bold")).grid(
                row=row, column=0, sticky="e", **pad)
            var = tk.StringVar(value=value)
            self._vars.append(var)
            e = ttk.Entry(self, textvariable=var, state="readonly", width=38)
            e.grid(row=row, column=1, sticky="w", **pad)

        comments = entry.get("comments", [])
        ttk.Label(self, text=i18n._("lbl_comments_plain"), font=("", 9, "bold")).grid(
            row=len(fields), column=0, sticky="ne", **pad)
        if comments:
            text = tk.Text(self, width=38, height=min(len(comments) + 1, 8),
                           relief="flat", background=self.cget("background"))
            text.insert("1.0", "\n".join(f"• {c}" for c in comments))
            text.bind("<<Paste>>", lambda e: "break")
            text.bind("<<Cut>>", lambda e: "break")
            text.bind("<Key>", lambda e: "break" if e.char else None)
            text.grid(row=len(fields), column=1, sticky="w", padx=12, pady=3)
        else:
            ttk.Label(self, text=i18n._("lbl_none"), foreground=theme.FG_DIM).grid(
                row=len(fields), column=1, sticky="w", **pad)

        ttk.Button(self, text=i18n._("btn_close"), command=self.destroy).grid(
            row=len(fields) + 1, column=0, columnspan=2, pady=12)
        _center_dialog(self, parent)
