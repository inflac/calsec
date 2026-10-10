"""Reading and changing calendar entries."""

import calendar as _cal_mod
import uuid
from datetime import date as _date
from datetime import datetime

import i18n
from core.recurrence import expand_recurrence
from crypto import encrypt_entry


class EntriesMixin:
    """Entry queries (all users) and mutations (editors and admins)."""

    # -- Queries ---------------------------------------------------------------

    def get_entries(self) -> list[dict]:
        """Return all decrypted entry dicts, sorted by timestamp."""
        return [e["data"] for e in self.buffer]

    def get_entries_for_month(self, year: int, month: int) -> list[dict]:
        """Return entries for the given month, expanding recurring ones."""
        _, last_day = _cal_mod.monthrange(year, month)
        month_start = _date(year, month, 1)
        month_end   = _date(year, month, last_day)

        result = []
        for e in self.buffer:
            data = e["data"]
            rec  = data.get("recurrence")

            if not rec or rec.get("freq", "none") == "none":
                try:
                    entry_date = datetime.strptime(data["date"], "%d.%m.%Y").date()
                    if month_start <= entry_date <= month_end:
                        result.append(data)
                except Exception as exc:
                    raise RuntimeError(
                        i18n._("app_err_entry_invalid_date").format(
                            id=data.get("id", "<unknown>"))
                    ) from exc
            else:
                for d in expand_recurrence(data, year, month):
                    date_str = d.strftime("%d.%m.%Y")
                    instance = dict(data)
                    instance["date"] = date_str
                    dt = datetime.strptime(date_str, "%d.%m.%Y")
                    time_str = instance.get("time", "all-day")
                    if time_str not in ("all-day", "unknown"):
                        try:
                            t = datetime.strptime(time_str, "%H:%M")
                            dt = dt.replace(hour=t.hour, minute=t.minute)
                        except Exception as exc:
                            raise RuntimeError(
                                i18n._("app_err_entry_invalid_time").format(
                                    id=data.get("id", "<unknown>"))
                            ) from exc
                    instance["timestamp"]  = dt.timestamp()
                    instance["is_recurring"] = True
                    instance["_row_iid"] = (
                        f"{data['id']}_inst_{date_str.replace('.', '')}")
                    result.append(instance)

        result.sort(key=lambda x: x.get("timestamp", 0))
        return result

    # -- Mutations (editor + admin) --------------------------------------------

    def add_entry(self, title: str, date_str: str, time_str: str,
                  comments: list[str], color: str | None = None,
                  recurrence: dict | None = None, on_sync_done=None):
        date_dt = datetime.strptime(date_str, "%d.%m.%Y")
        if time_str not in ("all-day", "unknown"):
            t = datetime.strptime(time_str, "%H:%M")
            date_dt = date_dt.replace(hour=t.hour, minute=t.minute)
        timestamp = date_dt.timestamp()

        entry = {
            "id":        str(uuid.uuid4()),
            "title":     title,
            "date":      date_str,
            "time":      time_str,
            "timestamp": timestamp,
            "comments":  comments,
        }
        if color:
            entry["color"] = color
        if recurrence:
            entry["recurrence"] = recurrence

        def op():
            encrypted = encrypt_entry(entry, self._sym_key_cal)
            pos = 0
            for i, e in enumerate(self.buffer):
                if timestamp < e["timestamp"]:
                    pos = i
                    break
                pos = i + 1
            self._entries_enc.insert(pos, encrypted)
            return "entries"

        self._commit(op, on_sync_done)

    def update_entry(self, entry_id: str, title: str, date_str: str,
                     time_str: str, comments: list[str],
                     color: str | None = None, recurrence: dict | None = None,
                     on_sync_done=None):
        existing = next((e["data"] for e in self.buffer if e["id"] == entry_id), None)
        if existing is None:
            return
        if (existing.get("title") == title
                and existing.get("date") == date_str
                and existing.get("time") == time_str
                and existing.get("comments", []) == comments
                and existing.get("color") == color
                and existing.get("recurrence") == recurrence):
            return  # nothing changed - skip save and sync

        date_dt = datetime.strptime(date_str, "%d.%m.%Y")
        if time_str not in ("all-day", "unknown"):
            t = datetime.strptime(time_str, "%H:%M")
            date_dt = date_dt.replace(hour=t.hour, minute=t.minute)
        timestamp = date_dt.timestamp()

        entry = {
            "id":        entry_id,
            "title":     title,
            "date":      date_str,
            "time":      time_str,
            "timestamp": timestamp,
            "comments":  comments,
        }
        if color:
            entry["color"] = color
        if recurrence:
            entry["recurrence"] = recurrence

        def op():
            if not any(e["id"] == entry_id for e in self._entries_enc):
                # Deleted by someone else in the meantime.
                raise RuntimeError(i18n._("app_err_entry_not_found"))
            encrypted = encrypt_entry(entry, self._sym_key_cal)
            self._entries_enc = [
                encrypted if e["id"] == entry_id else e
                for e in self._entries_enc
            ]
            return "entries"

        self._commit(op, on_sync_done)

    def delete_entries(self, ids: list[str], on_sync_done=None) -> bool:
        if not any(e["id"] in ids for e in self._entries_enc):
            return False

        def op():
            before = len(self._entries_enc)
            self._entries_enc = [e for e in self._entries_enc if e["id"] not in ids]
            return "entries" if len(self._entries_enc) != before else None

        self._commit(op, on_sync_done)
        return True

