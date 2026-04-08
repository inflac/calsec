import tkinter as tk
from tkinter import ttk

import i18n
import theme

# Color palette for entry color picker
_PALETTE = [
    "#eb1111", "#e91e63", "#e74c3c", "#e67e22",
    "#f1c40f", "#9b59b6", "#3498db", "#00bcd4",
    "#795548", "#607d8b", "#8bc34a", "#2ecc70",
]

# Default padding for dialog form rows
_PAD = {"padx": 14, "pady": 6}


def _center_dialog(dlg: tk.Toplevel, parent: tk.BaseWidget) -> None:
    """Show dialog, wait until compositor has rendered it, then center on screen."""
    dlg.deiconify()
    dlg.wait_visibility()  # window is now truly mapped and sized by the compositor
    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    w = dlg.winfo_width()
    h = dlg.winfo_height()
    dlg.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")
    dlg.grab_set()


def _make_dialog(parent: tk.BaseWidget, title: str) -> tk.Toplevel:
    dlg = tk.Toplevel(parent)
    dlg.withdraw()
    dlg.transient(parent)
    dlg.title(title)
    dlg.resizable(False, False)
    dlg.minsize(540, 160)
    return dlg


def show_info(parent: tk.BaseWidget, title: str, message: str) -> None:
    dlg = _make_dialog(parent, title)
    ttk.Label(dlg, text=message, wraplength=360,
              justify="center").pack(padx=24, pady=(20, 12))
    ttk.Button(dlg, text=i18n._("btn_ok"), command=dlg.destroy).pack(pady=(0, 16))
    _center_dialog(dlg, parent)
    parent.winfo_toplevel().wait_window(dlg)


def show_copyable_text(parent: tk.BaseWidget, title: str,
                       message: str, text: str) -> None:
    dlg = _make_dialog(parent, title)
    ttk.Label(dlg, text=message, wraplength=420,
              justify="center").pack(padx=24, pady=(20, 10))

    box = tk.Text(
        dlg,
        width=52,
        height=3,
        wrap="word",
        relief="solid",
        borderwidth=1,
        font=("Courier New", 10),
    )
    box.pack(fill="x", padx=24, pady=(0, 12))
    box.insert("1.0", text)
    box.configure(state="disabled")

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(pady=(0, 16))
    ttk.Button(
        btn_frame,
        text=i18n._("btn_copy"),
        command=lambda: copy_to_clipboard(dlg, text),
    ).pack(side="left", padx=6)
    ttk.Button(
        btn_frame,
        text=i18n._("btn_ok"),
        command=dlg.destroy,
    ).pack(side="left", padx=6)

    _center_dialog(dlg, parent)
    parent.winfo_toplevel().wait_window(dlg)


def show_error(parent: tk.BaseWidget, title: str, message: str) -> None:
    dlg = _make_dialog(parent, title)
    ttk.Label(dlg, text=message, wraplength=360,
              justify="center", foreground=theme.RED).pack(padx=24, pady=(20, 12))
    ttk.Button(dlg, text=i18n._("btn_ok"), command=dlg.destroy).pack(pady=(0, 16))
    _center_dialog(dlg, parent)
    parent.winfo_toplevel().wait_window(dlg)


def ask_yes_no(parent: tk.BaseWidget, title: str, message: str) -> bool:
    result = [False]
    dlg = _make_dialog(parent, title)
    ttk.Label(dlg, text=message, wraplength=360,
              justify="center").pack(padx=24, pady=(20, 12))
    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(pady=(0, 16))
    ttk.Button(btn_frame, text=i18n._("btn_yes"),
               command=lambda: [result.__setitem__(0, True), dlg.destroy()]).pack(side="left", padx=6)
    ttk.Button(btn_frame, text=i18n._("btn_no"),
               command=dlg.destroy).pack(side="left", padx=6)
    _center_dialog(dlg, parent)
    parent.winfo_toplevel().wait_window(dlg)
    return result[0]


def ask_text(parent: tk.BaseWidget, title: str, message: str,
             initial_value: str = "") -> str | None:
    result = [None]
    dlg = _make_dialog(parent, title)
    ttk.Label(dlg, text=message, wraplength=420,
              justify="center").pack(padx=24, pady=(20, 12))

    entry = ttk.Entry(dlg, width=42)
    entry.pack(fill="x", padx=24, pady=(0, 12))
    entry.insert(0, initial_value)
    entry.focus_set()
    entry.selection_range(0, "end")

    btn_frame = ttk.Frame(dlg)
    btn_frame.pack(pady=(0, 16))

    def _submit():
        result[0] = entry.get().strip()
        dlg.destroy()

    ttk.Button(btn_frame, text=i18n._("btn_ok"),
               command=_submit).pack(side="left", padx=6)
    ttk.Button(btn_frame, text=i18n._("btn_cancel"),
               command=dlg.destroy).pack(side="left", padx=6)

    entry.bind("<Return>", lambda _: _submit())
    _center_dialog(dlg, parent)
    parent.winfo_toplevel().wait_window(dlg)
    return result[0]


def copy_to_clipboard(parent: tk.BaseWidget, text: str) -> None:
    root = parent.winfo_toplevel()
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()
