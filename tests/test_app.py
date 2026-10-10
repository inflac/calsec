"""Integration tests for CalendarApp — provisions real storage, no mocking of crypto."""
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import load_pem_private_key
from gui.app import CalendarApp

import storage
from crypto import ecies_decrypt

ADMIN_IDENTIFIER = "admin@example.com"
ADMIN_PW         = b"testpassword123"


@pytest.fixture()
def provisioned(tmp_path, monkeypatch):
    """Provision a fresh calendar and return (CalendarApp, admin_hash)."""
    monkeypatch.setattr(storage, "BASE_DIR",  str(tmp_path))
    monkeypatch.setattr(storage, "KEYS_DIR",  str(tmp_path / "keys"))
    monkeypatch.setattr(storage, "DATA_FILE", str(tmp_path / "calendar.json"))

    storage.provision(ADMIN_IDENTIFIER, ADMIN_PW, None)

    h = storage.identifier_to_hash(ADMIN_IDENTIFIER)
    kpriv_user = storage.load_user_private_key(h, ADMIN_PW)

    raw        = storage.load_file_raw()
    user_entry = raw["users"][h]
    sym_key_cal = ecies_decrypt(kpriv_user, user_entry["sym_key_cal_enc"])

    pem = ecies_decrypt(kpriv_user, user_entry["admin_sign_key_enc"])
    kpriv_admin_sign = load_pem_private_key(pem, password=None)

    pem = ecies_decrypt(kpriv_user, user_entry["edit_sign_key_enc"])
    kpriv_edit_sign = load_pem_private_key(pem, password=None)

    cal = CalendarApp(
        sym_key_cal,
        kpriv_admin_sign=kpriv_admin_sign,
        kpriv_edit_sign=kpriv_edit_sign,
        role="admin",
        user_hash=h,
    )
    return cal, h


# ── Properties ────────────────────────────────────────────────────────────────

def test_role_is_admin(provisioned):
    cal, _ = provisioned
    assert cal.role == "admin"


def test_is_admin_true(provisioned):
    cal, _ = provisioned
    assert cal.is_admin is True


def test_can_edit_true(provisioned):
    cal, _ = provisioned
    assert cal.can_edit is True


def test_sync_config_none_by_default(provisioned):
    cal, _ = provisioned
    assert cal.sync_config is None


def test_fingerprint_present(provisioned):
    cal, _ = provisioned
    assert len(cal.fingerprint) == 64


# ── Entries — initial state ───────────────────────────────────────────────────

def test_get_entries_initially_empty(provisioned):
    cal, _ = provisioned
    assert cal.get_entries() == []


def test_get_entries_for_month_initially_empty(provisioned):
    cal, _ = provisioned
    assert cal.get_entries_for_month(2026, 1) == []


# ── add_entry / get_entries ───────────────────────────────────────────────────

def test_add_entry_appears_in_get_entries(provisioned):
    cal, _ = provisioned
    cal.add_entry("Team Meeting", "15.01.2026", "10:00", [])
    entries = cal.get_entries()
    assert len(entries) == 1
    assert entries[0]["title"] == "Team Meeting"


def test_add_entry_appears_in_correct_month(provisioned):
    cal, _ = provisioned
    cal.add_entry("January Event", "20.01.2026", "all-day", [])
    cal.add_entry("February Event", "10.02.2026", "all-day", [])
    jan = cal.get_entries_for_month(2026, 1)
    feb = cal.get_entries_for_month(2026, 2)
    assert len(jan) == 1
    assert len(feb) == 1
    assert jan[0]["title"] == "January Event"


def test_add_entry_with_color(provisioned):
    cal, _ = provisioned
    cal.add_entry("Colored", "01.01.2026", "all-day", [], color="#ff0000")
    entries = cal.get_entries()
    assert entries[0]["color"] == "#ff0000"


def test_add_entry_with_comments(provisioned):
    cal, _ = provisioned
    cal.add_entry("With notes", "01.01.2026", "all-day", ["note 1", "note 2"])
    entries = cal.get_entries()
    assert entries[0]["comments"] == ["note 1", "note 2"]


def test_add_multiple_entries_sorted_by_timestamp(provisioned):
    cal, _ = provisioned
    cal.add_entry("Late",  "20.01.2026", "14:00", [])
    cal.add_entry("Early", "20.01.2026", "08:00", [])
    entries = cal.get_entries()
    assert entries[0]["title"] == "Early"
    assert entries[1]["title"] == "Late"


