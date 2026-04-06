# CalSec

A secure, encrypted shared calendar for privacy-focused teams — built for [Tails](https://tails.net).

CalSec stores your calendar data in an end-to-end encrypted file that is synchronized through a third-party WebDAV service (e.g. Nextcloud). The server never sees plaintext data. For a full description of the encryption model, see [WHITEPAPER.md](WHITEPAPER.md).

## Installation

> [!WARNING]
> Only install CalSec from the official GitHub release page. Third-party copies may have been modified.

Download the ZIP for your platform from the [latest release](https://github.com/inflac/calsec/releases/latest). Every release binary is signed with Ed25519 — the auto-updater verifies this automatically. For manual verification see [WHITEPAPER.md — Release Integrity](WHITEPAPER.md#release-integrity).

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

- Enter your **email address**
- Optionally set a **password** for your private key (required on every subsequent start)
- Optionally configure a **WebDAV folder URL** for sync

CalSec will generate your admin keypair and create the encrypted `calendar.json`.

**Adding users** — Each new user installs CalSec and generates a keypair. They send their public key file (`.pub.pem`) and email address to the admin, who adds them via **User Management**.

**Non-admin first start** — If a local key exists but no `calendar.json` is present, CalSec prompts for WebDAV credentials to download the calendar once. Both signatures are verified before saving.

## Updates

Update behavior is configured in **Settings → Updates**:

| Mode | Behavior |
| ---- | -------- |
| **Disabled** | No update checks |
| **Auto** | Checks and installs silently on startup; login is blocked until complete |
| **Notify** | Checks in the background; a toolbar banner appears if an update is available |

Every downloaded binary is verified against the Ed25519 signing key before installation. A custom channel URL can be configured for self-hosted mirrors.

## Data Locations

```
/live/persistence/TailsData_unlocked/
└── programs/calsec/
    ├── calsec              # binary
    ├── icon.png            # application icon
    ├── install_calsec.sh   # installer (for uninstall)
    ├── calendar.json       # encrypted calendar (after sync)
    ├── keys/               # private keys (SECRET — never share these)
    └── pubkeys/            # public keys for sharing
```

The desktop entry is stored via the Dotfiles feature at `/live/persistence/TailsData_unlocked/dotfiles/.local/share/applications/calsec.desktop`.

> [!NOTE]
> The **Dotfiles** feature must be enabled in Tails Persistent Storage settings for the app menu entry to survive a reboot.

User preferences are stored at `/home/amnesia/Persistent/.calsec/preferences.json`.
