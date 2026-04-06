import tkinter as tk
from tkinter import ttk

import i18n
import theme

from ui.dialogs.base import _center_dialog


class SettingsDialog(tk.Toplevel):
    """App settings: language + update preferences."""

    def __init__(self, parent):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("settings_title"))
        self.resizable(False, False)

        import settings as _settings

        pad = {"padx": 14, "pady": 4}

        # ── Language ──────────────────────────────────────────────────────────
        ttk.Label(self, text=i18n._("settings_lang_section"),
                  font=("Cantarell", 10, "bold")).pack(
            anchor="w", padx=14, pady=(14, 2))

        self._lang_var = tk.StringVar(value=i18n.get())
        for code, label in i18n.SUPPORTED:
            ttk.Radiobutton(self, text=label,
                            variable=self._lang_var, value=code).pack(
                anchor="w", padx=28, pady=1)

        ttk.Label(self, text=i18n._("settings_lang_hint"),
                  foreground=theme.FG_DIM).pack(anchor="w", padx=28, pady=(0, 6))

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=4)

        # ── Updates ───────────────────────────────────────────────────────────
        ttk.Label(self, text=i18n._("settings_update_section"),
                  font=("Cantarell", 10, "bold")).pack(
            anchor="w", padx=14, pady=(6, 2))

        self._upd_enabled = tk.BooleanVar(value=bool(_settings.get("updates_enabled")))
        ttk.Checkbutton(self, text=i18n._("settings_updates_enabled"),
                        variable=self._upd_enabled,
                        command=self._toggle_update_widgets).pack(
            anchor="w", padx=28, pady=(2, 6))

        # Mode frame
        self._mode_frame = ttk.Frame(self)
        self._mode_frame.pack(anchor="w", padx=28)

        ttk.Label(self._mode_frame,
                  text=i18n._("settings_update_mode")).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 2))

        self._upd_mode = tk.StringVar(value=_settings.get("update_mode"))
        ttk.Radiobutton(self._mode_frame, text=i18n._("settings_update_auto"),
                        variable=self._upd_mode, value="auto").grid(
            row=1, column=0, sticky="w", padx=(10, 0))
        ttk.Radiobutton(self._mode_frame, text=i18n._("settings_update_notify"),
                        variable=self._upd_mode, value="notify").grid(
            row=2, column=0, sticky="w", padx=(10, 0))

        ttk.Separator(self._mode_frame, orient="horizontal").grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=6)

        # Channel frame
        ttk.Label(self._mode_frame,
                  text=i18n._("settings_channel_label")).grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(0, 2))

        current_ch = _settings.get("update_channel")
        self._ch_var = tk.StringVar(
            value="official" if current_ch == "official" else "custom")

        ttk.Radiobutton(self._mode_frame,
                        text=i18n._("settings_channel_official"),
                        variable=self._ch_var, value="official",
                        command=self._toggle_custom_entry).grid(
            row=5, column=0, sticky="w", padx=(10, 0))

        custom_row = ttk.Frame(self._mode_frame)
        custom_row.grid(row=6, column=0, sticky="w", padx=(10, 0), pady=(2, 0))
        ttk.Radiobutton(custom_row, text=i18n._("settings_channel_custom"),
                        variable=self._ch_var, value="custom",
                        command=self._toggle_custom_entry).pack(side="left")
        self._custom_entry = ttk.Entry(custom_row, width=30)
        self._custom_entry.pack(side="left", padx=(4, 0))
        if current_ch and current_ch != "official":
            self._custom_entry.insert(0, current_ch)

        self._toggle_update_widgets()

        # ── Buttons ───────────────────────────────────────────────────────────
        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=(10, 4))
        btn_frame = ttk.Frame(self)
        btn_frame.pack(pady=(0, 14))
        ttk.Button(btn_frame, text=i18n._("btn_save"),
                   command=self._save).pack(side="left", padx=6)
        ttk.Button(btn_frame, text=i18n._("btn_cancel"),
                   command=self.destroy).pack(side="left", padx=6)

        _center_dialog(self, parent)

    def _toggle_update_widgets(self):
        state = "normal" if self._upd_enabled.get() else "disabled"
        for child in self._mode_frame.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass
            for grandchild in child.winfo_children():
                try:
                    grandchild.configure(state=state)
                except tk.TclError:
                    pass
        if self._upd_enabled.get():
            self._toggle_custom_entry()

    def _toggle_custom_entry(self):
        state = "normal" if self._ch_var.get() == "custom" else "disabled"
        self._custom_entry.configure(state=state)

    def _save(self):
        import settings as _settings
        _settings.set("language", self._lang_var.get())
        _settings.set("updates_enabled", self._upd_enabled.get())
        _settings.set("update_mode", self._upd_mode.get())
        if self._ch_var.get() == "custom":
            _settings.set("update_channel", self._custom_entry.get().strip() or "official")
        else:
            _settings.set("update_channel", "official")
        self.destroy()


