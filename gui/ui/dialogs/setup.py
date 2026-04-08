import hmac
import tkinter as tk
from tkinter import ttk

import i18n
import storage
import theme
from ui.dialogs.base import _PAD, _center_dialog, show_error


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
        ttk.Label(self, text=i18n._("lbl_webdav_url_hint"),
                  foreground=theme.FG_DIM).grid(row=3, column=1, sticky="w", padx=14, pady=(0, 2))

        ttk.Label(self, text=i18n._("lbl_username")).grid(row=4, column=0, sticky="e", **pad)
        self._user = ttk.Entry(self, width=42)
        self._user.grid(row=4, column=1, sticky="w", **pad)

        ttk.Label(self, text=i18n._("lbl_app_password")).grid(row=5, column=0, sticky="e", **pad)
        self._pw = ttk.Entry(self, show="*", width=42)
        self._pw.grid(row=5, column=1, sticky="w", **pad)

        ttk.Label(self, text=i18n._("lbl_fingerprint")).grid(row=6, column=0, sticky="e", **pad)
        self._fingerprint = ttk.Entry(self, width=42)
        self._fingerprint.grid(row=6, column=1, sticky="w", **pad)
        ttk.Label(self, text=i18n._("lbl_fingerprint_hint"),
                  foreground=theme.FG_DIM, wraplength=320, justify="left").grid(
            row=7, column=1, sticky="w", padx=14, pady=(0, 2))

        self._status_var = tk.StringVar()
        ttk.Label(self, textvariable=self._status_var,
                  foreground=theme.RED, wraplength=400,
                  justify="center").grid(
            row=8, column=0, columnspan=2, padx=10, pady=(6, 0))

        ttk.Separator(self, orient="horizontal").grid(
            row=9, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=10, column=0, columnspan=2, pady=(0, 12))
        self._dl_btn = ttk.Button(btn_frame, text=i18n._("btn_download"),
                                   command=self._download)
        self._dl_btn.pack(side="left", padx=6)
        ttk.Button(btn_frame, text=i18n._("btn_cancel"),
                   command=self.destroy).pack(side="left", padx=6)

        self._url.focus_set()
        self.bind("<Return>", lambda _: self._download())
        _center_dialog(self, parent)

    def _download(self):
        url = self._url.get().strip().rstrip("/")
        if url.endswith("/calendar.json"):
            url = url[: -len("/calendar.json")]
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
            from crypto import (
                format_fingerprint,
                normalize_fingerprint,
                pem_to_public_key,
                sign_keys_fingerprint,
                verify_entries,
                verify_users,
            )
            from sync import sync_pull

            data, msg = sync_pull(config)
            if data is None:
                self._status_var.set(msg)
                self._dl_btn.configure(state="normal")
                return

            version_users = data["version_users"]
            version_entries = data["version_entries"]

            sign_keys = data.get("sign_keys", {})
            if not sign_keys:
                self._status_var.set(i18n._("err_no_sign_keys"))
                self._dl_btn.configure(state="normal")
                return

            expected_fingerprint = normalize_fingerprint(self._fingerprint.get())
            if len(expected_fingerprint) != 64:
                self._status_var.set(i18n._("err_fingerprint_required"))
                self._dl_btn.configure(state="normal")
                return

            actual_fingerprint = sign_keys_fingerprint(sign_keys)
            if not hmac.compare_digest(actual_fingerprint, expected_fingerprint):
                self._status_var.set(i18n._("err_fingerprint_mismatch").format(
                    fingerprint=format_fingerprint(actual_fingerprint)))
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

            if not verify_users(version_users, sign_keys, data.get("users", {}),
                                 data.get("sync_config"), sig_users, kpub_admin):
                self._status_var.set(i18n._("err_user_sig_invalid"))
                self._dl_btn.configure(state="normal")
                return

            if not verify_entries(version_entries, data.get("entries", []),
                                  sig_entries, kpub_edit):
                self._status_var.set(i18n._("err_entry_sig_invalid"))
                self._dl_btn.configure(state="normal")
                return

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
    """Shown on first start. Collects admin identifier + password + optional Nextcloud config.

    result = None              → cancelled
    result = ("__reload__",)  → language changed, caller should reopen
    result = (identifier, pw, sync) → confirmed
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

        # ── Admin account ─────────────────────────────��───────────────────────
        ttk.Label(self, text=i18n._("provision_admin_label")).grid(
            row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(8, 2))

        ttk.Label(self, text=i18n._("lbl_email")).grid(row=3, column=0, sticky="e", **pad)
        self._identifier = ttk.Entry(self, width=30)
        self._identifier.grid(row=3, column=1, sticky="w", **pad)

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
        ttk.Label(self, text=i18n._("lbl_webdav_url_hint"),
                  foreground=theme.FG_DIM).grid(row=10, column=1, sticky="w", padx=14, pady=(0, 2))

        ttk.Label(self, text=i18n._("lbl_username")).grid(row=11, column=0, sticky="e", **pad)
        self._nc_user = ttk.Entry(self, width=36)
        self._nc_user.grid(row=11, column=1, sticky="w", **pad)

        ttk.Label(self, text=i18n._("lbl_app_password")).grid(row=12, column=0, sticky="e", **pad)
        self._nc_pw = ttk.Entry(self, show="*", width=36)
        self._nc_pw.grid(row=12, column=1, sticky="w", **pad)

        ttk.Separator(self, orient="horizontal").grid(
            row=13, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=14, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(btn_frame, text=i18n._("btn_generate_key"),
                   command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text=i18n._("btn_cancel"),
                   command=self.destroy).pack(side="left", padx=6)

        self._identifier.focus_set()
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
        identifier = self._identifier.get().strip()
        if not identifier:
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
        url = self._nc_url.get().strip().rstrip("/")
        if url.endswith("/calendar.json"):
            url = url[: -len("/calendar.json")]
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

        self.result = (identifier, password, sync_data)
        self.destroy()
