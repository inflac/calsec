#!/usr/bin/env python3

import json
import os
import uuid
import calendar as _cal_mod
import threading
from datetime import datetime, date as _date, timedelta as _timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from crypto import (
    encrypt_entry, decrypt_entry,
    sign_file, verify_file,
    sym_encrypt, sym_decrypt,
    ecies_encrypt,
    b64, b64d,
)
import storage

# Weekday codes: index matches Python's date.weekday() (0=Mon … 6=Sun)
_WD_CODES = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]


def _nth_weekday_of_month(year: int, month: int, weekday: int, pos: int):
    """Return the pos-th occurrence (1-based; -1 = last) of weekday in month."""
    _, last_day = _cal_mod.monthrange(year, month)
    days = [_date(year, month, d) for d in range(1, last_day + 1)
            if _date(year, month, d).weekday() == weekday]
    if not days:
        return None
    if pos == -1:
        return days[-1]
    idx = pos - 1
    return days[idx] if 0 <= idx < len(days) else None


def _expand_recurrence(data: dict, year: int, month: int) -> list:
    """Return sorted list of date objects for recurring entry within (year, month)."""
    rec = data.get("recurrence")
    if not rec:
        return []
    freq = rec.get("freq", "none")
    if freq == "none":
        return []

    try:
        base = datetime.strptime(data["date"], "%d.%m.%Y").date()
    except (KeyError, ValueError):
        return []

    interval = max(1, int(rec.get("interval", 1)))
    end_mode = rec.get("end_mode", "never")
    max_count = int(rec["count"]) if end_mode == "count" and "count" in rec else None
    end_date = None
    if end_mode == "until" and "until" in rec:
        try:
            end_date = datetime.strptime(rec["until"], "%d.%m.%Y").date()
        except ValueError:
            pass

    _, last_day = _cal_mod.monthrange(year, month)
    month_start = _date(year, month, 1)
    month_end   = _date(year, month, last_day)

    upper = month_end
    if end_date and end_date < upper:
        upper = end_date

    if base > upper:
        return []

    occurrences = []

    if freq == "daily":
        gap = max(0, (month_start - base).days)
        steps_before = gap // interval
        d = base + _timedelta(days=steps_before * interval)
        count = steps_before
        while d <= upper:
            if max_count is not None and count >= max_count:
                break
            if d >= month_start:
                occurrences.append(d)
            count += 1
            d += _timedelta(days=interval)

    elif freq == "weekly":
        weekdays = rec.get("weekdays", [])
        wd_indices = sorted({_WD_CODES.index(wd) for wd in weekdays if wd in _WD_CODES})
        if not wd_indices:
            return []
        week_start = base - _timedelta(days=base.weekday())
        count = 0
        done = False
        while not done and week_start <= upper + _timedelta(days=6):
            for wd_idx in wd_indices:
                d = week_start + _timedelta(days=wd_idx)
                if d < base:
                    continue
                if max_count is not None and count >= max_count:
                    done = True
                    break
                if d > upper:
                    done = True
                    break
                count += 1
                if d >= month_start:
                    occurrences.append(d)
            if not done:
                week_start += _timedelta(weeks=interval)

    elif freq == "monthly":
        mode = rec.get("month_mode", "monthday")
        cur_year, cur_month = base.year, base.month
        count = 0
        while _date(cur_year, cur_month, 1) <= upper:
            if mode == "monthday":
                day = int(rec.get("month_day", base.day))
                _, lday = _cal_mod.monthrange(cur_year, cur_month)
                try:
                    d = _date(cur_year, cur_month, min(day, lday))
                except ValueError:
                    d = None
            else:
                pos     = int(rec.get("month_pos", "1"))
                wd_code = rec.get("month_weekday", _WD_CODES[0])
                wd_idx  = _WD_CODES.index(wd_code) if wd_code in _WD_CODES else 0
                d = _nth_weekday_of_month(cur_year, cur_month, wd_idx, pos)

            if d and d >= base:
                if max_count is not None and count >= max_count:
                    break
                count += 1
                if d <= upper and d >= month_start:
                    occurrences.append(d)

            m = cur_month + interval
            cur_year  += (m - 1) // 12
            cur_month  = ((m - 1) % 12) + 1

    elif freq == "yearly":
        cur_year = base.year
        count = 0
        while True:
            try:
                d = base.replace(year=cur_year)
            except ValueError:
                d = base.replace(year=cur_year, day=28)
            if d > upper:
                break
            if d >= base:
                if max_count is not None and count >= max_count:
                    break
                count += 1
                if d >= month_start:
                    occurrences.append(d)
            cur_year += interval

    return sorted(occurrences)


