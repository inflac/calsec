import sys

import gui.updater as updater
import pytest

# ── is_frozen ─────────────────────────────────────────────────────────────────

def test_is_frozen_false_in_tests():
    assert updater.is_frozen() is False


def test_is_frozen_true_when_meipass_set(monkeypatch):
    monkeypatch.setattr(sys, "_MEIPASS", "/tmp/fake", raising=False)
    assert updater.is_frozen() is True


# ── _version_tuple ────────────────────────────────────────────────────────────

def test_version_tuple_basic():
    assert updater._version_tuple("1.2.3") == (1, 2, 3)


def test_version_tuple_strips_v_prefix():
    assert updater._version_tuple("v2.0.0") == (2, 0, 0)


def test_version_tuple_single_digit():
    assert updater._version_tuple("5") == (5,)


def test_version_tuple_invalid_returns_zero():
    assert updater._version_tuple("not-a-version") == (0,)


def test_version_tuple_ordering():
    assert updater._version_tuple("1.10.0") > updater._version_tuple("1.9.0")


# ── current_version ───────────────────────────────────────────────────────────

def test_current_version_returns_string():
    assert isinstance(updater.current_version(), str)


def test_current_version_fallback_when_no_module(monkeypatch):
    monkeypatch.setitem(sys.modules, "version", None)
    assert updater.current_version() == "0.0.0"


# ── _asset_name ───────────────────────────────────────────────────────────────

def test_asset_name_linux(monkeypatch):
    monkeypatch.setattr(sys, "platform", "linux")
    assert updater._asset_name() == "calsec-linux"


def test_asset_name_non_linux_returns_empty(monkeypatch):
    monkeypatch.setattr(sys, "platform", "freebsd")
    assert updater._asset_name() == ""


# ── _channel_url ──────────────────────────────────────────────────────────────

def test_channel_url_returns_official_by_default(monkeypatch):
    import settings
    monkeypatch.setattr(settings, "_current", {"update_channel": "official"})
    assert updater._channel_url() == updater.OFFICIAL_CHANNEL


def test_channel_url_returns_custom(monkeypatch):
    import settings
    url = "https://my-mirror.example.com/releases/latest"
    monkeypatch.setattr(settings, "_current", {"update_channel": url})
    assert updater._channel_url() == url


def test_channel_url_falls_back_when_empty(monkeypatch):
    import settings
    monkeypatch.setattr(settings, "_current", {"update_channel": ""})
    assert updater._channel_url() == updater.OFFICIAL_CHANNEL


def test_verify_release_signature_fails_when_sig_missing(monkeypatch, tmp_path):
    binary = tmp_path / "calsec-linux"
    binary.write_bytes(b"binary")

    class FakeResponse:
        status_code = 404
        text = ""

        def raise_for_status(self):
            return None

    monkeypatch.setattr(updater, "_session", lambda: type("S", (), {
        "get": staticmethod(lambda *a, **kw: FakeResponse())
    })())

    with pytest.raises(ValueError, match="missing"):
        updater._verify_release_signature(binary, "https://example.com/calsec-linux")
