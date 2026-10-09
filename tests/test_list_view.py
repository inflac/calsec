import pytest
from conftest import FakeEvent

ENTRIES = [
    {"id": "a", "date": "05.10.2026", "time": "10:00", "title": "Alpha",
     "comments": ["x", "y"], "color": "#e74c3c"},
    {"id": "b", "date": "06.10.2026", "time": "all-day", "title": "Beta", "comments": []},
    # two instances of one recurring entry, in different weeks
    {"id": "r", "date": "07.10.2026", "time": "all-day", "title": "Weekly",
     "is_recurring": True, "_row_iid": "r_inst_07102026"},
    {"id": "r", "date": "14.10.2026", "time": "all-day", "title": "Weekly",
     "is_recurring": True, "_row_iid": "r_inst_14102026"},
]


@pytest.fixture()
def view(tk_root):
    from ui.list_view import ListView

    opened = []
    v = ListView(tk_root, on_open=opened.append)
    v.opened = opened
    v.pack(fill="both", expand=True)
    v.set_data(2026, 10, ENTRIES)
    tk_root.update()
    return v


def _rows(view):
    return list(view._tree.get_children())


def test_week_headers_are_inserted(view):
    rows = _rows(view)
    assert rows == ["_kw_2026_41", "a", "b", "r_inst_07102026",
                    "_kw_2026_42", "r_inst_14102026"]
    assert view._tree.item("_kw_2026_41", "values")[0] == "CW 41 · 2026"


def test_row_values(view):
    date, time, title, comments = view._tree.item("a", "values")
    assert (date, time, title, comments) == ("05.10.2026", "10:00", "Alpha", "2")
    assert view._tree.item("b", "values")[3] == ""          # no comments → empty


def test_recurring_rows_are_marked(view):
    assert view._tree.item("r_inst_07102026", "values")[2].startswith("↻")


def test_colored_rows_get_their_own_tag(view):
    assert view._tree.item("a", "tags") == ("color_e74c3c",)
    assert view._tree.item("b", "tags") == ("row_default",)


def test_set_data_replaces_previous_rows(view):
    view.set_data(2026, 11, [])
    assert _rows(view) == []


def test_selected_base_ids_deduplicates_recurring_instances(view):
    view._tree.selection_set(("a", "r_inst_07102026", "r_inst_14102026"))
    assert view.selected_base_ids() == ["a", "r"]


def test_selecting_a_week_header_is_undone(view, tk_root):
    view._tree.selection_set(("_kw_2026_41", "b"))
    tk_root.update()                       # fires <<TreeviewSelect>>
    assert view._tree.selection() == ("b",)
    assert view.selected_base_ids() == ["b"]


def test_double_click_opens_entry(view):
    _, y, _, h = view._tree.bbox("b")
    view._on_double_click(FakeEvent(y=y + h // 2))
    assert view.opened == ["b"]


def test_double_click_on_week_header_does_nothing(view):
    _, y, _, h = view._tree.bbox("_kw_2026_41")
    view._on_double_click(FakeEvent(y=y + h // 2))
    assert view.opened == []