# ── update_entry ──────────────────────────────────────────────────────────────

def test_update_entry_changes_title(provisioned):
    cal, _ = provisioned
    cal.add_entry("Original", "15.01.2026", "10:00", [])
    entry_id = cal.get_entries()[0]["id"]
    cal.update_entry(entry_id, title="Updated", date_str="15.01.2026",
                     time_str="10:00", comments=[])
    assert cal.get_entries()[0]["title"] == "Updated"


def test_update_nonexistent_entry_is_noop(provisioned):
    cal, _ = provisioned
    cal.update_entry("nonexistent-id", title="X", date_str="01.01.2026",
                     time_str="all-day", comments=[])
    assert cal.get_entries() == []


# ── delete_entry ──────────────────────────────────────────────────────────────

def test_delete_entry_removes_it(provisioned):
    cal, _ = provisioned
    cal.add_entry("To delete", "01.01.2026", "all-day", [])
    entry_id = cal.get_entries()[0]["id"]
    assert cal.delete_entries([entry_id]) is True
    assert cal.get_entries() == []


def test_delete_nonexistent_entry_returns_false(provisioned):
    cal, _ = provisioned
    assert cal.delete_entries(["nonexistent-id"]) is False


# ── User management ───────────────────────────────────────────────────────────

def test_list_users_contains_admin(provisioned):
    cal, h = provisioned
    users = cal.list_users()
    assert any(u["hash"] == h for u in users)


def test_list_users_admin_role(provisioned):
    cal, h = provisioned
    users = cal.list_users()
    admin = next(u for u in users if u["hash"] == h)
    assert admin["role"] == "admin"


def test_add_user_registers_new_user(provisioned):
    cal, _ = provisioned
    fingerprint_before = cal.fingerprint
    kpriv_bytes = cal.add_user("newuser@example.com", None, b"userpass123", role="viewer")
    users = cal.list_users()
    identifiers = [u["identifier"] for u in users]
    assert "newuser@example.com" in identifiers
    assert kpriv_bytes is not None
    assert cal.fingerprint == fingerprint_before


def test_add_user_with_external_key(provisioned):
    cal, _ = provisioned
    kpriv = ec.generate_private_key(ec.SECP256R1())
    kpub  = kpriv.public_key()
    cal.add_user("external@example.com", kpub, None, role="viewer")
    identifiers = [u["identifier"] for u in cal.list_users()]
    assert "external@example.com" in identifiers


def test_add_user_non_admin_raises(provisioned):
    cal, _ = provisioned
    viewer_cal = CalendarApp(cal._sym_key_cal, role="viewer")
    with pytest.raises(RuntimeError):
        viewer_cal.add_user("x@example.com", None, b"pass12345", role="viewer")


def test_remove_user(provisioned):
    cal, _ = provisioned
    cal.add_user("todelete@example.com", None, b"pass12345", role="viewer")
    fingerprint_before = cal.fingerprint
    h = storage.identifier_to_hash("todelete@example.com")
    cal.remove_user(h)
    identifiers = [u["identifier"] for u in cal.list_users()]
    assert "todelete@example.com" not in identifiers
    assert cal.fingerprint == fingerprint_before


def test_remove_self_raises(provisioned):
    cal, h = provisioned
    with pytest.raises(RuntimeError):
        cal.remove_user(h)


def test_remove_user_non_admin_raises(provisioned):
    cal, _ = provisioned
    viewer_cal = CalendarApp(cal._sym_key_cal, role="viewer")
    with pytest.raises(RuntimeError):
        viewer_cal.remove_user("somehash")


# ── Signature verification on reload ─────────────────────────────────────────

def test_tampered_file_raises_on_reload(provisioned):
    cal, _ = provisioned
    raw = storage.load_file_raw()
    raw["sig_users"] = "invalidsignature=="
    storage.save_file(raw)
    with pytest.raises(RuntimeError, match="tampered"):
        cal._reload()


# ── Translated messages ───────────────────────────────────────────────────────

def test_errors_follow_selected_language(provisioned):
    import i18n
    cal, h = provisioned
    i18n.load("de")
    try:
        with pytest.raises(RuntimeError) as exc_info:
            cal.remove_user(h)
        assert str(exc_info.value) == i18n._("app_err_cannot_remove_self")
        assert "Konto" in str(exc_info.value)
    finally:
        i18n.load("en")


def test_sync_pull_without_config_reports_info_not_error(provisioned):
    import i18n
    cal, _ = provisioned
    results = []
    cal.sync_pull(on_done=lambda msg, is_error: results.append((msg, is_error)))
    assert results == [(i18n._("sync_not_configured"), False)]


