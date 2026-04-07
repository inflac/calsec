#!/usr/bin/env python3

import hashlib
import json
import os
import sys
import tempfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


KEYS_DIR  = os.path.join(BASE_DIR, "keys")
DATA_FILE = os.path.join(BASE_DIR, "calendar.json")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def normalize_identifier(identifier: str) -> str:
    """Canonicalize a user identifier for storage and hashing."""
    return identifier.strip()


def identifier_to_hash(identifier: str) -> str:
    """First 16 bytes of sha256(identifier) as 32 hex chars."""
    normalized = normalize_identifier(identifier)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:32]


def email_to_hash(email: str) -> str:
    """Backward-compatible alias for identifier_to_hash()."""
    return identifier_to_hash(email)


# ---------------------------------------------------------------------------
# State checks
# ---------------------------------------------------------------------------

def is_provisioned() -> bool:
    raw = load_file_raw()
    return bool(raw.get("users"))


def find_user_key_hashes() -> list[str]:
    """Return sha256 hex strings for all user key files found in KEYS_DIR."""
    if not os.path.isdir(KEYS_DIR):
        return []
    return [
        name[:-4] for name in os.listdir(KEYS_DIR)
        if name.endswith(".pem")
    ]


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def load_file_raw() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RuntimeError("Failed to read calendar file.") from exc


def _atomic_write_bytes(path: str, data: bytes, mode: int | None = None) -> None:
    directory = os.path.dirname(path) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        if mode is not None:
            os.chmod(tmp_path, mode)
        os.replace(tmp_path, path)
        if mode is not None:
            os.chmod(path, mode)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def save_file(data: dict) -> None:
    try:
        payload = json.dumps(data, indent=2).encode("utf-8")
        _atomic_write_bytes(DATA_FILE, payload)
    except (OSError, TypeError) as exc:
        raise RuntimeError("Failed to write calendar file.") from exc


# ---------------------------------------------------------------------------
# Key I/O
# ---------------------------------------------------------------------------

def _write_private_key(path: str, kpriv, password: bytes | None) -> None:
    enc_algo = (serialization.BestAvailableEncryption(password)
                if password else serialization.NoEncryption())
    pem = kpriv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=enc_algo,
    )
    _atomic_write_bytes(path, pem, mode=0o600)


def load_user_private_key(user_hash_str: str, password: bytes | None):
    path = os.path.join(KEYS_DIR, f"{user_hash_str}.pem")
    if not os.path.exists(path):
        raise FileNotFoundError("User key not found.")
    try:
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=password or None)
    except (OSError, ValueError, TypeError, UnicodeDecodeError) as exc:
        raise ValueError("Invalid password or corrupted user key.") from exc


def save_user_key_file(user_hash_str: str, kpriv, password: bytes | None) -> None:
    _write_private_key(os.path.join(KEYS_DIR, f"{user_hash_str}.pem"), kpriv, password)


# ---------------------------------------------------------------------------
# Provisioning (first-time admin setup)
# ---------------------------------------------------------------------------

def provision(admin_identifier: str, admin_password: bytes,
              sync_data: dict | None) -> None:
    """Generate two signing keypairs + admin encryption keypair, write calendar.json v4.

    Two sign keys with separate authority:
      kpriv_admin_sign — signs the users+sync_config block; stored ECIES-encrypted for admins only.
      kpriv_edit_sign  — signs entries; stored ECIES-encrypted for admins+editors.
    Both public keys are embedded in sign_keys in calendar.json.
    """
    from crypto import b64, ecies_encrypt, sym_encrypt, sign_users, sign_entries

    os.makedirs(KEYS_DIR, exist_ok=True)

    # Admin sign keypair — controls user management
    kpriv_admin_sign = ec.generate_private_key(ec.SECP256R1())
    admin_sign_key_pem = kpriv_admin_sign.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    # Edit sign keypair — controls entries
    kpriv_edit_sign = ec.generate_private_key(ec.SECP256R1())
    edit_sign_key_pem = kpriv_edit_sign.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )

    # Public keys embedded in the file for verification by all users
    sign_keys = {
        "admin": kpriv_admin_sign.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode(),
        "edit": kpriv_edit_sign.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode(),
    }

    # Admin encryption keypair (used to derive sym_key_cal via ECIES)
    kpriv_admin = ec.generate_private_key(ec.SECP256R1())
    kpub_admin  = kpriv_admin.public_key()
    admin_identifier = normalize_identifier(admin_identifier)
    h = identifier_to_hash(admin_identifier)
    save_user_key_file(h, kpriv_admin, admin_password)

    # Calendar symmetric key
    sym_key_cal = os.urandom(32)

    kpub_admin_bytes = kpub_admin.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    admin_entry = {
        "kpub_enc":           b64(kpub_admin_bytes),
        "sym_key_cal_enc":    ecies_encrypt(kpub_admin, sym_key_cal),
        "identifier_enc":     sym_encrypt(sym_key_cal, admin_identifier.encode()),
        "role":               "admin",
        "admin_sign_key_enc": ecies_encrypt(kpub_admin, admin_sign_key_pem),
        "edit_sign_key_enc":  ecies_encrypt(kpub_admin, edit_sign_key_pem),
    }

    sync_enc = None
    if sync_data:
        sync_enc = sym_encrypt(sym_key_cal, json.dumps(sync_data).encode())

    users   = {h: admin_entry}
    entries = []
    version = 4

    sig_users   = sign_users(sign_keys, users, sync_enc, kpriv_admin_sign)
    sig_entries = sign_entries(entries, kpriv_edit_sign)

    save_file({
        "version":     version,
        "sign_keys":   sign_keys,
        "users":       users,
        "sync_config": sync_enc,
        "entries":     entries,
        "sig_users":   sig_users,
        "sig_entries": sig_entries,
    })
