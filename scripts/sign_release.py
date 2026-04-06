#!/usr/bin/env python3
"""
CI signing script — called by the GitHub Actions release workflow.

Signs a binary with the Ed25519 private key stored in the environment
variable RELEASE_SIGNING_KEY, and writes a base64-encoded signature to
<binary_path>.sig.

Usage:
    RELEASE_SIGNING_KEY="$(cat private.pem)" python scripts/sign_release.py build/calsec-linux
"""

import base64
import os
import sys
from pathlib import Path

from cryptography.hazmat.primitives.serialization import load_pem_private_key


def main():
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} <binary_path>", file=sys.stderr)
        sys.exit(1)

    binary_path = Path(sys.argv[1])
    if not binary_path.exists():
        print(f"Error: binary not found: {binary_path}", file=sys.stderr)
        sys.exit(1)

    priv_pem = os.environ.get("RELEASE_SIGNING_KEY", "").strip()
    if not priv_pem:
        print("Error: RELEASE_SIGNING_KEY environment variable is not set.", file=sys.stderr)
        sys.exit(1)

    try:
        private_key = load_pem_private_key(priv_pem.encode(), password=None)
    except Exception as exc:
        print(f"Error: could not load private key: {exc}", file=sys.stderr)
        sys.exit(1)

    data = binary_path.read_bytes()
    signature = private_key.sign(data)
    sig_b64 = base64.b64encode(signature).decode()

    sig_path = binary_path.with_suffix(binary_path.suffix + ".sig")
    sig_path.write_text(sig_b64)

    print(f"Signed:     {binary_path}")
    print(f"Signature:  {sig_path}")


if __name__ == "__main__":
    main()
