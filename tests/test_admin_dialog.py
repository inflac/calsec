"""Layout of the user management dialog."""
import pytest


class StubApp:
    def list_users(self):
        return [{"hash": f"h{i}", "identifier": f"user{i}@example.com", "role": "viewer"}
                for i in range(12)]


def _buttons_inside(dlg):
    """True if every button of the action row lies fully inside the window."""
    from tkinter import ttk

    dlg.update()
    win_bottom = dlg.winfo_rooty() + dlg.winfo_height()
    win_right = dlg.winfo_rootx() + dlg.winfo_width()
    buttons = [w for frame in dlg.winfo_children() if isinstance(frame, ttk.Frame)
               for w in frame.winfo_children() if isinstance(w, ttk.Button)]
    assert len(buttons) == 4
    return all(b.winfo_ismapped()
               and b.winfo_rooty() + b.winfo_height() <= win_bottom
               and b.winfo_rootx() + b.winfo_width() <= win_right
               for b in buttons)


@pytest.fixture()
def open_dialog(tk_root, monkeypatch):
    from ui.dialogs import admin

    # The test root is withdrawn; show the dialog without centering or grabbing.
    monkeypatch.setattr(admin, "_center_dialog", lambda dlg, parent: dlg.deiconify())
    opened = []

    def _open():
        dlg = admin.UserManagementDialog(tk_root, StubApp())
        opened.append(dlg)
        return dlg

    yield _open
    for dlg in opened:
        dlg.destroy()


@pytest.mark.parametrize("scaling", [1.0, 2.0])
def test_buttons_visible_by_default_and_at_minimum_size(open_dialog, tk_root, scaling):
    old = float(tk_root.tk.call("tk", "scaling"))
    tk_root.tk.call("tk", "scaling", scaling)
    try:
        dlg = open_dialog()
        assert _buttons_inside(dlg)

        min_w, min_h = dlg.minsize()
        dlg.geometry(f"{min_w}x{min_h}")
        assert _buttons_inside(dlg)
    finally:
        tk_root.tk.call("tk", "scaling", old)


def test_default_size_keeps_the_previous_size_as_floor(open_dialog, tk_root):
    old = float(tk_root.tk.call("tk", "scaling"))
    tk_root.tk.call("tk", "scaling", 1.0)
    try:
        dlg = open_dialog()
        dlg.update()
        assert dlg.winfo_width() >= 700
        assert dlg.winfo_height() >= 460
    finally:
        tk_root.tk.call("tk", "scaling", old)
