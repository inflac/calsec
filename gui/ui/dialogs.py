#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk

import i18n
import storage
import theme

_PALETTE = [
    "#eb1111", "#e91e63", "#e74c3c", "#e67e22",
    "#f1c40f", "#9b59b6", "#3498db", "#00bcd4",
    "#795548", "#607d8b", "#8bc34a", "#2ecc70",
]

# Internal weekday codes (stored in calendar data — do NOT translate)
_WD_CODES = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]

# Default padding for dialog form rows
_PAD = {"padx": 14, "pady": 6}


def _center_dialog(dlg: tk.Toplevel, parent: tk.BaseWidget) -> None:
    """Show dialog, wait until compositor has rendered it, then center on screen."""
    dlg.deiconify()
    dlg.wait_visibility()  # window is now truly mapped and sized by the compositor
    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    w = dlg.winfo_width()
    h = dlg.winfo_height()
    dlg.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
    dlg.grab_set()


def _make_dialog(parent: tk.BaseWidget, title: str) -> tk.Toplevel:
    dlg = tk.Toplevel(parent)
    dlg.withdraw()
    dlg.transient(parent)
    dlg.title(title)
    dlg.resizable(False, False)
    dlg.minsize(540, 160)
    return dlg


def show_info(parent: tk.BaseWidget, title: str, message: str) -> None:
    dlg = _make_dialog(parent, title)
    ttk.Label(dlg, text=message, wraplength=360,
              justify="center").pack(padx=24, pady=(20, 12))
    ttk.Button(dlg, text=i18n._("btn_ok"), command=dlg.destroy).pack(pady=(0, 16))
    _center_dialog(dlg, parent)
    parent.winfo_toplevel().wait_window(dlg)


def show_error(parent: tk.BaseWidget, title: str, message: str) -> None:
    dlg = _make_dialog(parent, title)
    ttk.Label(dlg, text=message, wraplength=360,
              justify="center", foreground=theme.RED).pack(padx=24, pady=(20, 12))
    ttk.Button(dlg, text=i18n._("btn_ok"), command=dlg.destroy).pack(pady=(0, 16))
    _center_dialog(dlg, parent)
    parent.winfo_toplevel().wait_window(dlg)


def ask_yes_no(parent: tk.BaseWidget, title: str, message: str) -> bool:
    result = [False]
    dlg = _make_dialog(parent, title)
    ttk.Label(dlg, text=message, wraplength=360,
              justify="center").pack(padx=24, pady=(20, 12))
    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(pady=(0, 16))
    ttk.Button(btn_frame, text=i18n._("btn_yes"),
               command=lambda: [result.__setitem__(0, True), dlg.destroy()]).pack(side="left", padx=6)
    ttk.Button(btn_frame, text=i18n._("btn_no"),
               command=dlg.destroy).pack(side="left", padx=6)
    _center_dialog(dlg, parent)
    parent.winfo_toplevel().wait_window(dlg)
    return result[0]


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