# ── Concurrent changes ────────────────────────────────────────────────────────

import json  # noqa: E402
import threading  # noqa: E402
import time  # noqa: E402

import sync  # noqa: E402
from crypto import decrypt_entry, encrypt_entry, sign_entries, sign_users  # noqa: E402

SYNC_CONFIG = {"webdav_url": "https://dav.example.invalid/cal",
               "auth_user": "u", "password": "p"}


class FakeServer:
    """In-memory WebDAV file with ETags and If-Match / If-None-Match checks."""

    def __init__(self):
        self.body = None
        self.etag = None
        self.puts = 0
        self.before_put = None   # one-shot hook: someone else writes first
        self.fail_next_push = False

    def store(self, data: dict):
        self.body = json.dumps(data, indent=2).encode()
        self.puts += 1
        self.etag = f'"v{self.puts}"'

    def data(self) -> dict:
        return json.loads(self.body)

    def fetch(self, config):
        if self.body is None:
            return sync.FetchResult("missing", None, None, "missing")
        return sync.FetchResult("ok", self.data(), self.etag, "pulled")

    def push(self, config, body, if_match=None, create_only=False):
        if self.fail_next_push:
            self.fail_next_push = False
            return sync.PushResult("error", "offline")
        if self.before_put:
            hook, self.before_put = self.before_put, None
            hook()
        if create_only and self.body is not None:
            return sync.PushResult("conflict", "conflict")
        if if_match is not None and if_match != self.etag:
            return sync.PushResult("conflict", "conflict")
        self.store(json.loads(body))
        return sync.PushResult("ok", "pushed")


def _wait(start):
    """Run start(on_done) and wait for the background sync to report back."""
    done = threading.Event()
    result = {}

    def on_done(msg, is_error):
        result["msg"], result["is_error"] = msg, is_error
        done.set()

    start(on_done)
    assert done.wait(10)
    return result["msg"], result["is_error"]


def _wait_idle(cal):
    deadline = time.time() + 10
    while time.time() < deadline:
        with cal._sync_lock:
            if not cal._pending:
                return
        time.sleep(0.01)
    raise AssertionError("sync did not finish")


@pytest.fixture()
def synced(provisioned, monkeypatch):
    cal, h = provisioned
    server = FakeServer()
    monkeypatch.setattr(sync, "fetch", server.fetch)
    monkeypatch.setattr(sync, "push", server.push)
    msg, is_error = _wait(lambda cb: cal.update_sync_config(SYNC_CONFIG, on_sync_done=cb))
    assert not is_error, msg
    return cal, server


def _titles(cal, data):
    return sorted(decrypt_entry(e, cal._sym_key_cal)["title"] for e in data["entries"])


def _other_edits_entries(cal, server, change):
    """Another editor changes the entries on the server."""
    data = server.data()
    entries = change(data["entries"])
    data["entries"] = entries
    data["version_entries"] += 1
    data["version"] = max(data["version_users"], data["version_entries"])
    data["sig_entries"] = sign_entries(
        data["version_entries"], entries, cal._kpriv_edit_sign)
    server.store(data)


def _other_adds(cal, server, title):
    entry = {"id": f"other-{title}", "title": title, "date": "01.01.2026",
             "time": "all-day", "timestamp": 0, "comments": []}
    _other_edits_entries(
        cal, server, lambda es: es + [encrypt_entry(entry, cal._sym_key_cal)])


def test_change_without_concurrency_is_uploaded(synced):
    cal, server = synced
    msg, is_error = _wait(lambda cb: cal.add_entry(
        "Local", "02.01.2026", "all-day", [], on_sync_done=cb))
    assert not is_error
    assert msg == "pushed"
    assert _titles(cal, server.data()) == ["Local"]


def test_remote_change_since_last_sync_is_merged(synced):
    cal, server = synced
    _other_adds(cal, server, "Remote")
    msg, is_error = _wait(lambda cb: cal.add_entry(
        "Local", "02.01.2026", "all-day", [], on_sync_done=cb))
    assert not is_error
    assert msg == i18n_text("sync_merged")
    assert _titles(cal, server.data()) == ["Local", "Remote"]
    assert sorted(e["title"] for e in cal.get_entries()) == ["Local", "Remote"]


