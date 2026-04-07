import tkinter as tk
from tkinter import ttk

import i18n
import storage
import theme
from crypto import format_fingerprint

from ui.dialogs.base import (
    _PAD, _center_dialog, show_info, show_error, ask_yes_no, copy_to_clipboard,
)


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
        ttk.Label(self, text=i18n._("lbl_webdav_url_hint"),
                  foreground=theme.FG_DIM).grid(row=2, column=1, sticky="w", padx=14, pady=(0, 2))

        ttk.Label(self, text=i18n._("lbl_username")).grid(row=3, column=0, sticky="e", **pad)
        self._user = ttk.Entry(self, width=40)
        self._user.grid(row=3, column=1, sticky="w", **pad)

        ttk.Label(self, text=i18n._("lbl_app_password")).grid(row=4, column=0, sticky="e", **pad)
        self._pw = ttk.Entry(self, show="*", width=40)
        self._pw.grid(row=4, column=1, sticky="w", **pad)

        if current_config:
            self._url.insert(0, current_config.get("webdav_url", ""))
            self._user.insert(0, current_config.get("auth_user", ""))
            self._pw.insert(0, current_config.get("password", ""))

        ttk.Separator(self, orient="horizontal").grid(
            row=5, column=0, columnspan=2, sticky="ew", padx=10, pady=8)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=6, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(btn_frame, text=i18n._("btn_save"), command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text=i18n._("btn_cancel"), command=self.destroy).pack(side="left", padx=6)

        self._url.focus_set()
        self.bind("<Return>", lambda _: self._confirm())
        _center_dialog(self, parent)

    def _confirm(self):
        url = self._url.get().strip().rstrip("/")
        if url.endswith("/calendar.json"):
            url = url[: -len("/calendar.json")]
        if not url:
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


class AddUserDialog(tk.Toplevel):
    """Admin: add a new user — generate keypair or register an existing public key."""

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("add_user_title"))
        self.resizable(False, False)

        # result: (identifier, kpub_or_None, password_or_None, role)
        # kpub_or_None — cryptography public key object if user provided their own
        # password_or_None — bytes if keypair should be generated with this password
        self.result = None

        pad = _PAD

        ttk.Label(self, text=i18n._("lbl_email")).grid(row=0, column=0, sticky="e", **pad)
        self._identifier = ttk.Entry(self, width=32)
        self._identifier.grid(row=0, column=1, columnspan=2, sticky="w", **pad)

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

        self._identifier.focus_set()
        _center_dialog(self, parent)

    def _toggle_pw(self):
        state = "disabled" if self._no_pw.get() else "normal"
        self._pw1.configure(state=state)
        self._pw2.configure(state=state)
        self._pw_label1.configure(foreground="#888888" if self._no_pw.get() else "")
        self._pw_label2.configure(foreground="#888888" if self._no_pw.get() else "")

    def _confirm(self):
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        identifier = self._identifier.get().strip()
        if not identifier:
            show_error(self, i18n._("err_title"), i18n._("err_email_invalid"))
            return

        mode = self._mode.get()

        if mode == "generate":
            if self._no_pw.get():
                self.result = (identifier, None, None, self._role.get())
            else:
                pw1 = self._pw1.get()
                pw2 = self._pw2.get()
                if pw1 != pw2:
                    show_error(self, i18n._("err_title"), i18n._("err_passwords_mismatch"))
                    return
                if len(pw1) < 8:
                    show_error(self, i18n._("err_title"), i18n._("err_password_too_short"))
                    return
                self.result = (identifier, None, pw1.encode(), self._role.get())
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
            self.result = (identifier, kpub, None, self._role.get())

        self.destroy()


class ChangeRoleDialog(tk.Toplevel):
    """Admin: change the role of an existing user."""

    def __init__(self, parent, identifier: str, current_role: str):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("change_role_title"))
        self.resizable(False, False)

        # result: new role string, or None if cancelled
        self.result = None

        pad = _PAD

        ttk.Label(self, text=i18n._("change_role_user").format(identifier=identifier),
                  wraplength=320).grid(row=0, column=0, columnspan=2, sticky="w",
                                       padx=14, pady=(14, 6))

        ttk.Label(self, text=i18n._("change_role_current").format(
            role=current_role.capitalize())).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=14, pady=(0, 8))

        ttk.Separator(self, orient="horizontal").grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=4)

        ttk.Label(self, text=i18n._("change_role_new")).grid(
            row=3, column=0, sticky="e", **pad)

        self._role = tk.StringVar(value=current_role)
        role_frame = ttk.Frame(self)
        role_frame.grid(row=3, column=1, sticky="w", **pad)
        for label, value in [("Viewer", "viewer"), ("Editor", "editor"), ("Admin", "admin")]:
            ttk.Radiobutton(role_frame, text=label,
                            variable=self._role, value=value).pack(side="left", padx=4)

        ttk.Separator(self, orient="horizontal").grid(
            row=4, column=0, columnspan=2, sticky="ew", padx=10, pady=6)

        btn_frame = ttk.Frame(self)
        btn_frame.grid(row=5, column=0, columnspan=2, pady=(0, 10))
        ttk.Button(btn_frame, text=i18n._("btn_save"),
                   command=self._confirm).pack(side="left", padx=6)
        ttk.Button(btn_frame, text=i18n._("btn_cancel"),
                   command=self.destroy).pack(side="left", padx=6)

        _center_dialog(self, parent)

    def _confirm(self):
        self.result = self._role.get()
        self.destroy()


