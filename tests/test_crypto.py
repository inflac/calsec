import os
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

import gui.crypto as crypto


def _keypair():
    kpriv = ec.generate_private_key(ec.SECP256R1())
    return kpriv, kpriv.public_key()


# ── b64 helpers ───────────────────────────────────────────────────────────────

def test_b64_roundtrip():
    data = b"hello world"
    assert crypto.b64d(crypto.b64(data)) == data


def test_b64d_roundtrip():
    raw = os.urandom(32)
    assert crypto.b64d(crypto.b64(raw)) == raw


# ── derive_key ────────────────────────────────────────────────────────────────

def test_derive_key_deterministic():
    shared = b"shared_secret"
    salt   = b"0" * 32
    assert crypto.derive_key(shared, salt) == crypto.derive_key(shared, salt)


def test_derive_key_length():
    assert len(crypto.derive_key(b"s", b"t" * 16)) == 32


def test_derive_key_differs_on_different_inputs():
    salt = b"x" * 16
    assert crypto.derive_key(b"a", salt) != crypto.derive_key(b"b", salt)


# ── sym_encrypt / sym_decrypt ─────────────────────────────────────────────────

def test_sym_roundtrip():
    key  = os.urandom(32)
    data = b"secret calendar data"
    enc  = crypto.sym_encrypt(key, data)
    assert crypto.sym_decrypt(key, enc) == data


def test_sym_with_aad():
    key  = os.urandom(32)
    data = b"entry payload"
    aad  = b"entry-id-123"
    enc  = crypto.sym_encrypt(key, data, aad=aad)
    assert crypto.sym_decrypt(key, enc, aad=aad) == data


def test_sym_aad_mismatch_raises():
    key = os.urandom(32)
    enc = crypto.sym_encrypt(key, b"data", aad=b"correct-aad")
    with pytest.raises(Exception):
        crypto.sym_decrypt(key, enc, aad=b"wrong-aad")


def test_sym_wrong_key_raises():
    enc = crypto.sym_encrypt(os.urandom(32), b"data")
    with pytest.raises(Exception):
        crypto.sym_decrypt(os.urandom(32), enc)


def test_sym_encrypt_nonce_is_random():
    key = os.urandom(32)
    e1  = crypto.sym_encrypt(key, b"same")
    e2  = crypto.sym_encrypt(key, b"same")
    assert e1["iv"] != e2["iv"]


# ── ecies_encrypt / ecies_decrypt ─────────────────────────────────────────────

def test_ecies_roundtrip():
    kpriv, kpub = _keypair()
    plaintext = b"symmetric key material"
    enc = crypto.ecies_encrypt(kpub, plaintext)
    assert crypto.ecies_decrypt(kpriv, enc) == plaintext


def test_ecies_wrong_key_raises():
    _, kpub = _keypair()
    kpriv2, _ = _keypair()
    enc = crypto.ecies_encrypt(kpub, b"secret")
    with pytest.raises(Exception):
        crypto.ecies_decrypt(kpriv2, enc)


def test_ecies_ciphertext_randomized():
    _, kpub = _keypair()
    enc1 = crypto.ecies_encrypt(kpub, b"same")
    enc2 = crypto.ecies_encrypt(kpub, b"same")
    assert enc1["ct"] != enc2["ct"]


# ── encrypt_entry / decrypt_entry ─────────────────────────────────────────────

def test_encrypt_entry_roundtrip():
    sym_key = os.urandom(32)
    entry = {"id": "abc-123", "title": "Meeting", "date": "01.01.2026"}
    enc = crypto.encrypt_entry(entry, sym_key)
    assert crypto.decrypt_entry(enc, sym_key) == entry


def test_encrypt_entry_preserves_id():
    sym_key = os.urandom(32)
    entry = {"id": "my-id", "title": "Test"}
    enc = crypto.encrypt_entry(entry, sym_key)
    assert enc["id"] == "my-id"


def test_encrypt_entry_aad_prevents_substitution():
    sym_key = os.urandom(32)
    e1 = {"id": "id-1", "title": "A"}
    e2 = {"id": "id-2", "title": "B"}
    enc1 = crypto.encrypt_entry(e1, sym_key)
    enc2 = crypto.encrypt_entry(e2, sym_key)
    # Swap the data_enc between entries — decryption must fail (AAD mismatch)
    tampered = dict(enc1)
    tampered["data_enc"] = enc2["data_enc"]
    with pytest.raises(Exception):
        crypto.decrypt_entry(tampered, sym_key)


