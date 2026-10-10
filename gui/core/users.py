"""User management, signing key distribution and sync configuration."""

import json
import os

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
    sym_decrypt,
    sym_encrypt,
)


def _get_identifier_enc(user_entry: dict) -> dict:
    """Return the encrypted identifier field."""
    return user_entry["identifier_enc"]



class UsersMixin:
    """Admin-only changes to users, roles, signing keys and sync config."""

    # ── Signing keys ──────────────────────────────────────────────────────────

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

    # ── Users (admin only) ────────────────────────────────────────────────────

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

