#!/usr/bin/env python3

import calendar as _cal_mod
import json
import os
import threading
import uuid
from datetime import date as _date
from datetime import datetime
from datetime import timedelta as _timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

import storage
from crypto import (
    b64,
    b64d,
    decrypt_entry,
    ecies_encrypt,
    encrypt_entry,
    pem_to_public_key,
    sign_entries,
    sign_keys_fingerprint,
    sign_users,
    sym_decrypt,
    sym_encrypt,
    verify_entries,
    verify_users,
)

# Weekday codes: index matches Python's date.weekday() (0=Mon … 6=Sun)
_WD_CODES = ["MO", "DI", "MI", "DO", "FR", "SA", "SO"]


def _get_identifier_enc(user_entry: dict) -> dict:
    """Return the encrypted identifier field for current or legacy files."""
    if "identifier_enc" in user_entry:
        return user_entry["identifier_enc"]
    if "email_enc" in user_entry:
        return user_entry["email_enc"]
    raise KeyError("User entry is missing identifier data.")


def build_onboarding_text(identifier: str, sync_config: dict, fingerprint: str) -> str:
    """Return a standardized onboarding message for a user."""
    if not sync_config:
        raise RuntimeError("Sync configuration is not available.")
    return (
        "CalSec Onboarding\n\n"
        f"Identifier: {identifier}\n\n"
        "1. Install CalSec.\n"
        "2. Generate your local keypair.\n"
        "3. Send your public key and identifier to the admin.\n"
        "4. Wait until the admin confirms that your user has been added.\n"
        "5. Enter the following sync data in CalSec:\n\n"
        f"WebDAV URL: {sync_config['webdav_url']}\n"
        f"Username: {sync_config['auth_user']}\n"
        f"App Password: {sync_config['password']}\n\n"
        "6. On the first calendar download, compare this signing fingerprint exactly:\n\n"
        f"{fingerprint}\n\n"
        "If the fingerprint does not match exactly, stop and contact the admin.\n"
        "Never share your private key."
    )


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

    def __init__(self, sym_key_cal: bytes,
                 kpriv_admin_sign=None,
                 kpriv_edit_sign=None,
                 role: str = "viewer",
                 user_hash: str | None = None):
        self._sym_key_cal      = sym_key_cal
        self._kpriv_admin_sign = kpriv_admin_sign  # None unless admin
        self._kpriv_edit_sign  = kpriv_edit_sign   # None unless admin or editor
        self._role             = role
        self._is_admin         = role == "admin"
        self._user_hash        = user_hash

        self.buffer   = []
        self.unsigned = False
        self._reload()

    def _reload(self):
        raw = storage.load_file_raw()
        self.version          = raw.get("version", 2)
        self._sign_keys       = raw.get("sign_keys", {})
        self._users           = raw.get("users", {})
        self._entries_enc     = raw.get("entries", [])
        self._sync_config_enc = raw.get("sync_config")
        self._sig_users       = raw.get("sig_users")
        self._sig_entries     = raw.get("sig_entries")

        self.unsigned = False

        if self._sign_keys:
            kpub_admin_sign = pem_to_public_key(self._sign_keys["admin"])
            kpub_edit_sign  = pem_to_public_key(self._sign_keys["edit"])

            if self._sig_users is None:
                self.unsigned = True
            elif not verify_users(self._sign_keys, self._users,
                                   self._sync_config_enc,
                                   self._sig_users, kpub_admin_sign):
                raise RuntimeError(
                    "Users section signature is invalid. "
                    "File may have been tampered with.")

            if self._sig_entries is None:
                self.unsigned = True
            elif not verify_entries(self._entries_enc,
                                     self._sig_entries, kpub_edit_sign):
                raise RuntimeError(
                    "Entries section signature is invalid. "
                    "File may have been tampered with.")
        else:
            # v3 or older — no split sign_keys present
            self.unsigned = True

        if self._sync_config_enc is None:
            self._sync_config = None
        else:
            try:
                self._sync_config = json.loads(
                    sym_decrypt(self._sym_key_cal, self._sync_config_enc))
            except Exception as exc:
                raise RuntimeError(
                    "Sync configuration could not be decrypted.") from exc

        self.buffer = []
        failed_entries = []
        for enc in self._entries_enc:
            try:
                dec = decrypt_entry(enc, self._sym_key_cal)
                self.buffer.append({
                    "id":        dec["id"],
                    "timestamp": dec["timestamp"],
                    "data":      dec,
                })
            except Exception as exc:
                failed_entries.append(enc.get("id", "<unknown>"))
                if len(failed_entries) == 1:
                    first_error = exc
        if failed_entries:
            preview = ", ".join(failed_entries[:3])
            if len(failed_entries) > 3:
                preview += ", ..."
            raise RuntimeError(
                f"Failed to decrypt {len(failed_entries)} entr"
                f"{'y' if len(failed_entries) == 1 else 'ies'}: {preview}"
            ) from first_error
        self.buffer.sort(key=lambda x: x["timestamp"])

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def role(self) -> str:
        return self._role

    @property
    def is_admin(self) -> bool:
        return self._is_admin

    @property
    def can_edit(self) -> bool:
        return self._kpriv_edit_sign is not None

    @property
    def fingerprint(self) -> str:
        return sign_keys_fingerprint(self._sign_keys)

    @property
    def sync_config(self):
        return self._sync_config

    # ── Internal save ─────────────────────────────────────────────────────────

    def _save_and_sync(self, changed: str = "entries", on_sync_done=None):
        """Sign the changed section(s), save, reload, then push to Nextcloud.

        changed: "entries" — re-signs entries only (requires kpriv_edit_sign)
                 "users"   — re-signs users+sync_config block (requires kpriv_admin_sign)
                 "both"    — re-signs both (requires both keys; used on key rotation)
        """
        if changed in ("entries", "both"):
            if self._kpriv_edit_sign is None:
                raise RuntimeError("Only editors and admins can save entry changes.")
            sig_entries = sign_entries(self._entries_enc, self._kpriv_edit_sign)
        else:
            sig_entries = self._sig_entries  # unchanged

        if changed in ("users", "both"):
            if self._kpriv_admin_sign is None:
                raise RuntimeError("Only admins can save user changes.")
            sig_users = sign_users(
                self._sign_keys, self._users, self._sync_config_enc,
                self._kpriv_admin_sign)
        else:
            sig_users = self._sig_users  # unchanged

        new_version = self.version + 1
        storage.save_file({
            "version":     new_version,
            "sign_keys":   self._sign_keys,
            "users":       self._users,
            "sync_config": self._sync_config_enc,
            "entries":     self._entries_enc,
            "sig_users":   sig_users,
            "sig_entries": sig_entries,
        })
        self._reload()

        config = self.sync_config
        if config is not None:
            def _run():
                try:
                    from sync import sync_push
                    msg = sync_push(config)
                except Exception as exc:
                    msg = f"Sync error: {exc}"
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
                except Exception as exc:
                    raise RuntimeError(
                        f"Entry {data.get('id', '<unknown>')} contains an invalid date."
                    ) from exc
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
                        except Exception as exc:
                            raise RuntimeError(
                                f"Entry {data.get('id', '<unknown>')} contains an invalid time."
                            ) from exc
                    instance["timestamp"]  = dt.timestamp()
                    instance["is_recurring"] = True
                    instance["_row_iid"] = (
                        f"{data['id']}_inst_{date_str.replace('.', '')}")
                    result.append(instance)

        result.sort(key=lambda x: x.get("timestamp", 0))
        return result

    # ── Entry mutations (editor + admin) ──────────────────────────────────────

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
        self._save_and_sync(changed="entries", on_sync_done=on_sync_done)

    def update_entry(self, entry_id: str, title: str, date_str: str,
                     time_str: str, comments: list[str],
                     color: str | None = None, recurrence: dict | None = None,
                     on_sync_done=None):
        existing = next((e["data"] for e in self.buffer if e["id"] == entry_id), None)
        if existing is not None:
            if (existing.get("title") == title
                    and existing.get("date") == date_str
                    and existing.get("time") == time_str
                    and existing.get("comments", []) == comments
                    and existing.get("color") == color
                    and existing.get("recurrence") == recurrence):
                return  # nothing changed — skip save and sync

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
        self._save_and_sync(changed="entries", on_sync_done=on_sync_done)

    def delete_entries(self, ids: list[str], on_sync_done=None) -> bool:
        original_len = len(self._entries_enc)
        self._entries_enc = [e for e in self._entries_enc if e["id"] not in ids]
        if len(self._entries_enc) == original_len:
            return False
        self._save_and_sync(changed="entries", on_sync_done=on_sync_done)
        return True

    # ── Sync config (admin only) ──────────────────────────────────────────────

    def update_sync_config(self, sync_data: dict | None, on_sync_done=None):
        if not self._is_admin:
            raise RuntimeError("Only admin can change sync configuration.")
        if sync_data is None:
            self._sync_config_enc = None
        else:
            self._sync_config_enc = sym_encrypt(
                self._sym_key_cal, json.dumps(sync_data).encode())
        self._save_and_sync(changed="users", on_sync_done=on_sync_done)

    # ── Sync pull (all users) ─────────────────────────────────────────────────

    def sync_pull(self, on_done=None) -> None:
        """Download a newer calendar.json from Nextcloud in the background."""
        config = self.sync_config
        if config is None:
            if on_done:
                on_done("Kein Sync konfiguriert.")
            return

        local_sign_keys = self._sign_keys

        def _run():
            from sync import sync_pull as _pull
            data, msg = _pull(config)
            if data is None:
                if on_done:
                    on_done(msg)
                return

            # Reject files whose signing infrastructure differs from ours
            remote_sign_keys = data.get("sign_keys", {})
            if remote_sign_keys != local_sign_keys:
                if on_done:
                    on_done("Sync error: Signierschlüssel der heruntergeladenen "
                            "Datei stimmen nicht überein.")
                return

            # Verify both signatures of the downloaded file
            sig_users   = data.get("sig_users")
            sig_entries = data.get("sig_entries")

            if not sig_users or not sig_entries or not remote_sign_keys:
                if on_done:
                    on_done("Sync error: Signaturen der heruntergeladenen Datei fehlen.")
                return

            kpub_admin_sign = pem_to_public_key(remote_sign_keys["admin"])
            kpub_edit_sign  = pem_to_public_key(remote_sign_keys["edit"])

            if not verify_users(remote_sign_keys, data.get("users", {}),
                                 data.get("sync_config"),
                                 sig_users, kpub_admin_sign):
                if on_done:
                    on_done("Sync error: Benutzersignatur der heruntergeladenen "
                            "Datei ungültig.")
                return

            if not verify_entries(data.get("entries", []),
                                   sig_entries, kpub_edit_sign):
                if on_done:
                    on_done("Sync error: Eintrags-Signatur der heruntergeladenen "
                            "Datei ungültig.")
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
        """Return [{hash, identifier, role}] for all registered users."""
        result = []
        for h, u in self._users.items():
            try:
                identifier = sym_decrypt(
                    self._sym_key_cal, _get_identifier_enc(u)).decode()
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to decrypt identifier for user {h}.") from exc
            result.append({
                "hash":       h,
                "identifier": identifier,
                "role":       u.get("role", "viewer"),
            })
        return result

    def add_user(self, identifier: str, kpub_user=None,
                 password: bytes | None = None,
                 role: str = "viewer",
                 save_locally: bool = True) -> bytes | None:
        """Add a user to the calendar.

        If *kpub_user* is None a new SECP256R1 keypair is generated.
        If *save_locally* is True the private key is saved to KEYS_DIR.
        Returns the private key PEM bytes, or None if an external kpub was provided.
        Raises RuntimeError if caller is not admin.
        """
        if not self._is_admin:
            raise RuntimeError("Only admin can add users.")

        identifier = storage.normalize_identifier(identifier)
        h = storage.identifier_to_hash(identifier)
        if h in self._users:
            raise RuntimeError(f"User already exists: {identifier}")

        kpriv_bytes = None
        if kpub_user is None:
            kpriv_user = ec.generate_private_key(ec.SECP256R1())
            kpub_user  = kpriv_user.public_key()
            if save_locally:
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
        user_entry = {
            "kpub_enc":        b64(kpub_bytes),
            "sym_key_cal_enc": ecies_encrypt(kpub_user, self._sym_key_cal),
            "identifier_enc":  sym_encrypt(self._sym_key_cal, identifier.encode()),
            "role":            role,
        }

        # Distribute sign keys based on role
        if role in ("admin", "editor"):
            if self._kpriv_edit_sign is None:
                raise RuntimeError("Edit sign key unavailable — cannot create editor/admin.")
            edit_sign_key_pem = self._kpriv_edit_sign.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            user_entry["edit_sign_key_enc"] = ecies_encrypt(kpub_user, edit_sign_key_pem)

        if role == "admin":
            if self._kpriv_admin_sign is None:
                raise RuntimeError("Admin sign key unavailable — cannot create admin.")
            admin_sign_key_pem = self._kpriv_admin_sign.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
            user_entry["admin_sign_key_enc"] = ecies_encrypt(kpub_user, admin_sign_key_pem)

        self._users[h] = user_entry
        self._save_and_sync(changed="users")
        return kpriv_bytes

    def change_user_role(self, user_hash: str, new_role: str) -> None:
        """Change the role of an existing user.

        Adds or removes the encrypted sign keys stored in the user entry as
        required by the new role:
          viewer  → no sign keys
          editor  → edit_sign_key_enc only
          admin   → edit_sign_key_enc + admin_sign_key_enc

        Raises RuntimeError if caller is not admin or tries to change their own role.
        """
        if not self._is_admin:
            raise RuntimeError("Only admin can change user roles.")
        if user_hash == self._user_hash:
            raise RuntimeError("Cannot change your own role.")
        if user_hash not in self._users:
            raise RuntimeError("User not found.")

        u = self._users[user_hash]
        if u.get("role") == new_role:
            return  # nothing to do

        kpub = ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), b64d(u["kpub_enc"]))

        # ── edit_sign_key_enc ─────────────────────────────────────────────────
        if new_role in ("admin", "editor"):
            if "edit_sign_key_enc" not in u:
                if self._kpriv_edit_sign is None:
                    raise RuntimeError(
                        "Edit sign key unavailable — cannot promote to editor/admin.")
                edit_sign_key_pem = self._kpriv_edit_sign.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
                u["edit_sign_key_enc"] = ecies_encrypt(kpub, edit_sign_key_pem)
        else:  # viewer
            u.pop("edit_sign_key_enc", None)

        # ── admin_sign_key_enc ────────────────────────────────────────────────
        if new_role == "admin":
            if "admin_sign_key_enc" not in u:
                if self._kpriv_admin_sign is None:
                    raise RuntimeError(
                        "Admin sign key unavailable — cannot promote to admin.")
                admin_sign_key_pem = self._kpriv_admin_sign.private_bytes(
                    serialization.Encoding.PEM,
                    serialization.PrivateFormat.PKCS8,
                    serialization.NoEncryption(),
                )
                u["admin_sign_key_enc"] = ecies_encrypt(kpub, admin_sign_key_pem)
        else:
            u.pop("admin_sign_key_enc", None)

        u["role"] = new_role
        self._save_and_sync(changed="users")

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
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to decrypt entry during key rotation: {enc.get('id', '<unknown>')}"
                ) from exc

        # Re-encrypt sym_key_cal and identifier_enc for all remaining users
        for h, u in self._users.items():
            kpub = ec.EllipticCurvePublicKey.from_encoded_point(
                ec.SECP256R1(), b64d(u["kpub_enc"]))
            u["sym_key_cal_enc"] = ecies_encrypt(kpub, new_key)
            try:
                identifier_plain = sym_decrypt(
                    self._sym_key_cal, _get_identifier_enc(u))
                u["identifier_enc"] = sym_encrypt(new_key, identifier_plain)
                u.pop("email_enc", None)
            except Exception as exc:
                raise RuntimeError(
                    f"Failed to re-encrypt identifier for user {h}.") from exc

        # Re-encrypt sync config with new key
        if self._sync_config_enc:
            try:
                sc_plain = sym_decrypt(self._sym_key_cal, self._sync_config_enc)
                self._sync_config_enc = sym_encrypt(new_key, sc_plain)
            except Exception as exc:
                raise RuntimeError(
                    "Failed to re-encrypt sync configuration during key rotation."
                ) from exc

        self._sym_key_cal = new_key
        self._entries_enc = new_entries
        # Both sections changed: users (user removed) + entries (re-encrypted)
        self._save_and_sync(changed="both")
