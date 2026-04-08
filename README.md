# CalSec

A secure, encrypted shared calendar for privacy-focused teams — built for [Tails](https://tails.net).

CalSec stores your calendar data in an end-to-end encrypted file that is synchronized through a third-party WebDAV service (e.g. Nextcloud). The server never sees plaintext data. For a full description of the encryption model, see [WHITEPAPER.md](https://github.com/inflac/calsec/blob/main/WHITEPAPER.md).

## Installation

> [!WARNING]
> Only install CalSec from the official GitHub release page. Third-party copies may have been modified.

Download the ZIP for your platform from the [latest release](https://github.com/inflac/calsec/releases/latest). Every release binary is signed with Ed25519 — the auto-updater verifies this automatically. For manual verification see [WHITEPAPER.md — Release Integrity](https://github.com/inflac/calsec/blob/main/WHITEPAPER.md#release-integrity).

1. Unzip the downloaded file
2. Open the extracted folder in your file browser
3. Right-click inside the folder and select **"Open in Terminal"**
4. Make the installer executable and run it:

    ```bash
    chmod +x install_calsec.sh
    ./install_calsec.sh
    ```

To uninstall, run the installer again and choose **"Uninstall"**. You will be asked whether to also delete your keys — they are **not** deleted by default.

> [!IMPORTANT]
> If you are setting up CalSec as **admin**, do not generate a keypair during installation. If a key already exists when CalSec starts, the admin setup dialog will not appear. Let CalSec generate your key on first launch.

## First Start

**Admin setup** — On the very first start, CalSec prompts you to set up the calendar:

- Enter your **identifier** (for example a username or mail address)
- Optionally set a **password** for your private key (required on every subsequent start). Without a password the private key is stored unencrypted on disk — strongly recommended on Tails and any shared or portable device.
- Optionally configure a **WebDAV folder URL** for sync

CalSec will generate your admin keypair and create the encrypted `calendar.json`. After setup, CalSec shows the calendar signing fingerprint in a copyable popup. Share this fingerprint with new users over a separate trusted channel.

**User onboarding** — The recommended order for new users is:

1. Install CalSec
2. Generate a local keypair
3. Send the public key file (`.pub.pem`) and identifier to the admin
4. Wait until the admin has added the user
5. Receive the sync data and signing fingerprint from the admin over separate channels where possible
6. Enter the sync data in CalSec
7. On the first calendar download, compare the displayed signing fingerprint with the one received from the admin

**Adding users as admin** — Add new users only after you have received their public key and identifier. Then send them:

- the WebDAV sync data
- the current signing fingerprint shown by CalSec

CalSec can standardize this handoff for you: in **User Management**, select a user and use **Copy Onboarding** to copy a ready-to-send onboarding message containing the sync data, signing fingerprint, and user instructions.

If you remove a user with role `editor` or `admin`, or demote a user so they lose editor/admin signing rights, CalSec rotates the affected signing keys. This changes the signing fingerprint. The new fingerprint must then be redistributed to all remaining users over a separate trusted channel before they can trust future syncs.

**Non-admin first start** — If a local key exists but no `calendar.json` is present, CalSec prompts for WebDAV credentials and the expected signing fingerprint. The calendar is only saved if the fingerprint matches and both signatures verify successfully.

## Updates

Update behavior is configured in **Settings → Updates**:

| Mode | Behavior |
| ---- | -------- |
| **Disabled** | No update checks |
| **Auto** | Checks and installs silently on startup; login is blocked until complete |
| **Notify** | Checks in the background; a toolbar banner appears if an update is available |

Every downloaded binary is verified against the Ed25519 signing key before installation. A custom channel URL can be configured for self-hosted mirrors.

## Data Locations

CalSec stores all data relative to the binary. On Tails with the recommended install script:

```text
/live/persistence/TailsData_unlocked/
└── programs/calsec/
    ├── calsec              # binary
    ├── icon.png            # application icon
    ├── install_calsec.sh   # installer (for uninstall)
    ├── calendar.json       # encrypted calendar (after sync)
    ├── keys/               # private keys (SECRET — never share these)
    └── pubkeys/            # public keys for sharing
```

On other systems, the same layout is created in whichever directory you place the binary:

```text
<directory containing the binary>/
├── calsec              # binary (calsec.exe on Windows)
├── calendar.json
├── keys/
└── pubkeys/
```

The desktop entry is stored via the Dotfiles feature at `/live/persistence/TailsData_unlocked/dotfiles/.local/share/applications/calsec.desktop`.

> [!NOTE]
> The **Dotfiles** feature must be enabled in Tails Persistent Storage settings for the app menu entry to survive a reboot.

On Tails, user preferences are stored via Dotfiles at `/live/persistence/TailsData_unlocked/dotfiles/.calsec/settings.json`.

Private key filenames use `sha256(identifier)[:16 bytes]`, encoded as 32 hex characters.
