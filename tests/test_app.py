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
