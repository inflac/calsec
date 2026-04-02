"""
Tails OS inspired theme for tkinter / ttk.

Two palettes — dark and light — both using Tails' brand purple (#56347c).
Call apply(root, mode) once at startup and again whenever the mode changes.
All module-level colour constants are updated in-place so widgets recreated
after the call automatically get the new palette.

Usage:
    import theme, settings
    settings.load()
    theme.apply(root, settings.get("theme"))   # "dark" | "light"
"""

import tkinter as tk
from tkinter import ttk

# ---------- Static palettes ----------

_DARK = dict(
    BG       = "#1a1625",   # deep purple-black
    BG_ALT   = "#231d30",   # widget field background
    BG_PANEL = "#130f1c",   # status bar / heading row
    FG       = "#e8e0f0",   # primary text
    FG_DIM   = "#9b8fb0",   # secondary / hint text
    ACCENT   = "#9460d8",   # bright purple (readable on dark bg)
    ACCENT_H = "#7a48b8",   # accent hover / pressed
    RED      = "#e06c75",   # error text
    BORDER   = "#3d3050",   # widget borders
    SEL_BG   = "#3d2566",   # selection background
)

_LIGHT = dict(
    BG       = "#f7f4fc",   # near-white with purple tint
    BG_ALT   = "#ede5f8",   # entry / field background
    BG_PANEL = "#e0d4f0",   # status bar / heading row
    FG       = "#1a0d2e",   # dark purple-black text
    FG_DIM   = "#6b5580",   # secondary text
    ACCENT   = "#56347c",   # Tails brand purple (exact)
    ACCENT_H = "#3d2260",   # accent hover / pressed
    RED      = "#c0392b",   # error text
    BORDER   = "#c9b0e0",   # widget borders
    SEL_BG   = "#c4a8e8",   # selection background
)

# ---------- Module-level colour constants (mutated by apply()) ----------
# These are imported directly by widget constructors: `foreground=theme.FG_DIM`

BG       = _DARK["BG"]
BG_ALT   = _DARK["BG_ALT"]
BG_PANEL = _DARK["BG_PANEL"]
FG       = _DARK["FG"]
FG_DIM   = _DARK["FG_DIM"]
ACCENT   = _DARK["ACCENT"]
ACCENT_H = _DARK["ACCENT_H"]
RED      = _DARK["RED"]
BORDER   = _DARK["BORDER"]
SEL_BG   = _DARK["SEL_BG"]


# ---------- Public API ----------

def apply(root: tk.Tk, mode: str = "dark") -> None:
    """Update palette constants and re-apply all ttk / tk-option styles."""
    _load_palette(mode)
    _apply_tk_options(root)
    root.configure(bg=BG)
    _apply_ttk_styles(root)


# ---------- Internals ----------

def _load_palette(mode: str) -> None:
    global BG, BG_ALT, BG_PANEL, FG, FG_DIM, ACCENT, ACCENT_H, RED, BORDER, SEL_BG
    p = _DARK if mode == "dark" else _LIGHT
    BG       = p["BG"]
    BG_ALT   = p["BG_ALT"]
    BG_PANEL = p["BG_PANEL"]
    FG       = p["FG"]
    FG_DIM   = p["FG_DIM"]
    ACCENT   = p["ACCENT"]
    ACCENT_H = p["ACCENT_H"]
    RED      = p["RED"]
    BORDER   = p["BORDER"]
    SEL_BG   = p["SEL_BG"]


