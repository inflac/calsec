"""
Persistent app settings stored in ~/.calsec/settings.json.
"""

import json
import os

_DIR  = os.path.join(os.path.expanduser("~"), ".calsec")
_FILE = os.path.join(_DIR, "settings.json")

_DEFAULTS: dict = {"theme": "dark"}
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
    with open(_FILE, "w") as f:
        json.dump(_current, f, indent=2)


def get(key: str):
    return _current.get(key, _DEFAULTS.get(key))


def set(key: str, value) -> None:
    _current[key] = value
    save()
