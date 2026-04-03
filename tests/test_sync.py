import os
import types
import pytest

import gui.sync as sync_module


class _Dummy(Exception):
    """Platzhalter-Exception für Typen, die im jeweiligen Test nicht ausgelöst werden."""


def _exc_ns(**overrides):
    """
    Baut einen SimpleNamespace mit allen vier Exception-Typen die sync.py referenziert.
    sync.py evaluiert alle except-Klauseln der Reihe nach — fehlt ein Attribut,
    gibt es einen AttributeError noch bevor der passende Handler gefunden wird.
    """
    base = {
        "MissingSchema":   _Dummy,
        "SSLError":        _Dummy,
        "ConnectionError": _Dummy,
        "Timeout":         _Dummy,
    }
    base.update(overrides)
    return types.SimpleNamespace(**base)


# ---------- Helpers ----------

@pytest.fixture
def temp_file(tmp_path, monkeypatch):
    """
    Erzeugt eine temporäre calendar.json
    """
    data_file = tmp_path / "calendar.json"
    data_file.write_text('{"test": 1}')

    monkeypatch.setattr(sync_module, "DATA_FILE", str(data_file))
    return data_file


def make_config():
    return {
        "url": "https://example.com",
        "user": "user",
        "password": "pw",
        "remote_path": "/file.json"
    }


# ---------- basic ----------

def test_sync_no_config():
    assert sync_module.sync(None) is None


def test_sync_requests_missing(monkeypatch, temp_file):
    monkeypatch.setitem(__import__("sys").modules, "requests", None)

    result = sync_module.sync(make_config())

    assert "not installed" in result

# ---------- file handling ----------

def test_sync_file_missing(monkeypatch):
    monkeypatch.setattr(sync_module, "DATA_FILE", "/nonexistent/file.json")

    result = sync_module.sync(make_config())

    assert "not found" in result


def test_sync_file_read_error(monkeypatch, temp_file):
    def fail(*args, **kwargs):
        raise OSError

    monkeypatch.setattr("builtins.open", fail)

    result = sync_module.sync(make_config())

    assert "Failed to read" in result


# ---------- request success ----------

def test_sync_success(monkeypatch, temp_file):
    class FakeResponse:
        status_code = 200

    def fake_put(*args, **kwargs):
        return FakeResponse()

    fake_requests = types.SimpleNamespace(
        put=fake_put,
        exceptions=types.SimpleNamespace()
    )

    monkeypatch.setitem(__import__("sys").modules, "requests", fake_requests)

    result = sync_module.sync(make_config())

    assert "Synced to" in result


# ---------- HTTP status handling ----------

@pytest.mark.parametrize("code,msg", [
    (401, "Authentication failed"),
    (403, "Access denied"),
    (404, "Remote directory"),
    (500, "Unexpected response"),
])
def test_sync_http_errors(monkeypatch, temp_file, code, msg):
    class FakeResponse:
        status_code = code

    def fake_put(*args, **kwargs):
        return FakeResponse()

    fake_requests = types.SimpleNamespace(
        put=fake_put,
        exceptions=types.SimpleNamespace()
    )

    monkeypatch.setitem(__import__("sys").modules, "requests", fake_requests)

    result = sync_module.sync(make_config())

    assert msg in result


# ---------- exceptions ----------

def test_sync_invalid_url(monkeypatch, temp_file):
    class MissingSchema(Exception):
        pass

    def fake_put(*args, **kwargs):
        raise MissingSchema()

    fake_requests = types.SimpleNamespace(
        put=fake_put,
        exceptions=_exc_ns(MissingSchema=MissingSchema),
    )

    monkeypatch.setitem(__import__("sys").modules, "requests", fake_requests)

    result = sync_module.sync(make_config())

    assert "Ungültige URL" in result


def test_sync_ssl_error(monkeypatch, temp_file):
    class SSLError(Exception):
        pass

    def fake_put(*args, **kwargs):
        raise SSLError()

    fake_requests = types.SimpleNamespace(
        put=fake_put,
        exceptions=_exc_ns(SSLError=SSLError),
    )

    monkeypatch.setitem(__import__("sys").modules, "requests", fake_requests)

    result = sync_module.sync(make_config())

    assert "SSL certificate" in result


def test_sync_connection_error(monkeypatch, temp_file):
    class ConnectionError(Exception):
        pass

    def fake_put(*args, **kwargs):
        raise ConnectionError()

    fake_requests = types.SimpleNamespace(
        put=fake_put,
        exceptions=_exc_ns(ConnectionError=ConnectionError),
    )

    monkeypatch.setitem(__import__("sys").modules, "requests", fake_requests)

    result = sync_module.sync(make_config())

    assert "Could not connect" in result


def test_sync_timeout(monkeypatch, temp_file):
    class Timeout(Exception):
        pass

    def fake_put(*args, **kwargs):
        raise Timeout()

    fake_requests = types.SimpleNamespace(
        put=fake_put,
        exceptions=_exc_ns(Timeout=Timeout),
    )

    monkeypatch.setitem(__import__("sys").modules, "requests", fake_requests)

    result = sync_module.sync(make_config())

    assert "timed out" in result