def test_change_between_download_and_upload_is_not_overwritten(synced):
    cal, server = synced
    server.before_put = lambda: _other_adds(cal, server, "Remote")
    msg, is_error = _wait(lambda cb: cal.add_entry(
        "Local", "02.01.2026", "all-day", [], on_sync_done=cb))
    assert not is_error
    assert _titles(cal, server.data()) == ["Local", "Remote"]


def test_user_change_is_merged_with_remote_entry_change(synced):
    cal, server = synced
    _other_adds(cal, server, "Remote")
    cal.add_user("new@example.com", None, b"pass12345", role="viewer")
    _wait_idle(cal)
    data = server.data()
    assert storage.identifier_to_hash("new@example.com") in data["users"]
    assert _titles(cal, data) == ["Remote"]


def test_update_of_remotely_deleted_entry_is_reported(synced):
    cal, server = synced
    _wait(lambda cb: cal.add_entry("Doomed", "02.01.2026", "all-day", [], on_sync_done=cb))
    entry_id = cal.get_entries()[0]["id"]
    _other_edits_entries(cal, server, lambda es: [])

    msg, is_error = _wait(lambda cb: cal.update_entry(
        entry_id, "Edited", "02.01.2026", "all-day", [], on_sync_done=cb))
    assert is_error
    assert server.data()["entries"] == []
    assert cal.get_entries() == []


def test_remote_signing_key_change_keeps_change_pending(synced):
    cal, server = synced
    data = server.data()
    new_edit = ec.generate_private_key(ec.SECP256R1())
    data["sign_keys"]["edit"] = cal._public_signing_key_pem(new_edit)
    data["version_users"] += 1
    data["sig_users"] = sign_users(data["version_users"], data["sign_keys"],
                                   data["users"], data["sync_config"],
                                   cal._kpriv_admin_sign)
    data["sig_entries"] = sign_entries(data["version_entries"], data["entries"], new_edit)
    server.store(data)
    remote_before = server.body

    msg, is_error = _wait(lambda cb: cal.add_entry(
        "Local", "02.01.2026", "all-day", [], on_sync_done=cb))
    assert is_error
    assert msg == i18n_text("sync_err_rebase_keys_changed")
    assert server.body == remote_before
    assert len(cal._pending) == 1


def test_manual_sync_uploads_pending_change_after_failed_push(synced):
    cal, server = synced
    server.fail_next_push = True
    msg, is_error = _wait(lambda cb: cal.add_entry(
        "Local", "02.01.2026", "all-day", [], on_sync_done=cb))
    assert is_error
    _other_adds(cal, server, "Remote")

    msg, is_error = _wait(lambda cb: cal.sync_pull(on_done=cb))
    assert not is_error, msg
    assert _titles(cal, server.data()) == ["Local", "Remote"]
    assert cal._pending == []


def test_gives_up_when_remote_keeps_changing(synced, monkeypatch):
    cal, server = synced
    original_push = server.push

    def always_conflicting(*args, **kwargs):
        _other_adds(cal, server, f"R{server.puts}")
        return original_push(*args, **kwargs)

    monkeypatch.setattr(sync, "push", always_conflicting)
    msg, is_error = _wait(lambda cb: cal.add_entry(
        "Local", "02.01.2026", "all-day", [], on_sync_done=cb))
    assert is_error
    assert msg == i18n_text("sync_err_conflict_unresolved")
    assert len(cal._pending) == 1


def i18n_text(key):
    import i18n
    return i18n._(key)


def test_is_syncing_while_upload_runs(synced, monkeypatch):
    cal, server = synced
    release = threading.Event()
    original_push = server.push

    def slow_push(*args, **kwargs):
        release.wait(10)
        return original_push(*args, **kwargs)

    monkeypatch.setattr(sync, "push", slow_push)
    done = threading.Event()
    cal.add_entry("Local", "02.01.2026", "all-day", [],
                  on_sync_done=lambda msg, is_error: done.set())
    assert cal.is_syncing
    release.set()
    assert done.wait(10)
    deadline = time.time() + 10
    while cal.is_syncing and time.time() < deadline:
        time.sleep(0.01)
    assert not cal.is_syncing


def test_failed_upload_leaves_unsynced_changes(synced):
    cal, server = synced
    assert not cal.has_unsynced_changes
    server.fail_next_push = True
    _wait(lambda cb: cal.add_entry("Local", "02.01.2026", "all-day", [], on_sync_done=cb))
    assert cal.has_unsynced_changes

    _wait(lambda cb: cal.sync_pull(on_done=cb))
    assert not cal.has_unsynced_changes
