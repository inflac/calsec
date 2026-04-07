"""
Persistent app settings stored in ~/.calsec/settings.json.
"""

import json
import os
import tempfile

_DIR  = os.path.join(os.path.expanduser("~"), ".calsec")
_FILE = os.path.join(_DIR, "settings.json")

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
    try:
        with open(_FILE) as f:
            _current = {**_DEFAULTS, **json.load(f)}
    except Exception:
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
