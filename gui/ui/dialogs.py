#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk, messagebox

import theme

_PALETTE = [
    "#eb1111", "#e91e63", "#e74c3c", "#e67e22",
    "#f1c40f", "#9b59b6", "#3498db", "#00bcd4",
    "#795548", "#607d8b", "#8bc34a", "#2ecc70",
]

# --- Recurrence constants ---

_WD_CODES = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]
_WD_SHORT = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
_WD_LONG  = ["Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag"]

_FREQ_OPTS = [
    ("Nicht wiederkehrend", "none"),
    ("Täglich",             "daily"),
    ("Wöchentlich",         "weekly"),
    ("Monatlich",           "monthly"),
    ("Jährlich",            "yearly"),
]
_FREQ_UNITS = {
    "daily": "Tag(e)", "weekly": "Woche(n)",
    "monthly": "Monat(e)", "yearly": "Jahr(e)",
}

_POS_OPTS = [("1.", "1"), ("2.", "2"), ("3.", "3"), ("4.", "4"), ("Letzten", "-1")]


def _center_dialog(dlg: tk.Toplevel, parent: tk.BaseWidget) -> None:
    """Compute size, center on parent, then reveal and grab."""
    dlg.update_idletasks()
    cx = parent.winfo_rootx() + parent.winfo_width() // 2
    cy = parent.winfo_rooty() + parent.winfo_height() // 2
    dlg.geometry(f"+{cx - dlg.winfo_reqwidth() // 2}+{cy - dlg.winfo_reqheight() // 2}")
    dlg.deiconify()
    dlg.wait_visibility()  # wait for WM to actually map and paint the window
    dlg.grab_set()


def _recurrence_summary(r: dict | None) -> str:
    if not r:
        return "-"
    freq = r.get("freq", "none")
    n = r.get("interval", 1)
    if freq == "daily":
        return "Täglich" if n == 1 else f"Alle {n} Tage"
    if freq == "weekly":
        days = r.get("weekdays", [])
        base = "Wöchentlich" if n == 1 else f"Alle {n} Wochen"
        return f"{base} ({', '.join(days)})" if days else base
    if freq == "monthly":
        base = "Monatlich" if n == 1 else f"Alle {n} Monate"
        mode = r.get("month_mode", "monthday")
        if mode == "monthday":
            return f"{base}, am {r.get('month_day', '?')}."
        pos_map = dict(_POS_OPTS)
        pos = pos_map.get(str(r.get("month_pos", "1")), "?")
        wd = r.get("month_weekday", "")
        wd_long = _WD_LONG[_WD_CODES.index(wd)] if wd in _WD_CODES else wd
        return f"{base}, {pos} {wd_long}"
    if freq == "yearly":
        return "Jährlich" if n == 1 else f"Alle {n} Jahre"
    return "-"


