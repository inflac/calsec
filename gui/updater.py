"""
Auto-updater for frozen (PyInstaller) builds.

Queries the GitHub Releases API (or a compatible custom endpoint) for the
latest release, downloads the platform binary, and replaces the running
executable.

Only active when running as a packaged binary (sys._MEIPASS is set).
"""

import json
import os
import stat
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

OFFICIAL_CHANNEL = "https://api.github.com/repos/inflac/calsec/releases/latest"

# Expected asset filenames per platform
_ASSET_NAMES = {
    "win32":  "calsec.exe",
    "linux":  "calsec-linux",
    "darwin": "calsec-macos",
}

# Ed25519 public key used to verify release binaries.
# Generate with: python scripts/gen_signing_key.py

_RELEASE_PUBLIC_KEY_PEM = b"""-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAUsv9qguzU98L3EcONyrMLxDj+8GoLPS/QTzrcA8A7cA=
-----END PUBLIC KEY-----"""


def is_frozen() -> bool:
    """True when running as a PyInstaller single-file binary."""
    return getattr(sys, "_MEIPASS", None) is not None


@dataclass
class UpdateInfo:
    version: str
    download_url: str


# ── Version helpers ────────────────────────────────────────────────────────────

def current_version() -> str:
    try:
        from version import VERSION
        return VERSION
    except ImportError:
        return "0.0.0"


def _version_tuple(v: str) -> tuple:
    v = v.lstrip("v")
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


# ── Channel / asset resolution ─────────────────────────────────────────────────

def _channel_url() -> str:
    import settings
    ch = settings.get("update_channel")
    if not ch or ch == "official":
        return OFFICIAL_CHANNEL
    return ch


def _asset_name() -> str:
    for prefix, name in _ASSET_NAMES.items():
        if sys.platform.startswith(prefix):
            return name
    return ""


# ── Public API ─────────────────────────────────────────────────────────────────

def check_for_update() -> Optional[UpdateInfo]:
    """
    Query the configured channel for a newer release.

    Returns an UpdateInfo if a newer version exists and a matching binary
    asset is found.  Returns None if already up-to-date or no asset matches.
    Raises urllib.error.URLError / json.JSONDecodeError on network failures.
    """
    url = _channel_url()
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": f"calsec-updater/{current_version()}",
            "Accept": "application/vnd.github+json",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())

    latest_tag = data.get("tag_name", "")
    if _version_tuple(latest_tag) <= _version_tuple(current_version()):
        return None

    asset_name = _asset_name()
    if not asset_name:
        return None

    for asset in data.get("assets", []):
        if asset.get("name") == asset_name:
            return UpdateInfo(
                version=latest_tag,
                download_url=asset["browser_download_url"],
            )

    return None


def download_update(
    info: UpdateInfo,
    progress_cb: Optional[Callable[[int, int], None]] = None,
) -> Path:
    """
    Download the update binary to a temporary file, then verify its signature.

    progress_cb(downloaded_bytes, total_bytes) is called after each chunk.
    Returns the path to the temporary file on success.
    Raises ValueError if signature verification fails.
    Cleans up the temp file and re-raises on any error.
    """
    suffix = ".exe" if sys.platform.startswith("win32") else ""
    fd, tmp = tempfile.mkstemp(suffix=f".new{suffix}", prefix="calsec_upd_")
    os.close(fd)

    try:
        req = urllib.request.Request(
            info.download_url,
            headers={"User-Agent": f"calsec-updater/{current_version()}"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            with open(tmp, "wb") as f:
                while True:
                    chunk = resp.read(65536)
                    if not chunk:
                        break
                    f.write(chunk)
                    done += len(chunk)
                    if progress_cb:
                        progress_cb(done, total)

        _verify_release_signature(Path(tmp), info.download_url)

    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise

    return Path(tmp)


# ── Signature verification ─────────────────────────────────────────────────────

def _verify_release_signature(binary: Path, binary_url: str) -> None:
    """
    Download and verify the Ed25519 signature for *binary*.

    The signature file is expected at <binary_url>.sig.
    Behaviour:
      - Public key not configured → skip (no-op, logs nothing)
      - Signature file not found (HTTP 404) → skip
      - Signature present but invalid → raises ValueError
    """
    if not _RELEASE_PUBLIC_KEY_PEM:
        return

    sig_url = binary_url + ".sig"
    try:
        req = urllib.request.Request(
            sig_url,
            headers={"User-Agent": f"calsec-updater/{current_version()}"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            sig_b64 = resp.read().decode().strip()
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return  # no .sig file published — skip verification
        raise

    import base64
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.serialization import load_pem_public_key

    pub_key = load_pem_public_key(_RELEASE_PUBLIC_KEY_PEM)
    signature = base64.b64decode(sig_b64)
    data = binary.read_bytes()

    try:
        pub_key.verify(signature, data)
    except InvalidSignature:
        raise ValueError(
            "Signature verification failed — the downloaded binary does not "
            "match the expected signature. Aborting update."
        )


def apply_update(new_binary: Path) -> None:
    """
    Replace the running binary with *new_binary* and restart the process.

    On Linux/macOS: atomic os.replace() + os.execv() (never returns).
    On Windows: launches a detached batch script that waits for this process
                to exit, copies the new binary, then restarts — then exits.
    """
    exe = Path(sys.executable)
    if sys.platform.startswith("win32"):
        _apply_windows(exe, new_binary)
    else:
        _apply_unix(exe, new_binary)


# ── Platform-specific replace logic ───────────────────────────────────────────

def _apply_unix(exe: Path, new_binary: Path) -> None:
    import errno
    import shutil

    # Ensure executable bit is set on the downloaded binary
    mode = os.stat(new_binary).st_mode
    os.chmod(new_binary, mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    # Prefer atomic rename; fall back to copy+delete when tmp and exe live on
    # different filesystems (EXDEV — common on Tails where /tmp is tmpfs).
    try:
        os.replace(new_binary, exe)
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise
        shutil.copy2(new_binary, exe)
        os.unlink(new_binary)

    # Re-exec: load new binary in place of this process
    os.execv(str(exe), sys.argv)


def _apply_windows(exe: Path, new_binary: Path) -> None:
    import subprocess

    fd, bat = tempfile.mkstemp(suffix=".bat", prefix="calsec_upd_")
    os.close(fd)

    # The batch script runs after this process exits:
    #  1. Short delay to ensure the process is gone
    #  2. Copy new binary over old path
    #  3. Delete temp binary and self-delete the script
    #  4. Restart the updated binary
    script = (
        "@echo off\n"
        "ping -n 4 127.0.0.1 >NUL\n"
        f'copy /Y "{new_binary}" "{exe}"\n'
        f'del "{new_binary}"\n'
        f'start "" "{exe}"\n'
        'del "%~f0"\n'
    )
    with open(bat, "w") as f:
        f.write(script)

    subprocess.Popen(
        ["cmd.exe", "/C", bat],
        creationflags=subprocess.CREATE_NO_WINDOW,
        close_fds=True,
    )
    sys.exit(0)
