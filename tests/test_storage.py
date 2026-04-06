import json
import os
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization

import gui.storage as storage


@pytest.fixture(autouse=True)
def isolate(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "BASE_DIR",  str(tmp_path))
    monkeypatch.setattr(storage, "KEYS_DIR",  str(tmp_path / "keys"))
    monkeypatch.setattr(storage, "DATA_FILE", str(tmp_path / "calendar.json"))


# ── email_to_hash ─────────────────────────────────────────────────────────────

def test_email_to_hash_length():
    assert len(storage.email_to_hash("alice@example.com")) == 16


def test_email_to_hash_uses_localpart_only():
    h1 = storage.email_to_hash("alice@example.com")
    h2 = storage.email_to_hash("alice@other.org")
    assert h1 == h2


def test_email_to_hash_case_insensitive():
    assert storage.email_to_hash("Alice@example.com") == storage.email_to_hash("alice@example.com")


def test_email_to_hash_different_users():
    assert storage.email_to_hash("alice@x.com") != storage.email_to_hash("bob@x.com")


# ── find_user_key_hashes ──────────────────────────────────────────────────────

def test_find_user_key_hashes_empty_when_no_dir():
    assert storage.find_user_key_hashes() == []


def test_find_user_key_hashes_returns_pem_stems(tmp_path, monkeypatch):
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    monkeypatch.setattr(storage, "KEYS_DIR", str(keys_dir))
    (keys_dir / "abcd1234abcd1234.pem").write_text("key")
    (keys_dir / "ignored.txt").write_text("not a key")
    result = storage.find_user_key_hashes()
    assert result == ["abcd1234abcd1234"]


# ── load_file_raw ─────────────────────────────────────────────────────────────

def test_load_file_raw_returns_empty_when_missing():
    assert storage.load_file_raw() == {}


def test_load_file_raw_returns_dict():
    data = {"version": 4, "entries": []}
    with open(storage.DATA_FILE, "w") as f:
        json.dump(data, f)
    result = storage.load_file_raw()
    assert result["version"] == 4
    assert result["entries"] == []


def test_load_file_raw_raises_on_invalid_json():
    with open(storage.DATA_FILE, "w") as f:
        f.write("not json{{{")
    with pytest.raises(RuntimeError):
        storage.load_file_raw()


# ── save_file ─────────────────────────────────────────────────────────────────

def test_save_file_writes_json():
    data = {"version": 4, "entries": [], "users": {}}
    storage.save_file(data)
    with open(storage.DATA_FILE) as f:
        loaded = json.load(f)
    assert loaded == data


def test_save_and_load_roundtrip():
    data = {"version": 4, "entries": [{"id": "1"}], "sig_users": "abc"}
    storage.save_file(data)
    assert storage.load_file_raw() == data


def test_save_file_raises_on_write_failure(monkeypatch):
    monkeypatch.setattr(storage, "DATA_FILE", "/nonexistent/dir/calendar.json")
    with pytest.raises(RuntimeError, match="Failed to write"):
        storage.save_file({"version": 4})


# ── is_provisioned ────────────────────────────────────────────────────────────

def test_is_provisioned_false_when_no_file():
    assert storage.is_provisioned() is False


def test_is_provisioned_false_when_no_users():
    storage.save_file({"version": 4, "users": {}})
    assert storage.is_provisioned() is False


def test_is_provisioned_true_when_users_present():
    storage.save_file({"version": 4, "users": {"abc": {"role": "admin"}}})
    assert storage.is_provisioned() is True


# ── save_user_key_file / load_user_private_key ────────────────────────────────

def _generate_pem_key(password: bytes | None = None):
    kpriv = ec.generate_private_key(ec.SECP256R1())
    return kpriv


def test_save_and_load_user_key_no_password(tmp_path, monkeypatch):
    keys_dir = tmp_path / "keys"
    monkeypatch.setattr(storage, "KEYS_DIR", str(keys_dir))
    kpriv = _generate_pem_key()
    storage.save_user_key_file("testhash1234abcd", kpriv, None)
    loaded = storage.load_user_private_key("testhash1234abcd", None)
    assert loaded.private_numbers() == kpriv.private_numbers()


def test_save_and_load_user_key_with_password(tmp_path, monkeypatch):
    keys_dir = tmp_path / "keys"
    monkeypatch.setattr(storage, "KEYS_DIR", str(keys_dir))
    kpriv    = _generate_pem_key()
    pw       = b"s3cr3tpassword"
    storage.save_user_key_file("testhash1234abcd", kpriv, pw)
    loaded = storage.load_user_private_key("testhash1234abcd", pw)
    assert loaded.private_numbers() == kpriv.private_numbers()


def test_load_user_private_key_wrong_password(tmp_path, monkeypatch):
    keys_dir = tmp_path / "keys"
    monkeypatch.setattr(storage, "KEYS_DIR", str(keys_dir))
    storage.save_user_key_file("testhash1234abcd", _generate_pem_key(), b"correct")
    with pytest.raises(ValueError):
        storage.load_user_private_key("testhash1234abcd", b"wrong")


def test_load_user_private_key_missing(tmp_path, monkeypatch):
    keys_dir = tmp_path / "keys"
    keys_dir.mkdir()
    monkeypatch.setattr(storage, "KEYS_DIR", str(keys_dir))
    with pytest.raises(FileNotFoundError):
        storage.load_user_private_key("nonexistent", None)


# ── provision ─────────────────────────────────────────────────────────────────

def test_provision_creates_calendar_file():
    storage.provision("admin@example.com", b"password123", None)
    assert os.path.exists(storage.DATA_FILE)


def test_provision_calendar_structure():
    storage.provision("admin@example.com", b"password123", None)
    data = storage.load_file_raw()
    assert data["version"] == 4
    assert "sign_keys" in data
    assert "users" in data
    assert "entries" in data
    assert "sig_users" in data
    assert "sig_entries" in data


def test_provision_creates_admin_key_file():
    storage.provision("admin@example.com", b"password123", None)
    h = storage.email_to_hash("admin@example.com")
    assert os.path.exists(os.path.join(storage.KEYS_DIR, f"{h}.pem"))


def test_provision_admin_key_loadable():
    pw = b"testpassword"
    storage.provision("admin@example.com", pw, None)
    h = storage.email_to_hash("admin@example.com")
    key = storage.load_user_private_key(h, pw)
    assert key is not None


def test_provision_with_sync_data():
    sync = {"webdav_url": "https://example.com/dav", "auth_user": "u", "password": "p"}
    storage.provision("admin@example.com", b"pw12345678", sync)
    data = storage.load_file_raw()
    assert data["sync_config"] is not None


def test_provision_without_sync_data():
    storage.provision("admin@example.com", b"pw12345678", None)
    data = storage.load_file_raw()
    assert data["sync_config"] is None


def test_provision_marks_as_provisioned():
    assert storage.is_provisioned() is False
    storage.provision("admin@example.com", b"pw12345678", None)
    assert storage.is_provisioned() is True
