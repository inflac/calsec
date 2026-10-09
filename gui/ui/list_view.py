"""List view of calendar entries: one row per entry, grouped by calendar week.

Same interface as MonthView, so MainWindow can switch between both:
  set_data(year, month, entries)   show the entries of one month
  selected_base_ids()              ids of the selected entries
  on_open(row_iid)                 called on double-click
"""

from datetime import datetime
from tkinter import ttk

import i18n
import theme


def _kw_iid(year: int, week: int) -> str:
    return f"_kw_{year}_{week:02d}"


def _is_header(iid: str) -> bool:
    return iid.startswith("_kw_")


class ListView(ttk.Frame):
    def __init__(self, parent, on_open):
        super().__init__(parent)
        self._on_open = on_open            # (row_iid) -> None
        self._row_to_id: dict[str, str] = {}

        cols = ("date", "time", "title", "comments")
        self._tree = ttk.Treeview(self, columns=cols, show="headings",
                                  selectmode="extended")

        self._tree.heading("date",     text=i18n._("col_date"))
        self._tree.heading("time",     text=i18n._("col_time"))
        self._tree.heading("title",    text=i18n._("col_title"))
        self._tree.heading("comments", text=i18n._("col_comments"))

        self._tree.column("date",     width=100, anchor="center")
        self._tree.column("time",     width=80,  anchor="center")
        self._tree.column("title",    width=260)
        self._tree.column("comments", width=80,  anchor="center")

        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=scrollbar.set)

        self._tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        self._tree.bind("<Double-1>",         self._on_double_click)
        self._tree.bind("<<TreeviewSelect>>", self._on_selection_change)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_data(self, year: int, month: int, entries: list[dict]) -> None:
        self._tree.delete(*self._tree.get_children())
        self._row_to_id.clear()

        # Configure all tags BEFORE inserting any rows.
        # In the clam theme, calling tag_configure after inserts causes the last
        # configured background to override all previously configured ones.
        self._tree.tag_configure("kw_header",
            foreground=theme.ACCENT,
            background=theme.BG_PANEL,
            font=("Cantarell", 8),
        )
        self._tree.tag_configure("row_default", background=theme.BG_ALT)

        # Pre-configure one tag per unique color before inserting any items
        for e in entries:
            color = e.get("color")
            if color:
                self._tree.tag_configure(f"color_{color.lstrip('#')}",
                                         background=theme.blend(color, theme.BG))

        current_week_key = None
        for e in entries:
            try:
                iso = datetime.strptime(e["date"], "%d.%m.%Y").isocalendar()
                week_key = (iso.year, iso.week)
            except Exception:
                week_key = None

            if week_key != current_week_key:
                current_week_key = week_key
                if week_key:
                    yr, wk = week_key
                    iid = _kw_iid(yr, wk)
                    if not self._tree.exists(iid):
                        self._tree.insert("", "end", iid=iid,
                            values=(i18n._("kw_label").format(wk=wk, yr=yr), "", "", ""),
                            tags=("kw_header",),
                        )

            n = len(e.get("comments", []))
            color = e.get("color")
            tags = (f"color_{color.lstrip('#')}",) if color else ("row_default",)

            title = ("↻  " + e["title"]) if e.get("is_recurring") else e["title"]
            row_iid = e.get("_row_iid", e["id"])
            self._row_to_id[row_iid] = e["id"]

            self._tree.insert("", "end", iid=row_iid, values=(
                e["date"], e["time"], title, f"{n}" if n else ""
            ), tags=tags)

    def selected_base_ids(self) -> list[str]:
        """Deduplicated base entry ids for all selected non-header rows."""
        seen = []
        for iid in self._tree.selection():
            if _is_header(iid):
                continue
            base = self._row_to_id.get(iid, iid)
            if base not in seen:
                seen.append(base)
        return seen

    # ── Events ────────────────────────────────────────────────────────────────

    def _on_selection_change(self, _event):
        headers = [iid for iid in self._tree.selection() if _is_header(iid)]
        if headers:
            self._tree.selection_remove(*headers)

    def _on_double_click(self, event):
        item = self._tree.identify_row(event.y)
        if item and not _is_header(item):
            self._on_open(item)
