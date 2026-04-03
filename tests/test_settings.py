import json
import os
import pytest

import gui.settings as settings


# ---------- Isolation ----------

@pytest.fixture(autouse=True)
def isolate_settings(tmp_path, monkeypatch):
    """
    Patcht _DIR, _FILE und _current direkt, da diese Modul-Level-Konstanten
    beim Import berechnet werden — expanduser zu patchen wäre zu spät.
    """
    fake_dir  = str(tmp_path / "home" / ".calsec")
    fake_file = os.path.join(fake_dir, "settings.json")

    monkeypatch.setattr(settings, "_DIR",     fake_dir)
    monkeypatch.setattr(settings, "_FILE",    fake_file)
    # _current zwischen Tests zurücksetzen
    monkeypatch.setattr(settings, "_current", dict(settings._DEFAULTS))


# ---------- load ----------

def test_load_defaults_when_no_file():
    settings.load()
    assert settings.get("theme") == "dark"


def test_load_existing_settings():
    fake_dir  = settings._DIR
    fake_file = settings._FILE

    os.makedirs(fake_dir, exist_ok=True)
    with open(fake_file, "w") as f:
        json.dump({"theme": "light"}, f)

    settings.load()

    assert settings.get("theme") == "light"


def test_load_merges_defaults():
    fake_dir  = settings._DIR
    fake_file = settings._FILE

    os.makedirs(fake_dir, exist_ok=True)
    with open(fake_file, "w") as f:
        json.dump({"custom": "value"}, f)

    settings.load()

    assert settings.get("theme") == "dark"   # Default bleibt erhalten
    assert settings.get("custom") == "value"


# ---------- save ----------

def test_save_writes_file():
    settings.set("theme", "light")  # triggert save()

    assert os.path.exists(settings._FILE)

    with open(settings._FILE) as f:
        data = json.load(f)

    assert data["theme"] == "light"


# ---------- get ----------

def test_get_returns_value():
    settings.set("theme", "light")
    assert settings.get("theme") == "light"


def test_get_returns_default():
    assert settings.get("nonexistent_key") is None


# ---------- set ----------

def test_set_updates_value():
    settings.set("theme", "light")

    assert settings.get("theme") == "light"

    with open(settings._FILE) as f:
        data = json.load(f)

    assert data["theme"] == "light"
