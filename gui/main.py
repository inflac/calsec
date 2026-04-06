#!/usr/bin/env python3

import sys
import os
import tkinter as tk
from tkinter import ttk, PhotoImage

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import settings
import i18n
import theme
import storage
import updater
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from crypto import ecies_decrypt
from app import CalendarApp


class LoginFrame(ttk.Frame):
    """Password prompt: decrypts user key → derives sym_key_cal → loads CalendarApp."""

    def __init__(self, parent, on_login, user_hash: str):
        super().__init__(parent)
        self._on_login  = on_login
        self._user_hash = user_hash

        ttk.Label(self, text="calsec",
                  font=("Cantarell", 18, "bold")).pack(pady=(30, 6))
        ttk.Label(self, text=i18n._("login_subtitle"),
                  foreground=theme.FG_DIM).pack()
        ttk.Label(self, text=f"Key: {user_hash}",
                  foreground=theme.FG_DIM).pack(pady=(4, 0))

        form = ttk.Frame(self)
        form.pack(pady=20)

        ttk.Label(form, text=i18n._("login_password")).grid(
            row=0, column=0, sticky="e", padx=8, pady=4)
        self._pw_entry = ttk.Entry(form, show="*", width=24)
        self._pw_entry.grid(row=0, column=1, sticky="w", padx=8, pady=4)

        self._error_var = tk.StringVar()
        ttk.Label(self, textvariable=self._error_var,
                  foreground=theme.RED).pack()

        ttk.Button(self, text=i18n._("btn_unlock"), command=self._submit).pack(pady=4)

        self._pw_entry.focus_set()
        self._pw_entry.bind("<Return>", lambda _: self._submit())

    def _submit(self):
        pw = self._pw_entry.get().encode() or None

        # 1. Decrypt the user's encryption private key
        try:
            kpriv_user = storage.load_user_private_key(self._user_hash, pw)
        except ValueError:
            self._error_var.set(i18n._("err_wrong_password"))
            self._pw_entry.delete(0, "end")
            return
        except FileNotFoundError as e:
            self._error_var.set(str(e))
            return

        # 2. Derive sym_key_cal via ECIES
        try:
            raw         = storage.load_file_raw()
            user_entry  = raw["users"][self._user_hash]
            sym_key_cal = ecies_decrypt(kpriv_user, user_entry["sym_key_cal_enc"])
        except Exception:
            self._error_var.set(i18n._("err_key_derivation"))
            return

        # 3. Decrypt sign keys from calendar.json
        #    admin_sign_key — admin only (user management + sync config)
        #    edit_sign_key  — admin + editor (entry management)
        role = user_entry.get("role", "viewer")
        kpriv_admin_sign = None
        kpriv_edit_sign  = None

        if role == "admin" and "admin_sign_key_enc" in user_entry:
            try:
                pem = ecies_decrypt(kpriv_user, user_entry["admin_sign_key_enc"])
                kpriv_admin_sign = load_pem_private_key(pem, password=None)
            except Exception:
                self._error_var.set(i18n._("err_admin_key_decrypt"))
                return

        if role in ("admin", "editor") and "edit_sign_key_enc" in user_entry:
            try:
                pem = ecies_decrypt(kpriv_user, user_entry["edit_sign_key_enc"])
                kpriv_edit_sign = load_pem_private_key(pem, password=None)
            except Exception:
                self._error_var.set(i18n._("err_edit_key_decrypt"))
                return

        # 4. Build CalendarApp
        try:
            app = CalendarApp(sym_key_cal,
                              kpriv_admin_sign=kpriv_admin_sign,
                              kpriv_edit_sign=kpriv_edit_sign,
                              role=role, user_hash=self._user_hash)
        except RuntimeError as e:
            self._error_var.set(str(e))
            return

        self._on_login(app)


def _patch_toplevel_icon(icon_path: str) -> None:
    if not icon_path.endswith(".ico"):
        return  # nur Windows

    _orig_init = tk.Toplevel.__init__

    def _patched_init(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)
        try:
            self.iconbitmap(icon_path)
        except Exception:
            pass

    tk.Toplevel.__init__ = _patched_init


def _patch_toplevel_minsize() -> None:
    """Ensure all Toplevel windows have a readable minimum size."""
    _orig_init = tk.Toplevel.__init__

    def _patched_init(self, *args, **kwargs):
        _orig_init(self, *args, **kwargs)
        try:
            self.minsize(540, 180)
        except Exception:
            pass

    tk.Toplevel.__init__ = _patched_init


def _center_on_screen(win: tk.Tk) -> None:
    win.update_idletasks()
    sw = win.winfo_screenwidth()
    sh = win.winfo_screenheight()
    w = max(win.winfo_width(), win.winfo_reqwidth())
    h = max(win.winfo_height(), win.winfo_reqheight())
    win.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")


