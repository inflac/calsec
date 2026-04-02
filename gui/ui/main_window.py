#!/usr/bin/env python3

from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox

import settings
import theme
from ui.dialogs import AddEntryDialog, ViewEntryDialog, SyncConfigDialog


def _kw_iid(year: int, week: int) -> str:
    return f"_kw_{year}_{week:02d}"


def _is_header(iid: str) -> bool:
    return iid.startswith("_kw_")


class MainWindow(ttk.Frame):
    """Main application frame: entry list + action buttons + status bar."""

    def __init__(self, parent, app, on_toggle_theme=None):
        super().__init__(parent)
        self._app = app
        self._on_toggle_theme = on_toggle_theme
        self._build_ui()
        self.refresh()

        if app.unsigned:
            self._set_status(
                "Warning: calendar file is unsigned — entries may have been tampered with.",
                error=True
            )

    def _build_ui(self):
        # Toolbar
        toolbar = ttk.Frame(self)
        toolbar.pack(side="top", fill="x", padx=6, pady=(6, 0))

        ttk.Button(toolbar, text="Add", command=self._add).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Delete", command=self._delete).pack(side="left", padx=2)
        ttk.Button(toolbar, text="Settings", command=self._sync_settings).pack(side="left", padx=2)

        # Version label + theme toggle (right side)
        self._version_var = tk.StringVar()
        ttk.Label(toolbar, textvariable=self._version_var, foreground=theme.FG_DIM).pack(
            side="right", padx=8)

        if self._on_toggle_theme:
            icon = "☀" if settings.get("theme") == "dark" else "☾"
            ttk.Button(toolbar, text=icon, width=3,
                       command=self._on_toggle_theme).pack(side="right", padx=(0, 2))

        # Treeview
        tree_frame = ttk.Frame(self)
        tree_frame.pack(fill="both", expand=True, padx=6, pady=6)

        cols = ("date", "time", "title", "comments")
        self._tree = ttk.Treeview(tree_frame, columns=cols, show="headings", selectmode="extended")

        self._tree.heading("date", text="Date")
        self._tree.heading("time", text="Time")
        self._tree.heading("title", text="Title")
        self._tree.heading("comments", text="Comments")

        self._tree.column("date", width=100, anchor="center")
        self._tree.column("time", width=80, anchor="center")
        self._tree.column("title", width=260)
        self._tree.column("comments", width=80, anchor="center")

        scrollbar = ttk.Scrollbar(tree_frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._tree.bind("<Double-1>", self._on_double_click)
        self._tree.bind("<<TreeviewSelect>>", self._on_selection_change)

        # Status bar
        self._status_var = tk.StringVar()
        status_bar = ttk.Label(self, textvariable=self._status_var,
                               relief="sunken", anchor="w")
        status_bar.pack(side="bottom", fill="x", padx=0, pady=0)

    def refresh(self):
        self._tree.delete(*self._tree.get_children())

        # Tag for KW separator rows — reconfigure on every refresh so theme changes apply
        self._tree.tag_configure("kw_header",
            foreground=theme.ACCENT,
            background=theme.BG_PANEL,
            font=("Cantarell", 8),
        )

        entries = self._app.get_entries()
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
                    year, week = week_key
                    label = f"KW {week:02d} · {year}"
                    self._tree.insert("", "end",
                        iid=_kw_iid(year, week),
                        values=(label, "", "", ""),
                        tags=("kw_header",),
                    )

            n = len(e.get("comments", []))
            self._tree.insert("", "end", iid=e["id"], values=(
                e["date"], e["time"], e["title"], f"{n}" if n else ""
            ))

        self._version_var.set(f"v{self._app.version}")
        self._set_status(f"{len(entries)} entr{'y' if len(entries) == 1 else 'ies'}")

    def _set_status(self, msg: str):
        self._status_var.set(f"  {msg}")

    def _on_selection_change(self, _event):
        headers = [iid for iid in self._tree.selection() if _is_header(iid)]
        if headers:
            self._tree.selection_remove(*headers)

    def _selected_ids(self):
        return [iid for iid in self._tree.selection() if not _is_header(iid)]

    def _add(self):
        dlg = AddEntryDialog(self)
        self.wait_window(dlg)
        if dlg.result is None:
            return

        title, date_str, time_str, comments = dlg.result
        try:
            self._app.add_entry(
                title, date_str, time_str, comments,
                on_sync_done=self._on_sync_done
            )
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return

        self.refresh()
        self._set_status("Entry added.")

    def _on_double_click(self, event):
        item = self._tree.identify_row(event.y)
        if item and not _is_header(item):
            self._open_entry(item)

    def _open_entry(self, entry_id):
        entries = self._app.get_entries()
        entry = next((e for e in entries if e["id"] == entry_id), None)
        if entry is None:
            return
        ViewEntryDialog(self, entry)

    def _delete(self):
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo("Delete", "Select one or more entries first.", parent=self)
            return

        count = len(ids)
        noun = "entry" if count == 1 else "entries"
        if not messagebox.askyesno(
            "Confirm Delete",
            f"Delete {count} {noun}?",
            parent=self
        ):
            return

        try:
            deleted = self._app.delete_entries(ids, on_sync_done=self._on_sync_done)
        except Exception as exc:
            messagebox.showerror("Error", str(exc), parent=self)
            return

        self.refresh()
        if deleted:
            self._set_status(f"{count} {noun} deleted.")
        else:
            self._set_status("No matching entries found.")

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
            messagebox.showerror("Error", str(exc), parent=self)
            return

        if sync_data:
            self._set_status(f"Sync config saved — {sync_data['url']}")
        else:
            self._set_status("Sync disabled.")
        self.refresh()

    def _on_sync_done(self, msg: str):
        # Called from background thread — schedule on main thread
        self.after(0, lambda: self._set_status(msg or "Sync complete."))
