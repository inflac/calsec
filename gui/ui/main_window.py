#!/usr/bin/env python3

from datetime import datetime, date as _date

import tkinter as tk
from tkinter import ttk

import i18n
import settings
import theme
from crypto import format_fingerprint
from updater import current_version
from ui.dialogs import (AddEntryDialog, ViewEntryDialog,
                        SyncConfigDialog, UserManagementDialog,
                        SettingsDialog, UpdateDialog,
                        DatePickerDialog,
                        show_info, show_error, ask_yes_no,
                        show_copyable_text)


def _kw_iid(year: int, week: int) -> str:
    return f"_kw_{year}_{week:02d}"


def _blend(color: str, base: str, alpha: float = 0.4) -> str:
    """Mix *color* with *base* at *alpha* (0 = base only, 1 = color only)."""
    def _p(h):
        h = h.lstrip("#")
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    r1, g1, b1 = _p(color)
    r2, g2, b2 = _p(base)
    r = int(r1 * alpha + r2 * (1 - alpha))
    g = int(g1 * alpha + g2 * (1 - alpha))
    b = int(b1 * alpha + b2 * (1 - alpha))
    return f"#{r:02x}{g:02x}{b:02x}"


def _is_header(iid: str) -> bool:
    return iid.startswith("_kw_")