class Application(tk.Tk):

    def __init__(self):
        super().__init__(className="calsec")
        self.title("calsec")
        self.minsize(680, 440)
        _patch_toplevel_minsize()
        _base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        if sys.platform.startswith("win"):
            icon_path = os.path.join(_base, "icon.ico")
            if os.path.exists(icon_path):
                self.iconbitmap(icon_path)
                _patch_toplevel_icon(icon_path)

        else:
            icon_path = os.path.join(_base, "icon.png")
            if os.path.exists(icon_path):
                icon = PhotoImage(file=icon_path)
                self.iconphoto(True, icon)
        self._frame          = None
        self._logged_in_app  = None
        self._pending_update = None  # set when notify-mode check finds an update

        settings.load()
        i18n.load(settings.get("language"))
        theme.apply(self, settings.get("theme"))

        if updater.is_frozen() and settings.get("updates_enabled"):
            if settings.get("update_mode") == "auto":
                self._run_auto_update_check()
            else:
                self._run_notify_update_check()

        self._start()
        _center_on_screen(self)

    def _run_auto_update_check(self):
        """Show a blocking update dialog; login proceeds only after it closes."""
        from ui.dialogs import UpdateDialog
        dlg = UpdateDialog(self, update_info=None, can_skip=False)
        self.wait_window(dlg)

    def _run_notify_update_check(self):
        """Check for updates silently; store result for the toolbar banner."""
        import threading

        def _check():
            try:
                info = updater.check_for_update()
            except Exception:
                info = None
            self.after(0, lambda: self._on_notify_check_done(info))

        threading.Thread(target=_check, daemon=True).start()

    def _on_notify_check_done(self, info):
        self._pending_update = info
        from ui.main_window import MainWindow
        if isinstance(self._frame, MainWindow) and info:
            self._frame.show_update_banner(info)

    def _start(self):
        if not storage.is_provisioned():
            if storage.find_user_key_hashes():
                # Keys exist locally but no calendar yet — fetch from server
                self._show_fetch()
            else:
                # No keys and no calendar — first-time admin setup
                self._show_provision()
        else:
            self._show_login()

    def _show_fetch(self):
        from ui.dialogs import FetchCalendarDialog
        dlg = FetchCalendarDialog(self)
        self.wait_window(dlg)
        if not dlg.result:
            self.destroy()
            return
        self._show_login()

    def _show_login(self):
        self._logged_in_app = None

        raw           = storage.load_file_raw()
        users_in_file = raw.get("users", {})
        key_hashes    = storage.find_user_key_hashes()
        matching      = [h for h in key_hashes if h in users_in_file]

        if not matching:
            from ui.dialogs import show_error
            show_error(self, i18n._("err_no_user_title"),
                i18n._("err_no_user_body").format(keys_dir=storage.KEYS_DIR))
            self.destroy()
            return

        # Use first matching key (typical Tails setup: one key per device)
        user_hash = matching[0]
        self._switch_to(LoginFrame(
            self,
            on_login=self._show_main,
            user_hash=user_hash,
        ))

    def _show_provision(self):
        from ui.dialogs import ProvisionDialog, show_info, show_error
        while True:
            dlg = ProvisionDialog(self)
            self.wait_window(dlg)

            if dlg.result is None:
                self.destroy()
                return

            # Language-change reload: reopen the dialog with the new language
            if dlg.result == ("__reload__",):
                continue

            break

        email, password, sync_data = dlg.result
        try:
            storage.provision(email, password, sync_data)
        except RuntimeError as e:
            show_error(self, i18n._("err_title"), str(e))
            self.destroy()
            return

        body = i18n._("setup_done_body_pw") if password else i18n._("setup_done_body")
        show_info(self, i18n._("setup_done_title"), body)
        self._show_login()

    def _show_main(self, app: CalendarApp):
        from ui.main_window import MainWindow
        self._logged_in_app = app
        main_win = MainWindow(self, app, on_toggle_theme=self._toggle_theme,
                              pending_update=self._pending_update)
        self._switch_to(main_win)
        # Auto-pull after login so the user always sees the latest version
        if app.sync_config is not None:
            app.sync_pull(on_done=main_win._on_sync_done)

    def _toggle_theme(self):
        new_mode = "light" if settings.get("theme") == "dark" else "dark"
        settings.set("theme", new_mode)
        theme.apply(self, new_mode)
        if self._logged_in_app is not None:
            from ui.main_window import MainWindow
            self._switch_to(
                MainWindow(self, self._logged_in_app,
                           on_toggle_theme=self._toggle_theme,
                           pending_update=self._pending_update))
        else:
            self._show_login()

    def _switch_to(self, frame: ttk.Frame):
        if self._frame is not None:
            self._frame.destroy()
        self._frame = frame
        self._frame.pack(fill="both", expand=True)
        self.after(0, lambda: _center_on_screen(self))


def main():
    app = Application()
    app.mainloop()


if __name__ == "__main__":
    main()
