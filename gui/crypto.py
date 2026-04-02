#!/usr/bin/env python3

import json
import os
import base64

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from cryptography.hazmat.primitives.asymmetric import ec


def b64(x): return base64.b64encode(x).decode()
def b64d(x): return base64.b64decode(x)


def derive_key(shared, salt):
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        info=b'calsec-v2'
    ).derive(shared)


def canonical_file(entries, sync_config_enc, version):
    return json.dumps(
        {"entries": entries, "sync_config": sync_config_enc, "version": version},
        sort_keys=True, separators=(',', ':')
    ).encode()


def sign_file(entries, sync_config_enc, version, private_key):
    data = canonical_file(entries, sync_config_enc, version)
    sig = private_key.sign(data, ec.ECDSA(hashes.SHA256()))
    return b64(sig)


def verify_file(entries, sync_config_enc, version, signature_b64, public_key):
    data = canonical_file(entries, sync_config_enc, version)
    try:
        public_key.verify(b64d(signature_b64), data, ec.ECDSA(hashes.SHA256()))
        return True
    except InvalidSignature:
        return False


def wrap_key(aes_key, public_key):
    eph = ec.generate_private_key(ec.SECP256R1())
    eph_pub_bytes = eph.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint
    )

    salt = os.urandom(32)
    shared = eph.exchange(ec.ECDH(), public_key)
    derived = derive_key(shared, salt)

    aesgcm = AESGCM(derived)
    iv = os.urandom(12)
    wrapped = aesgcm.encrypt(iv, aes_key, eph_pub_bytes)

    return {
        "ephemeral_pub": b64(eph_pub_bytes),
        "iv_wrap": b64(iv),
        "wrapped_key": b64(wrapped),
        "hkdf_salt": b64(salt)
    }


def unwrap_key(entry, private_key):
    eph_pub_bytes = b64d(entry["ephemeral_pub"])
    eph_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), eph_pub_bytes)

    salt = b64d(entry["hkdf_salt"])
    shared = private_key.exchange(ec.ECDH(), eph_pub)
    derived = derive_key(shared, salt)

    aesgcm = AESGCM(derived)
    return aesgcm.decrypt(b64d(entry["iv_wrap"]), b64d(entry["wrapped_key"]), eph_pub_bytes)


def encrypt_entry(entry, public_key):
    aes_key = AESGCM.generate_key(bit_length=256)
    aesgcm = AESGCM(aes_key)
    iv = os.urandom(12)

    plaintext = json.dumps(entry).encode()
    ciphertext = aesgcm.encrypt(iv, plaintext, entry["id"].encode())

    wrapped = wrap_key(aes_key, public_key)

    return {
        "id": entry["id"],
        "iv": b64(iv),
        "ciphertext": b64(ciphertext),
        **wrapped
    }


def decrypt_entry(entry, private_key):
    aes_key = unwrap_key(entry, private_key)

    aesgcm = AESGCM(aes_key)
    plaintext = aesgcm.decrypt(
        b64d(entry["iv"]),
        b64d(entry["ciphertext"]),
        entry["id"].encode()
    )

    return json.loads(plaintext.decode())
