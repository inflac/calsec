import os
import pytest

from cryptography.hazmat.primitives.asymmetric import ec

import gui.crypto as crypto


# ---------- Helpers ----------

def generate_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key


# ---------- b64 helpers ----------

def test_b64_roundtrip():
    data = b"hello"
    encoded = crypto.b64(data)
    decoded = crypto.b64d(encoded)
    assert decoded == data


# ---------- derive_key ----------

def test_derive_key_deterministic():
    shared = b"shared_secret"
    salt = b"12345678901234567890123456789012"

    k1 = crypto.derive_key(shared, salt)
    k2 = crypto.derive_key(shared, salt)

    assert k1 == k2
    assert len(k1) == 32


# ---------- canonical file ----------

def test_canonical_file():
    data = crypto.canonical_file([{"a": 1}], "cfg", 1)

    assert isinstance(data, bytes)
    assert b'"entries"' in data
    assert b'"version"' in data


# ---------- sign / verify ----------

def test_sign_and_verify():
    private, public = generate_keypair()

    entries = [{"id": "1"}]
    sig = crypto.sign_file(entries, "cfg", 1, private)

    assert crypto.verify_file(entries, "cfg", 1, sig, public) is True


def test_verify_fails_with_modified_data():
    private, public = generate_keypair()

    entries = [{"id": "1"}]
    sig = crypto.sign_file(entries, "cfg", 1, private)

    # Daten ändern → Signatur muss ungültig werden
    assert crypto.verify_file([{"id": "2"}], "cfg", 1, sig, public) is False


# ---------- wrap / unwrap ----------

def test_wrap_and_unwrap():
    private, public = generate_keypair()

    aes_key = os.urandom(32)

    wrapped = crypto.wrap_key(aes_key, public)
    unwrapped = crypto.unwrap_key(wrapped, private)

    assert unwrapped == aes_key


# ---------- encrypt / decrypt ----------

def test_encrypt_decrypt_roundtrip():
    private, public = generate_keypair()

    entry = {
        "id": "test-id",
        "secret": "data",
        "value": 123
    }

    enc = crypto.encrypt_entry(entry, public)
    dec = crypto.decrypt_entry(enc, private)

    assert dec == entry


def test_encrypt_changes_output():
    private, public = generate_keypair()

    entry = {"id": "test-id", "data": "value"}

    enc1 = crypto.encrypt_entry(entry, public)
    enc2 = crypto.encrypt_entry(entry, public)

    # Unterschiedlich wegen Random IV / Key
    assert enc1 != enc2


# ---------- unwrap failure ----------

def test_decrypt_fails_with_wrong_key():
    private1, public1 = generate_keypair()
    private2, _ = generate_keypair()

    entry = {"id": "test", "data": "secret"}

    enc = crypto.encrypt_entry(entry, public1)

    with pytest.raises(Exception):
        crypto.decrypt_entry(enc, private2)