#!/usr/bin/env python3

import calendar as _cal_mod
import copy
import json
import os
import threading
import uuid
from datetime import date as _date
from datetime import datetime
from datetime import timedelta as _timedelta

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

import i18n
import storage
from crypto import (
    b64,
    b64d,
    decrypt_entry,
    ecies_encrypt,
    encrypt_entry,
    format_fingerprint,
    normalize_fingerprint,
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
    """Return the encrypted identifier field."""
    return user_entry["identifier_enc"]


def build_onboarding_text(identifier: str, sync_config: dict, fingerprint: str) -> str:
    """Return a standardized onboarding message for a user."""
    if not sync_config:
        raise RuntimeError(i18n._("app_err_sync_config_unavailable"))
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

    # How often an upload is retried when others keep changing the remote file.
    _MAX_SYNC_CONFLICTS = 5

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

        # _lock guards the in-memory and local file state. _sync_lock makes
        # sure only one download/upload sequence talks to the server at a time.
        self._lock      = threading.RLock()
        self._sync_lock = threading.Lock()
        # Local changes not yet on the server, as re-applicable operations.
        self._pending: list = []

        self.buffer   = []
        self._reload()
        # Last state known to be on the server; pending ops build on top of it.
        self._base = self._snapshot()

    def _reload(self):
        raw = storage.load_file_raw()
        self.version_users    = raw["version_users"]
        self.version_entries  = raw["version_entries"]
        self.version          = max(self.version_users, self.version_entries)
        self._sign_keys       = raw.get("sign_keys", {})
        self._users           = raw.get("users", {})
        self._entries_enc     = raw.get("entries", [])
        self._sync_config_enc = raw.get("sync_config")
        self._sig_users       = raw.get("sig_users")
        self._sig_entries     = raw.get("sig_entries")

        if not self._sign_keys:
            raise RuntimeError(i18n._("app_err_missing_sign_keys"))
        if self._sig_users is None or self._sig_entries is None:
            raise RuntimeError(i18n._("app_err_missing_signatures"))

        kpub_admin_sign = pem_to_public_key(self._sign_keys["admin"])
        kpub_edit_sign  = pem_to_public_key(self._sign_keys["edit"])

        if not verify_users(self.version_users, self._sign_keys, self._users,
                             self._sync_config_enc,
                             self._sig_users, kpub_admin_sign):
            raise RuntimeError(i18n._("app_err_users_sig_invalid"))

        if not verify_entries(self.version_entries, self._entries_enc,
                               self._sig_entries, kpub_edit_sign):
            raise RuntimeError(i18n._("app_err_entries_sig_invalid"))

        if self._sync_config_enc is None:
            self._sync_config = None
        else:
            try:
                self._sync_config = json.loads(
                    sym_decrypt(self._sym_key_cal, self._sync_config_enc))
            except Exception as exc:
                raise RuntimeError(
                    i18n._("app_err_sync_config_decrypt")) from exc

        buffer = []
        failed_entries = []
        for enc in self._entries_enc:
            try:
                dec = decrypt_entry(enc, self._sym_key_cal)
                buffer.append({
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
                i18n._("app_err_decrypt_entries").format(
                    count=len(failed_entries), preview=preview)
            ) from first_error
        buffer.sort(key=lambda x: x["timestamp"])
        self.buffer = buffer

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

    def _private_key_pem(self, kpriv) -> bytes:
        if kpriv is None:
            raise RuntimeError(i18n._("app_err_signing_key_unavailable"))
        return kpriv.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )

    def _user_public_key(self, user_entry: dict):
        return ec.EllipticCurvePublicKey.from_encoded_point(
            ec.SECP256R1(), b64d(user_entry["kpub_enc"]))

    def _public_signing_key_pem(self, kpriv) -> str:
        return kpriv.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

    def _apply_signing_keys_for_role(self, user_entry: dict) -> None:
        role = user_entry.get("role", "viewer")
        kpub = self._user_public_key(user_entry)

        if role in ("admin", "editor"):
            user_entry["edit_sign_key_enc"] = ecies_encrypt(
                kpub, self._private_key_pem(self._kpriv_edit_sign))
        else:
            user_entry.pop("edit_sign_key_enc", None)

        if role == "admin":
            user_entry["admin_sign_key_enc"] = ecies_encrypt(
                kpub, self._private_key_pem(self._kpriv_admin_sign))
        else:
            user_entry.pop("admin_sign_key_enc", None)

    def _rotate_signing_keys(self, rotate_admin: bool = False,
                             rotate_edit: bool = False) -> None:
        if rotate_admin:
            self._kpriv_admin_sign = ec.generate_private_key(ec.SECP256R1())
            self._sign_keys["admin"] = self._public_signing_key_pem(
                self._kpriv_admin_sign)
        if rotate_edit:
            self._kpriv_edit_sign = ec.generate_private_key(ec.SECP256R1())
            self._sign_keys["edit"] = self._public_signing_key_pem(
                self._kpriv_edit_sign)

        if rotate_admin or rotate_edit:
            for user_entry in self._users.values():
                self._apply_signing_keys_for_role(user_entry)

    # ── Local state ───────────────────────────────────────────────────────────

    def _snapshot(self) -> dict:
        """Capture the signed file state plus the keys needed to read and sign it."""
        return {
            "version_users":    self.version_users,
            "version_entries":  self.version_entries,
            "sign_keys":        copy.deepcopy(self._sign_keys),
            "users":            copy.deepcopy(self._users),
            "entries":          list(self._entries_enc),
            "sync_config":      self._sync_config_enc,
            "sig_users":        self._sig_users,
            "sig_entries":      self._sig_entries,
            "sym_key_cal":      self._sym_key_cal,
            "kpriv_admin_sign": self._kpriv_admin_sign,
            "kpriv_edit_sign":  self._kpriv_edit_sign,
        }

    def _restore(self, snap: dict) -> None:
        self.version_users     = snap["version_users"]
        self.version_entries   = snap["version_entries"]
        self.version           = max(self.version_users, self.version_entries)
        self._sign_keys        = copy.deepcopy(snap["sign_keys"])
        self._users            = copy.deepcopy(snap["users"])
        self._entries_enc      = list(snap["entries"])
        self._sync_config_enc  = snap["sync_config"]
        self._sig_users        = snap["sig_users"]
        self._sig_entries      = snap["sig_entries"]
        self._sym_key_cal      = snap["sym_key_cal"]
        self._kpriv_admin_sign = snap["kpriv_admin_sign"]
        self._kpriv_edit_sign  = snap["kpriv_edit_sign"]

    def _raw_state(self) -> dict:
        return {
            "version":         max(self.version_users, self.version_entries),
            "version_users":   self.version_users,
            "version_entries": self.version_entries,
            "sign_keys":       self._sign_keys,
            "users":           self._users,
            "sync_config":     self._sync_config_enc,
            "entries":         self._entries_enc,
            "sig_users":       self._sig_users,
            "sig_entries":     self._sig_entries,
        }

    def _write_local(self, changed: str) -> None:
        """Sign the changed section(s), then save and reload the local file.

        changed: "entries" — re-signs entries only (requires kpriv_edit_sign)
                 "users"   — re-signs users+sync_config block (requires kpriv_admin_sign)
                 "both"    — re-signs both (requires both keys; used on key rotation)
        """
        if changed in ("entries", "both") and self._kpriv_edit_sign is None:
            raise RuntimeError(i18n._("app_err_only_editors_save"))
        if changed in ("users", "both") and self._kpriv_admin_sign is None:
            raise RuntimeError(i18n._("app_err_only_admins_save_users"))

        if changed in ("entries", "both"):
            self.version_entries += 1
            self._sig_entries = sign_entries(
                self.version_entries, self._entries_enc, self._kpriv_edit_sign)
        if changed in ("users", "both"):
            self.version_users += 1
            self._sig_users = sign_users(
                self.version_users, self._sign_keys, self._users,
                self._sync_config_enc, self._kpriv_admin_sign)

        storage.save_file(self._raw_state())
        self._reload()

    # ── Change + sync ─────────────────────────────────────────────────────────

    def _commit(self, op, on_sync_done=None) -> None:
        """Apply op locally, save, and upload without overwriting others' changes.

        op mutates the in-memory state and returns the changed section
        ("entries", "users" or "both"), or None if there is nothing to do.
        It must be safe to run again on a newer state: if someone else uploaded
        in the meantime, their file is loaded and all pending ops are re-applied.
        """
        with self._lock:
            snap = self._snapshot()
            written = False
            try:
                changed = op()
                if changed is None:
                    return
                written = True
                self._write_local(changed)
            except Exception:
                self._restore(snap)
                if written:
                    storage.save_file(self._raw_state())
                    self._reload()
                raise
            sync_enabled = self.sync_config is not None
            if sync_enabled:
                self._pending.append(op)
            else:
                self._base = self._snapshot()
        if sync_enabled:
            self._start_push(on_sync_done)

    def _start_push(self, on_sync_done=None) -> None:
        def _run():
            with self._sync_lock:
                try:
                    msg, is_error = self._push_pending()
                except Exception as exc:
                    msg, is_error = i18n._("sync_err_exception").format(exc=exc), True
            if on_sync_done:
                on_sync_done(msg, is_error)

        threading.Thread(target=_run, daemon=True).start()

    def _push_pending(self) -> tuple[str, bool]:
        """Upload pending local changes. The caller must hold _sync_lock.

        The remote file is downloaded first. If someone else changed it since
        our last sync, their version is loaded and the pending changes are
        re-applied on top. The upload only succeeds if the remote file still
        has the ETag we just read, so a change that lands in between is
        detected and handled the same way.
        """
        import sync as _sync

        merged = False
        dropped = 0
        conflicts = 0
        while True:
            with self._lock:
                if not self._pending:
                    return self._push_summary(i18n._("sync_pull_ok"), merged, dropped)
                config = self.sync_config
            if config is None:
                with self._lock:
                    self._pending.clear()
                    self._base = self._snapshot()
                return i18n._("sync_not_configured"), False

            remote = _sync.fetch(config)
            if remote.status == "error":
                return remote.msg, True

            with self._lock:
                if remote.status == "ok" and not self._matches_base(remote.data):
                    error, n_dropped = self._rebase_onto(remote.data)
                    if error:
                        return error, True
                    merged = True
                    dropped += n_dropped
                    if not self._pending:
                        return self._push_summary(i18n._("sync_pull_ok"), merged, dropped)
                body = json.dumps(self._raw_state(), indent=2).encode("utf-8")
                pushed = self._snapshot()
                n_pushed = len(self._pending)

            result = _sync.push(
                config, body,
                if_match=remote.etag if remote.status == "ok" else None,
                create_only=remote.status == "missing",
            )
            if result.status == "conflict":
                conflicts += 1
                if conflicts >= self._MAX_SYNC_CONFLICTS:
                    return i18n._("sync_err_conflict_unresolved"), True
                continue
            if result.status != "ok":
                return result.msg, True

            with self._lock:
                del self._pending[:n_pushed]
                self._base = pushed
                if not self._pending:
                    return self._push_summary(result.msg, merged, dropped)

    @staticmethod
    def _push_summary(msg: str, merged: bool, dropped: int) -> tuple[str, bool]:
        if merged:
            msg = i18n._("sync_merged")
        if dropped:
            return i18n._("sync_ops_dropped").format(msg=msg, count=dropped), True
        return msg, False

    def _matches_base(self, data: dict) -> bool:
        """True if data is the remote state our pending changes build on."""
        base = self._base
        return (data.get("version_users") == base["version_users"]
                and data.get("version_entries") == base["version_entries"]
                and data.get("sig_users") == base["sig_users"]
                and data.get("sig_entries") == base["sig_entries"])

    @staticmethod
    def _verify_remote(data: dict) -> str | None:
        """Verify both signatures of a downloaded file against its own keys.
        Returns an error message, or None if the file is consistently signed."""
        sign_keys = data.get("sign_keys") or {}
        sig_users = data.get("sig_users")
        sig_entries = data.get("sig_entries")
        if not sig_users or not sig_entries or not sign_keys:
            return i18n._("sync_err_missing_signatures")
        try:
            kpub_admin_sign = pem_to_public_key(sign_keys["admin"])
            kpub_edit_sign = pem_to_public_key(sign_keys["edit"])
        except Exception:
            return i18n._("sync_err_users_sig_invalid")
        if not verify_users(data.get("version_users"), sign_keys, data.get("users", {}),
                            data.get("sync_config"), sig_users, kpub_admin_sign):
            return i18n._("sync_err_users_sig_invalid")
        if not verify_entries(data.get("version_entries"), data.get("entries", []),
                              sig_entries, kpub_edit_sign):
            return i18n._("sync_err_entries_sig_invalid")
        return None

    def _rebase_onto(self, data: dict) -> tuple[str | None, int]:
        """Load a newer remote file and re-apply pending ops on top of it.

        The caller must hold _lock. Returns (error, dropped). On error the
        local state is left unchanged. dropped counts pending ops that no
        longer apply to the remote state.
        """
        error = self._verify_remote(data)
        if error:
            return error, 0
        # Only build on files signed with the keys we already trust. A key
        # change needs the trust prompt of a manual sync.
        if data.get("sign_keys") != self._base["sign_keys"]:
            return i18n._("sync_err_rebase_keys_changed"), 0

        local = self._snapshot()
        self._restore(self._base)
        try:
            storage.save_file(data)
            self._reload()
        except Exception:
            self._restore(local)
            storage.save_file(self._raw_state())
            self._reload()
            return i18n._("sync_err_rebase_failed"), 0
        self._base = self._snapshot()
        return None, self._reapply_pending()

    def _reapply_pending(self) -> int:
        changed = set()
        kept = []
        dropped = 0
        for op in self._pending:
            snap = self._snapshot()
            try:
                result = op()
            except Exception:
                self._restore(snap)
                dropped += 1
                continue
            if result is not None:
                changed.add(result)
                kept.append(op)
        self._pending[:] = kept
        if changed:
            self._write_local(
                "both" if "both" in changed or len(changed) > 1 else changed.pop())
        return dropped

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
                        i18n._("app_err_entry_invalid_date").format(
                            id=data.get("id", "<unknown>"))
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

    # ── Sync config (admin only) ──────────────────────────────────────────────

    def update_sync_config(self, sync_data: dict | None, on_sync_done=None):
        if not self._is_admin:
            raise RuntimeError(i18n._("app_err_only_admin_sync_config"))

        def op():
            if sync_data is None:
                self._sync_config_enc = None
            else:
                self._sync_config_enc = sym_encrypt(
                    self._sym_key_cal, json.dumps(sync_data).encode())
            return "users"

        self._commit(op, on_sync_done)

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
                    i18n._("app_err_decrypt_identifier").format(user=h)) from exc
            result.append({
                "hash":       h,
                "identifier": identifier,
                "role":       u.get("role", "viewer"),
            })
        return result

    # ── Sync pull (all users) ─────────────────────────────────────────────────

    def sync_pull(self, on_done=None, request_trust=None) -> None:
        """Download a newer calendar.json in the background.

        Local changes that are not uploaded yet are kept: they are re-applied
        on top of the downloaded state and uploaded.
        """
        config = self.sync_config
        if config is None:
            if on_done:
                on_done(i18n._("sync_not_configured"), False)
            return

        def _run():
            with self._sync_lock:
                try:
                    msg, is_error = self._pull(config, request_trust)
                except Exception as exc:
                    msg, is_error = i18n._("sync_err_exception").format(exc=exc), True
            if on_done:
                on_done(msg, is_error)

        threading.Thread(target=_run, daemon=True).start()

    def _pull(self, config, request_trust) -> tuple[str, bool]:
        """Download and apply the remote file. The caller must hold _sync_lock."""
        import sync as _sync

        with self._lock:
            has_pending = bool(self._pending)
        if has_pending:
            msg, is_error = self._push_pending()
            if msg != i18n._("sync_err_rebase_keys_changed"):
                return msg, is_error
            # The signing keys changed: fall through to the trust prompt. The
            # pending changes were signed with keys that are no longer valid.

        remote = _sync.fetch(config)
        if remote.status != "ok":
            return remote.msg, True
        data = remote.data

        error = self._verify_remote(data)
        if error:
            return error, True

        remote_sign_keys = data["sign_keys"]
        with self._lock:
            trusted_sign_keys = copy.deepcopy(self._base["sign_keys"])
        sign_keys_changed = remote_sign_keys != trusted_sign_keys
        if sign_keys_changed:
            if request_trust is None:
                return i18n._("sync_err_sign_keys_mismatch"), True
            remote_fingerprint = sign_keys_fingerprint(remote_sign_keys)
            expected = request_trust(remote_fingerprint)
            if expected is None:
                return i18n._("sync_err_sign_keys_not_confirmed"), True
            if normalize_fingerprint(expected) != remote_fingerprint:
                return i18n._("sync_err_fingerprint_mismatch").format(
                    fingerprint=format_fingerprint(remote_fingerprint)), True

        with self._lock:
            if self._pending and not sign_keys_changed:
                # Changes made while this download was running.
                if self._matches_base(data):
                    return remote.msg, False
                error, dropped = self._rebase_onto(data)
                if error:
                    return error, True
                return self._push_summary(remote.msg, False, dropped)

            dropped_pending = bool(self._pending)
            if (not dropped_pending
                    and data["version_users"] <= self.version_users
                    and data["version_entries"] <= self.version_entries):
                return i18n._("sync_up_to_date"), False

            local = self._snapshot()
            if dropped_pending:
                self._pending.clear()
                self._restore(self._base)
            try:
                storage.save_file(data)
                self._reload()
            except Exception:
                self._restore(local)
                storage.save_file(self._raw_state())
                self._reload()
                return i18n._("sync_err_load_failed"), True
            self._base = self._snapshot()

        msg = remote.msg
        if sign_keys_changed:
            msg = i18n._("sync_sign_keys_accepted").format(msg=msg)
        if dropped_pending:
            return i18n._("sync_pending_dropped").format(msg=msg), True
        return msg, False

    def add_user(self, identifier: str, kpub_user=None,
                 password: bytes | None = None,
                 role: str = "viewer",
                 save_locally: bool = True) -> bytes | None:
        """Add a user to the calendar."""
        if not self._is_admin:
            raise RuntimeError(i18n._("app_err_only_admin_add_users"))

        identifier = storage.normalize_identifier(identifier)
        h = storage.identifier_to_hash(identifier)
        if h in self._users:
            raise RuntimeError(
                i18n._("app_err_user_exists").format(identifier=identifier))

        kpriv_bytes = None
        if kpub_user is None:
            kpriv_user = ec.generate_private_key(ec.SECP256R1())
            kpub_user = kpriv_user.public_key()
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

        def op():
            if h in self._users:
                raise RuntimeError(
                    i18n._("app_err_user_exists").format(identifier=identifier))
            user_entry = {
                "kpub_enc": b64(kpub_bytes),
                "sym_key_cal_enc": ecies_encrypt(kpub_user, self._sym_key_cal),
                "identifier_enc": sym_encrypt(self._sym_key_cal, identifier.encode()),
                "role": role,
            }
            self._apply_signing_keys_for_role(user_entry)
            self._users[h] = user_entry
            return "users"

        self._commit(op)
        return kpriv_bytes

    def change_user_role(self, user_hash: str, new_role: str) -> None:
        """Change the role of an existing user and rotate compromised sign keys."""
        if not self._is_admin:
            raise RuntimeError(i18n._("app_err_only_admin_change_roles"))
        if user_hash == self._user_hash:
            raise RuntimeError(i18n._("app_err_cannot_change_own_role"))
        if user_hash not in self._users:
            raise RuntimeError(i18n._("app_err_user_not_found"))

        def op():
            user_entry = self._users.get(user_hash)
            if user_entry is None:
                raise RuntimeError(i18n._("app_err_user_not_found"))
            old_role = user_entry.get("role", "viewer")
            if old_role == new_role:
                return None

            user_entry["role"] = new_role

            rotate_admin = old_role == "admin" and new_role != "admin"
            rotate_edit = (old_role in ("admin", "editor")
                           and new_role not in ("admin", "editor"))

            if rotate_admin or rotate_edit:
                self._rotate_signing_keys(rotate_admin=rotate_admin, rotate_edit=rotate_edit)
                return "both" if rotate_edit else "users"
            self._apply_signing_keys_for_role(user_entry)
            return "users"

        self._commit(op)

    def remove_user(self, user_hash_str: str) -> None:
        """Remove a user, rotate sym_key_cal, and revoke any distributed sign keys."""
        if not self._is_admin:
            raise RuntimeError(i18n._("app_err_only_admin_remove_users"))
        if user_hash_str == self._user_hash:
            raise RuntimeError(i18n._("app_err_cannot_remove_self"))
        if user_hash_str not in self._users:
            raise RuntimeError(i18n._("app_err_user_not_found"))

        def op():
            if user_hash_str not in self._users:
                raise RuntimeError(i18n._("app_err_user_not_found"))
            removed_role = self._users[user_hash_str].get("role", "viewer")
            del self._users[user_hash_str]

            new_key = os.urandom(32)
            new_entries = []
            for enc in self._entries_enc:
                try:
                    data = decrypt_entry(enc, self._sym_key_cal)
                    new_entries.append(encrypt_entry(data, new_key))
                except Exception as exc:
                    raise RuntimeError(
                        i18n._("app_err_rotation_entry").format(
                            id=enc.get("id", "<unknown>"))
                    ) from exc

            for h, user_entry in self._users.items():
                kpub = self._user_public_key(user_entry)
                user_entry["sym_key_cal_enc"] = ecies_encrypt(kpub, new_key)
                try:
                    identifier_plain = sym_decrypt(
                        self._sym_key_cal, _get_identifier_enc(user_entry))
                    user_entry["identifier_enc"] = sym_encrypt(new_key, identifier_plain)
                except Exception as exc:
                    raise RuntimeError(
                        i18n._("app_err_rotation_identifier").format(user=h)) from exc

            if self._sync_config_enc:
                try:
                    sc_plain = sym_decrypt(self._sym_key_cal, self._sync_config_enc)
                    self._sync_config_enc = sym_encrypt(new_key, sc_plain)
                except Exception as exc:
                    raise RuntimeError(
                        i18n._("app_err_rotation_sync_config")) from exc

            self._sym_key_cal = new_key
            self._entries_enc = new_entries
            self._rotate_signing_keys(
                rotate_admin=(removed_role == "admin"),
                rotate_edit=(removed_role in ("admin", "editor")),
            )
            return "both"

        self._commit(op)
