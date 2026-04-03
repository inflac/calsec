#!/usr/bin/env python3

import json
import os
import base64

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


# ── File signing ──────────────────────────────────────────────────────────────

def _canonical(version: int, users: dict, entries: list, sync_config_enc) -> bytes:
    """Deterministic JSON encoding of the fields covered by the signature."""
    return json.dumps(
        {"version": version, "users": users,
         "entries": entries, "sync_config": sync_config_enc},
        sort_keys=True, separators=(",", ":"),
    ).encode()


def sign_file(version: int, users: dict, entries: list,
              sync_config_enc, kpriv_sign) -> str:
    sig = kpriv_sign.sign(
        _canonical(version, users, entries, sync_config_enc),
        ec.ECDSA(hashes.SHA256()))
    return b64(sig)


def verify_file(version: int, users: dict, entries: list,
                sync_config_enc, signature_b64: str, kpub_sign) -> bool:
    try:
        kpub_sign.verify(
            b64d(signature_b64),
            _canonical(version, users, entries, sync_config_enc),
            ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False