class ProvisionDialog(tk.Toplevel):
    """Shown on first start. Collects admin email + password + optional Nextcloud config."""

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title("Setup — Erstkonfiguration")
        self.resizable(False, False)

        self.result = None  # set to (email, password_bytes, sync_data_or_None) on confirm

        pad = {"padx": 10, "pady": 4}

        ttk.Label(self, text="Admin-Konto einrichten:").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(12, 2))

        ttk.Label(self, text="E-Mail:").grid(row=1, column=0, sticky="e", **pad)
        self._email = ttk.Entry(self, width=30)
        self._email.grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(self, text="Passwort:").grid(row=2, column=0, sticky="e", **pad)
        self._pw1 = ttk.Entry(self, show="*", width=30)
        self._pw1.grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(self, text="Wiederholen:").grid(row=3, column=0, sticky="e", **pad)
        self._pw2 = ttk.Entry(self, show="*", width=30)
        self._pw2.grid(row=3, column=1, sticky="w", **pad)

        ttk.Separator(self, orient="horizontal").grid(
            row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        ttk.Label(self, text="Nextcloud Sync (URL leer lassen zum Überspringen):").grid(
            row=5, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 2))

        ttk.Label(self, text="URL:").grid(row=6, column=0, sticky="e", **pad)
        self._nc_url = ttk.Entry(self, width=30)
        self._nc_url.grid(row=6, column=1, sticky="w", **pad)

        ttk.Label(self, text="Benutzername:").grid(row=7, column=0, sticky="e", **pad)
        self._nc_user = ttk.Entry(self, width=30)
        self._nc_user.grid(row=7, column=1, sticky="w", **pad)

        ttk.Label(self, text="App-Passwort:").grid(row=8, column=0, sticky="e", **pad)
        self._nc_pw = ttk.Entry(self, show="*", width=30)
        self._nc_pw.grid(row=8, column=1, sticky="w", **pad)

        ttk.Label(self, text="Remote-Pfad:").grid(row=9, column=0, sticky="e", **pad)
        self._nc_path = ttk.Entry(self, width=30)
        self._nc_path.insert(0, "/calendar.json")
        self._nc_path.grid(row=9, column=1, sticky="w", **pad)

        ttk.Separator(self, orient="horizontal").grid(
            row=10, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=11, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(btn_frame, text="Schlüssel generieren",
                   command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Abbrechen",
                   command=self.destroy).pack(side="left", padx=6)

        self._email.focus_set()
        self.bind("<Return>", lambda _: self._confirm())
        _center_dialog(self, parent)

    def _confirm(self):
        email = self._email.get().strip()
        if not email or "@" not in email:
            messagebox.showerror("Fehler", "Bitte eine gültige E-Mail-Adresse eingeben.",
                                 parent=self)
            return

        pw1 = self._pw1.get()
        pw2 = self._pw2.get()
        if pw1 != pw2:
            messagebox.showerror("Fehler", "Passwörter stimmen nicht überein.", parent=self)
            return
        if len(pw1) < 8:
            messagebox.showerror("Fehler", "Passwort muss mindestens 8 Zeichen haben.",
                                 parent=self)
            return

        sync_data = None
        url = self._nc_url.get().strip().rstrip("/")
        if url:
            if not url.startswith(("http://", "https://")):
                messagebox.showerror(
                    "Ungültige URL",
                    "URL muss mit http:// oder https:// beginnen.\n\n"
                    f"Meintest du: https://{url} ?",
                    parent=self,
                )
                return
            nc_user = self._nc_user.get().strip()
            nc_pw   = self._nc_pw.get()
            nc_path = self._nc_path.get().strip() or "/calendar.json"
            if not nc_path.startswith("/"):
                nc_path = "/" + nc_path
            if not nc_user:
                messagebox.showerror("Fehler", "Nextcloud-Benutzername erforderlich.",
                                     parent=self)
                return
            sync_data = {
                "url": url, "user": nc_user,
                "password": nc_pw, "remote_path": nc_path,
            }

        self.result = (email, pw1.encode(), sync_data)
        self.destroy()


class AddEntryDialog(tk.Toplevel):
    """Dialog to create or edit a calendar entry.

    Pass *entry* (a decrypted entry dict) to open in edit mode with pre-filled fields.
    result is a 6-tuple: (title, date_str, time_str, comments, color_or_None, recurrence_or_None)
    """

    def __init__(self, parent, entry: dict | None = None):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title("Edit Entry" if entry else "Add Entry")
        self.resizable(False, False)

        self.result = None  # (title, date_str, time_str, comments, color, recurrence)
        self._color      = entry.get("color")      if entry else None
        self._recurrence = entry.get("recurrence") if entry else None

        pad = {"padx": 10, "pady": 4}

        ttk.Label(self, text="Title:").grid(row=0, column=0, sticky="e", **pad)
        self._title = ttk.Entry(self, width=30)
        self._title.grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(self, text="Date (DD.MM.YYYY):").grid(row=1, column=0, sticky="e", **pad)
        self._date = ttk.Entry(self, width=14)
        self._date.grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(self, text="Time (HH:MM | all-day | unknown):").grid(row=2, column=0, sticky="e", **pad)
        self._time = ttk.Entry(self, width=14)
        self._time.grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(self, text="Comments:").grid(row=3, column=0, sticky="ne", padx=10, pady=4)
        self._comments = tk.Text(self, width=28, height=5)
        self._comments.grid(row=3, column=1, sticky="w", padx=10, pady=4)
        ttk.Label(self, text="(one per line)", foreground=theme.FG_DIM).grid(
            row=4, column=1, sticky="w", padx=10)

        # Color picker — 12 swatches in two rows of 6
        ttk.Label(self, text="Color:").grid(row=5, column=0, sticky="ne", padx=10, pady=6)
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
        # Mark the pre-selected color if editing
        if self._color and self._color in self._swatch_btns:
            self._swatch_btns[self._color].config(relief="sunken")

        # Recurrence row
        ttk.Label(self, text="Wiederholung:").grid(row=6, column=0, sticky="e", **pad)
        rec_frame = ttk.Frame(self)
        rec_frame.grid(row=6, column=1, sticky="w", **pad)
        self._rec_lbl = ttk.Label(rec_frame,
                                   text=_recurrence_summary(self._recurrence),
                                   foreground=theme.FG_DIM)
        self._rec_lbl.pack(side="left")
        ttk.Button(rec_frame, text="Bearbeiten…",
                   command=self._open_recurrence).pack(side="left", padx=(10, 0))

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=10)
        btn_label = "Save" if entry else "Add"
        ttk.Button(btn_frame, text=btn_label, command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=6)

        # Pre-fill fields when editing
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
        from datetime import datetime

        title = self._title.get().strip()
        if not title:
            messagebox.showerror("Error", "Title cannot be empty.", parent=self)
            return

        date_str = self._date.get().strip()
        try:
            datetime.strptime(date_str, "%d.%m.%Y")
        except ValueError:
            messagebox.showerror("Error", "Invalid date. Use DD.MM.YYYY.", parent=self)
            return

        time_str = self._time.get().strip().lower()
        if time_str not in ("all-day", "unknown"):
            try:
                datetime.strptime(time_str, "%H:%M")
            except ValueError:
                messagebox.showerror("Error", "Invalid time. Use HH:MM, all-day, or unknown.", parent=self)
                return

        raw_comments = self._comments.get("1.0", "end").strip()
        comments = [c.strip() for c in raw_comments.splitlines() if c.strip()]

        self.result = (title, date_str, time_str, comments, self._color, self._recurrence)
        self.destroy()