class FetchCalendarDialog(tk.Toplevel):
    """One-time download dialog for non-admin users who have a local key but no calendar.json.

    Downloads the file from a Nextcloud WebDAV URL, verifies both signatures,
    confirms the user's local key hash is registered, then saves the file.
    result is True on success, False if cancelled or failed.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("fetch_title"))
        self.resizable(False, False)

        self.result = False

        pad = _PAD

        ttk.Label(self, text="calsec",
                  font=("Cantarell", 14, "bold")).grid(
            row=0, column=0, columnspan=2, pady=(14, 2))
        ttk.Label(self,
                  text=i18n._("fetch_description"),
                  justify="center", foreground=theme.FG_DIM).grid(
            row=1, column=0, columnspan=2, padx=10, pady=(0, 10))

        ttk.Label(self, text=i18n._("lbl_webdav_url")).grid(row=2, column=0, sticky="e", **pad)
        self._url = ttk.Entry(self, width=42)
        self._url.grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(self, text=i18n._("lbl_username")).grid(row=3, column=0, sticky="e", **pad)
        self._user = ttk.Entry(self, width=42)
        self._user.grid(row=3, column=1, sticky="w", **pad)

        ttk.Label(self, text=i18n._("lbl_app_password")).grid(row=4, column=0, sticky="e", **pad)
        self._pw = ttk.Entry(self, show="*", width=42)
        self._pw.grid(row=4, column=1, sticky="w", **pad)

        self._status_var = tk.StringVar()
        ttk.Label(self, textvariable=self._status_var,
                  foreground=theme.RED, wraplength=400,
                  justify="center").grid(
            row=5, column=0, columnspan=2, padx=10, pady=(6, 0))

        ttk.Separator(self, orient="horizontal").grid(
            row=6, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=7, column=0, columnspan=2, pady=(0, 12))
        self._dl_btn = ttk.Button(btn_frame, text=i18n._("btn_download"),
                                   command=self._download)
        self._dl_btn.pack(side="left", padx=6)
        ttk.Button(btn_frame, text=i18n._("btn_cancel"),
                   command=self.destroy).pack(side="left", padx=6)

        self._url.focus_set()
        self.bind("<Return>", lambda _: self._download())
        _center_dialog(self, parent)

    def _download(self):
        url = self._url.get().strip()
        if not url:
            self._status_var.set(i18n._("err_url_required"))
            return
        if not url.startswith(("http://", "https://")):
            self._status_var.set(i18n._("err_url_prefix").format(url=url))
            return

        user = self._user.get().strip()
        if not user:
            self._status_var.set(i18n._("err_username_required"))
            return

        config = {
            "webdav_url": url,
            "auth_user":  user,
            "password":   self._pw.get(),
        }

        self._status_var.set(i18n._("status_connecting"))
        self._dl_btn.configure(state="disabled")
        self.update()

        try:
            from sync import sync_pull
            from crypto import verify_users, verify_entries, pem_to_public_key

            data, msg = sync_pull(config)
            if data is None:
                self._status_var.set(msg)
                self._dl_btn.configure(state="normal")
                return

            sign_keys = data.get("sign_keys", {})
            if not sign_keys:
                self._status_var.set(i18n._("err_no_sign_keys"))
                self._dl_btn.configure(state="normal")
                return

            sig_users   = data.get("sig_users")
            sig_entries = data.get("sig_entries")
            if not sig_users or not sig_entries:
                self._status_var.set(i18n._("err_signatures_missing"))
                self._dl_btn.configure(state="normal")
                return

            kpub_admin = pem_to_public_key(sign_keys["admin"])
            kpub_edit  = pem_to_public_key(sign_keys["edit"])

            if not verify_users(sign_keys, data.get("users", {}),
                                 data.get("sync_config"), sig_users, kpub_admin):
                self._status_var.set(i18n._("err_user_sig_invalid"))
                self._dl_btn.configure(state="normal")
                return

            if not verify_entries(data.get("entries", []), sig_entries, kpub_edit):
                self._status_var.set(i18n._("err_entry_sig_invalid"))
                self._dl_btn.configure(state="normal")
                return

            # Confirm at least one local key is registered in this calendar
            local_hashes = storage.find_user_key_hashes()
            registered = [h for h in local_hashes if h in data.get("users", {})]
            if not registered:
                self._status_var.set(i18n._("err_key_not_registered"))
                self._dl_btn.configure(state="normal")
                return

            storage.save_file(data)
            self.result = True
            self.destroy()

        except Exception as exc:
            self._status_var.set(i18n._("err_generic").format(exc=exc))
            self._dl_btn.configure(state="normal")


class ProvisionDialog(tk.Toplevel):
    """Shown on first start. Collects admin email + password + optional Nextcloud config.

    result = None              → cancelled
    result = ("__reload__",)  → language changed, caller should reopen
    result = (email, pw, sync) → confirmed
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("provision_title"))
        self.resizable(False, False)

        self.result = None

        pad = _PAD

        # ── Language selector ─────────────────────────────────────────────────
        lang_frame = ttk.Frame(self)
        lang_frame.grid(row=0, column=0, columnspan=2, sticky="e", padx=10, pady=(10, 0))
        self._lang_var = tk.StringVar(value=i18n.get())
        for code, label in i18n.SUPPORTED:
            ttk.Radiobutton(lang_frame, text=label,
                            variable=self._lang_var, value=code,
                            command=self._on_lang_change).pack(side="left", padx=4)

        ttk.Separator(self, orient="horizontal").grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=10, pady=(6, 2))

        # ── Admin account ─────────────────────────────────────────────────────
        ttk.Label(self, text=i18n._("provision_admin_label")).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 2))

        ttk.Label(self, text=i18n._("lbl_email")).grid(row=3, column=0, sticky="e", **pad)
        self._email = ttk.Entry(self, width=30)
        self._email.grid(row=3, column=1, sticky="w", **pad)

        self._no_pw = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text=i18n._("lbl_no_password"),
                        variable=self._no_pw,
                        command=self._toggle_pw).grid(
            row=4, column=0, columnspan=2, sticky="w", padx=14, pady=(4, 0))

        self._pw_label1 = ttk.Label(self, text=i18n._("lbl_password"))
        self._pw_label1.grid(row=5, column=0, sticky="e", **pad)
        self._pw1 = ttk.Entry(self, show="*", width=30)
        self._pw1.grid(row=5, column=1, sticky="w", **pad)

        self._pw_label2 = ttk.Label(self, text=i18n._("lbl_confirm_pw"))
        self._pw_label2.grid(row=6, column=0, sticky="e", **pad)
        self._pw2 = ttk.Entry(self, show="*", width=30)
        self._pw2.grid(row=6, column=1, sticky="w", **pad)

        ttk.Separator(self, orient="horizontal").grid(
            row=7, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        ttk.Label(self, text=i18n._("provision_webdav_hint")).grid(
            row=8, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 2))

        ttk.Label(self, text=i18n._("lbl_webdav_url")).grid(row=9, column=0, sticky="e", **pad)
        self._nc_url = ttk.Entry(self, width=36)
        self._nc_url.grid(row=9, column=1, sticky="w", **pad)

        ttk.Label(self, text=i18n._("lbl_username")).grid(row=10, column=0, sticky="e", **pad)
        self._nc_user = ttk.Entry(self, width=36)
        self._nc_user.grid(row=10, column=1, sticky="w", **pad)

        ttk.Label(self, text=i18n._("lbl_app_password")).grid(row=11, column=0, sticky="e", **pad)
        self._nc_pw = ttk.Entry(self, show="*", width=36)
        self._nc_pw.grid(row=11, column=1, sticky="w", **pad)

        ttk.Separator(self, orient="horizontal").grid(
            row=12, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=13, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(btn_frame, text=i18n._("btn_generate_key"),
                   command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text=i18n._("btn_cancel"),
                   command=self.destroy).pack(side="left", padx=6)

        self._email.focus_set()
        self.bind("<Return>", lambda _: self._confirm())
        _center_dialog(self, parent)

    def _on_lang_change(self):
        import settings
        lang = self._lang_var.get()
        settings.set("language", lang)
        i18n.load(lang)
        self.result = ("__reload__",)
        self.destroy()

    def _toggle_pw(self):
        state = "disabled" if self._no_pw.get() else "normal"
        self._pw1.configure(state=state)
        self._pw2.configure(state=state)
        dim = "#888888" if self._no_pw.get() else ""
        self._pw_label1.configure(foreground=dim)
        self._pw_label2.configure(foreground=dim)

    def _confirm(self):
        email = self._email.get().strip()
        if not email or "@" not in email:
            show_error(self, i18n._("err_title"), i18n._("err_email_invalid"))
            return

        if self._no_pw.get():
            password = None
        else:
            pw1 = self._pw1.get()
            pw2 = self._pw2.get()
            if pw1 != pw2:
                show_error(self, i18n._("err_title"), i18n._("err_passwords_mismatch"))
                return
            if len(pw1) < 8:
                show_error(self, i18n._("err_title"), i18n._("err_password_too_short"))
                return
            password = pw1.encode()

        sync_data = None
        url = self._nc_url.get().strip()
        if url:
            if not url.startswith(("http://", "https://")):
                show_error(self, i18n._("err_url_invalid_title"),
                    i18n._("err_url_invalid_body").format(url=url))
                return
            nc_user = self._nc_user.get().strip()
            if not nc_user:
                show_error(self, i18n._("err_title"), i18n._("err_username_required"))
                return
            sync_data = {
                "webdav_url": url,
                "auth_user":  nc_user,
                "password":   self._nc_pw.get(),
            }

        self.result = (email, password, sync_data)
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
        # Mark the pre-selected color if editing
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


class SyncConfigDialog(tk.Toplevel):
    """View and update the WebDAV sync configuration (admin only)."""

    def __init__(self, parent, current_config: dict | None):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("sync_title"))
        self.resizable(False, False)

        # result: dict with sync data, {} to clear, None if cancelled
        self.result = None

        pad = _PAD

        ttk.Label(self, text=i18n._("sync_hint")).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(12, 6))

        ttk.Label(self, text=i18n._("lbl_webdav_url")).grid(row=1, column=0, sticky="e", **pad)
        self._url = ttk.Entry(self, width=40)
        self._url.grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(self, text=i18n._("lbl_username")).grid(row=2, column=0, sticky="e", **pad)
        self._user = ttk.Entry(self, width=40)
        self._user.grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(self, text=i18n._("lbl_app_password")).grid(row=3, column=0, sticky="e", **pad)
        self._pw = ttk.Entry(self, show="*", width=40)
        self._pw.grid(row=3, column=1, sticky="w", **pad)

        # Pre-fill with existing config
        if current_config:
            self._url.insert(0, current_config.get("webdav_url", ""))
            self._user.insert(0, current_config.get("auth_user", ""))
            self._pw.insert(0, current_config.get("password", ""))

        ttk.Separator(self, orient="horizontal").grid(
            row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(btn_frame, text=i18n._("btn_save"), command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text=i18n._("btn_cancel"), command=self.destroy).pack(side="left", padx=6)

        self._url.focus_set()
        self.bind("<Return>", lambda _: self._confirm())
        _center_dialog(self, parent)

    def _confirm(self):
        url = self._url.get().strip()
        if not url:
            # Disable sync
            self.result = {}
            self.destroy()
            return

        if not url.startswith(("http://", "https://")):
            show_error(self, i18n._("err_url_invalid_title"),
                i18n._("err_url_invalid_body").format(url=url))
            return

        user = self._user.get().strip()
        if not user:
            show_error(self, i18n._("err_title"), i18n._("err_username_required"))
            return

        self.result = {
            "webdav_url": url,
            "auth_user":  user,
            "password":   self._pw.get(),
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

        # Frequency row
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

        # Interval (shown for all freq except none)
        self._interval_frame = ttk.Frame(self)
        ttk.Label(self._interval_frame, text=i18n._("lbl_every")).pack(side="left")
        ttk.Entry(self._interval_frame, textvariable=self._interval,
                  width=4).pack(side="left", padx=4)
        self._unit_lbl = ttk.Label(self._interval_frame, text="")
        self._unit_lbl.pack(side="left")

        # Weekday checkboxes (weekly only)
        self._weekly_frame = ttk.Frame(self)
        ttk.Label(self._weekly_frame, text=i18n._("lbl_on_weekdays")).pack(side="left")
        for code, short in zip(_WD_CODES, i18n.WD_SHORT):
            ttk.Checkbutton(self._weekly_frame, text=short,
                            variable=self._wd_vars[code]).pack(side="left", padx=1)

        # Monthly options (monthly only)
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

        # Separator — used as anchor for pack(before=...) ordering
        self._sep = ttk.Separator(self, orient="horizontal")
        self._sep.pack(fill="x", padx=px, pady=8)

        # End section
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

        # Buttons
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
            # Allow selection/copy/navigation but block editing
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


# ── User management ───────────────────────────────────────────────────────────

class AddUserDialog(tk.Toplevel):
    """Admin: add a new user — generate keypair or register an existing public key."""

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("add_user_title"))
        self.resizable(False, False)

        # result: (email, kpub_or_None, password_or_None)
        # kpub_or_None — cryptography public key object if user provided their own
        # password_or_None — bytes if keypair should be generated with this password
        self.result = None

        pad = _PAD

        ttk.Label(self, text=i18n._("lbl_email")).grid(row=0, column=0, sticky="e", **pad)
        self._email = ttk.Entry(self, width=32)
        self._email.grid(row=0, column=1, columnspan=2, sticky="w", **pad)

        ttk.Separator(self, orient="horizontal").grid(
            row=1, column=0, columnspan=3, sticky="ew", padx=10, pady=6)

        self._mode = tk.StringVar(value="generate")
        ttk.Radiobutton(self, text=i18n._("lbl_generate_keypair"),
                        variable=self._mode, value="generate").grid(
            row=2, column=0, columnspan=3, sticky="w", padx=10)

        self._no_pw = tk.BooleanVar(value=False)
        ttk.Checkbutton(self, text=i18n._("lbl_no_password"),
                        variable=self._no_pw,
                        command=self._toggle_pw).grid(
            row=3, column=0, columnspan=3, sticky="w", padx=28)

        self._pw_label1 = ttk.Label(self, text=i18n._("lbl_password"))
        self._pw_label1.grid(row=4, column=0, sticky="e", **pad)
        self._pw1 = ttk.Entry(self, show="*", width=24)
        self._pw1.grid(row=4, column=1, columnspan=2, sticky="w", **pad)

        self._pw_label2 = ttk.Label(self, text=i18n._("lbl_confirm_pw"))
        self._pw_label2.grid(row=5, column=0, sticky="e", **pad)
        self._pw2 = ttk.Entry(self, show="*", width=24)
        self._pw2.grid(row=5, column=1, columnspan=2, sticky="w", **pad)

        ttk.Separator(self, orient="horizontal").grid(
            row=6, column=0, columnspan=3, sticky="ew", padx=10, pady=6)

        ttk.Radiobutton(self, text=i18n._("lbl_external_key"),
                        variable=self._mode, value="external").grid(
            row=7, column=0, columnspan=3, sticky="w", padx=10)

        self._kpub_text = tk.Text(self, width=38, height=6, wrap="none")
        self._kpub_text.grid(row=8, column=0, columnspan=3,
                              padx=10, pady=(0, 6), sticky="ew")

        ttk.Separator(self, orient="horizontal").grid(
            row=9, column=0, columnspan=3, sticky="ew", padx=10, pady=6)

        ttk.Label(self, text=i18n._("lbl_role")).grid(row=10, column=0, sticky="e", **pad)
        self._role = tk.StringVar(value="viewer")
        role_frame = ttk.Frame(self)
        role_frame.grid(row=10, column=1, columnspan=2, sticky="w", **pad)
        for label, value in [("Viewer", "viewer"), ("Editor", "editor"), ("Admin", "admin")]:
            ttk.Radiobutton(role_frame, text=label,
                            variable=self._role, value=value).pack(side="left", padx=4)

        ttk.Separator(self, orient="horizontal").grid(
            row=11, column=0, columnspan=3, sticky="ew", padx=10, pady=6)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=12, column=0, columnspan=3, pady=(0, 10))
        ttk.Button(btn_frame, text=i18n._("btn_add_user"),
                   command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text=i18n._("btn_cancel"),
                   command=self.destroy).pack(side="left", padx=6)

        self._email.focus_set()
        _center_dialog(self, parent)

    def _toggle_pw(self):
        state = "disabled" if self._no_pw.get() else "normal"
        self._pw1.configure(state=state)
        self._pw2.configure(state=state)
        self._pw_label1.configure(foreground="#888888" if self._no_pw.get() else "")
        self._pw_label2.configure(foreground="#888888" if self._no_pw.get() else "")

    def _confirm(self):
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        email = self._email.get().strip()
        if not email or "@" not in email:
            show_error(self, i18n._("err_title"), i18n._("err_email_invalid"))
            return

        mode = self._mode.get()

        if mode == "generate":
            if self._no_pw.get():
                self.result = (email, None, None, self._role.get())
            else:
                pw1 = self._pw1.get()
                pw2 = self._pw2.get()
                if pw1 != pw2:
                    show_error(self, i18n._("err_title"), i18n._("err_passwords_mismatch"))
                    return
                if len(pw1) < 8:
                    show_error(self, i18n._("err_title"), i18n._("err_password_too_short"))
                    return
                self.result = (email, None, pw1.encode(), self._role.get())
        else:
            pem_text = self._kpub_text.get("1.0", "end").strip().encode()
            if not pem_text:
                show_error(self, i18n._("err_title"), i18n._("err_pubkey_empty"))
                return
            try:
                kpub = load_pem_public_key(pem_text)
            except Exception:
                show_error(self, i18n._("err_title"), i18n._("err_pubkey_invalid"))
                return
            self.result = (email, kpub, None, self._role.get())

        self.destroy()


