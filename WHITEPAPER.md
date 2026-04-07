# CalSec — Technical Whitepaper

## Motivation

Staying anonymous nowadays becomes more challenging from day to day. One of the most established methods for journalists, activists and people who want to hide in an anonymity set is to use [Tails](https://tails.net). However with Tails and the need to undergo surveillance and censorship, you have to face limitations — including not trusting most third-party services without [E2E encryption](https://en.wikipedia.org/wiki/End-to-end_encryption).

When dealing with others you might face the need to share a calendar so everyone stays informed about upcoming events and appointments. Using services without E2E is not an option. Trusting companies which claim security and privacy is an advance of trust that may not be acceptable. So two options remain:

The most obvious is to host your own hidden service with a calendar tool. Besides the many advantages, this requires securing your hardware, exposes your home address as the origin of your hidden service, and may be overkill for a simple calendar.

The second option — used by CalSec — is described below.

## Concept

For a shared calendar, we need an accessible server to store and distribute the data. Since we do not want to host such a server ourselves, nor rely on the promises of third-party providers, we instead use a synchronization approach similar to what is used in local password managers.

The calendar data is stored in an encrypted file, which is then synchronized through a third-party service (e.g. Nextcloud via WebDAV). Other users download this file and access it locally on their own devices.

While this method does not eliminate all risks, it significantly reduces them by ensuring that the data remains encrypted and under our control at all times.

## Encryption Scheme

CalSec uses a layered encryption model. All cryptographic operations use standard algorithms from the `cryptography` Python library.

### Keys

| Key | Algorithm | Purpose |
| --- | --------- | ------- |
| User keypair | EC SECP256R1 | Per-user encryption identity |
| `sym_key_cal` | AES-256 (random) | Encrypts all calendar entries |
| `kpriv_admin_sign` | EC SECP256R1 | Signs users + sync config (admin only) |
| `kpriv_edit_sign` | EC SECP256R1 | Signs entries (admin + editors) |

### Calendar Symmetric Key Distribution

Each user receives a copy of `sym_key_cal` encrypted to their public key via **ECIES** (Ephemeral ECDH + HKDF-SHA256 + AES-256-GCM). This means:

- The server never sees `sym_key_cal` in plaintext
- Revoking a user triggers a key rotation: a new `sym_key_cal` is generated and re-encrypted for all remaining users, and all entries are re-encrypted

### Entry Encryption

Each calendar entry is encrypted with a **random per-entry AES-256 key**:

```text
entry_key  ──AES-256-GCM──▶  entry_key_enc   (wrapped with sym_key_cal)
entry_data ──AES-256-GCM──▶  data_enc        (encrypted with entry_key, entry ID as AAD)
```

Using the entry ID as Additional Authenticated Data (AAD) prevents an attacker from substituting one encrypted entry for another.

### Integrity — Split Signatures

`calendar.json` contains two independent ECDSA-SHA256 signatures:

```text
sig_users   = ECDSA(kpriv_admin_sign,  sign_keys || users || sync_config)
sig_entries = ECDSA(kpriv_edit_sign,   entries)
```

This separation means editors can sign entry changes without being able to forge user or access-control changes. The sync configuration is also covered by `sig_users`, so it can be decrypted by all users who hold `sym_key_cal` but only admins can authorize changes to it.

### First-Import Trust

For the very first import on a new non-admin device, signature verification alone is not sufficient because the signing public keys are distributed inside `calendar.json` itself. CalSec therefore uses a manually verified trust-on-first-import step:

- The admin shares the current signing fingerprint over a separate trusted channel
- The new user enters this expected fingerprint before the first calendar download
- CalSec computes the fingerprint from `sign_keys` and only saves the file if both values match and all signatures verify successfully

The fingerprint is defined as:

```text
fingerprint = SHA-256(canonical_json({"sign_keys": sign_keys}))
```

After the first trusted import, later syncs only accept files whose `sign_keys` exactly match the locally stored ones.

### Sign Key Distribution

Signing private keys are stored inside `calendar.json` encrypted to each eligible user's public key via ECIES:

- `edit_sign_key_enc` — present for admins and editors
- `admin_sign_key_enc` — present for admins only

### File Structure

```text
calendar.json
├── version
├── sign_keys          (public signing keys — readable by all)
├── users
│   └── <hash>
│       ├── kpub_enc           (user's EC public key)
│       ├── sym_key_cal_enc    (ECIES: sym_key_cal → user)
│       ├── identifier_enc     (AES-256-GCM with sym_key_cal)
│       ├── role
│       ├── edit_sign_key_enc  (ECIES, editors + admins)
│       └── admin_sign_key_enc (ECIES, admins only)
├── entries[]
│   └── { id, entry_key_enc, data_enc }
├── sync_config        (AES-256-GCM with sym_key_cal, readable by all users)
├── sig_users          (ECDSA over sign_keys + users + sync_config)
└── sig_entries        (ECDSA over entries)
```

## Release Integrity

All official CalSec binaries are signed with an Ed25519 key. The corresponding public key is embedded in the binary itself and used by the auto-updater to verify every downloaded update before installation.

**Release signing public key:**

```text
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAUsv9qguzU98L3EcONyrMLxDj+8GoLPS/QTzrcA8A7cA=
-----END PUBLIC KEY-----
```

To verify a release binary manually:

```bash
# Download the binary and its signature from the release page, then:
python3 - <<'EOF'
import base64, sys
from cryptography.hazmat.primitives.serialization import load_pem_public_key

PUB = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAUsv9qguzU98L3EcONyrMLxDj+8GoLPS/QTzrcA8A7cA=
-----END PUBLIC KEY-----"""

binary = open("calsec-linux", "rb").read()
sig    = base64.b64decode(open("calsec-linux.sig").read().strip())
load_pem_public_key(PUB).verify(sig, binary)
print("Signature valid.")
EOF
```

## Limitations & Risks

- **Sync provider trust** — CalSec does not hide metadata from the WebDAV provider (file size, access times).
- **Key storage** — Private keys are stored on the Tails persistent volume. Physical access to the device is a risk regardless of encryption.
- **No forward secrecy for entries** — If a user's private key is compromised, past entries encrypted to that key can be decrypted. Key rotation on user removal mitigates this for future entries only.
- **Admin trust** — The admin controls user access, key rotation, and the sync configuration. A malicious admin can deny access to all users or manipulate the sync config. The sync URL is enforced to always point to `calendar.json` in the configured folder, preventing an admin from redirecting clients to arbitrary remote resources.
- **First-import verification** — New users must compare the signing fingerprint with the value received from the admin over a separate trusted channel. If that channel is compromised, the first import can still be subverted.
