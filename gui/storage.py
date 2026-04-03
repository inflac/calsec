#!/usr/bin/env python3

import hashlib
import json
import os
import sys

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

print(f"Using base directory: {BASE_DIR}", file=sys.stderr)

KEYS_DIR         = os.path.join(BASE_DIR, "keys")
DATA_FILE        = os.path.join(BASE_DIR, "calendar.json")
KEY_SIGN_PRIVATE = os.path.join(KEYS_DIR, "sign_private.pem")
KEY_SIGN_PUBLIC  = os.path.join(BASE_DIR, "calsec_public.pem")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def email_to_hash(email: str) -> str:
    """First 16 hex chars of sha256(localpart) — user identifier and key file name."""
    localpart = email.split("@")[0].lower()
    return hashlib.sha256(localpart.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# State checks
# ---------------------------------------------------------------------------

def is_provisioned() -> bool:
    raw = load_file_raw()
    return bool(raw.get("users"))


def sign_key_exists() -> bool:
    return os.path.exists(KEY_SIGN_PRIVATE)


def find_user_key_hashes() -> list[str]:
    """Return sha256 hex strings for all user key files found in KEYS_DIR."""
    if not os.path.isdir(KEYS_DIR):
        return []
    return [
        name[:-4] for name in os.listdir(KEYS_DIR)
        if name.endswith(".pem") and name != "sign_private.pem"
    ]


# ---------------------------------------------------------------------------
# File I/O
# ---------------------------------------------------------------------------

def load_file_raw() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE) as f:
            return json.load(f)
    except Exception:
        raise RuntimeError("Failed to read calendar file.")


def save_file(data: dict) -> None:
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except Exception:
        raise RuntimeError("Failed to write calendar file.")


# ---------------------------------------------------------------------------
# Key I/O
# ---------------------------------------------------------------------------

def _write_private_key(path: str, kpriv, password: bytes) -> None:
    pem = kpriv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(password),
    )
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(pem)
    os.chmod(path, 0o600)


def load_sign_private_key(password: bytes):
    if not os.path.exists(KEY_SIGN_PRIVATE):
        raise FileNotFoundError("Signing key not found.")
    try:
        with open(KEY_SIGN_PRIVATE, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=password)
    except Exception:
        raise ValueError("Invalid password or corrupted signing key.")


def load_sign_public_key():
    if not os.path.exists(KEY_SIGN_PUBLIC):
        raise FileNotFoundError("Signing public key not found.")
    try:
        with open(KEY_SIGN_PUBLIC, "rb") as f:
            return serialization.load_pem_public_key(f.read())
    except Exception:
        raise RuntimeError("Failed to load signing public key.")


def load_user_private_key(user_hash_str: str, password: bytes):
    path = os.path.join(KEYS_DIR, f"{user_hash_str}.pem")
    if not os.path.exists(path):
        raise FileNotFoundError("User key not found.")
    try:
        with open(path, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=password)
    except Exception:
        raise ValueError("Invalid password or corrupted user key.")


def save_user_key_file(user_hash_str: str, kpriv, password: bytes) -> None:
    _write_private_key(os.path.join(KEYS_DIR, f"{user_hash_str}.pem"), kpriv, password)


# ---------------------------------------------------------------------------
# Provisioning (first-time admin setup)
# ---------------------------------------------------------------------------

def provision(admin_email: str, admin_password: bytes,
              sync_data: dict | None) -> None:
    """Generate signing + admin encryption keypairs, write calendar.json v2."""
    from crypto import b64, ecies_encrypt, sym_encrypt, sign_file as _sign_file

    os.makedirs(KEYS_DIR, exist_ok=True)

    # Signing keypair (admin only — used to sign calendar.json)
    kpriv_sign = ec.generate_private_key(ec.SECP256R1())
    _write_private_key(KEY_SIGN_PRIVATE, kpriv_sign, admin_password)
    with open(KEY_SIGN_PUBLIC, "wb") as f:
        f.write(kpriv_sign.public_key().public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        ))

    # Admin encryption keypair (used to derive sym_key_cal via ECIES)
    kpriv_admin = ec.generate_private_key(ec.SECP256R1())
    kpub_admin  = kpriv_admin.public_key()
    h = email_to_hash(admin_email)
    save_user_key_file(h, kpriv_admin, admin_password)

    # Calendar symmetric key — all entries are encrypted with per-entry keys
    # wrapped by this key; each user gets an ECIES-encrypted copy of it.
    sym_key_cal = os.urandom(32)

    kpub_admin_bytes = kpub_admin.public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    admin_entry = {
        "kpub_enc":        b64(kpub_admin_bytes),
        "sym_key_cal_enc": ecies_encrypt(kpub_admin, sym_key_cal),
        "email_enc":       sym_encrypt(sym_key_cal, admin_email.encode()),
        "is_admin":        True,
    }

    sync_enc = None
    if sync_data:
        sync_enc = sym_encrypt(sym_key_cal, json.dumps(sync_data).encode())

    users   = {h: admin_entry}
    entries = []
    version = 2
    sig = _sign_file(version, users, entries, sync_enc, kpriv_sign)

    save_file({
        "version":     version,
        "users":       users,
        "sync_config": sync_enc,
        "entries":     entries,
        "signature":   sig,
    })
