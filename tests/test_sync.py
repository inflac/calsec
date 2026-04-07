import json
import sys
import types

import gui.i18n as i18n
import gui.sync as sync_module
import pytest


class _Dummy(Exception):
    pass


def _exc_ns(**overrides):
    base = {
        "MissingSchema":   _Dummy,
        "SSLError":        _Dummy,
        "ConnectionError": _Dummy,
        "Timeout":         _Dummy,
    }
    base.update(overrides)
    return types.SimpleNamespace(**base)


def _make_config(url="https://example.com/dav"):
    return {"webdav_url": url, "auth_user": "user", "password": "pw"}


@pytest.fixture
def calendar_file(tmp_path, monkeypatch):
    f = tmp_path / "calendar.json"
    f.write_text(json.dumps({"version": 4, "entries": []}))
    monkeypatch.setattr(sync_module, "DATA_FILE", str(f))
    return f


def _fake_put(status=200):
    class FakeResponse:
        status_code = status
    return types.SimpleNamespace(
        put=lambda *a, **kw: FakeResponse(),
        exceptions=_exc_ns(),
    )


def _fake_get(status=200, body=None):
    class FakeResponse:
        status_code = status
        content = json.dumps(body or {}).encode()
        text    = json.dumps(body or {})
        headers = {"Content-Type": "application/json"}
    return types.SimpleNamespace(
        get=lambda *a, **kw: FakeResponse(),
        exceptions=_exc_ns(),
    )


# ── _calendar_url ─────────────────────────────────────────────────────────────

def test_calendar_url_appends_filename():
    assert sync_module._calendar_url(_make_config("https://cloud.example.com/dav/folder")) \
        == "https://cloud.example.com/dav/folder/calendar.json"


def test_calendar_url_strips_trailing_slash():
    assert sync_module._calendar_url(_make_config("https://cloud.example.com/dav/folder/")) \
        == "https://cloud.example.com/dav/folder/calendar.json"


# ── sync_push ─────────────────────────────────────────────────────────────────

def test_push_none_config_returns_none():
    assert sync_module.sync_push(None) is None


def test_push_requests_not_installed(monkeypatch, calendar_file):
    monkeypatch.setitem(sys.modules, "requests", None)
    assert sync_module.sync_push(_make_config()) == i18n._("sync_err_no_requests")


def test_push_missing_file(monkeypatch):
    monkeypatch.setattr(sync_module, "DATA_FILE", "/nonexistent/calendar.json")
    result = sync_module.sync_push(_make_config())
    assert result == i18n._("sync_file_not_found").format(file="/nonexistent/calendar.json")


def test_push_file_read_error(monkeypatch, calendar_file):
    original_open = open
    def fail_open(path, mode="r", **kw):
        if "rb" in mode and str(calendar_file) in str(path):
            raise OSError("read failed")
        return original_open(path, mode, **kw)
    monkeypatch.setattr("builtins.open", fail_open)
    assert sync_module.sync_push(_make_config()) == i18n._("sync_err_read_failed")


def test_push_success(monkeypatch, calendar_file):
    monkeypatch.setitem(sys.modules, "requests", _fake_put(201))
    assert "201" in sync_module.sync_push(_make_config())


def test_push_success_204(monkeypatch, calendar_file):
    monkeypatch.setitem(sys.modules, "requests", _fake_put(204))
    assert "204" in sync_module.sync_push(_make_config())


@pytest.mark.parametrize("code,key", [
    (401, "sync_err_auth"),
    (403, "sync_err_access_denied"),
    (404, "sync_err_path_not_found"),
    (500, "sync_err_unexpected"),
])
def test_push_http_errors(monkeypatch, calendar_file, code, key):
    monkeypatch.setitem(sys.modules, "requests", _fake_put(code))
    result = sync_module.sync_push(_make_config())
    assert i18n._(key).format(code=code) in result


def _push_exc(exc_cls, exc_name):
    def fake_put(*a, **kw):
        raise exc_cls()
    return types.SimpleNamespace(
        put=fake_put,
        exceptions=_exc_ns(**{exc_name: exc_cls}),
    )


def test_push_ssl_error(monkeypatch, calendar_file):
    class SSLError(Exception):
        pass
    monkeypatch.setitem(sys.modules, "requests", _push_exc(SSLError, "SSLError"))
    assert sync_module.sync_push(_make_config()) == i18n._("sync_err_ssl")


