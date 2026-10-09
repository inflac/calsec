"""Month grid view of calendar entries, drawn on a Canvas.

Shows one month as a 7-column grid (Monday first) with ISO week numbers on
the left. Entries are drawn as coloured chips inside their day cell; if a day
has more entries than fit, a "+N more" link opens a menu with all of them.

Interaction mirrors the list view:
  click chip          select it (Ctrl+click toggles, for multi-delete)
  double-click chip   open the entry
  double-click day    add an entry on that day (if on_add_date is given)
"""

import calendar
import tkinter as tk
import tkinter.font as tkfont
from datetime import date as _date
from datetime import datetime

import i18n
import theme

_HEADER_H = 26      # weekday header row
_KW_W     = 38      # week number column
_DAY_H    = 22      # space for the day number at the top of a cell
_CHIP_H   = 18
_CHIP_GAP = 2
_PAD      = 3


class MonthView(tk.Canvas):
    def __init__(self, parent, on_open, on_add_date=None, on_select=None):
        super().__init__(parent, highlightthickness=0, borderwidth=0,
                         background=theme.BG)
        self._on_open = on_open            # (row_iid) -> None
        self._on_add_date = on_add_date    # ("dd.mm.yyyy") -> None, or None
        self._on_select = on_select        # () -> None, after selection changes

        self._year = self._month = 0
        self._entries: list[dict] = []
        self._row_to_id: dict[str, str] = {}
        self._selected: list[str] = []     # row iids, in click order

        self._font      = tkfont.Font(family="Cantarell", size=9)
        self._font_day  = tkfont.Font(family="Cantarell", size=10)
        self._font_bold = tkfont.Font(family="Cantarell", size=10, weight="bold")
        self._font_kw   = tkfont.Font(family="Cantarell", size=8)

        self._redraw_pending = False
        self.bind("<Configure>", lambda _e: self._schedule_redraw())
        self.bind("<Button-1>", self._on_click)
        self.bind("<Control-Button-1>", lambda e: self._on_click(e, toggle=True))
        self.bind("<Double-Button-1>", self._on_double_click)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_data(self, year: int, month: int, entries: list[dict]) -> None:
        self._year, self._month = year, month
        self._entries = entries
        self._row_to_id = {e.get("_row_iid", e["id"]): e["id"] for e in entries}
        self._selected = [iid for iid in self._selected if iid in self._row_to_id]
        self._schedule_redraw()

    def selected_base_ids(self) -> list[str]:
        """Deduplicated base entry ids of all selected chips."""
        seen = []
        for iid in self._selected:
            base = self._row_to_id.get(iid, iid)
            if base not in seen:
                seen.append(base)
        return seen

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _schedule_redraw(self):
        if not self._redraw_pending:
            self._redraw_pending = True
            self.after_idle(self._redraw)

    def _weeks(self) -> list[list[_date]]:
        cal = calendar.Calendar(firstweekday=0)
        return cal.monthdatescalendar(self._year, self._month)

    def _cell_geometry(self):
        w, h = self.winfo_width(), self.winfo_height()
        weeks = len(self._weeks())
        cell_w = (w - _KW_W) / 7
        cell_h = (h - _HEADER_H) / weeks
        return cell_w, cell_h

    def _redraw(self):
        self._redraw_pending = False
        self.delete("all")
        if not self._year or self.winfo_width() < 50:
            return

        self.configure(background=theme.BG)
        weeks = self._weeks()
        cell_w, cell_h = self._cell_geometry()
        today = _date.today()

        by_day: dict[_date, list[dict]] = {}
        for e in self._entries:
            try:
                d = datetime.strptime(e["date"], "%d.%m.%Y").date()
            except (KeyError, ValueError):
                continue
            by_day.setdefault(d, []).append(e)

        # Weekday header
        for col, name in enumerate(i18n.WD_SHORT):
            x = _KW_W + col * cell_w + cell_w / 2
            self.create_text(x, _HEADER_H / 2, text=name, fill=theme.FG_DIM,
                             font=self._font)

        max_chips = max(int((cell_h - _DAY_H - _PAD) // (_CHIP_H + _CHIP_GAP)), 0)

        for row, week in enumerate(weeks):
            y0 = _HEADER_H + row * cell_h
            iso = week[0].isocalendar()
            self.create_text(_KW_W / 2, y0 + _DAY_H / 2 + 1,
                             text=f"{i18n._('kw_short')} {iso.week}",
                             fill=theme.ACCENT, font=self._font_kw)

            for col, day in enumerate(week):
                x0 = _KW_W + col * cell_w
                in_month = day.month == self._month
                is_today = day == today
                self.create_rectangle(
                    x0, y0, x0 + cell_w, y0 + cell_h,
                    fill=theme.BG_ALT if in_month else theme.BG,
                    outline=theme.BORDER,
                    tags=("cell", f"day_{day.isoformat()}"))

                # Day number, today as a filled accent badge
                nx, ny = x0 + _PAD + 11, y0 + _DAY_H / 2 + 1
                if is_today:
                    self.create_oval(nx - 10, ny - 10, nx + 10, ny + 10,
                                     fill=theme.ACCENT, outline="",
                                     tags=(f"day_{day.isoformat()}",))
                self.create_text(
                    nx, ny, text=str(day.day),
                    font=self._font_bold if is_today else self._font_day,
                    fill="#ffffff" if is_today else
                         (theme.FG if in_month else theme.FG_DIM),
                    tags=(f"day_{day.isoformat()}",))

                if in_month:
                    self._draw_chips(day, by_day.get(day, []), x0, y0,
                                     cell_w, max_chips)

        # Today outline on top of the neighbouring cell borders
        for row, week in enumerate(weeks):
            if today in week:
                col = week.index(today)
                x0 = _KW_W + col * cell_w
                y0 = _HEADER_H + row * cell_h
                self.create_rectangle(x0 + 1, y0 + 1, x0 + cell_w - 1, y0 + cell_h - 1,
                                      outline=theme.ACCENT, width=2)

    def _draw_chips(self, day, entries, x0, y0, cell_w, max_chips):
        if not entries:
            return
        shown = entries if len(entries) <= max_chips else entries[:max(max_chips - 1, 0)]
        cx0, cx1 = x0 + _PAD, x0 + cell_w - _PAD
        y = y0 + _DAY_H

        for e in shown:
            row_iid = e.get("_row_iid", e["id"])
            color = e.get("color") or theme.ACCENT
            selected = row_iid in self._selected
            tag = f"chip_{row_iid}"
            self.create_rectangle(
                cx0, y, cx1, y + _CHIP_H,
                fill=theme.SEL_BG if selected else theme.blend(color, theme.BG_ALT, 0.45),
                outline=theme.FG if selected else "",
                tags=("chip", tag))
            # colour bar on the left edge
            self.create_rectangle(cx0, y, cx0 + 3, y + _CHIP_H, fill=color,
                                  outline="", tags=("chip", tag))

            label = e["title"]
            t = e.get("time", "all-day")
            if t not in ("all-day", "unknown", ""):
                label = f"{t} {label}"
            if e.get("is_recurring"):
                label = f"↻ {label}"
            self.create_text(cx0 + 7, y + _CHIP_H / 2,
                             text=self._fit(label, cx1 - cx0 - 10),
                             anchor="w", fill=theme.FG, font=self._font,
                             tags=("chip", tag))
            y += _CHIP_H + _CHIP_GAP

        hidden = len(entries) - len(shown)
        if hidden:
            self.create_text(cx0 + 4, y + _CHIP_H / 2,
                             text=i18n._("more_entries").format(n=hidden),
                             anchor="w", fill=theme.ACCENT, font=self._font,
                             tags=("more", f"more_{day.isoformat()}"))

    def _fit(self, text: str, width: float) -> str:
        """Shorten *text* with an ellipsis so it fits into *width* pixels."""
        if self._font.measure(text) <= width:
            return text
        while text and self._font.measure(text + "…") > width:
            text = text[:-1]
        return text + "…" if text else ""

    # ── Hit testing / events ──────────────────────────────────────────────────

    def _tags_at(self, event) -> tuple:
        items = self.find_overlapping(event.x, event.y, event.x, event.y)
        return self.gettags(items[-1]) if items else ()

    def _chip_at(self, event) -> str | None:
        for t in self._tags_at(event):
            if t.startswith("chip_"):
                return t[len("chip_"):]
        return None

    def _day_at(self, event) -> _date | None:
        for t in self._tags_at(event):
            if t.startswith(("day_", "more_")):
                return _date.fromisoformat(t.split("_", 1)[1])
        return None

    def _on_click(self, event, toggle: bool = False):
        for t in self._tags_at(event):
            if t.startswith("more_"):
                self._show_day_menu(_date.fromisoformat(t[len("more_"):]), event)
                return "break"

        row_iid = self._chip_at(event)
        if toggle and row_iid:
            if row_iid in self._selected:
                self._selected.remove(row_iid)
            else:
                self._selected.append(row_iid)
        elif row_iid:
            self._selected = [row_iid]
        elif not toggle:
            self._selected = []
        self._schedule_redraw()
        if self._on_select:
            self._on_select()
        return "break"

    def _on_double_click(self, event):
        row_iid = self._chip_at(event)
        if row_iid:
            self._on_open(row_iid)
            return
        day = self._day_at(event)
        if day and day.month == self._month and self._on_add_date:
            self._on_add_date(day.strftime("%d.%m.%Y"))

    def _show_day_menu(self, day: _date, event):
        """Popup listing all entries of *day*; choosing one opens it."""
        menu = tk.Menu(self, tearoff=False, background=theme.BG_ALT,
                       foreground=theme.FG, activebackground=theme.SEL_BG,
                       activeforeground=theme.FG, borderwidth=1)
        menu.add_command(label=day.strftime("%d.%m.%Y"), state="disabled")
        menu.add_separator()
        for e in self._entries:
            if e.get("date") != day.strftime("%d.%m.%Y"):
                continue
            t = e.get("time", "all-day")
            label = e["title"] if t in ("all-day", "unknown", "") else f"{t}  {e['title']}"
            row_iid = e.get("_row_iid", e["id"])
            menu.add_command(label=label,
                             command=lambda r=row_iid: self._on_open(r))
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()