class MainWindow(ttk.Frame):
    """Main application frame: entry list + month navigator + action buttons."""

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

        if app.unsigned:
            self._set_status(i18n._("warn_unsigned"), error=True)

    def _build_ui(self):
        # ── Combined top section (2-row grid) ─────────────────────────────────
        # Row 0: toolbar buttons | right-side controls
        # Row 1: [← month →] [Heute] aligned under Löschen | fingerprint
        top = ttk.Frame(self)
        top.pack(side="top", fill="x", padx=6, pady=(6, 0))
        top.columnconfigure(99, weight=1)

        # Right-side controls — spans both toolbar row and nav row
        right = ttk.Frame(top)
        right.grid(row=0, column=99, rowspan=2, sticky="ne")

        # Toolbar row items (packed horizontally at the top of right)
        right_top = ttk.Frame(right)
        right_top.pack(side="top", anchor="e", pady=(0, 2))
        self._top_right = right_top  # used by show_update_banner

        self._version_var = tk.StringVar()
        ttk.Label(right_top, textvariable=self._version_var,
                  foreground=theme.FG_DIM).pack(side="right", padx=8)

        if self._on_toggle_theme:
            icon = "☀" if settings.get("theme") == "dark" else "☾"
            ttk.Button(right_top, text=icon, width=3,
                       command=self._on_toggle_theme).pack(side="right", padx=2)

        ttk.Button(right_top, text=i18n._("btn_app_settings"), width=3,
                   command=self._open_settings).pack(side="right", padx=2)

        if self._pending_update:
            self._update_btn = ttk.Button(
                right_top,
                text=i18n._("update_available_toolbar").format(
                    version=self._pending_update.version),
                command=self._install_update)
            self._update_btn.pack(side="right", padx=(0, 4))
        else:
            self._update_btn = None

        # Toolbar buttons (row 0, left side) — track column index
        col = 0
        if self._app.can_edit:
            ttk.Button(top, text=i18n._("btn_add_toolbar"),
                       command=self._add).grid(
                row=0, column=col, padx=(0, 2), pady=(0, 2), sticky="ew")
            col += 1
            ttk.Button(top, text=i18n._("btn_edit_toolbar"),
                       command=self._edit).grid(
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

        # Nav row (row 1): [← month →] spans cols 0-1, [Heute] at col 2 (under Löschen)
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

        # Fingerprint label (nav row — same styling as version label above)
        if self._app.is_admin:
            fp_label = tk.Label(
                right, text="🔑",
                cursor="hand2",
                font=("Segoe UI Emoji", 9),
                bg=theme.BG, fg=theme.FG_DIM,
            )
            fp_label.pack(side="top", anchor="e", padx=8, pady=(7, 0))
            fp_label.bind("<Button-1>", lambda _: self._show_fingerprint())

        # ── Treeview ──────────────────────────────────────────────────────────
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=6)

        cols = ("date", "time", "title", "comments")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                   selectmode="extended")

        self._tree.heading("date",     text=i18n._("col_date"))
        self._tree.heading("time",     text=i18n._("col_time"))
        self._tree.heading("title",    text=i18n._("col_title"))
        self._tree.heading("comments", text=i18n._("col_comments"))

        self._tree.column("date",     width=100, anchor="center")
        self._tree.column("time",     width=80,  anchor="center")
        self._tree.column("title",    width=260)
        self._tree.column("comments", width=80,  anchor="center")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical",
                                   command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._tree.bind("<Double-1>",        self._on_double_click)
        self._tree.bind("<<TreeviewSelect>>", self._on_selection_change)

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom_frame = ttk.Frame(self)
        bottom_frame.pack(side="bottom", fill="x")

        self._status_var = tk.StringVar()
        self._status_label = tk.Label(bottom_frame, textvariable=self._status_var,
                  relief="sunken", anchor="w", bg=theme.BG, fg=theme.FG)
        self._status_label.pack(side="left", fill="x", expand=True)

        self._app_version_var = tk.StringVar()
        self._app_version_label = tk.Label(bottom_frame, textvariable=self._app_version_var,
                  relief="sunken", anchor="e", bg=theme.BG, fg=theme.FG)
        self._app_version_label.pack(side="right")
        self._app_version_var.set(f"v{current_version()}")

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
        self._tree.delete(*self._tree.get_children())
        self._row_to_id.clear()

        self._month_var.set(
            f"{i18n.MONTHS[self._view_month]} {self._view_year}")

        # Configure all tags BEFORE inserting any rows.
        # In the clam theme, calling tag_configure after inserts causes the last
        # configured background to override all previously configured ones.
        self._tree.tag_configure("kw_header",
            foreground=theme.ACCENT,
            background=theme.BG_PANEL,
            font=("Cantarell", 8),
        )
        self._tree.tag_configure("row_default", background=theme.BG_ALT)

        entries = self._app.get_entries_for_month(self._view_year, self._view_month)

        # Pre-configure one tag per unique color before inserting any items
        for e in entries:
            color = e.get("color")
            if color:
                tag_name = f"color_{color.lstrip('#')}"
                self._tree.tag_configure(tag_name,
                    background=_blend(color, theme.BG))

        current_week_key = None

        for e in entries:
            try:
                iso = datetime.strptime(e["date"], "%d.%m.%Y").isocalendar()
                week_key = (iso.year, iso.week)
            except Exception:
                week_key = None

            if week_key != current_week_key:
                current_week_key = week_key
                if week_key:
                    yr, wk = week_key
                    label = i18n._("kw_label").format(wk=wk, yr=yr)
                    iid = _kw_iid(yr, wk)
                    if not self._tree.exists(iid):
                        self._tree.insert("", "end",
                            iid=iid,
                            values=(label, "", "", ""),
                            tags=("kw_header",),
                        )

            n = len(e.get("comments", []))
            color = e.get("color")
            if color:
                tags = (f"color_{color.lstrip('#')}",)
            else:
                tags = ("row_default",)

            title = ("↻  " + e["title"]) if e.get("is_recurring") else e["title"]
            row_iid = e.get("_row_iid", e["id"])
            self._row_to_id[row_iid] = e["id"]

            self._tree.insert("", "end", iid=row_iid, values=(
                e["date"], e["time"], title, f"{n}" if n else ""
            ), tags=tags)

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

    def _on_selection_change(self, _event):
        headers = [iid for iid in self._tree.selection() if _is_header(iid)]
        if headers:
            self._tree.selection_remove(*headers)

    def _selected_base_ids(self) -> list[str]:
        """Return deduplicated base entry ids for all selected non-header rows."""
        seen = []
        for iid in self._tree.selection():
            if _is_header(iid):
                continue
            base = self._row_to_id.get(iid, iid)
            if base not in seen:
                seen.append(base)
        return seen

    # ── CRUD actions ──────────────────────────────────────────────────────────

    def _add(self):
        dlg = AddEntryDialog(self)
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

    def _edit(self):
        ids = self._selected_base_ids()
        if len(ids) != 1:
            show_info(self, i18n._("btn_edit_toolbar"), i18n._("edit_select_one"))
            return

        entry_id = ids[0]
        entries = self._app.get_entries()
        entry = next((e for e in entries if e["id"] == entry_id), None)
        if entry is None:
            return

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

    def _on_double_click(self, event):
        item = self._tree.identify_row(event.y)
        if item and not _is_header(item):
            self._open_entry(item)

    def _open_entry(self, row_iid: str):
        entry_id = self._row_to_id.get(row_iid, row_iid)
        entries = self._app.get_entries()
        entry = next((e for e in entries if e["id"] == entry_id), None)
        if entry is None:
            return
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
        self._update_btn.pack(side="right", padx=(0, 4))

    def _install_update(self):
        dlg = UpdateDialog(self, update_info=self._pending_update, can_skip=True)
        self.wait_window(dlg)

    def _pull_sync(self):
        self._set_status(i18n._("status_syncing"))
        self._app.sync_pull(on_done=self._on_sync_done)

    def _on_sync_done(self, msg: str):
        is_error = bool(msg and msg.startswith("Sync error"))
        display = msg or i18n._("status_sync_done")
        self.after(0, lambda: self._set_status(display, error=is_error))
        self.after(0, self.refresh)
