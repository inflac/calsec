#!/usr/bin/env python3

import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox

# Ensure gui/ directory is on the path so sibling imports work
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import settings
import theme
from storage import keys_exist, provision, load_private_key
from app import CalendarApp
from ui.main_window import MainWindow


class LoginFrame(ttk.Frame):
    """Password prompt shown at startup when keys already exist."""

    def __init__(self, parent, on_login):
        super().__init__(parent)
        self._on_login = on_login

        ttk.Label(self, text="calsec", font=("Cantarell", 18, "bold")).pack(pady=(30, 6))
        ttk.Label(self, text="Encrypted Calendar", foreground=theme.FG_DIM).pack()

        form = ttk.Frame(self)
        form.pack(pady=20)

        ttk.Label(form, text="Password:").grid(row=0, column=0, sticky="e", padx=8, pady=4)
        self._pw_entry = ttk.Entry(form, show="*", width=24)
        self._pw_entry.grid(row=0, column=1, sticky="w", padx=8, pady=4)

        self._error_var = tk.StringVar()
        ttk.Label(self, textvariable=self._error_var, foreground=theme.RED).pack()

        ttk.Button(self, text="Unlock", command=self._submit).pack(pady=4)

        self._pw_entry.focus_set()
        self._pw_entry.bind("<Return>", lambda _: self._submit())

    def _submit(self):
        pw = self._pw_entry.get().encode()
        try:
            private_key = load_private_key(pw)
        except ValueError:
            self._error_var.set("Wrong password.")
            self._pw_entry.delete(0, "end")
            return
        except FileNotFoundError as e:
            self._error_var.set(str(e))
            return

        try:
            app = CalendarApp(private_key)
        except RuntimeError as e:
            self._error_var.set(str(e))
            return

        self._on_login(app)


class Application(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("calsec")
        self.minsize(600, 380)
        self._frame = None
        self._logged_in_app = None   # CalendarApp instance once unlocked

        settings.load()
        theme.apply(self, settings.get("theme"))

        self._start()

    def _start(self):
        if keys_exist():
            self._show_login()
        else:
            self._show_provision()

    def _show_login(self):
        self._logged_in_app = None
        self._switch_to(LoginFrame(self, on_login=self._show_main))

    def _show_provision(self):
        from ui.dialogs import ProvisionDialog
        dlg = ProvisionDialog(self)
        self.wait_window(dlg)

        if dlg.result is None:
            self.destroy()
            return

        password, sync_data = dlg.result
        try:
            provision(password, sync_data)
        except RuntimeError as e:
            messagebox.showerror("Error", str(e), parent=self)
            self.destroy()
            return

        messagebox.showinfo("Done", "Keys generated. Please unlock with your password.", parent=self)
        self._show_login()

    def _show_main(self, app: CalendarApp):
        self._logged_in_app = app
        self._switch_to(MainWindow(self, app, on_toggle_theme=self._toggle_theme))

    def _toggle_theme(self):
        new_mode = "light" if settings.get("theme") == "dark" else "dark"
        settings.set("theme", new_mode)
        theme.apply(self, new_mode)
        # Rebuild the current frame so inline colour references pick up the new palette
        if self._logged_in_app is not None:
            self._switch_to(MainWindow(self, self._logged_in_app, on_toggle_theme=self._toggle_theme))
        else:
            self._switch_to(LoginFrame(self, on_login=self._show_main))

    def _switch_to(self, frame: ttk.Frame):
        if self._frame is not None:
            self._frame.destroy()
        self._frame = frame
        self._frame.pack(fill="both", expand=True)


def main():
    app = Application()
    app.mainloop()


if __name__ == "__main__":
    main()
