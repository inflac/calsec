import json
import os
import pytest
from unittest import mock

import gui.storage as storage


# ---------- Helpers ----------

@pytest.fixture
def temp_base(tmp_path, monkeypatch):
    """
    Isoliert BASE_DIR auf ein temporäres Verzeichnis,
    damit keine echten Dateien angefasst werden.
    """
    monkeypatch.setattr(storage, "BASE_DIR", str(tmp_path))

    # Dateien neu definieren
    storage.DATA_FILE = os.path.join(tmp_path, "calendar.json")
    storage.KEY_PRIVATE = os.path.join(tmp_path, "calsec_private.pem")
    storage.KEY_PUBLIC = os.path.join(tmp_path, "calsec_public.pem")

    return tmp_path


# ---------- keys_exist ----------

def test_keys_exist_false(temp_base):
    assert storage.keys_exist() is False


def test_keys_exist_true(temp_base):
    open(storage.KEY_PRIVATE, "w").close()
    open(storage.KEY_PUBLIC, "w").close()

    assert storage.keys_exist() is True


# ---------- load_file ----------

def test_load_file_empty(temp_base):
    entries, sync, version, sig = storage.load_file()

    assert entries == []
    assert sync is None
    assert version == 0
    assert sig is None


def test_load_file_valid(temp_base):
    data = {
        "entries": [{"id": "1"}],
        "sync_config": {"foo": "bar"},
        "version": 5,
        "signature": "sig"
    }

    with open(storage.DATA_FILE, "w") as f:
        json.dump(data, f)

    entries, sync, version, sig = storage.load_file()

    assert entries == [{"id": "1"}]
    assert sync == {"foo": "bar"}
    assert version == 5
    assert sig == "sig"


def test_load_file_invalid(temp_base):
    with open(storage.DATA_FILE, "w") as f:
        f.write("not json")

    with pytest.raises(RuntimeError):
        storage.load_file()


# ---------- save_file ----------

def test_save_and_load_roundtrip(temp_base):
    entries = [{"id": "1"}]

    storage.save_file(entries, sync_config_enc="sync", version=1, signature="sig")

    assert os.path.exists(storage.DATA_FILE)

    with open(storage.DATA_FILE) as f:
        data = json.load(f)

    assert data["entries"] == entries
    assert data["version"] == 1
    assert data["sync_config"] == "sync"
    assert data["signature"] == "sig"


def test_save_file_failure(temp_base, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("fail")

    monkeypatch.setattr("builtins.open", fail)

    with pytest.raises(RuntimeError):
        storage.save_file([], None, 0, None)


# ---------- load_private_key ----------

def test_load_private_key_missing(temp_base):
    with pytest.raises(FileNotFoundError):
        storage.load_private_key(b"pw")


def test_load_private_key_invalid(temp_base):
    with open(storage.KEY_PRIVATE, "w") as f:
        f.write("invalid key")

    with pytest.raises(ValueError):
        storage.load_private_key(b"pw")


# ---------- load_public_key ----------

def test_load_public_key_missing(temp_base):
    with pytest.raises(FileNotFoundError):
        storage.load_public_key()


def test_load_public_key_invalid(temp_base):
    with open(storage.KEY_PUBLIC, "w") as f:
        f.write("invalid key")

    with pytest.raises(RuntimeError):
        storage.load_public_key()


# ---------- provision ----------

def test_provision_creates_files(temp_base, monkeypatch):
    password = b"testpass"

    # crypto mocken (wichtig → keine echte Kryptographie nötig)
    monkeypatch.setattr(storage, "encrypt_entry", lambda e, p: "enc")
    monkeypatch.setattr(storage, "sign_file", lambda *args, **kwargs: "sig")

    # load_file mocken → keine vorhandene Datei nötig
    monkeypatch.setattr(storage, "load_file", lambda: ([], None, 0, None))

    sync_data = {
        "url": "http://test",
        "user": "user",
        "password": "pw",
        "remote_path": "/path"
    }

    storage.provision(password, sync_data)

    assert os.path.exists(storage.KEY_PRIVATE)
    assert os.path.exists(storage.KEY_PUBLIC)
    assert os.path.exists(storage.DATA_FILE)


def test_provision_without_sync(temp_base, monkeypatch):
    password = b"testpass"

    monkeypatch.setattr(storage, "encrypt_entry", lambda e, p: "enc")
    monkeypatch.setattr(storage, "sign_file", lambda *args, **kwargs: "sig")
    monkeypatch.setattr(storage, "load_file", lambda: ([], None, 0, None))

    storage.provision(password, None)

    with open(storage.DATA_FILE) as f:
        data = json.load(f)

    assert data["sync_config"] is None
    assert data["version"] == 1


def test_provision_write_failure(temp_base, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("fail")

    monkeypatch.setattr("builtins.open", fail)

    with pytest.raises(RuntimeError):
        storage.provision(b"pw", None)