#!/usr/bin/env python3

import json
import os
import sys
import uuid

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from crypto import sign_file, encrypt_entry

# All paths are relative to the parent directory (calsec/), not gui/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "calendar.json")
KEY_PRIVATE = os.path.join(BASE_DIR, "calsec_private.pem")
KEY_PUBLIC = os.path.join(BASE_DIR, "calsec_public.pem")

SYNC_CONFIG_ID = "__sync_config__"


def keys_exist():
    return os.path.exists(KEY_PRIVATE) and os.path.exists(KEY_PUBLIC)


def load_file():
    if not os.path.exists(DATA_FILE):
        return [], None, 0, None
    try:
        with open(DATA_FILE, "r") as f:
            obj = json.load(f)
        if isinstance(obj, list):
            return obj, None, 0, None
        return obj.get("entries", []), obj.get("sync_config"), obj.get("version", 0), obj.get("signature")
    except Exception:
        raise RuntimeError("Failed to read calendar file.")


def save_file(entries, sync_config_enc=None, version=0, signature=None):
    try:
        with open(DATA_FILE, "w") as f:
            json.dump(
                {"version": version, "entries": entries, "sync_config": sync_config_enc, "signature": signature},
                f, indent=2
            )
    except Exception:
        raise RuntimeError("Failed to write calendar file.")


def load_private_key(password: bytes):
    """Raises ValueError on wrong password or corrupted key."""
    if not os.path.exists(KEY_PRIVATE):
        raise FileNotFoundError("Private key not found.")
    try:
        with open(KEY_PRIVATE, "rb") as f:
            return serialization.load_pem_private_key(f.read(), password=password)
    except Exception:
        raise ValueError("Invalid password or corrupted key.")


def load_public_key():
    if not os.path.exists(KEY_PUBLIC):
        raise FileNotFoundError("Public key not found.")
    try:
        with open(KEY_PUBLIC, "rb") as f:
            return serialization.load_pem_public_key(f.read())
    except Exception:
        raise RuntimeError("Failed to load public key.")


def provision(password: bytes, sync_data: dict | None):
    """
    Generate new SECP256R1 keypair, write PEM files, and save initial calendar.json.
    sync_data: dict with keys url/user/password/remote_path, or None to skip sync.
    Raises RuntimeError on I/O failure.
    """
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    try:
        with open(KEY_PRIVATE, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.PKCS8,
                    encryption_algorithm=serialization.BestAvailableEncryption(password)
                )
            )
        with open(KEY_PUBLIC, "wb") as f:
            f.write(
                public_key.public_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PublicFormat.SubjectPublicKeyInfo
                )
            )
        os.chmod(KEY_PRIVATE, 0o600)
        os.chmod(KEY_PUBLIC, 0o644)
    except Exception:
        raise RuntimeError("Failed to write key files.")

    sync_config_enc = None
    if sync_data:
        config_entry = {
            "id": SYNC_CONFIG_ID,
            "url": sync_data["url"],
            "user": sync_data["user"],
            "password": sync_data["password"],
            "remote_path": sync_data["remote_path"],
        }
        sync_config_enc = encrypt_entry(config_entry, public_key)

    existing_entries, _, existing_version, _ = load_file()
    new_version = existing_version + 1
    new_sig = sign_file(existing_entries, sync_config_enc, new_version, private_key)
    save_file(existing_entries, sync_config_enc, new_version, new_sig)
