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
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

OFFICIAL_CHANNEL = "https://api.github.com/repos/inflac/calsec/releases/latest"

_ASSET_NAME = "calsec-linux"

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
    return _ASSET_NAME if sys.platform.startswith("linux") else ""


# ── HTTP session ───────────────────────────────────────────────────────────────

def _session():
    """Return a requests.Session configured for Tor if torsocks is active."""
    import requests

    s = requests.Session()
    s.headers["User-Agent"] = f"calsec-updater/{current_version()}"
    s.headers["Accept"] = "application/vnd.github+json"

    # If launched under torsocks (LD_PRELOAD), bypass the LD_PRELOAD mechanism
    # and talk to the Tor SOCKS5 proxy directly. socks5h delegates hostname
    # resolution to the proxy so no DNS leaks occur.
    if "torsocks" in os.environ.get("LD_PRELOAD", "").lower():
        tor_proxy = "socks5h://127.0.0.1:9050"
        s.proxies = {"http": tor_proxy, "https": tor_proxy}

    return s


# ── Public API ─────────────────────────────────────────────────────────────────

def check_for_update() -> Optional[UpdateInfo]:
    """
    Query the configured channel for a newer release.

    Returns an UpdateInfo if a newer version exists and a matching binary
    asset is found.  Returns None if already up-to-date or no asset matches.
    Raises requests.exceptions.RequestException on network failures.
    """
    url = _channel_url()
    resp = _session().get(url, timeout=10)
    resp.raise_for_status()
    data = resp.json()

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
    fd, tmp = tempfile.mkstemp(suffix=".new", prefix="calsec_upd_")
    os.close(fd)

    try:
        with _session().get(info.download_url, timeout=120, stream=True) as resp:
            resp.raise_for_status()
            total = int(resp.headers.get("Content-Length", 0))
            done = 0
            with open(tmp, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if not chunk:
                        continue
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
      - Signature file not found (HTTP 404) → fail closed
      - Signature present but invalid → raises ValueError
    """
    if not _RELEASE_PUBLIC_KEY_PEM:
        return

    import requests

    sig_url = binary_url + ".sig"
    resp = _session().get(sig_url, timeout=15)
    if resp.status_code == 404:
        raise ValueError(
            "Signature verification failed — the release signature file is missing. "
            "Aborting update."
        )
    resp.raise_for_status()
    sig_b64 = resp.text.strip()

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

    Replaces the binary atomically, then spawns a detached fresh process with
    close_fds=True to avoid inheriting X11 sockets or other open handles.
    Falls back to copy+delete when tmp and exe live on different filesystems
    (EXDEV — common on Tails where /tmp is tmpfs).
    """
    import errno
    import shutil
    import subprocess

    exe = Path(sys.executable)

    mode = os.stat(new_binary).st_mode
    os.chmod(new_binary, mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)

    try:
        os.replace(new_binary, exe)
    except OSError as exc:
        if exc.errno in (errno.EXDEV, errno.ETXTBSY):
            # EXDEV:   /tmp and install dir are on different filesystems (common on Tails)
            # ETXTBSY: binary is currently executing — unlink first, then copy
            try:
                os.unlink(exe)
            except OSError:
                pass
            shutil.copy2(new_binary, exe)
            os.unlink(new_binary)
        else:
            raise

    subprocess.Popen(
        [str(exe)] + sys.argv[1:],
        close_fds=True,
        start_new_session=True,  # detach from parent terminal
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    os._exit(0)  # hard exit — bypasses tkinter mainloop to close all windows
