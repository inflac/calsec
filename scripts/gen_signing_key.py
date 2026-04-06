#!/usr/bin/env python3
"""
One-time setup: generate the Ed25519 release-signing keypair.

Run this ONCE locally, then:
  1. Add the private key as a GitHub Actions secret named RELEASE_SIGNING_KEY
  2. Paste the public key into gui/updater.py as _RELEASE_PUBLIC_KEY_PEM

Usage:
    python scripts/gen_signing_key.py
"""

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

key = Ed25519PrivateKey.generate()

priv_pem = key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption(),
).decode()

pub_pem = key.public_key().public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo,
).decode()

print("=" * 60)
print("PRIVATE KEY — add as GitHub secret: RELEASE_SIGNING_KEY")
print("=" * 60)
print(priv_pem)

print("=" * 60)
print("PUBLIC KEY — paste into gui/updater.py as _RELEASE_PUBLIC_KEY_PEM")
print("=" * 60)
print(pub_pem)
