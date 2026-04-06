import json
import os
import pytest

import gui.settings as settings


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    fake_dir  = str(tmp_path / ".calsec")
    fake_file = os.path.join(fake_dir, "settings.json")
    monkeypatch.setattr(settings, "_DIR",     fake_dir)
    monkeypatch.setattr(settings, "_FILE",    fake_file)
    monkeypatch.setattr(settings, "_current", dict(settings._DEFAULTS))


# ── defaults ──────────────────────────────────────────────────────────────────

def test_default_theme():
    assert settings.get("theme") == "dark"


def test_default_language():
    assert settings.get("language") == "en"


def test_default_updates_disabled():
    assert settings.get("updates_enabled") is False


def test_default_update_mode():
    assert settings.get("update_mode") == "notify"


def test_default_update_channel():
    assert settings.get("update_channel") == "official"


def test_unknown_key_returns_none():
    assert settings.get("nonexistent_key") is None


# ── load ──────────────────────────────────────────────────────────────────────

def test_load_uses_defaults_when_no_file():
    settings.load()
    assert settings.get("theme") == "dark"


def test_load_reads_saved_value():
    os.makedirs(settings._DIR)
    with open(settings._FILE, "w") as f:
        json.dump({"theme": "light"}, f)
    settings.load()
    assert settings.get("theme") == "light"


def test_load_merges_missing_keys_with_defaults():
    os.makedirs(settings._DIR)
    with open(settings._FILE, "w") as f:
        json.dump({"theme": "light"}, f)
    settings.load()
    assert settings.get("language") == "en"
    assert settings.get("updates_enabled") is False


def test_load_handles_corrupt_file():
    os.makedirs(settings._DIR)
    with open(settings._FILE, "w") as f:
        f.write("}{invalid json")
    settings.load()
    assert settings.get("theme") == "dark"


# ── set / get ─────────────────────────────────────────────────────────────────

def test_set_updates_in_memory():
    settings.set("theme", "light")
    assert settings.get("theme") == "light"


def test_set_persists_to_file():
    settings.set("theme", "light")
    with open(settings._FILE) as f:
        data = json.load(f)
    assert data["theme"] == "light"


def test_set_update_mode():
    settings.set("update_mode", "auto")
    assert settings.get("update_mode") == "auto"


def test_set_custom_channel():
    url = "https://my-mirror.example.com/releases"
    settings.set("update_channel", url)
    assert settings.get("update_channel") == url


def test_set_creates_directory():
    assert not os.path.exists(settings._DIR)
    settings.set("theme", "light")
    assert os.path.exists(settings._DIR)


# ── save / load roundtrip ─────────────────────────────────────────────────────

def test_save_load_roundtrip():
    settings.set("theme", "light")
    settings.set("language", "de")
    settings.set("updates_enabled", True)
    settings.load()
    assert settings.get("theme") == "light"
    assert settings.get("language") == "de"
    assert settings.get("updates_enabled") is True
