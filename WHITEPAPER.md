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

### Fingerprint Concept

The fingerprint is a cryptographic digest of the calendar's signing public keys. It serves as a short, human-verifiable representation of the trust anchor — if two parties compute the same fingerprint over the same `sign_keys` block, they know they are working with the same signing keys.

#### Computation

```text
fingerprint = SHA-256(canonical_json({"sign_keys": sign_keys}))
```

Canonical JSON is deterministic: keys are sorted and no extra whitespace is added. Any change to the signing keys — whether key rotation or tampering — produces a completely different fingerprint.

#### Purpose: Trust-on-First-Use (TOFU)

When a new user imports the calendar for the first time, CalSec has no prior knowledge to verify the signing keys against. The keys are distributed inside `calendar.json` itself, so an active attacker who intercepts the first download could substitute their own keys. The fingerprint breaks this attack:

1. The admin reads the fingerprint from the main window ("FP" button) and communicates it to the new user over a separate, trusted channel (e.g. Signal, in-person).
2. The new user enters the expected fingerprint in the onboarding dialog before the first calendar download.
3. CalSec downloads the file, computes the fingerprint from the received `sign_keys`, and only accepts the file if both values match *and* all signatures verify successfully.

Without a matching fingerprint, the import is aborted — even if the signatures would technically verify against the received keys.

#### After First Import

Once a device has a locally stored copy of `sign_keys`, later syncs no longer use the fingerprint. Instead, CalSec directly checks that the `sign_keys` in every new download exactly match the stored ones. The fingerprint is only relevant for the initial TOFU step.

#### Key Rotation

If the admin regenerates the signing keys (e.g., after a suspected compromise), the fingerprint changes. All existing non-admin users will notice a mismatch on the next sync and reject the updated file. The admin must communicate the new fingerprint to every user individually before they can sync again.

#### Display and Format

The fingerprint is displayed as a 64-character hex string grouped in blocks of 4 for readability:

```text
abcd ef12 3456 7890 ...
```

Spaces are cosmetic only. Comparison strips whitespace and is case-insensitive. The fingerprint is accessible at any time via the "FP" button in the main window (visible to admins). The full value can be copied to the clipboard from the popup.

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
- **Admin trust** — The admin holds `sym_key_cal` (decrypts all entries) and both signing private keys (can sign any change). A malicious or compromised admin can:
  - Read all calendar entries in plaintext
  - Add, modify, or delete entries and re-sign them (forged entries will pass signature verification)
  - Manipulate metadata such as timestamps
  - Revoke or demote any other user
  - Modify the sync configuration
  
  The sync URL is enforced to always point to `calendar.json` in the configured folder, preventing an admin from redirecting clients to arbitrary remote resources. Non-admin users have no cryptographic way to detect admin-authored manipulation of the users section or entries — they rely entirely on trusting the admin.
- **First-import verification** — New users must compare the signing fingerprint with the value received from the admin over a separate trusted channel. If that channel is compromised, the first import can still be subverted.