class UpdateDialog(tk.Toplevel):
    """
    Shown at startup (auto mode) or when the user clicks the update toolbar button.

    auto mode   — can_skip=False, update_info=None:
        Checks for updates, then downloads and installs without asking.
        Cannot be dismissed until finished or an error occurs.

    notify mode — can_skip=True, update_info=<UpdateInfo>:
        Starts downloading an already-found update.
        The user can cancel.
    """

    def __init__(self, parent, update_info=None, can_skip=False):
        super().__init__(parent)
        self.withdraw()
        self.transient(parent)
        self.title(i18n._("update_checking") if update_info is None
                   else i18n._("update_available").format(version=update_info.version))
        self.resizable(False, False)
        if not can_skip:
            self.protocol("WM_DELETE_WINDOW", lambda: None)

        self._can_skip = can_skip
        self._update_info = update_info

        import threading
        self._lock = threading.Lock()

        ttk.Label(self, text="calsec",
                  font=("Cantarell", 14, "bold")).pack(pady=(20, 4))

        self._status_var = tk.StringVar(
            value=i18n._("update_checking") if update_info is None
            else i18n._("update_available").format(version=update_info.version))
        ttk.Label(self, textvariable=self._status_var,
                  wraplength=340, justify="center").pack(padx=24, pady=(0, 8))

        self._progress = ttk.Progressbar(self, length=320, mode="indeterminate")
        self._progress.pack(padx=24, pady=(0, 10))
        self._progress.start(12)

        self._btn_frame = ttk.Frame(self)
        self._btn_frame.pack(pady=(0, 16))

        if can_skip:
            self._cancel_btn = ttk.Button(
                self._btn_frame, text=i18n._("btn_cancel"),
                command=self.destroy)
            self._cancel_btn.pack(side="left", padx=6)
        else:
            # "Continue anyway" — only enabled on error
            self._continue_btn = ttk.Button(
                self._btn_frame, text=i18n._("btn_continue"),
                command=self.destroy, state="disabled")
            self._continue_btn.pack(side="left", padx=6)

        _center_dialog(self, parent)

        import threading
        if update_info is None:
            threading.Thread(target=self._do_check, daemon=True).start()
        else:
            threading.Thread(target=self._do_download, daemon=True).start()

    # ── Background workers ────────────────────────────────────────────────────

    def _do_check(self):
        try:
            import updater
            info = updater.check_for_update()
        except Exception as exc:
            self.after(0, lambda: self._on_error(str(exc)))
            return
        self.after(0, lambda: self._on_check_done(info))

    def _on_check_done(self, info):
        if info is None:
            self._status_var.set(i18n._("update_up_to_date"))
            self._progress.stop()
            self._progress.configure(mode="determinate", value=100)
            self.after(2000, self.destroy)
            return
        self._update_info = info
        self._status_var.set(
            i18n._("update_available").format(version=info.version))
        import threading
        threading.Thread(target=self._do_download, daemon=True).start()

    def _do_download(self):
        import updater

        def _progress(done, total):
            if total > 0:
                pct = int(done * 100 / total)
                self.after(0, lambda p=pct: self._on_progress(p))

        try:
            tmp = updater.download_update(self._update_info, progress_cb=_progress)
        except Exception as exc:
            self.after(0, lambda: self._on_error(str(exc)))
            return
        self.after(0, lambda: self._on_download_done(tmp))

    def _on_progress(self, pct: int):
        self._status_var.set(i18n._("update_downloading").format(pct=pct))
        self._progress.stop()
        self._progress.configure(mode="determinate", value=pct)

    def _on_download_done(self, tmp_path):
        import updater
        self._status_var.set(i18n._("update_restarting"))
        self._progress.configure(mode="determinate", value=100)
        self.update()
        try:
            # Stop the mainloop to close windows before starting new process
            self.master.winfo_toplevel().quit()
            updater.apply_update(tmp_path)  # spawns new process + sys.exit(0)
        except Exception as exc:
            self._on_error(str(exc))

    def _on_error(self, msg: str):
        self._status_var.set(i18n._("update_error").format(exc=msg))
        self._progress.stop()
        self._progress.configure(mode="determinate", value=0)
        if not self._can_skip:
            self._continue_btn.configure(state="normal")
