"""
Persistent app settings.

On Tails, settings are stored inside the Dotfiles persistent directory so they
survive reboots together with the rest of the Dotfiles payload.
"""

import json
import os
import tempfile

_LEGACY_DIR = os.path.join(os.path.expanduser("~"), ".calsec")
_TAILS_PERSISTENT_ROOT = "/live/persistence/TailsData_unlocked"
_TAILS_DOTFILES_DIR = os.path.join(_TAILS_PERSISTENT_ROOT, "dotfiles")


def _settings_dir() -> str:
    if os.path.isdir(_TAILS_PERSISTENT_ROOT):
        return os.path.join(_TAILS_DOTFILES_DIR, ".calsec")
    return _LEGACY_DIR


_DIR = _settings_dir()
_FILE = os.path.join(_DIR, "settings.json")
_LEGACY_FILE = os.path.join(_LEGACY_DIR, "settings.json")

_DEFAULTS: dict = {
    "theme": "dark",
    "language": "en",
    # Update settings (only relevant for frozen/PyInstaller builds)
    "updates_enabled": False,
    "update_mode": "notify",    # "auto" | "notify"
    "update_channel": "official",  # "official" | custom URL string
}
_current:  dict = dict(_DEFAULTS)


def load() -> None:
    global _current
    for path in (_FILE, _LEGACY_FILE):
        if not path or not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                _current = {**_DEFAULTS, **json.load(f)}
            return
        except Exception:
            pass
    _current = dict(_DEFAULTS)


def save() -> None:
    os.makedirs(_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(prefix=".tmp-", dir=_DIR)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(_current, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, _FILE)
    finally:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)


def get(key: str):
    return _current.get(key, _DEFAULTS.get(key))


def set(key: str, value) -> None:
    _current[key] = value
    save()
