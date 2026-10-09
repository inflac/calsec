from datetime import date

import pytest
from conftest import FakeEvent

YEAR, MONTH = 2026, 10        # October 2026 starts on a Thursday


def _entry(id_, day, title="T", time="all-day", **extra):
    return {"id": id_, "date": f"{day:02d}.{MONTH:02d}.{YEAR}", "time": time,
            "title": title, **extra}


@pytest.fixture()
def make_view(tk_root):
    from ui.month_view import MonthView

    def _make(entries, on_add_date="record"):
        calls = {"open": [], "add": [], "select": 0}

        def _sel():
            calls["select"] += 1

        v = MonthView(
            tk_root,
            on_open=calls["open"].append,
            on_add_date=calls["add"].append if on_add_date == "record" else on_add_date,
            on_select=_sel,
        )
        v.calls = calls
        v.configure(width=840, height=600)
        v.pack(fill="both", expand=True)
        v.set_data(YEAR, MONTH, entries)
        tk_root.update()
        v._redraw()
        return v

    return _make


def _center(view, tag):
    x0, y0, x1, y1 = view.bbox(view.find_withtag(tag)[0])
    return FakeEvent((x0 + x1) // 2, (y0 + y1) // 2)


def _empty_spot_of_day(view, day: date):
    """A point inside the day cell below its chips."""
    x0, y0, x1, y1 = view.coords(
        [i for i in view.find_withtag(f"day_{day.isoformat()}")
         if "cell" in view.gettags(i)][0])
    return FakeEvent(int((x0 + x1) / 2), int(y1) - 4)


# ── layout ────────────────────────────────────────────────────────────────────

def test_weeks_start_on_monday_and_cover_the_month(make_view):
    weeks = make_view([])._weeks()
    assert all(w[0].weekday() == 0 for w in weeks)
    assert weeks[0][0] == date(2026, 9, 28)
    assert weeks[-1][-1] == date(2026, 11, 1)
    assert len(weeks) == 5


def test_every_day_has_a_cell(make_view):
    v = make_view([])
    cells = v.find_withtag("cell")
    assert len(cells) == 5 * 7


def test_entries_are_drawn_as_chips(make_view):
    v = make_view([_entry("a", 5, "Alpha", "10:00"), _entry("b", 20, "Beta")])
    assert v.find_withtag("chip_a") and v.find_withtag("chip_b")
    texts = [v.itemcget(i, "text") for i in v.find_withtag("chip_a")
             if v.type(i) == "text"]
    assert texts == ["10:00 Alpha"]


def test_recurring_chip_is_marked(make_view):
    v = make_view([_entry("r", 7, "Weekly", is_recurring=True, _row_iid="r_inst_07102026")])
    texts = [v.itemcget(i, "text") for i in v.find_withtag("chip_r_inst_07102026")
             if v.type(i) == "text"]
    assert texts[0].startswith("↻")


def test_entries_outside_the_month_are_not_drawn(make_view):
    other = {"id": "x", "date": "30.09.2026", "time": "all-day", "title": "Sept"}
    v = make_view([other])
    assert not v.find_withtag("chip_x")


def test_too_many_entries_show_more_link(make_view):
    entries = [_entry(f"e{i}", 15, f"E{i}") for i in range(12)]
    v = make_view(entries)
    more = v.find_withtag("more_2026-10-15")
    assert more
    shown = sum(1 for i in range(12) if v.find_withtag(f"chip_e{i}"))
    assert v.itemcget(more[0], "text") == f"+{12 - shown} more"
    assert 0 < shown < 12


def test_long_titles_are_shortened(make_view):
    v = make_view([])
    short = v._fit("A very long title " * 10, 80)
    assert short.endswith("…")
    assert v._font.measure(short) <= 80
    assert v._fit("Hi", 80) == "Hi"


# ── selection ─────────────────────────────────────────────────────────────────

def test_click_selects_chip(make_view):
    v = make_view([_entry("a", 5), _entry("b", 6)])
    v._on_click(_center(v, "chip_a"))
    assert v.selected_base_ids() == ["a"]
    v._on_click(_center(v, "chip_b"))
    assert v.selected_base_ids() == ["b"]
    assert v.calls["select"] == 2


def test_ctrl_click_toggles_selection(make_view):
    v = make_view([_entry("a", 5), _entry("b", 6)])
    v._on_click(_center(v, "chip_a"))
    v._on_click(_center(v, "chip_b"), toggle=True)
    assert v.selected_base_ids() == ["a", "b"]
    v._on_click(_center(v, "chip_a"), toggle=True)
    assert v.selected_base_ids() == ["b"]


def test_click_on_empty_space_clears_selection(make_view):
    v = make_view([_entry("a", 5)])
    v._on_click(_center(v, "chip_a"))
    v._on_click(_empty_spot_of_day(v, date(2026, 10, 20)))
    assert v.selected_base_ids() == []


def test_selected_recurring_instances_map_to_one_base_id(make_view):
    v = make_view([
        _entry("r", 7, is_recurring=True, _row_iid="r_inst_07102026"),
        _entry("r", 14, is_recurring=True, _row_iid="r_inst_14102026"),
    ])
    v._on_click(_center(v, "chip_r_inst_07102026"))
    v._on_click(_center(v, "chip_r_inst_14102026"), toggle=True)
    assert v.selected_base_ids() == ["r"]


def test_set_data_drops_selection_of_vanished_entries(make_view):
    v = make_view([_entry("a", 5), _entry("b", 6)])
    v._on_click(_center(v, "chip_a"))
    v.set_data(YEAR, MONTH, [_entry("b", 6)])
    assert v.selected_base_ids() == []


# ── double-click ──────────────────────────────────────────────────────────────

def test_double_click_chip_opens_entry(make_view):
    v = make_view([_entry("a", 5)])
    v._on_double_click(_center(v, "chip_a"))
    assert v.calls["open"] == ["a"]
    assert v.calls["add"] == []


def test_double_click_empty_day_adds_entry_on_that_date(make_view):
    v = make_view([])
    v._on_double_click(_empty_spot_of_day(v, date(2026, 10, 20)))
    assert v.calls["add"] == ["20.10.2026"]


def test_double_click_day_of_other_month_does_nothing(make_view):
    v = make_view([])
    v._on_double_click(_empty_spot_of_day(v, date(2026, 9, 28)))
    assert v.calls["add"] == []


def test_double_click_day_without_add_permission_does_nothing(make_view):
    v = make_view([], on_add_date=None)
    v._on_double_click(_empty_spot_of_day(v, date(2026, 10, 20)))     # must not raise
    assert v.calls["open"] == []
