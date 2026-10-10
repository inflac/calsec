"""Loading, verifying, snapshotting and saving the local calendar file."""

import copy
import json

import i18n
import storage
from crypto import (
    decrypt_entry,
    pem_to_public_key,
    sign_entries,
    sign_users,
    sym_decrypt,
    verify_entries,
    verify_users,
)


class StateMixin:
    """Owns the signed file state of CalendarApp."""

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

        changed: "entries" - re-signs entries only (requires kpriv_edit_sign)
                 "users"   - re-signs users+sync_config block (requires kpriv_admin_sign)
                 "both"    - re-signs both (requires both keys; used on key rotation)
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