class SyncConfigDialog(tk.Toplevel):
    """View and update the Nextcloud sync configuration."""

    def __init__(self, parent, current_config: dict | None):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title("Nextcloud Sync Settings")
        self.resizable(False, False)

        # result: dict with sync data, {} to clear, None if cancelled
        self.result = None

        pad = {"padx": 10, "pady": 4}

        ttk.Label(self, text="Leave URL blank to disable sync.").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(12, 6))

        ttk.Label(self, text="URL:").grid(row=1, column=0, sticky="e", **pad)
        self._url = ttk.Entry(self, width=34)
        self._url.grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(self, text="Username:").grid(row=2, column=0, sticky="e", **pad)
        self._user = ttk.Entry(self, width=34)
        self._user.grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(self, text="App password:").grid(row=3, column=0, sticky="e", **pad)
        self._pw = ttk.Entry(self, show="*", width=34)
        self._pw.grid(row=3, column=1, sticky="w", **pad)

        ttk.Label(self, text="Remote path:").grid(row=4, column=0, sticky="e", **pad)
        self._path = ttk.Entry(self, width=34)
        self._path.grid(row=4, column=1, sticky="w", **pad)

        # Pre-fill with existing config
        if current_config:
            self._url.insert(0, current_config.get("url", ""))
            self._user.insert(0, current_config.get("user", ""))
            self._pw.insert(0, current_config.get("password", ""))
            self._path.insert(0, current_config.get("remote_path", "/calendar.json"))
        else:
            self._path.insert(0, "/calendar.json")

        ttk.Separator(self, orient="horizontal").grid(
            row=5, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(btn_frame, text="Save", command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=6)

        self._url.focus_set()
        self.bind("<Return>", lambda _: self._confirm())
        _center_dialog(self, parent)

    def _confirm(self):
        url = self._url.get().strip().rstrip("/")
        if not url:
            # Disable sync
            self.result = {}
            self.destroy()
            return

        if not url.startswith(("http://", "https://")):
            messagebox.showerror(
                "Invalid URL",
                "URL must start with http:// or https://\n\n"
                f"Meintest du: https://{url} ?",
                parent=self,
            )
            return

        user = self._user.get().strip()
        if not user:
            messagebox.showerror("Error", "Username required.", parent=self)
            return

        path = self._path.get().strip() or "/calendar.json"
        if not path.startswith("/"):
            path = "/" + path

        self.result = {
            "url": url,
            "user": user,
            "password": self._pw.get(),
            "remote_path": path,
        }
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
        self.title("Wiederholung")
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

        # Frequency row
        row0 = ttk.Frame(self)
        row0.pack(fill="x", padx=px, pady=(12, 3))
        ttk.Label(row0, text="Frequenz:").pack(side="left")
        self._freq_cb = ttk.Combobox(
            row0, values=[l for l, _ in _FREQ_OPTS], state="readonly", width=20)
        self._freq_cb.set(
            next((l for l, v in _FREQ_OPTS if v == self._freq.get()),
                 _FREQ_OPTS[0][0]))
        self._freq_cb.pack(side="left", padx=8)
        self._freq_cb.bind("<<ComboboxSelected>>",
                           lambda _: self._freq.set(
                               _FREQ_OPTS[self._freq_cb.current()][1]))

        # Interval (shown for all freq except none)
        self._interval_frame = ttk.Frame(self)
        ttk.Label(self._interval_frame, text="Alle:").pack(side="left")
        ttk.Entry(self._interval_frame, textvariable=self._interval,
                  width=4).pack(side="left", padx=4)
        self._unit_lbl = ttk.Label(self._interval_frame, text="")
        self._unit_lbl.pack(side="left")

        # Weekday checkboxes (weekly only)
        self._weekly_frame = ttk.Frame(self)
        ttk.Label(self._weekly_frame, text="An:").pack(side="left")
        for code, short in zip(_WD_CODES, _WD_SHORT):
            ttk.Checkbutton(self._weekly_frame, text=short,
                            variable=self._wd_vars[code]).pack(side="left", padx=1)

        # Monthly options (monthly only)
        self._monthly_frame = ttk.Frame(self)
        r1 = ttk.Frame(self._monthly_frame)
        r1.pack(fill="x", pady=1)
        ttk.Radiobutton(r1, text="Am Tag", variable=self._month_mode,
                         value="monthday").pack(side="left")
        ttk.Entry(r1, textvariable=self._month_day, width=4).pack(side="left", padx=4)
        ttk.Label(r1, text="des Monats").pack(side="left")

        r2 = ttk.Frame(self._monthly_frame)
        r2.pack(fill="x", pady=1)
        ttk.Radiobutton(r2, text="Am", variable=self._month_mode,
                         value="weekday").pack(side="left")
        pos_vals = [v for _, v in _POS_OPTS]
        self._pos_cb = ttk.Combobox(r2, values=[l for l, _ in _POS_OPTS],
                                     state="readonly", width=8)
        self._pos_cb.set(
            next((l for l, v in _POS_OPTS if v == self._month_pos.get()),
                 _POS_OPTS[0][0]))
        self._pos_cb.pack(side="left", padx=4)
        self._pos_cb.bind("<<ComboboxSelected>>",
                           lambda _: self._month_pos.set(
                               pos_vals[self._pos_cb.current()]))
        self._wd_cb = ttk.Combobox(r2, values=_WD_LONG, state="readonly", width=12)
        try:
            self._wd_cb.set(_WD_LONG[_WD_CODES.index(self._month_wd.get())])
        except ValueError:
            self._wd_cb.set(_WD_LONG[0])
        self._wd_cb.pack(side="left", padx=4)
        self._wd_cb.bind("<<ComboboxSelected>>",
                          lambda _: self._month_wd.set(
                              _WD_CODES[self._wd_cb.current()]))
        ttk.Label(r2, text="des Monats").pack(side="left")

        # Separator — used as anchor for pack(before=...) ordering
        self._sep = ttk.Separator(self, orient="horizontal")
        self._sep.pack(fill="x", padx=px, pady=8)

        # End section
        end = ttk.LabelFrame(self, text="Ende")
        end.pack(fill="x", padx=px, pady=(0, 6))
        ttk.Radiobutton(end, text="Nie",
                         variable=self._end_mode, value="never").grid(
            row=0, column=0, sticky="w", padx=8, pady=2)
        ttk.Radiobutton(end, text="Am:",
                         variable=self._end_mode, value="until").grid(
            row=1, column=0, sticky="w", padx=8, pady=2)
        ttk.Entry(end, textvariable=self._until, width=12).grid(
            row=1, column=1, sticky="w", padx=4)
        ttk.Label(end, text="DD.MM.YYYY").grid(row=1, column=2, sticky="w")
        ttk.Radiobutton(end, text="Nach:",
                         variable=self._end_mode, value="count").grid(
            row=2, column=0, sticky="w", padx=8, pady=2)
        ttk.Entry(end, textvariable=self._count, width=6).grid(
            row=2, column=1, sticky="w", padx=4)
        ttk.Label(end, text="Wiederholungen").grid(row=2, column=2, sticky="w")

        # Buttons
        btns = ttk.Frame(self)
        btns.pack(pady=(0, 10))
        ttk.Button(btns, text="OK", command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btns, text="Abbrechen", command=self.destroy).pack(side="left", padx=6)

    def _update_ui(self):
        freq = self._freq.get()
        for f in (self._interval_frame, self._weekly_frame, self._monthly_frame):
            f.pack_forget()
        if freq == "none":
            return
        self._unit_lbl.config(text=_FREQ_UNITS.get(freq, ""))
        self._interval_frame.pack(before=self._sep, fill="x", padx=10, pady=3)
        if freq == "weekly":
            self._weekly_frame.pack(before=self._sep, fill="x", padx=10, pady=3)
        elif freq == "monthly":
            self._monthly_frame.pack(before=self._sep, fill="x", padx=10, pady=3)

    def _confirm(self):
        from datetime import datetime
        freq = self._freq.get()
        if freq == "none":
            self.result = {}
            self.destroy()
            return

        try:
            interval = int(self._interval.get())
            assert interval >= 1
        except (ValueError, AssertionError):
            messagebox.showerror("Fehler", "Intervall muss ≥ 1 sein.", parent=self)
            return

        rule = {"freq": freq, "interval": interval}

        if freq == "weekly":
            days = [c for c in _WD_CODES if self._wd_vars[c].get()]
            if not days:
                messagebox.showerror("Fehler",
                    "Bitte mindestens einen Wochentag auswählen.", parent=self)
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
                    messagebox.showerror("Fehler",
                        "Tag muss zwischen 1 und 31 liegen.", parent=self)
                    return
                rule["month_day"] = day
            else:
                rule["month_pos"]     = [v for _, v in _POS_OPTS][self._pos_cb.current()]
                rule["month_weekday"] = _WD_CODES[self._wd_cb.current()]

        end_mode = self._end_mode.get()
        rule["end_mode"] = end_mode
        if end_mode == "until":
            until = self._until.get().strip()
            try:
                datetime.strptime(until, "%d.%m.%Y")
            except ValueError:
                messagebox.showerror("Fehler",
                    "Ungültiges Enddatum. Format: DD.MM.YYYY", parent=self)
                return
            rule["until"] = until
        elif end_mode == "count":
            try:
                count = int(self._count.get())
                assert count >= 1
            except (ValueError, AssertionError):
                messagebox.showerror("Fehler", "Anzahl muss ≥ 1 sein.", parent=self)
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
        self.title("View Entry")
        self.resizable(False, False)

        pad = {"padx": 12, "pady": 3}

        fields = [
            ("ID", entry.get("id", "")),
            ("Title", entry.get("title", "")),
            ("Date", entry.get("date", "")),
            ("Time", entry.get("time", "")),
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
        ttk.Label(self, text="Comments:", font=("", 9, "bold")).grid(
            row=len(fields), column=0, sticky="ne", **pad)
        if comments:
            text = tk.Text(self, width=38, height=min(len(comments) + 1, 8),
                           relief="flat", background=self.cget("background"))
            text.insert("1.0", "\n".join(f"• {c}" for c in comments))
            # Allow selection/copy/navigation but block editing
            text.bind("<<Paste>>", lambda e: "break")
            text.bind("<<Cut>>", lambda e: "break")
            text.bind("<Key>", lambda e: "break" if e.char else None)
            text.grid(row=len(fields), column=1, sticky="w", padx=12, pady=3)
        else:
            ttk.Label(self, text="none", foreground=theme.FG_DIM).grid(
                row=len(fields), column=1, sticky="w", **pad)

        ttk.Button(self, text="Close", command=self.destroy).grid(
            row=len(fields) + 1, column=0, columnspan=2, pady=12)
        _center_dialog(self, parent)


# ── User management ───────────────────────────────────────────────────────────

class AddUserDialog(tk.Toplevel):
    """Admin: add a new user — generate keypair or register an existing public key."""

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title("Benutzer hinzufügen")
        self.resizable(False, False)

        # result: (email, kpub_or_None, password_or_None)
        # kpub_or_None — cryptography public key object if user provided their own
        # password_or_None — bytes if keypair should be generated with this password
        self.result = None

        pad = {"padx": 10, "pady": 4}

        ttk.Label(self, text="E-Mail:").grid(row=0, column=0, sticky="e", **pad)
        self._email = ttk.Entry(self, width=32)
        self._email.grid(row=0, column=1, columnspan=2, sticky="w", **pad)

        ttk.Separator(self, orient="horizontal").grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=6)

        self._mode = tk.StringVar(value="generate")
        ttk.Radiobutton(self, text="Schlüsselpaar generieren",
                        variable=self._mode, value="generate").grid(
            row=2, column=0, columnspan=3, sticky="w", padx=10)

        ttk.Label(self, text="Passwort:").grid(row=3, column=0, sticky="e", **pad)
        self._pw1 = ttk.Entry(self, show="*", width=24)
        self._pw1.grid(row=3, column=1, columnspan=2, sticky="w", **pad)

        ttk.Label(self, text="Wiederholen:").grid(row=4, column=0, sticky="e", **pad)
        self._pw2 = ttk.Entry(self, show="*", width=24)
        self._pw2.grid(row=4, column=1, columnspan=2, sticky="w", **pad)

        ttk.Separator(self, orient="horizontal").grid(
            row=5, column=0, columnspan=3, sticky="ew", padx=10, pady=6)

        ttk.Radiobutton(self, text="Eigenen Public Key angeben (PEM):",
                        variable=self._mode, value="external").grid(
            row=6, column=0, columnspan=3, sticky="w", padx=10)

        self._kpub_text = tk.Text(self, width=38, height=6, wrap="none")
        self._kpub_text.grid(row=7, column=0, columnspan=3,
                              padx=10, pady=(0, 6), sticky="ew")

        ttk.Separator(self, orient="horizontal").grid(
            row=8, column=0, columnspan=3, sticky="ew", padx=10, pady=6)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=9, column=0, columnspan=3, pady=(0, 10))
        ttk.Button(btn_frame, text="Hinzufügen",
                   command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Abbrechen",
                   command=self.destroy).pack(side="left", padx=6)

        self._email.focus_set()
        _center_dialog(self, parent)

    def _confirm(self):
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        email = self._email.get().strip()
        if not email or "@" not in email:
            messagebox.showerror("Fehler",
                                 "Bitte eine gültige E-Mail-Adresse eingeben.",
                                 parent=self)
            return

        mode = self._mode.get()

        if mode == "generate":
            pw1 = self._pw1.get()
            pw2 = self._pw2.get()
            if pw1 != pw2:
                messagebox.showerror("Fehler",
                                     "Passwörter stimmen nicht überein.",
                                     parent=self)
                return
            if len(pw1) < 8:
                messagebox.showerror("Fehler",
                                     "Passwort muss mindestens 8 Zeichen haben.",
                                     parent=self)
                return
            self.result = (email, None, pw1.encode())
        else:
            pem_text = self._kpub_text.get("1.0", "end").strip().encode()
            if not pem_text:
                messagebox.showerror("Fehler",
                                     "Bitte einen Public Key (PEM) eingeben.",
                                     parent=self)
                return
            try:
                kpub = load_pem_public_key(pem_text)
            except Exception:
                messagebox.showerror("Fehler",
                                     "Ungültiger Public Key. Bitte PEM-Format verwenden.",
                                     parent=self)
                return
            self.result = (email, kpub, None)

        self.destroy()