class CalendarApp:

    def __init__(self, sym_key_cal: bytes, kpriv_sign=None,
                 is_admin: bool = False, user_hash: str | None = None):
        self._sym_key_cal = sym_key_cal
        self._kpriv_sign  = kpriv_sign   # None for non-admin users
        self._is_admin    = is_admin
        self._user_hash   = user_hash
        self._kpub_sign   = storage.load_sign_public_key()

        self.buffer   = []
        self.unsigned = False
        self._reload()

    def _reload(self):
        raw = storage.load_file_raw()
        self.version          = raw.get("version", 2)
        self._users           = raw.get("users", {})
        self._entries_enc     = raw.get("entries", [])
        self._sync_config_enc = raw.get("sync_config")
        sig = raw.get("signature")

        if sig is None:
            self.unsigned = True
        elif not verify_file(self.version, self._users, self._entries_enc,
                             self._sync_config_enc, sig, self._kpub_sign):
            raise RuntimeError(
                "Calendar file signature is invalid. "
                "File may have been tampered with.")

        self.buffer = []
        for enc in self._entries_enc:
            try:
                dec = decrypt_entry(enc, self._sym_key_cal)
                self.buffer.append({
                    "id":        dec["id"],
                    "timestamp": dec["timestamp"],
                    "data":      dec,
                })
            except Exception:
                continue
        self.buffer.sort(key=lambda x: x["timestamp"])

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_admin(self) -> bool:
        return self._is_admin

    @property
    def sync_config(self):
        if self._sync_config_enc is None:
            return None
        try:
            return json.loads(sym_decrypt(self._sym_key_cal, self._sync_config_enc))
        except Exception:
            return None

    # ── Internal save ─────────────────────────────────────────────────────────

    def _save_and_sync(self, on_sync_done=None):
        """Sign, save, reload, then push to Nextcloud (admin only)."""
        if self._kpriv_sign is None:
            raise RuntimeError("Only admin can save changes.")

        new_version = self.version + 1
        sig = sign_file(new_version, self._users, self._entries_enc,
                        self._sync_config_enc, self._kpriv_sign)
        storage.save_file({
            "version":     new_version,
            "users":       self._users,
            "sync_config": self._sync_config_enc,
            "entries":     self._entries_enc,
            "signature":   sig,
        })
        self._reload()

        config = self.sync_config
        if config is not None:
            def _run():
                from sync import sync_push
                msg = sync_push(config)
                if on_sync_done:
                    on_sync_done(msg)
            threading.Thread(target=_run, daemon=True).start()

    # ── Entry queries ─────────────────────────────────────────────────────────

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
                except Exception:
                    pass
            else:
                for d in _expand_recurrence(data, year, month):
                    date_str = d.strftime("%d.%m.%Y")
                    instance = dict(data)
                    instance["date"] = date_str
                    dt = datetime.strptime(date_str, "%d.%m.%Y")
                    time_str = instance.get("time", "all-day")
                    if time_str not in ("all-day", "unknown"):
                        try:
                            t = datetime.strptime(time_str, "%H:%M")
                            dt = dt.replace(hour=t.hour, minute=t.minute)
                        except Exception:
                            pass
                    instance["timestamp"]  = dt.timestamp()
                    instance["is_recurring"] = True
                    instance["_row_iid"] = (
                        f"{data['id']}_inst_{date_str.replace('.', '')}")
                    result.append(instance)

        result.sort(key=lambda x: x.get("timestamp", 0))
        return result

    # ── Entry mutations (admin only) ──────────────────────────────────────────

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

        encrypted = encrypt_entry(entry, self._sym_key_cal)

        pos = 0
        for i, e in enumerate(self.buffer):
            if timestamp < e["timestamp"]:
                pos = i
                break
            pos = i + 1

        self._entries_enc.insert(pos, encrypted)
        self._save_and_sync(on_sync_done)

    def update_entry(self, entry_id: str, title: str, date_str: str,
                     time_str: str, comments: list[str],
                     color: str | None = None, recurrence: dict | None = None,
                     on_sync_done=None):
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

        encrypted = encrypt_entry(entry, self._sym_key_cal)
        self._entries_enc = [
            encrypted if e["id"] == entry_id else e
            for e in self._entries_enc
        ]
        self._save_and_sync(on_sync_done)

    def delete_entries(self, ids: list[str], on_sync_done=None) -> bool:
        original_len = len(self._entries_enc)
        self._entries_enc = [e for e in self._entries_enc if e["id"] not in ids]
        if len(self._entries_enc) == original_len:
            return False
        self._save_and_sync(on_sync_done)
        return True

    # ── Sync config (admin only) ──────────────────────────────────────────────

    def update_sync_config(self, sync_data: dict | None, on_sync_done=None):
        if sync_data is None:
            self._sync_config_enc = None
        else:
            self._sync_config_enc = sym_encrypt(
                self._sym_key_cal, json.dumps(sync_data).encode())
        self._save_and_sync(on_sync_done)

    # ── Sync pull (all users) ─────────────────────────────────────────────────

    def sync_pull(self, on_done=None) -> None:
        """Download a newer calendar.json from Nextcloud in the background."""
        config = self.sync_config
        if config is None:
            if on_done:
                on_done("Kein Sync konfiguriert.")
            return

        kpub_sign = self._kpub_sign

        def _run():
            from sync import sync_pull as _pull
            data, msg = _pull(config)
            if data is None:
                if on_done:
                    on_done(msg)
                return

            # Verify signature of downloaded file
            sig = data.get("signature")
            if not sig or not verify_file(
                data.get("version", 2), data.get("users", {}),
                data.get("entries", []), data.get("sync_config"),
                sig, kpub_sign,
            ):
                if on_done:
                    on_done("Sync error: Signatur der heruntergeladenen Datei ungültig.")
                return

            if data.get("version", 0) <= self.version:
                if on_done:
                    on_done("Kalender bereits aktuell.")
                return

            storage.save_file(data)
            self._reload()
            if on_done:
                on_done(msg)

        threading.Thread(target=_run, daemon=True).start()

    # ── User management (admin only) ──────────────────────────────────────────

    def list_users(self) -> list[dict]:
        """Return [{hash, email, is_admin}] for all registered users."""
        result = []
        for h, u in self._users.items():
            email = ""
            try:
                email = sym_decrypt(self._sym_key_cal, u["email_enc"]).decode()
            except Exception:
                pass
            result.append({
                "hash":     h,
                "email":    email,
                "is_admin": u.get("is_admin", False),
            })
        return result

    def add_user(self, email: str, kpub_user=None,
                 password: bytes | None = None) -> bytes | None:
        """Add a user to the calendar.

        If *kpub_user* is None a new SECP256R1 keypair is generated.
        If *password* is provided the private key is also saved to KEYS_DIR.
        Returns the private key PEM bytes (password-protected if password given,
        unencrypted otherwise), or None if an external kpub was provided.
        Raises RuntimeError if caller is not admin.
        """
        if not self._is_admin:
            raise RuntimeError("Only admin can add users.")

        h = storage.email_to_hash(email)
        if h in self._users:
            raise RuntimeError(f"User already exists: {email}")

        kpriv_bytes = None
        if kpub_user is None:
            kpriv_user = ec.generate_private_key(ec.SECP256R1())
            kpub_user  = kpriv_user.public_key()
            if password:
                storage.save_user_key_file(h, kpriv_user, password)
            enc_algo = (serialization.BestAvailableEncryption(password)
                        if password else serialization.NoEncryption())
            kpriv_bytes = kpriv_user.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                enc_algo,
            )

        kpub_bytes = kpub_user.public_bytes(
            serialization.Encoding.X962,
            serialization.PublicFormat.UncompressedPoint,
        )
        self._users[h] = {
            "kpub_enc":        b64(kpub_bytes),
            "sym_key_cal_enc": ecies_encrypt(kpub_user, self._sym_key_cal),
            "email_enc":       sym_encrypt(self._sym_key_cal, email.encode()),
            "is_admin":        False,
        }
        self._save_and_sync()
        return kpriv_bytes

    def remove_user(self, user_hash_str: str) -> None:
        """Remove a user and rotate sym_key_cal (re-encrypts all entries).
        Raises RuntimeError if caller is not admin or tries to remove themselves."""
        if not self._is_admin:
            raise RuntimeError("Only admin can remove users.")
        if user_hash_str == self._user_hash:
            raise RuntimeError("Cannot remove your own account.")
        if user_hash_str not in self._users:
            raise RuntimeError("User not found.")

        del self._users[user_hash_str]

        # Rotate sym_key_cal so the removed user's copy is no longer valid
        new_key = os.urandom(32)

        new_entries = []
        for enc in self._entries_enc:
            try:
                data = decrypt_entry(enc, self._sym_key_cal)
                new_entries.append(encrypt_entry(data, new_key))
            except Exception:
                new_entries.append(enc)  # keep corrupted entries as-is

        # Re-encrypt sym_key_cal for all remaining users
        for h, u in self._users.items():
            kpub = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256R1(), b64d(u["kpub_enc"]))
            u["sym_key_cal_enc"] = ecies_encrypt(kpub, new_key)

        # Re-encrypt sync config with new key
        if self._sync_config_enc:
            try:
                sc_plain = sym_decrypt(self._sym_key_cal, self._sync_config_enc)
                self._sync_config_enc = sym_encrypt(new_key, sc_plain)
            except Exception:
                self._sync_config_enc = None

        self._sym_key_cal = new_key
        self._entries_enc = new_entries
        self._save_and_sync()