class UserManagementDialog(tk.Toplevel):
    """Admin-only: list, add, and remove users."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("user_mgmt_title"))
        self.resizable(True, True)
        self.minsize(600, 340)
        self.geometry("660x420")
        self._app = app

        ttk.Button(self, text=i18n._("btn_add_user_toolbar"),
                   command=self._add_user).pack(
            anchor="w", padx=10, pady=(10, 4))

        # Treeview
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10, pady=4)

        cols = ("email", "role")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings",
                                  selectmode="browse", height=8)
        self._tree.heading("email", text=i18n._("col_email"))
        self._tree.heading("role",  text=i18n._("col_role"))
        self._tree.column("email", width=440)
        self._tree.column("role",  width=120, anchor="center")

        sb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        ttk.Button(self, text=i18n._("btn_remove"),
                   command=self._remove_selected).pack(pady=(4, 0))
        ttk.Button(self, text=i18n._("btn_close"),
                   command=self.destroy).pack(pady=(4, 10))

        self._users: dict[str, dict] = {}  # iid → user dict
        self._refresh()
        _center_dialog(self, parent)

    def _refresh(self):
        self._tree.delete(*self._tree.get_children())
        self._users.clear()
        self._tree.tag_configure("row", background=theme.BG_ALT)
        role_labels = {"admin": "Admin", "editor": "Editor", "viewer": "Viewer"}
        for u in self._app.list_users():
            iid = self._tree.insert("", "end", tags=("row",), values=(
                u["email"] or f"{u['hash']}",
                role_labels.get(u["role"], u["role"]),
            ))
            self._users[iid] = u

    def _add_user(self):
        import tkinter.filedialog as fd

        dlg = AddUserDialog(self)
        self.wait_window(dlg)
        self.grab_set()
        if dlg.result is None:
            return

        email, kpub, password, role = dlg.result

        # If we'll be generating a key, ask WHERE to save it BEFORE
        # committing anything to disk / calendar.json.
        save_path = None
        if kpub is None:
            h = storage.email_to_hash(email)
            save_path = fd.asksaveasfilename(
                parent=self,
                title=i18n._("save_key_title").format(email=email),
                defaultextension=".pem",
                filetypes=[(i18n._("file_type_pem"), "*.pem")],
                initialfile=f"{h}.pem",
            )
            if not save_path:
                return  # user cancelled — nothing written yet

        try:
            kpriv_bytes = self._app.add_user(email, kpub, password, role=role,
                                             save_locally=save_path is None)
        except RuntimeError as e:
            show_error(self, i18n._("err_title"), str(e))
            return

        if kpriv_bytes and save_path:
            try:
                with open(save_path, "wb") as f:
                    f.write(kpriv_bytes)
                show_info(self, i18n._("key_saved_title"),
                    i18n._("key_saved_body").format(path=save_path))
            except Exception as exc:
                show_error(self, i18n._("err_title"),
                    i18n._("err_save_failed").format(exc=exc))
        self._refresh()

    def _remove_selected(self):
        sel = self._tree.selection()
        if not sel:
            show_info(self, i18n._("user_mgmt_title"), i18n._("hint_select_user"))
            return
        u = self._users.get(sel[0])
        if u is None:
            return
        label = u["email"] or u["hash"][:16]
        if not ask_yes_no(self, i18n._("confirm_remove_title"),
            i18n._("confirm_remove_body").format(label=label)):
            return
        try:
            self._app.remove_user(u["hash"])
        except RuntimeError as e:
            show_error(self, i18n._("err_title"), str(e))
            return
        self._refresh()


class LanguageDialog(tk.Toplevel):
    """Let the user pick a display language. Change takes effect on next start."""

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("lang_dialog_title"))
        self.resizable(False, False)

        self._lang_var = tk.StringVar(value=i18n.get())

        ttk.Label(self, text=i18n._("lang_dialog_hint"),
                  foreground=theme.FG_DIM).pack(padx=20, pady=(16, 8))

        for code, label in i18n.SUPPORTED:
            ttk.Radiobutton(self, text=label,
                            variable=self._lang_var, value=code).pack(
                anchor="w", padx=28, pady=2)

        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=(12, 14))
        ttk.Button(btn_frame, text=i18n._("btn_ok"),
                   command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text=i18n._("btn_cancel"),
                   command=self.destroy).pack(side="left", padx=6)

        _center_dialog(self, parent)

    def _confirm(self):
        import settings
        settings.set("language", self._lang_var.get())
        self.destroy()