class UserManagementDialog(tk.Toplevel):
    """Admin-only: list, add, and remove users."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title("Benutzerverwaltung")
        self.resizable(False, False)
        self._app = app

        ttk.Button(self, text="+ Benutzer hinzufügen",
                   command=self._add_user).pack(
            anchor="w", padx=10, pady=(10, 4))

        # Treeview
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10, pady=4)

        cols = ("email", "role")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings",
                                  selectmode="browse", height=8)
        self._tree.heading("email", text="E-Mail")
        self._tree.heading("role",  text="Rolle")
        self._tree.column("email", width=240)
        self._tree.column("role",  width=80, anchor="center")

        sb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        ttk.Button(self, text="Entfernen",
                   command=self._remove_selected).pack(pady=(4, 0))
        ttk.Button(self, text="Schließen",
                   command=self.destroy).pack(pady=(4, 10))

        self._users: dict[str, dict] = {}  # iid → user dict
        self._refresh()
        _center_dialog(self, parent)

    def _refresh(self):
        self._tree.delete(*self._tree.get_children())
        self._users.clear()
        self._tree.tag_configure("row", background=theme.BG_ALT)
        for u in self._app.list_users():
            iid = self._tree.insert("", "end", tags=("row",), values=(
                u["email"] or f"{u['hash']}",
                "Admin" if u["is_admin"] else "Benutzer",
            ))
            self._users[iid] = u

    def _add_user(self):
        import tkinter.filedialog as fd

        dlg = AddUserDialog(self)
        self.wait_window(dlg)
        self.grab_set()
        if dlg.result is None:
            return

        email, kpub, password = dlg.result

        # If we'll be generating a key, ask WHERE to save it BEFORE
        # committing anything to disk / calendar.json.
        save_path = None
        if kpub is None:
            save_path = fd.asksaveasfilename(
                parent=self,
                title=f"Privaten Schlüssel für {email} speichern",
                defaultextension=".pem",
                filetypes=[("PEM key", "*.pem")],
                initialfile=f"key_{email.split('@')[0]}.pem",
            )
            if not save_path:
                return  # user cancelled — nothing written yet

        try:
            kpriv_bytes = self._app.add_user(email, kpub, password)
        except RuntimeError as e:
            messagebox.showerror("Fehler", str(e), parent=self)
            return

        if kpriv_bytes and save_path:
            try:
                with open(save_path, "wb") as f:
                    f.write(kpriv_bytes)
                messagebox.showinfo(
                    "Gespeichert",
                    f"Schlüssel gespeichert:\n{save_path}\n\n"
                    "Diesen sicher an den Benutzer übertragen.",
                    parent=self,
                )
            except Exception as exc:
                messagebox.showerror("Fehler",
                                     f"Speichern fehlgeschlagen: {exc}",
                                     parent=self)
        self._refresh()

    def _remove_selected(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("Hinweis",
                                "Zuerst einen Benutzer auswählen.",
                                parent=self)
            return
        u = self._users.get(sel[0])
        if u is None:
            return
        label = u["email"] or u["hash"][:16]
        if not messagebox.askyesno(
            "Benutzer entfernen",
            f"Benutzer '{label}' entfernen?\n\n"
            "Der Kalender-Schlüssel wird dabei rotiert "
            "(alle Einträge werden neu verschlüsselt).",
            parent=self,
        ):
            return
        try:
            self._app.remove_user(u["hash"])
        except RuntimeError as e:
            messagebox.showerror("Fehler", str(e), parent=self)
            return
        self._refresh()
