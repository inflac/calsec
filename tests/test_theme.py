from tkinter import ttk

import theme

# ── blend ─────────────────────────────────────────────────────────────────────

def test_blend_alpha_zero_returns_base():
    assert theme.blend("#ff0000", "#000000", 0) == "#000000"


def test_blend_alpha_one_returns_color():
    assert theme.blend("#ff0000", "#000000", 1) == "#ff0000"


def test_blend_half_is_midpoint():
    assert theme.blend("#ffffff", "#000000", 0.5) == "#7f7f7f"


def test_blend_default_alpha():
    # 0.4 * 200 + 0.6 * 100 = 140 = 0x8c
    assert theme.blend("#c8c8c8", "#646464") == "#8c8c8c"


def test_blend_accepts_colors_without_hash():
    assert theme.blend("ff0000", "000000", 1) == "#ff0000"


# ── apply ─────────────────────────────────────────────────────────────────────

def test_apply_switches_palette(tk_root):
    theme.apply(tk_root, "light")
    assert theme.BG == theme._LIGHT["BG"]
    theme.apply(tk_root, "dark")
    assert theme.BG == theme._DARK["BG"]


def test_readonly_entry_background_is_dark(tk_root):
    """clam paints the 4 corner pixels of readonly entries light by default."""
    style = ttk.Style(tk_root)
    assert style.lookup("TEntry", "background", ["readonly"]) == theme.BG
    assert style.lookup("TEntry", "background", ["disabled"]) == theme.BG


def test_treeview_background_is_dark(tk_root):
    """clam's white Treeview background shows in the 4 corner pixels."""
    assert ttk.Style(tk_root).lookup("Treeview", "background") == theme.BG
