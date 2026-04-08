#!/usr/bin/env python3

import base64
import hashlib
import json
import os

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


def b64(x: bytes) -> str:
    return base64.b64encode(x).decode()


def b64d(x: str) -> bytes:
    return base64.b64decode(x)


def derive_key(shared: bytes, salt: bytes) -> bytes:
    return HKDF(
        algorithm=hashes.SHA256(), length=32,
        salt=salt, info=b"calsec-v2",
    ).derive(shared)


# ── Symmetric (AES-256-GCM) ───────────────────────────────────────────────────

def sym_encrypt(key: bytes, plaintext: bytes, aad: bytes | None = None) -> dict:
    """AES-256-GCM encrypt. Returns {iv, ct} as base64 strings."""
    iv = os.urandom(12)
    ct = AESGCM(key).encrypt(iv, plaintext, aad)
    return {"iv": b64(iv), "ct": b64(ct)}


def sym_decrypt(key: bytes, enc: dict, aad: bytes | None = None) -> bytes:
    """AES-256-GCM decrypt."""
    return AESGCM(key).decrypt(b64d(enc["iv"]), b64d(enc["ct"]), aad)


# ── ECIES (EC public-key encryption) ─────────────────────────────────────────

def ecies_encrypt(kpub: ec.EllipticCurvePublicKey, plaintext: bytes) -> dict:
    """Encrypt *plaintext* to *kpub* via ephemeral ECDH + HKDF + AES-256-GCM.
    Returns {kpub_eph, salt, iv, ct} as base64 strings."""
    kpriv_eph = ec.generate_private_key(ec.SECP256R1())
    shared = kpriv_eph.exchange(ec.ECDH(), kpub)
    salt = os.urandom(16)
    wrap_key = derive_key(shared, salt)
    kpub_eph_bytes = kpriv_eph.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    enc = sym_encrypt(wrap_key, plaintext)
    enc["kpub_eph"] = b64(kpub_eph_bytes)
    enc["salt"] = b64(salt)
    return enc  # {kpub_eph, salt, iv, ct}


def ecies_decrypt(kpriv: ec.EllipticCurvePrivateKey, enc: dict) -> bytes:
    """Decrypt ECIES data using *kpriv*."""
    kpub_eph = ec.EllipticCurvePublicKey.from_encoded_point(
        ec.SECP256R1(), b64d(enc["kpub_eph"]))
    shared = kpriv.exchange(ec.ECDH(), kpub_eph)
    wrap_key = derive_key(shared, b64d(enc["salt"]))
    return sym_decrypt(wrap_key, enc)


# ── Entry encryption ──────────────────────────────────────────────────────────

def encrypt_entry(data: dict, sym_key_cal: bytes) -> dict:
    """Encrypt a calendar entry with a per-entry AES-256 key wrapped by sym_key_cal.
    Entry ID is used as AAD to prevent entry substitution attacks."""
    entry_key = os.urandom(32)
    entry_id = data["id"].encode()
    return {
        "id":            data["id"],
        "entry_key_enc": sym_encrypt(sym_key_cal, entry_key),
        "data_enc":      sym_encrypt(entry_key, json.dumps(data).encode(), aad=entry_id),
    }


def decrypt_entry(enc_entry: dict, sym_key_cal: bytes) -> dict:
    """Decrypt a calendar entry."""
    entry_id = enc_entry["id"].encode()
    entry_key = sym_decrypt(sym_key_cal, enc_entry["entry_key_enc"])
    plaintext = sym_decrypt(entry_key, enc_entry["data_enc"], aad=entry_id)
    return json.loads(plaintext)


# ── Public key helpers ────────────────────────────────────────────────────────

def pem_to_public_key(pem_str: str):
    """Load an EC public key from a PEM string."""
    return serialization.load_pem_public_key(pem_str.encode())


def canonical_sign_keys(sign_keys: dict) -> bytes:
    """Canonical serialization of sign_keys for fingerprinting."""
    return json.dumps(
        {"sign_keys": sign_keys},
        sort_keys=True, separators=(",", ":"),
    ).encode()


def sign_keys_fingerprint(sign_keys: dict) -> str:
    """Return the SHA-256 fingerprint of sign_keys as 64 lowercase hex chars."""
    return hashlib.sha256(canonical_sign_keys(sign_keys)).hexdigest()


def normalize_fingerprint(value: str) -> str:
    """Normalize a fingerprint by removing separators and lowercasing."""
    return "".join(ch for ch in value.lower() if ch in "0123456789abcdef")


def format_fingerprint(value: str, group: int = 4) -> str:
    """Format a fingerprint for display."""
    normalized = normalize_fingerprint(value)
    return " ".join(
        normalized[i:i + group] for i in range(0, len(normalized), group)
    ).upper()


# ── File signing — two independent sections ───────────────────────────────────
#
# sig_users   covers version + sign_keys + users + sync_config → signed with kpriv_admin_sign
# sig_entries covers version + entries only → signed with kpriv_edit_sign
#
# Separating the two signatures means:
#   - Editors (kpriv_edit_sign only) can sign entry changes but cannot forge user changes.
#   - Admins hold both keys and can sign either section.

def _canonical_users(version: int, sign_keys: dict, users: dict, sync_config) -> bytes:
    """Admin-controlled section: version, sign_keys, users, and sync_config."""
    return json.dumps(
        {
            "version": version,
            "sign_keys": sign_keys,
            "users": users,
            "sync_config": sync_config,
        },
        sort_keys=True, separators=(",", ":"),
    ).encode()


def _canonical_entries(version: int, entries: list) -> bytes:
    """Editor-controlled section: version and entries."""
    return json.dumps(
        {"version": version, "entries": entries},
        sort_keys=True, separators=(",", ":"),
    ).encode()


def sign_users(version: int, sign_keys: dict, users: dict,
               sync_config, kpriv_admin_sign) -> str:
    sig = kpriv_admin_sign.sign(
        _canonical_users(version, sign_keys, users, sync_config),
        ec.ECDSA(hashes.SHA256()))
    return b64(sig)


def sign_entries(version: int, entries: list, kpriv_edit_sign) -> str:
    sig = kpriv_edit_sign.sign(
        _canonical_entries(version, entries), ec.ECDSA(hashes.SHA256()))
    return b64(sig)


def verify_users(version: int, sign_keys: dict, users: dict, sync_config,
                 sig_b64: str, kpub_admin_sign) -> bool:
    try:
        kpub_admin_sign.verify(
            b64d(sig_b64),
            _canonical_users(version, sign_keys, users, sync_config),
            ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False


def verify_entries(version: int, entries: list, sig_b64: str, kpub_edit_sign) -> bool:
    try:
        kpub_edit_sign.verify(
            b64d(sig_b64),
            _canonical_entries(version, entries),
            ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False
