#!/usr/bin/env python3

import calendar as _cal_mod
from datetime import datetime, date as _date

import tkinter as tk
from tkinter import ttk

import settings
import theme
from ui.dialogs import (AddEntryDialog, ViewEntryDialog,
                        SyncConfigDialog, UserManagementDialog,
                        show_info, show_error, ask_yes_no)


_GERMAN_MONTHS = [
    "", "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]


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

    def __init__(self, parent, app, on_toggle_theme=None):
        super().__init__(parent)
        self._app = app
        self._on_toggle_theme = on_toggle_theme
        self._row_to_id: dict[str, str] = {}

        today = _date.today()
        self._view_year = today.year
        self._view_month = today.month

        self._build_ui()
        self._initial_refresh()

        if app.unsigned:
            self._set_status(
                "Warning: calendar file is unsigned — entries may have been tampered with.",
                error=True,
            )

    def _build_ui(self):
        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x", padx=6, pady=(6, 0))

        if self._app.can_edit:
            ttk.Button(toolbar, text="Add",
                       command=self._add).pack(side="left", padx=2)
            ttk.Button(toolbar, text="Edit",
                       command=self._edit).pack(side="left", padx=2)
            ttk.Button(toolbar, text="Delete",
                       command=self._delete).pack(side="left", padx=2)
        if self._app.is_admin:
            ttk.Button(toolbar, text="Settings",
                       command=self._sync_settings).pack(side="left", padx=2)
            ttk.Button(toolbar, text="Benutzer",
                       command=self._manage_users).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Sync",
                   command=self._pull_sync).pack(side="left", padx=2)

        self._version_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self._version_var,
                  foreground=theme.FG_DIM).pack(side="right", padx=8)

        if self._on_toggle_theme:
            icon = "☀" if settings.get("theme") == "dark" else "☾"
            ttk.Button(toolbar, text=icon, width=3,
                       command=self._on_toggle_theme).pack(side="right", padx=(0, 2))

        # ── Month navigator ───────────────────────────────────────────────────
        nav = ttk.Frame(self)
        nav.pack(side="top", fill="x", padx=6, pady=(4, 0))

        ttk.Button(nav, text="←", width=3,
                   command=self._prev_month).pack(side="left")
        self._month_var = tk.StringVar()
        ttk.Label(nav, textvariable=self._month_var,
                  anchor="center", width=20).pack(side="left", padx=8)
        ttk.Button(nav, text="→", width=3,
                   command=self._next_month).pack(side="left")
        ttk.Button(nav, text="Heute",
                   command=self._goto_today).pack(side="left", padx=(14, 0))

        # ── Treeview ──────────────────────────────────────────────────────────
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=6)

        cols = ("date", "time", "title", "comments")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings",
                                   selectmode="extended")

        self._tree.heading("date",     text="Datum")
        self._tree.heading("time",     text="Uhrzeit")
        self._tree.heading("title",    text="Titel")
        self._tree.heading("comments", text="Kommentare")

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

        # ── Status bar ────────────────────────────────────────────────────────
        self._status_var = tk.StringVar()
        self._status_label = tk.Label(self, textvariable=self._status_var,
                  relief="sunken", anchor="w", bg=theme.BG, fg=theme.FG)
        self._status_label.pack(side="bottom", fill="x")

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

    # ── Data / display ────────────────────────────────────────────────────────

    def refresh(self):
        self._tree.delete(*self._tree.get_children())
        self._row_to_id.clear()

        self._month_var.set(
            f"{_GERMAN_MONTHS[self._view_month]} {self._view_year}")

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
                    label = f"KW {wk:02d} · {yr}"
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
            self._set_status("Keine Termine in diesem Monat.")
        else:
            self._set_status(f"{count} Termin{'e' if count != 1 else ''}")

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
            show_error(self, "Error", str(exc))
            return

        # Jump to the month of the new entry
        try:
            d = datetime.strptime(date_str, "%d.%m.%Y")
            self._view_year, self._view_month = d.year, d.month
        except Exception:
            pass

        self.refresh()
        self._set_status("Eintrag hinzugefügt.")

    def _edit(self):
        ids = self._selected_base_ids()
        if len(ids) != 1:
            show_info(self, "Edit", "Genau einen Eintrag zum Bearbeiten auswählen.")
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
            show_error(self, "Error", str(exc))
            return

        self.refresh()
        self._set_status("Eintrag aktualisiert.")

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
            show_info(self, "Delete", "Zuerst einen oder mehrere Einträge auswählen.")
            return

        count = len(ids)
        noun = "Eintrag" if count == 1 else "Einträge"
        if not ask_yes_no(self, "Löschen bestätigen", f"{count} {noun} löschen?"):
            return

        try:
            deleted = self._app.delete_entries(ids,
                on_sync_done=self._on_sync_done)
        except Exception as exc:
            show_error(self, "Error", str(exc))
            return

        self.refresh()
        if deleted:
            self._set_status(f"{count} {noun} gelöscht.")
        else:
            self._set_status("Keine passenden Einträge gefunden.")

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
            show_error(self, "Error", str(exc))
            return

        if sync_data:
            self._set_status(f"Sync gespeichert — {sync_data['webdav_url']}")
        else:
            self._set_status("Sync deaktiviert.")
        self.refresh()

    def _manage_users(self):
        UserManagementDialog(self, self._app)

    def _pull_sync(self):
        self._set_status("Synchronisiere…")
        self._app.sync_pull(on_done=self._on_sync_done)

    def _on_sync_done(self, msg: str):
        is_error = bool(msg and msg.startswith("Sync error"))
        self.after(0, lambda: self._set_status(msg or "Sync abgeschlossen.", error=is_error))
        self.after(0, self.refresh)
