#!/usr/bin/env python3

import threading
import tkinter as tk
from datetime import date as _date
from datetime import datetime
from tkinter import ttk

import i18n
import settings
import theme
from crypto import format_fingerprint
from ui.dialogs import (
    AddEntryDialog,
    DatePickerDialog,
    SettingsDialog,
    SyncConfigDialog,
    UpdateDialog,
    UserManagementDialog,
    ViewEntryDialog,
    ask_text,
    ask_yes_no,
    show_copyable_text,
    show_error,
    show_info,
)
from ui.list_view import ListView
from ui.month_view import MonthView
from updater import current_version


class MainWindow(ttk.Frame):
    """Main application frame: entry list or month grid + month navigator + action buttons."""

    def __init__(self, parent, app, on_toggle_theme=None, pending_update=None):
        super().__init__(parent)
        self._app = app
        self._on_toggle_theme = on_toggle_theme
        self._pending_update = pending_update
        self._row_to_id: dict[str, str] = {}

        today = _date.today()
        self._view_year = today.year
        self._view_month = today.month

        self._build_ui()
        self._initial_refresh()

    def _build_ui(self):
        # ── Combined top section (2-row grid) ─────────────────────────────────
        # Row 0: toolbar buttons | right-side controls
        # Row 1: [← month →] [Heute] aligned under Löschen | fingerprint
        top = ttk.Frame(self)
        top.pack(side="top", fill="x", padx=6, pady=(6, 0))
        top.columnconfigure(99, weight=1)
        self._top = top  # its width sets the window's minimum width

        # Right-side controls — spans both toolbar row and nav row
        right = ttk.Frame(top)
        right.grid(row=0, column=99, rowspan=2, sticky="ne")
        self._top_right = right  # used by show_update_banner

        ttk.Button(right, text=i18n._("btn_app_settings"), width=3,
                   command=self._open_settings).grid(
            row=0, column=1, padx=2, pady=(0, 2), sticky="ew")
        icon_cols = 1
        if self._on_toggle_theme:
            icon = "☀" if settings.get("theme") == "dark" else "☾"
            ttk.Button(right, text=icon, width=3,
                       command=self._on_toggle_theme).grid(
                row=0, column=2, padx=2, pady=(0, 2), sticky="ew")
            icon_cols = 2

        self._version_var = tk.StringVar()
        ttk.Label(right, textvariable=self._version_var,
                  foreground=theme.FG_DIM).grid(row=0, column=3, padx=8)

        # View toggle — as wide as settings + theme, directly below them.
        # Like the theme button, it shows the view a click switches to.
        self._view_btn = ttk.Button(right, style="Tight.TButton",
                                    command=self._toggle_view)
        self._view_btn.grid(row=1, column=1, columnspan=icon_cols,
                            padx=2, pady=(0, 4), sticky="ew")

        if self._pending_update:
            self._update_btn = ttk.Button(
                right,
                text=i18n._("update_available_toolbar").format(
                    version=self._pending_update.version),
                command=self._install_update)
            self._update_btn.grid(row=0, column=0, padx=(0, 4), pady=(0, 2))
        else:
            self._update_btn = None

        # Toolbar buttons (row 0, left side) — track column index
        col = 0
        if self._app.can_edit:
            ttk.Button(top, text=i18n._("btn_add_toolbar"),
                       command=self._add).grid(
                row=0, column=col, padx=(0, 2), pady=(0, 2), sticky="ew")
            col += 1
            ttk.Button(top, text=i18n._("btn_delete_toolbar"),
                       command=self._delete).grid(
                row=0, column=col, padx=(0, 2), pady=(0, 2), sticky="ew")
            col += 1
        if self._app.is_admin:
            ttk.Button(top, text=i18n._("btn_settings_toolbar"),
                       command=self._sync_settings).grid(
                row=0, column=col, padx=(0, 2), pady=(0, 2), sticky="ew")
            col += 1
            ttk.Button(top, text=i18n._("btn_users_toolbar"),
                       command=self._manage_users).grid(
                row=0, column=col, padx=(0, 2), pady=(0, 2), sticky="ew")
            col += 1
        ttk.Button(top, text=i18n._("btn_sync_toolbar"),
                   command=self._pull_sync).grid(
            row=0, column=col, padx=(0, 2), pady=(0, 2), sticky="ew")

        # Nav row (row 1): [← month →] spans cols 0-1, [Today] at col 2
        month_nav = ttk.Frame(top)
        month_nav.grid(row=1, column=0, columnspan=2, sticky="ew",
                       padx=(0, 2), pady=(0, 4))

        ttk.Button(month_nav, text="←", width=3,
                   command=self._prev_month).pack(side="left")
        ttk.Button(month_nav, text="→", width=3,
                   command=self._next_month).pack(side="right")
        self._month_var = tk.StringVar()
        self._month_label = tk.Label(
            month_nav,
            textvariable=self._month_var,
            anchor="center",
            cursor="hand2",
            bg=theme.BG,
            fg=theme.FG,
        )
        self._month_label.pack(side="left", expand=True, fill="x", padx=4)
        self._month_label.bind("<Button-1>", self._pick_date)

        ttk.Button(top, text=i18n._("btn_today"),
                   command=self._goto_today).grid(
            row=1, column=2, padx=(0, 2), pady=(0, 4), sticky="ew")

        # Fingerprint label (nav row, far right — same styling as version label above)
        if self._app.is_admin:
            fp_label = tk.Label(
                right, text="FP",
                cursor="hand2",
                font=("Sans", 9),
                bg=theme.BG, fg=theme.FG_DIM,
            )
            fp_label.grid(row=1, column=3, padx=8, pady=(0, 4))
            fp_label.bind("<Button-1>", lambda _: self._show_fingerprint())

        # ── Content: list or month grid (same interface, one shown at a time) ──
        content = ttk.Frame(self)
        content.pack(fill="both", expand=True, padx=6, pady=6)

        self._list_view = ListView(content, on_open=self._open_entry)
        self._month_view = MonthView(
            content,
            on_open=self._open_entry,
            on_add_date=self._add if self._app.can_edit else None,
        )
        # The window takes its default size from the shown view.
        self._list_view.update_idletasks()
        self._month_view.configure(width=self._list_view.winfo_reqwidth(),
                                   height=self._list_view.winfo_reqheight())
        self._views = {"list": self._list_view, "month": self._month_view}

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom_frame = ttk.Frame(self)
        # Pack before the content: when the window shrinks, pack takes space
        # from the widgets packed last, so the content shrinks, not this bar.
        bottom_frame.pack(side="bottom", fill="x", before=content)

        self._status_var = tk.StringVar()
        self._status_label = tk.Label(bottom_frame, textvariable=self._status_var,
                  relief="sunken", anchor="w", bg=theme.BG, fg=theme.FG)
        self._status_label.pack(side="left", fill="x", expand=True)

        self._app_version_var = tk.StringVar()
        self._app_version_label = tk.Label(bottom_frame, textvariable=self._app_version_var,
                  relief="sunken", anchor="e", bg=theme.BG, fg=theme.FG)
        self._app_version_label.pack(side="right")
        self._app_version_var.set(f"v{current_version()}")

        self._view_mode = None
        self._set_view(settings.get("view_mode"), save=False)

        # The window must not get narrower than the toolbar, otherwise the
        # controls on the right (version, settings, theme, view, FP) are cut off.
        # Restore the app's own minimum when this frame goes away.
        win = self.winfo_toplevel()
        # Remember the app's own minimum once: on a theme switch the new frame
        # is built while the old one has still raised it.
        if not hasattr(win, "_calsec_base_minsize"):
            win._calsec_base_minsize = win.minsize()
        self._base_minsize = win._calsec_base_minsize
        self.bind("<Destroy>", lambda e: e.widget is self and win.minsize(*self._base_minsize))
        self.after_idle(self._fit_min_width)

    def _fit_min_width(self):
        """Raise the window's minimum width to what the toolbar needs."""
        self._top.update_idletasks()
        needed = self._top.winfo_reqwidth() + 12   # + padx of the top frame
        base_w, base_h = self._base_minsize
        self.winfo_toplevel().minsize(max(base_w, needed), base_h)

    def _set_view(self, mode: str, save: bool = True):
        """Show the list ("list") or the month grid ("month")."""
        mode = mode if mode in ("list", "month") else "list"
        if mode == self._view_mode:
            return
        self._view_mode = mode
        for m, view in self._views.items():
            if m == mode:
                view.pack(fill="both", expand=True)
            else:
                view.pack_forget()
        self._view_btn.configure(
            text=i18n._("view_toggle_to_list") if mode == "month"
            else i18n._("view_toggle_to_month"))
        if save:
            settings.set("view_mode", mode)

    def _toggle_view(self):
        self._set_view("list" if self._view_mode == "month" else "month")

    # ── Month navigation ──────────────────────────────────────────────────────

    def _initial_refresh(self):
        """Refresh; if current month is empty, auto-jump to the nearest future month
        that has entries (scans up to 24 months ahead)."""
        self.refresh()
        if not self._app.get_entries_for_month(self._view_year, self._view_month):
            y, m = self._view_year, self._view_month
            for _ in range(24):
                m += 1
                if m > 12:
                    m, y = 1, y + 1
                if self._app.get_entries_for_month(y, m):
                    self._view_year, self._view_month = y, m
                    self.refresh()
                    return

    def _prev_month(self):
        m, y = self._view_month - 1, self._view_year
        if m < 1:
            m, y = 12, y - 1
        self._view_month, self._view_year = m, y
        self.refresh()

    def _next_month(self):
        m, y = self._view_month + 1, self._view_year
        if m > 12:
            m, y = 1, y + 1
        self._view_month, self._view_year = m, y
        self.refresh()

    def _goto_today(self):
        today = _date.today()
        self._view_year, self._view_month = today.year, today.month
        self.refresh()

    def _pick_date(self, _event=None):
        dlg = DatePickerDialog(
            self,
            _date(self._view_year, self._view_month, 1),
        )
        self.wait_window(dlg)
        if dlg.result is None:
            return
        self._view_year, self._view_month = dlg.result.year, dlg.result.month
        self.refresh()

    # ── Data / display ────────────────────────────────────────────────────────

    def refresh(self):
        self._month_var.set(
            f"{i18n.MONTHS[self._view_month]} {self._view_year}")

        entries = self._app.get_entries_for_month(self._view_year, self._view_month)
        # Recurring instances have their own row iid, map it back to the entry id
        self._row_to_id = {e.get("_row_iid", e["id"]): e["id"] for e in entries}
        for view in self._views.values():
            view.set_data(self._view_year, self._view_month, entries)

        self._version_var.set(f"v{self._app.version}")
        count = len(entries)
        if count == 0:
            self._set_status(i18n._("status_no_entries"))
        elif count == 1:
            self._set_status(i18n._("status_entry_singular").format(count=count))
        else:
            self._set_status(i18n._("status_entry_plural").format(count=count))

    def _set_status(self, msg: str, error: bool = False):
        self._status_var.set(f"  {msg}")
        self._status_label.configure(fg=theme.RED if error else theme.FG)

    # ── Selection helpers ─────────────────────────────────────────────────────

    def _selected_base_ids(self) -> list[str]:
        """Return deduplicated base entry ids selected in the visible view."""
        return self._views[self._view_mode].selected_base_ids()

    # ── CRUD actions ──────────────────────────────────────────────────────────

    def _add(self, date_str: str | None = None):
        dlg = AddEntryDialog(self, initial_date=date_str)
        self.wait_window(dlg)
        if dlg.result is None:
            return

        title, date_str, time_str, comments, color, recurrence = dlg.result
        try:
            self._app.add_entry(
                title, date_str, time_str, comments, color=color,
                recurrence=recurrence, on_sync_done=self._on_sync_done,
            )
        except Exception as exc:
            show_error(self, i18n._("err_title"), str(exc))
            return

        # Jump to the month of the new entry
        try:
            d = datetime.strptime(date_str, "%d.%m.%Y")
            self._view_year, self._view_month = d.year, d.month
        except Exception:
            pass

        self.refresh()
        self._set_status(i18n._("status_added"))

    def _edit(self, entry: dict):
        entry_id = entry["id"]
        dlg = AddEntryDialog(self, entry=entry)
        self.wait_window(dlg)
        if dlg.result is None:
            return

        title, date_str, time_str, comments, color, recurrence = dlg.result
        try:
            self._app.update_entry(
                entry_id, title, date_str, time_str, comments, color=color,
                recurrence=recurrence, on_sync_done=self._on_sync_done,
            )
        except Exception as exc:
            show_error(self, i18n._("err_title"), str(exc))
            return

        self.refresh()
        self._set_status(i18n._("status_updated"))

    def _open_entry(self, row_iid: str):
        """Double-click: editors and admins edit the entry, others only view it."""
        entry_id = self._row_to_id.get(row_iid, row_iid)
        entries = self._app.get_entries()
        entry = next((e for e in entries if e["id"] == entry_id), None)
        if entry is None:
            return
        if self._app.can_edit:
            self._edit(entry)
        else:
            ViewEntryDialog(self, entry)

    def _delete(self):
        ids = self._selected_base_ids()
        if not ids:
            show_info(self, i18n._("btn_delete_toolbar"), i18n._("delete_select_some"))
            return

        count = len(ids)
        body = (i18n._("confirm_delete_singular") if count == 1
                else i18n._("confirm_delete_plural")).format(count=count)
        if not ask_yes_no(self, i18n._("confirm_delete_title"), body):
            return

        try:
            deleted = self._app.delete_entries(ids,
                on_sync_done=self._on_sync_done)
        except Exception as exc:
            show_error(self, i18n._("err_title"), str(exc))
            return

        self.refresh()
        if deleted:
            status = (i18n._("status_deleted_singular") if count == 1
                      else i18n._("status_deleted_plural")).format(count=count)
            self._set_status(status)
        else:
            self._set_status(i18n._("status_not_found"))

    def _sync_settings(self):
        current = self._app.sync_config
        dlg = SyncConfigDialog(self, current)
        self.wait_window(dlg)
        if dlg.result is None:
            return

        sync_data = dlg.result if dlg.result else None
        try:
            self._app.update_sync_config(sync_data, on_sync_done=self._on_sync_done)
        except Exception as exc:
            show_error(self, i18n._("err_title"), str(exc))
            return

        if sync_data:
            self._set_status(i18n._("status_sync_saved").format(url=sync_data["webdav_url"]))
        else:
            self._set_status(i18n._("status_sync_disabled"))
        self.refresh()

    def _manage_users(self):
        UserManagementDialog(self, self._app)

    def _show_fingerprint(self):
        show_copyable_text(
            self,
            i18n._("fingerprint_title"),
            i18n._("fingerprint_copy_hint"),
            format_fingerprint(self._app.fingerprint),
        )

    def _open_settings(self):
        dlg = SettingsDialog(self)
        self.wait_window(dlg)

    def show_update_banner(self, info) -> None:
        """Called from Application when a notify-mode check finds an update."""
        self._pending_update = info
        if self._update_btn is not None:
            return  # already shown
        self._update_btn = ttk.Button(
            self._top_right,
            text=i18n._("update_available_toolbar").format(version=info.version),
            command=self._install_update)
        self._update_btn.grid(row=0, column=0, padx=(0, 4), pady=(0, 2))
        self._fit_min_width()  # the toolbar got wider

    def _install_update(self):
        dlg = UpdateDialog(self, update_info=self._pending_update, can_skip=True)
        self.wait_window(dlg)

    def _pull_sync(self):
        self._set_status(i18n._("status_syncing"))
        self._app.sync_pull(
            on_done=self._on_sync_done,
            request_trust=self._request_sign_key_trust,
        )

    def _on_sync_done(self, msg: str):
        is_error = bool(msg and msg.startswith("Sync error"))
        display = msg or i18n._("status_sync_done")
        self.after(0, lambda: self._set_status(display, error=is_error))
        self.after(0, self.refresh)

    def _request_sign_key_trust(self, remote_fingerprint: str) -> str | None:
        result = {"value": None}
        ready = threading.Event()

        def _prompt():
            result["value"] = ask_text(
                self,
                i18n._("trust_sign_keys_title"),
                i18n._("trust_sign_keys_body").format(
                    fingerprint=format_fingerprint(remote_fingerprint)),
            )
            ready.set()

        self.after(0, _prompt)
        ready.wait()
        return result["value"]
