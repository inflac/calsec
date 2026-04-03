# CalSec


A secure calendar tool for tails with hidden service sync

Staying anonymous nowadays becomes more challenging from day to day. One of the most established methods for journalists, activists and people who want to hide in an anonymity set is to use [Tails](https://tails.net). However with tails and the need to undergo surveillance and censorship, you have to face limitations.
Thus including not to trust most third party services without [E2E](https://en.wikipedia.org/wiki/End-to-end_encryption).

When dealing with others you might face the need to share a calendar so everyone stays informed about upcoming events and appointments.
However, using Services without E2E isn't an option. Also trusting companies which claim security and privacy is an advance of trust we might understandably not want to give. So there are two options left:
The most obvious is to host your own hidden service with a calendar tool. Besides the many advantages this could have, we now have the need to secure our Hardware. Also, this isn't an undoable task and there are a lot of cool concepts for hardening and securing local hardware against eavesdropping or actual physical access, this might be overkill for a simple calendar and leaves risks as well.
All your contacts communicating with your local hidden service, leads to your home. No matter the data might be enough protected, you could get into the scope of investigations or attacks. The second option which is used by this tool, will be explained in the "Concept" section.

## Concept


For a shared calendar, we need an accessible server to store and distribute the data. Since we do not want to host such a server ourselves, nor rely on the promises of third-party providers, we instead use a synchronization approach similar to what is used in local password managers.

The calendar data is stored in an encrypted file, which is then synchronized through a third-party service. Other users can download this file and access it locally on their own devices.

While this method does not eliminate all risks, it significantly reduces them by ensuring that the data remains encrypted and under our control.

## Encryption scheme

CalSec uses a layered encryption model. All cryptographic operations use standard algorithms from the `cryptography` Python library.

### Keys

| Key | Algorithm | Purpose |
| ----- | ----------- | --------- |
| ----- | ----------- | --------- |
| User keypair | EC SECP256R1 | Per-user encryption identity |
| `sym_key_cal` | AES-256 (random) | Encrypts all calendar entries |
| `kpriv_admin_sign` | EC SECP256R1 | Signs the users block (admin only) |
| `kpriv_edit_sign` | EC SECP256R1 | Signs entries and sync config (admin + editors) |

### Calendar symmetric key distribution

Each user receives a copy of `sym_key_cal` encrypted to their public key via **ECIES** (Ephemeral ECDH + HKDF-SHA256 + AES-256-GCM). This means:
- The server never sees `sym_key_cal` in plaintext
- Revoking a user triggers a key rotation: a new `sym_key_cal` is generated and re-encrypted for all remaining users, and all entries are re-encrypted

### Entry encryption

Each calendar entry is encrypted with a **random per-entry AES-256 key**:

```
entry_key  ──AES-256-GCM──▶  entry_key_enc   (wrapped with sym_key_cal)
entry_data ──AES-256-GCM──▶  data_enc        (encrypted with entry_key, entry ID as AAD)
```

Using the entry ID as Additional Authenticated Data (AAD) prevents an attacker from substituting one encrypted entry for another.

### Integrity — split signatures

`calendar.json` contains two independent ECDSA-SHA256 signatures:

```
sig_users   = ECDSA(kpriv_admin_sign,  sign_keys || users || sync_config)
sig_entries = ECDSA(kpriv_edit_sign,   entries)
```

This separation means editors can sign entry changes without being able to forge user or access-control changes. Only admins hold `kpriv_admin_sign`.

### Sign key distribution

Signing private keys are stored inside `calendar.json` encrypted to each eligible user's public key via ECIES:

- `edit_sign_key_enc` — present for admins and editors
- `admin_sign_key_enc` — present for admins only

### File structure overview

```
calendar.json
├── version
├── sign_keys          (public signing keys — readable by all)
├── users
│   └── <hash>
│       ├── kpub_enc           (user's EC public key)
│       ├── sym_key_cal_enc    (ECIES: sym_key_cal → user)
│       ├── email_enc          (AES-256-GCM with sym_key_cal)
│       ├── role
│       ├── edit_sign_key_enc  (ECIES, editors + admins)
│       └── admin_sign_key_enc (ECIES, admins only)
├── entries[]
│   └── { id, entry_key_enc, data_enc }
├── sync_config        (AES-256-GCM with sym_key_cal, admins only)
├── sig_users          (ECDSA over sign_keys + users + sync_config)
└── sig_entries        (ECDSA over entries)
```

## Limitations & Risks

## Installation Steps

> [!WARNING]
> For security reasons, you should only install CalSec using the ZIP file from the latest official release on GitHub.
> Be especially cautious when downloading ZIP files from unknown or untrusted sources. Third-party files may have been modified and could contain malicious code.
> Always verify the source before installation to ensure the integrity and safety of your system.

---

### 1. Verify the integrity of your local CalSec copy

1. Calculate the SHA256 hash of the ZIP:


    ```bash
    sha256sum calsec.zip
    ```


2. Compare the output with the hash from the latest release
3. If both hashes match, continue.
   If they do not match, delete your local copy and download a fresh version from the official release page.

---

### 2. Install / Uninstall CalSec

1. Unzip the file
2. Open the extracted folder in your file browser
3. Right-click inside the folder and select **“Open in Terminal”**
4. Make the installer executable:


    ```bash
    chmod +x install_calsec.sh
    ```


5. Start the installer:


    ```bash
    ./install_calsec.sh
    ```

To uninstall CalSec, run the installer again and choose **"Uninstall"** from the menu:


```bash
./install_calsec.sh
```


You will be asked whether to also delete your keys. Keys are **not** deleted by default.

---

### 3. Key Generation

After installation, you will be asked:
`Generate keypair now? [Y/n]`

#### If you choose **Yes**:

- Enter your **email address**
- Optionally set a **password** for your private key

> 🔐 If you set a password, you will need to enter it **every time you start CalSec**.

The installer will then:

- generate your **private key** (stored locally)
- export your **public key**

---

### 4. Send your Public Key to the Admin

After key generation:

- Send the **public key file** (`.pub.pem`)
- Provide your **email address**

The admin will add you to the calendar.

---

### 5. Start CalSec

You can now start CalSec from:

- the Applications menu
- or via terminal:


    ```bash
    /live/persistence/TailsData_unlocked/programs/calsec/calsec
    ```

## Data Locations


CalSec stores its data inside the persistent storage:


```bash
/live/persistence/TailsData_unlocked/
└── programs/calsec/
  ├── calsec              # binary
  ├── icon.png            # application icon
  ├── install_calsec.sh   # installer (for uninstall)
  ├── calendar.json       # encrypted calendar (after sync)
  ├── keys/               # private keys (SECRET!)
  └── pubkeys/            # public keys for sharing
```

The desktop entry is stored persistently via the Dotfiles feature at:


```bash
/live/persistence/TailsData_unlocked/dotfiles/.local/share/applications/
└── calsec.desktop
```


A symlink is created at `/home/amnesia/.local/share/applications/calsec.desktop` for the current session.

> [!NOTE]
> The **Dotfiles** feature must be enabled in Tails Persistent Storage settings for the application menu entry to survive a reboot.

User preferences (e.g. GUI color scheme) are stored at:


```bash
/home/amnesia/Persistent/
└── .calsec/
  └── preferences.json
```