def test_push_connection_error(monkeypatch, calendar_file):
    class ConnectionError(Exception):
        pass
    monkeypatch.setitem(sys.modules, "requests", _push_exc(ConnectionError, "ConnectionError"))
    assert sync_module.sync_push(_make_config()) == i18n._("sync_err_connection")


def test_push_timeout(monkeypatch, calendar_file):
    class Timeout(Exception):
        pass
    monkeypatch.setitem(sys.modules, "requests", _push_exc(Timeout, "Timeout"))
    assert sync_module.sync_push(_make_config()) == i18n._("sync_err_timeout")


def test_push_missing_schema(monkeypatch, calendar_file):
    class MissingSchema(Exception):
        pass
    url = sync_module._calendar_url(_make_config())
    monkeypatch.setitem(sys.modules, "requests", _push_exc(MissingSchema, "MissingSchema"))
    assert sync_module.sync_push(_make_config()) == i18n._("sync_err_invalid_url").format(url=url)


# ── sync_pull ─────────────────────────────────────────────────────────────────

def test_pull_none_config_returns_none():
    data, _ = sync_module.sync_pull(None)
    assert data is None


def test_pull_requests_not_installed(monkeypatch):
    monkeypatch.setitem(sys.modules, "requests", None)
    data, msg = sync_module.sync_pull(_make_config())
    assert data is None
    assert msg == i18n._("sync_err_no_requests")


def test_pull_success(monkeypatch):
    payload = {"version": 4, "entries": [], "users": {}}
    monkeypatch.setitem(sys.modules, "requests", _fake_get(200, payload))
    data, msg = sync_module.sync_pull(_make_config())
    assert data == payload


def test_pull_404(monkeypatch):
    monkeypatch.setitem(sys.modules, "requests", _fake_get(404))
    data, msg = sync_module.sync_pull(_make_config())
    assert data is None


def test_pull_401(monkeypatch):
    monkeypatch.setitem(sys.modules, "requests", _fake_get(401))
    data, msg = sync_module.sync_pull(_make_config())
    assert data is None
    assert msg == i18n._("sync_err_auth")


def test_pull_unexpected_status(monkeypatch):
    monkeypatch.setitem(sys.modules, "requests", _fake_get(500))
    data, msg = sync_module.sync_pull(_make_config())
    assert data is None
    assert msg == i18n._("sync_err_unexpected").format(code=500)


def test_pull_invalid_json(monkeypatch):
    class FakeResponse:
        status_code = 200
        content = b"<html>not json</html>"
        text    = "<html>not json</html>"
        headers = {"Content-Type": "text/html"}
    monkeypatch.setitem(sys.modules, "requests", types.SimpleNamespace(
        get=lambda *a, **kw: FakeResponse(), exceptions=_exc_ns()))
    data, msg = sync_module.sync_pull(_make_config())
    assert data is None
    assert "JSON" in i18n._("sync_err_invalid_json")


def _pull_exc(exc_cls, exc_name):
    def fake_get(*a, **kw):
        raise exc_cls()
    return types.SimpleNamespace(
        get=fake_get,
        exceptions=_exc_ns(**{exc_name: exc_cls}),
    )


def test_pull_connection_error(monkeypatch):
    class ConnectionError(Exception):
        pass
    monkeypatch.setitem(sys.modules, "requests", _pull_exc(ConnectionError, "ConnectionError"))
    data, msg = sync_module.sync_pull(_make_config())
    assert data is None
    assert msg == i18n._("sync_err_connection")


def test_pull_ssl_error(monkeypatch):
    class SSLError(Exception):
        pass
    monkeypatch.setitem(sys.modules, "requests", _pull_exc(SSLError, "SSLError"))
    data, msg = sync_module.sync_pull(_make_config())
    assert data is None
    assert msg == i18n._("sync_err_ssl")


def test_pull_timeout(monkeypatch):
    class Timeout(Exception):
        pass
    monkeypatch.setitem(sys.modules, "requests", _pull_exc(Timeout, "Timeout"))
    data, msg = sync_module.sync_pull(_make_config())
    assert data is None
    assert msg == i18n._("sync_err_timeout")


def test_pull_missing_schema(monkeypatch):
    class MissingSchema(Exception):
        pass
    url = sync_module._calendar_url(_make_config())
    monkeypatch.setitem(sys.modules, "requests", _pull_exc(MissingSchema, "MissingSchema"))
    data, msg = sync_module.sync_pull(_make_config())
    assert data is None
    assert msg == i18n._("sync_err_invalid_url").format(url=url)