def test_decrypt_entry_wrong_key_raises():
    enc = crypto.encrypt_entry({"id": "x", "title": "t"}, os.urandom(32))
    with pytest.raises(Exception):
        crypto.decrypt_entry(enc, os.urandom(32))


# ── split signatures: sign_users / verify_users ───────────────────────────────

def test_sign_and_verify_users():
    kpriv, kpub = _keypair()
    sign_keys = {"admin": "pk_admin", "edit": "pk_edit"}
    users     = {"hash1": {"role": "admin"}}
    sync_cfg  = None
    sig = crypto.sign_users(sign_keys, users, sync_cfg, kpriv)
    assert crypto.verify_users(sign_keys, users, sync_cfg, sig, kpub) is True


def test_verify_users_fails_on_tampered_data():
    kpriv, kpub = _keypair()
    sign_keys = {"admin": "pk_admin", "edit": "pk_edit"}
    users     = {"hash1": {"role": "admin"}}
    sig = crypto.sign_users(sign_keys, users, None, kpriv)
    tampered = {"hash1": {"role": "editor"}}
    assert crypto.verify_users(sign_keys, tampered, None, sig, kpub) is False


def test_verify_users_fails_with_wrong_key():
    kpriv, _   = _keypair()
    _, kpub2   = _keypair()
    sign_keys  = {"admin": "k", "edit": "k"}
    sig = crypto.sign_users(sign_keys, {}, None, kpriv)
    assert crypto.verify_users(sign_keys, {}, None, sig, kpub2) is False


# ── split signatures: sign_entries / verify_entries ──────────────────────────

def test_sign_and_verify_entries():
    kpriv, kpub = _keypair()
    entries = [{"id": "1", "title": "A"}, {"id": "2", "title": "B"}]
    sig = crypto.sign_entries(entries, kpriv)
    assert crypto.verify_entries(entries, sig, kpub) is True


def test_verify_entries_fails_on_tampered_data():
    kpriv, kpub = _keypair()
    entries = [{"id": "1", "title": "Original"}]
    sig     = crypto.sign_entries(entries, kpriv)
    assert crypto.verify_entries([{"id": "1", "title": "Tampered"}], sig, kpub) is False


def test_verify_entries_fails_with_wrong_key():
    kpriv, _ = _keypair()
    _, kpub2 = _keypair()
    sig = crypto.sign_entries([], kpriv)
    assert crypto.verify_entries([], sig, kpub2) is False


# ── pem_to_public_key ─────────────────────────────────────────────────────────

def test_pem_to_public_key_roundtrip():
    from cryptography.hazmat.primitives import serialization
    _, kpub = _keypair()
    pem = kpub.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    loaded = crypto.pem_to_public_key(pem)
    assert loaded.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    ) == kpub.public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_pem_to_public_key_invalid_raises():
    with pytest.raises(Exception):
        crypto.pem_to_public_key("not a pem key")


def test_sign_keys_fingerprint_stable_for_same_data():
    sign_keys = {"admin": "pk_admin", "edit": "pk_edit"}
    fp1 = crypto.sign_keys_fingerprint(sign_keys)
    fp2 = crypto.sign_keys_fingerprint(dict(sign_keys))
    assert fp1 == fp2


def test_sign_keys_fingerprint_changes_when_sign_keys_change():
    fp1 = crypto.sign_keys_fingerprint({"admin": "pk_admin", "edit": "pk_edit"})
    fp2 = crypto.sign_keys_fingerprint({"admin": "pk_admin2", "edit": "pk_edit"})
    assert fp1 != fp2


def test_normalize_fingerprint_strips_formatting():
    raw = "aabbccdd" * 8
    formatted = "AA BB CC DD " * 8
    assert crypto.normalize_fingerprint(formatted) == raw


def test_format_fingerprint_groups_for_display():
    raw = "aabbccdd" * 8
    assert crypto.format_fingerprint(raw) == "AABB CCDD AABB CCDD AABB CCDD AABB CCDD AABB CCDD AABB CCDD AABB CCDD AABB CCDD"
