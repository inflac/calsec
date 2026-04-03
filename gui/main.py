#!/usr/bin/env python3

import sys
import os
import tkinter as tk
from tkinter import ttk, messagebox

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import settings
import theme
import storage
from crypto import ecies_decrypt
from app import CalendarApp
from ui.main_window import MainWindow


class LoginFrame(ttk.Frame):
    """Password prompt: decrypts user key → derives sym_key_cal → loads CalendarApp."""

    def __init__(self, parent, on_login, user_hash: str,
                 is_admin_candidate: bool):
        super().__init__(parent)
        self._on_login          = on_login
        self._user_hash         = user_hash
        self._is_admin_candidate = is_admin_candidate

        ttk.Label(self, text="calsec",
                  font=("Cantarell", 18, "bold")).pack(pady=(30, 6))
        ttk.Label(self, text="Encrypted Calendar",
                  foreground=theme.FG_DIM).pack()
        ttk.Label(self, text=f"Key: {user_hash}",
                  foreground=theme.FG_DIM).pack(pady=(4, 0))

        form = ttk.Frame(self)
        form.pack(pady=20)

        ttk.Label(form, text="Password:").grid(
            row=0, column=0, sticky="e", padx=8, pady=4)
        self._pw_entry = ttk.Entry(form, show="*", width=24)
        self._pw_entry.grid(row=0, column=1, sticky="w", padx=8, pady=4)

        self._error_var = tk.StringVar()
        ttk.Label(self, textvariable=self._error_var,
                  foreground=theme.RED).pack()

        ttk.Button(self, text="Unlock", command=self._submit).pack(pady=4)

        self._pw_entry.focus_set()
        self._pw_entry.bind("<Return>", lambda _: self._submit())

    def _submit(self):
        pw = self._pw_entry.get().encode()

        # 1. Decrypt the user's encryption private key
        try:
            kpriv_user = storage.load_user_private_key(self._user_hash, pw)
        except ValueError:
            self._error_var.set("Wrong password.")
            self._pw_entry.delete(0, "end")
            return
        except FileNotFoundError as e:
            self._error_var.set(str(e))
            return

        # 2. Derive sym_key_cal via ECIES
        try:
            raw        = storage.load_file_raw()
            user_entry = raw["users"][self._user_hash]
            sym_key_cal = ecies_decrypt(kpriv_user, user_entry["sym_key_cal_enc"])
        except Exception:
            self._error_var.set("Schlüsselableitung fehlgeschlagen.")
            return

        # 3. Try to load the signing key (grants admin rights if successful)
        kpriv_sign = None
        if self._is_admin_candidate:
            try:
                kpriv_sign = storage.load_sign_private_key(pw)
            except Exception:
                pass  # not admin, or different sign-key password

        is_admin = user_entry.get("is_admin", False) and kpriv_sign is not None

        # 4. Build CalendarApp
        try:
            app = CalendarApp(sym_key_cal, kpriv_sign=kpriv_sign,
                              is_admin=is_admin, user_hash=self._user_hash)
        except RuntimeError as e:
            self._error_var.set(str(e))
            return

        self._on_login(app)


class Application(tk.Tk):

    def __init__(self):
        super().__init__()
        self.title("calsec")
        self.minsize(600, 380)
        self._frame         = None
        self._logged_in_app = None

        settings.load()
        theme.apply(self, settings.get("theme"))

        self._start()

    def _start(self):
        if not storage.is_provisioned():
            self._show_provision()
        else:
            self._show_login()

    def _show_login(self):
        self._logged_in_app = None

        raw           = storage.load_file_raw()
        users_in_file = raw.get("users", {})
        key_hashes    = storage.find_user_key_hashes()
        matching      = [h for h in key_hashes if h in users_in_file]

        if not matching:
            messagebox.showerror(
                "Kein Benutzer",
                f"Kein passender Schlüssel in\n'{storage.KEYS_DIR}'\ngefunden.\n\n"
                "Bitte den eigenen Schlüssel (sha256(localpart).pem) "
                "dort ablegen.",
                parent=self,
            )
            self.destroy()
            return

        # Use first matching key (typical Tails setup: one key per device)
        user_hash = matching[0]
        self._switch_to(LoginFrame(
            self,
            on_login=self._show_main,
            user_hash=user_hash,
            is_admin_candidate=storage.sign_key_exists(),
        ))

    def _show_provision(self):
        from ui.dialogs import ProvisionDialog
        dlg = ProvisionDialog(self)
        self.wait_window(dlg)

        if dlg.result is None:
            self.destroy()
            return

        email, password, sync_data = dlg.result
        try:
            storage.provision(email, password, sync_data)
        except RuntimeError as e:
            messagebox.showerror("Error", str(e), parent=self)
            self.destroy()
            return

        messagebox.showinfo(
            "Setup abgeschlossen",
            "Schlüssel generiert. Bitte mit dem Passwort entsperren.",
            parent=self,
        )
        self._show_login()

    def _show_main(self, app: CalendarApp):
        self._logged_in_app = app
        self._switch_to(
            MainWindow(self, app, on_toggle_theme=self._toggle_theme))

    def _toggle_theme(self):
        new_mode = "light" if settings.get("theme") == "dark" else "dark"
        settings.set("theme", new_mode)
        theme.apply(self, new_mode)
        if self._logged_in_app is not None:
            self._switch_to(
                MainWindow(self, self._logged_in_app,
                           on_toggle_theme=self._toggle_theme))
        else:
            self._show_login()

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