def _apply_tk_options(root: tk.Tk) -> None:
    """Set X-resource defaults for plain tk widgets (Text, Toplevel, …)."""
    P = "80"   # priority — overrides theme defaults but not widget-level settings
    root.option_add("*Background",           BG,     P)
    root.option_add("*Foreground",           FG,     P)
    root.option_add("*activeBackground",     BG_ALT, P)
    root.option_add("*activeForeground",     FG,     P)
    root.option_add("*disabledForeground",   FG_DIM, P)
    root.option_add("*highlightBackground",  BG,     P)
    root.option_add("*highlightColor",       ACCENT, P)
    root.option_add("*selectBackground",     SEL_BG, P)
    root.option_add("*selectForeground",     FG,     P)
    root.option_add("*Text.Background",      BG_ALT, P)
    root.option_add("*Text.Foreground",      FG,     P)
    root.option_add("*Text.insertBackground",FG,     P)
    root.option_add("*Text.selectBackground",SEL_BG, P)
    root.option_add("*Text.relief",          "flat", P)


def _apply_ttk_styles(root: tk.Tk) -> None:
    F       = ("Cantarell", 10)
    F_SMALL = ("Cantarell", 9)

    s = ttk.Style(root)
    s.theme_use("clam")

    s.configure(".",
        background=BG, foreground=FG,
        fieldbackground=BG_ALT,
        bordercolor=BORDER,
        darkcolor=BG_PANEL, lightcolor=BG_ALT,
        troughcolor=BG,
        focuscolor=ACCENT,
        insertcolor=FG,
        selectbackground=SEL_BG, selectforeground=FG,
        relief="flat", font=F,
    )

    s.configure("TFrame",      background=BG)
    s.configure("TLabelframe", background=BG, bordercolor=BORDER)
    s.configure("TLabelframe.Label", background=BG, foreground=FG_DIM, font=F)

    s.configure("TLabel",      background=BG, foreground=FG,     font=F)
    s.configure("Dim.TLabel",  background=BG, foreground=FG_DIM, font=F)
    s.configure("Error.TLabel",background=BG, foreground=RED,    font=F)

    s.configure("TEntry",
        fieldbackground=BG_ALT, foreground=FG,
        insertcolor=FG, bordercolor=BORDER,
        relief="flat", padding=5,
    )
    s.map("TEntry",
        fieldbackground=[("readonly", BG_PANEL), ("disabled", BG_PANEL)],
        foreground=[("readonly", FG), ("disabled", FG_DIM)],
        bordercolor=[("focus", ACCENT), ("active", ACCENT)],
    )

    s.configure("TButton",
        background=BG_ALT, foreground=FG,
        bordercolor=BORDER, relief="flat",
        padding=(10, 5), font=F,
    )
    s.map("TButton",
        background=[("active", ACCENT_H), ("pressed", ACCENT), ("disabled", BG_PANEL)],
        foreground=[("active", FG), ("disabled", FG_DIM)],
        bordercolor=[("active", ACCENT), ("focus", ACCENT)],
    )

    s.configure("TSeparator", background=BORDER)

    s.configure("TScrollbar",
        background=BG_ALT, troughcolor=BG,
        bordercolor=BG, arrowcolor=FG_DIM,
        relief="flat", arrowsize=12,
    )
    s.map("TScrollbar",
        background=[("active", ACCENT_H), ("pressed", ACCENT)],
        arrowcolor=[("active", FG)],
    )

    s.configure("Treeview",
        background=BG_ALT, foreground=FG,
        fieldbackground=BG_ALT, bordercolor=BORDER,
        rowheight=26, font=F,
    )
    s.configure("Treeview.Heading",
        background=BG_PANEL, foreground=FG_DIM,
        relief="flat", bordercolor=BORDER,
        font=F_SMALL, padding=(4, 4),
    )
    s.map("Treeview",
        background=[("selected", SEL_BG)],
        foreground=[("selected", FG)],
    )
    s.map("Treeview.Heading",
        background=[("active", BG_ALT)],
        relief=[("active", "flat")],
    )

    s.configure("TNotebook",     background=BG, bordercolor=BORDER)
    s.configure("TNotebook.Tab", background=BG_PANEL, foreground=FG_DIM, padding=(10, 4))
    s.map("TNotebook.Tab",
        background=[("selected", BG), ("active", BG_ALT)],
        foreground=[("selected", FG)],
    )
