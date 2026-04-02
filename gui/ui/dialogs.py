#!/usr/bin/env python3

import tkinter as tk
from tkinter import ttk, messagebox

import theme


class ProvisionDialog(tk.Toplevel):
    """Shown when no keypair exists. Collects password + optional Nextcloud config."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Setup — Generate Keypair")
        self.resizable(False, False)
        self.wait_visibility()
        self.grab_set()

        self.result = None  # set to (password, sync_data_or_None) on confirm

        pad = {"padx": 10, "pady": 4}

        # --- Password section ---
        ttk.Label(self, text="Create a password for your private key:").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=10, pady=(12, 2))

        ttk.Label(self, text="Password:").grid(row=1, column=0, sticky="e", **pad)
        self._pw1 = ttk.Entry(self, show="*", width=30)
        self._pw1.grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(self, text="Repeat:").grid(row=2, column=0, sticky="e", **pad)
        self._pw2 = ttk.Entry(self, show="*", width=30)
        self._pw2.grid(row=2, column=1, sticky="w", **pad)

        ttk.Separator(self, orient="horizontal").grid(
            row=3, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        # --- Nextcloud section ---
        ttk.Label(self, text="Nextcloud Sync (leave URL blank to skip):").grid(
            row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 2))

        ttk.Label(self, text="URL:").grid(row=5, column=0, sticky="e", **pad)
        self._nc_url = ttk.Entry(self, width=30)
        self._nc_url.grid(row=5, column=1, sticky="w", **pad)

        ttk.Label(self, text="Username:").grid(row=6, column=0, sticky="e", **pad)
        self._nc_user = ttk.Entry(self, width=30)
        self._nc_user.grid(row=6, column=1, sticky="w", **pad)

        ttk.Label(self, text="App password:").grid(row=7, column=0, sticky="e", **pad)
        self._nc_pw = ttk.Entry(self, show="*", width=30)
        self._nc_pw.grid(row=7, column=1, sticky="w", **pad)

        ttk.Label(self, text="Remote path:").grid(row=8, column=0, sticky="e", **pad)
        self._nc_path = ttk.Entry(self, width=30)
        self._nc_path.insert(0, "/calendar.json")
        self._nc_path.grid(row=8, column=1, sticky="w", **pad)

        ttk.Separator(self, orient="horizontal").grid(
            row=9, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=10, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(btn_frame, text="Generate Keys", command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=6)

        self._pw1.focus_set()
        self.bind("<Return>", lambda _: self._confirm())

    def _confirm(self):
        pw1 = self._pw1.get()
        pw2 = self._pw2.get()

        if pw1 != pw2:
            messagebox.showerror("Error", "Passwords do not match.", parent=self)
            return
        if len(pw1) < 8:
            messagebox.showerror("Error", "Password must be at least 8 characters.", parent=self)
            return

        sync_data = None
        url = self._nc_url.get().strip().rstrip("/")
        if url:
            if not url.startswith(("http://", "https://")):
                messagebox.showerror(
                    "Invalid URL",
                    "URL must start with http:// or https://\n\n"
                    f"Meintest du: https://{url} ?",
                    parent=self,
                )
                return
            nc_user = self._nc_user.get().strip()
            nc_pw = self._nc_pw.get()
            nc_path = self._nc_path.get().strip() or "/calendar.json"
            if not nc_path.startswith("/"):
                nc_path = "/" + nc_path
            if not nc_user:
                messagebox.showerror("Error", "Nextcloud username required.", parent=self)
                return
            sync_data = {
                "url": url,
                "user": nc_user,
                "password": nc_pw,
                "remote_path": nc_path,
            }

        self.result = (pw1.encode(), sync_data)
        self.destroy()


class AddEntryDialog(tk.Toplevel):
    """Dialog to create a new calendar entry."""

    def __init__(self, parent):
        super().__init__(parent)
        self.title("Add Entry")
        self.resizable(False, False)
        self.wait_visibility()
        self.grab_set()

        self.result = None  # (title, date_str, time_str, comments)

        pad = {"padx": 10, "pady": 4}

        ttk.Label(self, text="Title:").grid(row=0, column=0, sticky="e", **pad)
        self._title = ttk.Entry(self, width=30)
        self._title.grid(row=0, column=1, sticky="w", **pad)

        ttk.Label(self, text="Date (DD.MM.YYYY):").grid(row=1, column=0, sticky="e", **pad)
        self._date = ttk.Entry(self, width=14)
        self._date.grid(row=1, column=1, sticky="w", **pad)

        ttk.Label(self, text="Time (HH:MM | all-day | unknown):").grid(row=2, column=0, sticky="e", **pad)
        self._time = ttk.Entry(self, width=14)
        self._time.insert(0, "all-day")
        self._time.grid(row=2, column=1, sticky="w", **pad)

        ttk.Label(self, text="Comments:").grid(row=3, column=0, sticky="ne", padx=10, pady=4)
        self._comments = tk.Text(self, width=28, height=5)
        self._comments.grid(row=3, column=1, sticky="w", padx=10, pady=4)
        ttk.Label(self, text="(one per line)", foreground=theme.FG_DIM).grid(
            row=4, column=1, sticky="w", padx=10)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=10)
        ttk.Button(btn_frame, text="Add", command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text="Cancel", command=self.destroy).pack(side="left", padx=6)

        self._title.focus_set()

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

        self.result = (title, date_str, time_str, comments)
        self.destroy()


class SyncConfigDialog(tk.Toplevel):
    """View and update the Nextcloud sync configuration."""

    def __init__(self, parent, current_config: dict | None):
        super().__init__(parent)
        self.title("Nextcloud Sync Settings")
        self.resizable(False, False)
        self.wait_visibility()
        self.grab_set()

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


class ViewEntryDialog(tk.Toplevel):
    """Read-only view of a single entry."""

    def __init__(self, parent, entry: dict):
        super().__init__(parent)
        self.title("View Entry")
        self.resizable(False, False)
        self.wait_visibility()
        self.grab_set()

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
