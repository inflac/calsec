from datetime import date

import pytest

TODAY = date.today()
ENTRY = {"id": "a1", "date": TODAY.strftime("%d.%m.%Y"), "time": "10:00",
         "title": "Test", "comments": []}


class StubApp:
    """Just enough of CalendarApp for MainWindow."""

    def __init__(self, can_edit=True, is_admin=False):
        self.can_edit = can_edit
        self.is_admin = is_admin
        self.version = 3
        self.sync_config = None

    def get_entries_for_month(self, y, m):
        return [ENTRY] if (y, m) == (TODAY.year, TODAY.month) else []

    def get_entries(self):
        return [ENTRY]


@pytest.fixture()
def make_window(tk_root, no_settings_file):
    from ui.main_window import MainWindow

    def _make(**app_kwargs):
        tk_root.minsize(680, 440)                     # as main.Application does
        mw = MainWindow(tk_root, StubApp(**app_kwargs), on_toggle_theme=lambda: None)
        mw.pack(fill="both", expand=True)
        tk_root.update()
        return mw

    return _make


# ── list / month toggle ───────────────────────────────────────────────────────

def test_starts_in_saved_view(make_window, no_settings_file):
    no_settings_file._current["view_mode"] = "month"
    mw = make_window()
    assert mw._view_mode == "month"
    assert mw._month_view.winfo_ismapped()
    assert not mw._list_view.winfo_ismapped()


def test_unknown_saved_view_falls_back_to_list(make_window, no_settings_file):
    no_settings_file._current["view_mode"] = "bogus"
    assert make_window()._view_mode == "list"


def test_toggle_switches_view_and_saves_it(make_window, no_settings_file, tk_root):
    mw = make_window()
    assert mw._view_btn.cget("text") == "▦  Month"
    mw._view_btn.invoke()
    tk_root.update()
    assert mw._view_mode == "month"
    assert mw._month_view.winfo_ismapped() and not mw._list_view.winfo_ismapped()
    assert mw._view_btn.cget("text") == "☰  List"
    assert no_settings_file.get("view_mode") == "month"
    mw._toggle_view()
    assert mw._view_mode == "list"
    assert no_settings_file.get("view_mode") == "list"


def test_both_views_request_the_same_size(make_window):
    mw = make_window()
    assert int(mw._month_view.cget("width")) == mw._list_view.winfo_reqwidth()
    assert int(mw._month_view.cget("height")) == mw._list_view.winfo_reqheight()


def test_selection_comes_from_visible_view(make_window):
    mw = make_window()
    mw._list_view._tree.selection_set("a1")
    assert mw._selected_base_ids() == ["a1"]
    mw._set_view("month", save=False)
    assert mw._selected_base_ids() == []          # nothing selected in the grid


def test_view_toggle_sits_below_settings_and_theme(make_window):
    mw = make_window()
    grid = {w.cget("text"): w.grid_info() for w in mw._top_right.winfo_children()}
    toggle = mw._view_btn.grid_info()
    assert int(toggle["row"]) == 1
    assert int(toggle["column"]) == int(grid["⚙"]["column"])
    assert int(toggle["columnspan"]) == 2


# ── double-click per role ─────────────────────────────────────────────────────

@pytest.mark.parametrize("can_edit, expected", [(True, "edit"), (False, "view")])
def test_double_click_edits_or_views_by_role(make_window, monkeypatch, can_edit, expected):
    import ui.main_window as mw_module

    calls = []
    monkeypatch.setattr(mw_module, "ViewEntryDialog",
                        lambda parent, entry: calls.append(("view", entry["id"])))
    mw = make_window(can_edit=can_edit)
    monkeypatch.setattr(mw, "_edit", lambda entry: calls.append(("edit", entry["id"])))
    mw._open_entry("a1")
    assert calls == [(expected, "a1")]


def test_no_edit_button_in_toolbar(make_window):
    mw = make_window(can_edit=True)
    texts = [w.cget("text") for w in mw._top.winfo_children() if w.winfo_class() == "TButton"]
    assert "Edit" not in texts
    assert "Delete" in texts


def test_viewer_has_no_edit_buttons(make_window):
    mw = make_window(can_edit=False)
    texts = [w.cget("text") for w in mw._top.winfo_children() if w.winfo_class() == "TButton"]
    assert "Add" not in texts and "Delete" not in texts


# ── window size ───────────────────────────────────────────────────────────────

def test_status_bar_is_packed_before_content(make_window):
    """pack takes space from the last packed widget first: the bar must come earlier."""
    mw = make_window()
    order = mw.pack_slaves()
    bar = mw._status_label.master
    content = mw._list_view.master
    assert order.index(bar) < order.index(content)


@pytest.mark.parametrize("is_admin", [False, True])
def test_window_cannot_get_narrower_than_toolbar(make_window, tk_root, is_admin):
    mw = make_window(is_admin=is_admin)
    tk_root.update()
    min_w, min_h = tk_root.minsize()
    assert min_w >= mw._top.winfo_reqwidth()
    assert min_h == 440


def test_update_button_raises_min_width(make_window, tk_root):
    mw = make_window(is_admin=True)
    tk_root.update()
    before = tk_root.minsize()[0]
    mw.show_update_banner(type("Info", (), {"version": "9.9.9"})())
    assert tk_root.minsize()[0] > before


def test_min_size_is_restored_when_window_is_closed(make_window, tk_root):
    mw = make_window(is_admin=True)
    tk_root.update()
    mw.destroy()
    assert tk_root.minsize() == (680, 440)


# ── theme switch in main.Application ──────────────────────────────────────────

def test_theme_switch_keeps_position_and_month(tk_root, no_settings_file, monkeypatch):
    import tkinter as tk

    import main as main_module
    from ui.main_window import MainWindow

    # main.Application is its own Tk root: build one without its startup flow.
    # Retry like conftest.new_tk (Windows sometimes fails to find tk.tcl).
    app = main_module.Application.__new__(main_module.Application)
    for _ in range(3):
        try:
            tk.Tk.__init__(app, className="calsec")
            break
        except tk.TclError as exc:
            error = exc
    else:
        pytest.skip(f"no display available: {error}")
    try:
        app.minsize(680, 440)
        app._frame = None
        app._pending_update = None
        app._logged_in_app = StubApp()
        main_module.theme.apply(app, "dark")
        no_settings_file._current["theme"] = "dark"
        centered = []
        monkeypatch.setattr(main_module, "_center_on_screen", centered.append)

        app._switch_to(MainWindow(app, app._logged_in_app, on_toggle_theme=app._toggle_theme))
        app.update()
        app._frame._next_month()
        shown = (app._frame._view_year, app._frame._view_month)
        centered.clear()

        app._toggle_theme()
        app.update()
        assert no_settings_file.get("theme") == "light"
        assert (app._frame._view_year, app._frame._view_month) == shown
        assert centered == []               # not re-centered
    finally:
        app.destroy()