class UserManagementDialog(tk.Toplevel):
    """Admin-only: list, add, and remove users."""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("user_mgmt_title"))
        self.resizable(True, True)
        self.minsize(620, 400)
        self.geometry("700x460")
        self._app = app

        ttk.Button(self, text=i18n._("btn_add_user_toolbar"),
                   command=self._add_user).pack(
            anchor="w", padx=10, pady=(10, 4))

        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True, padx=10, pady=4)

        cols = ("identifier", "role")
        self._tree = ttk.Treeview(frame, columns=cols, show="headings",
                                  selectmode="browse", height=8)
        self._tree.heading("identifier", text=i18n._("col_email"))
        self._tree.heading("role",  text=i18n._("col_role"))
        self._tree.column("identifier", width=440)
        self._tree.column("role",  width=120, anchor="center")

        sb = ttk.Scrollbar(frame, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=sb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=10, pady=(4, 10))
        ttk.Button(actions, text=i18n._("btn_remove"),
                   command=self._remove_selected).pack(side="left")
        ttk.Button(actions, text=i18n._("btn_change_role"),
                   command=self._change_role_selected).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text=i18n._("btn_copy_onboarding"),
                   command=self._copy_onboarding).pack(side="left", padx=(8, 0))
        ttk.Button(actions, text=i18n._("btn_close"),
                   command=self.destroy).pack(side="right")

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
                u["identifier"] or f"{u['hash']}",
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

        identifier, kpub, password, role = dlg.result

        save_path = None
        if kpub is None:
            h = storage.identifier_to_hash(identifier)
            save_path = fd.asksaveasfilename(
                parent=self,
                title=i18n._("save_key_title").format(identifier=identifier),
                defaultextension=".pem",
                filetypes=[(i18n._("file_type_pem"), "*.pem")],
                initialfile=f"{h}.pem",
            )
            if not save_path:
                return  # user cancelled — nothing written yet

        try:
            kpriv_bytes = self._app.add_user(
                identifier, kpub, password, role=role,
                save_locally=save_path is None)
        except RuntimeError as e:
            show_error(self, i18n._("err_title"), str(e))
            return

        if kpriv_bytes and save_path:
            try:
                storage._atomic_write_bytes(save_path, kpriv_bytes, mode=0o600)
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
        label = u["identifier"] or u["hash"][:16]
        if not ask_yes_no(self, i18n._("confirm_remove_title"),
            i18n._("confirm_remove_body").format(label=label)):
            return
        try:
            self._app.remove_user(u["hash"])
        except RuntimeError as e:
            show_error(self, i18n._("err_title"), str(e))
            return
        self._refresh()

    def _change_role_selected(self):
        sel = self._tree.selection()
        if not sel:
            show_info(self, i18n._("user_mgmt_title"), i18n._("hint_select_user"))
            return
        u = self._users.get(sel[0])
        if u is None:
            return

        dlg = ChangeRoleDialog(self, u["identifier"] or u["hash"][:16], u["role"])
        self.wait_window(dlg)
        self.grab_set()
        if dlg.result is None or dlg.result == u["role"]:
            return

        new_role = dlg.result
        try:
            self._app.change_user_role(u["hash"], new_role)
        except RuntimeError as e:
            show_error(self, i18n._("err_title"), str(e))
            return

        self._refresh()
        show_info(
            self,
            i18n._("role_changed_title"),
            i18n._("role_changed_body").format(
                label=u["identifier"] or u["hash"][:16],
                role=new_role.capitalize(),
            ),
        )

    def _copy_onboarding(self):
        from app import build_onboarding_text

        sel = self._tree.selection()
        if not sel:
            show_info(self, i18n._("user_mgmt_title"), i18n._("hint_select_user"))
            return
        u = self._users.get(sel[0])
        if u is None:
            return

        sync_config = self._app.sync_config
        if sync_config is None:
            show_error(self, i18n._("err_title"), i18n._("err_sync_missing_onboarding"))
            return

        try:
            text = build_onboarding_text(
                u["identifier"],
                sync_config,
                format_fingerprint(self._app.fingerprint),
            )
            copy_to_clipboard(self, text)
        except Exception as exc:
            show_error(self, i18n._("err_title"), str(exc))
            return

        show_info(
            self,
            i18n._("onboarding_copied_title"),
            i18n._("onboarding_copied_body").format(identifier=u["identifier"]),
        )
