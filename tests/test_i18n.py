import pytest
import gui.i18n as i18n


@pytest.fixture(autouse=True)
def reset_lang():
    """Ensure tests start with a clean state."""
    i18n.load("de")
    yield
    i18n.load("de")


# ── load ──────────────────────────────────────────────────────────────────────

def test_load_german():
    i18n.load("de")
    assert i18n.get() == "de"


def test_load_english():
    i18n.load("en")
    assert i18n.get() == "en"


def test_load_unknown_falls_back_to_german():
    i18n.load("xx")
    assert i18n.get() == "de"


# ── _ (translate) ─────────────────────────────────────────────────────────────

def test_translate_known_key_german():
    i18n.load("de")
    result = i18n._("btn_save")
    assert isinstance(result, str)
    assert result != "btn_save"  # was actually translated


def test_translate_known_key_english():
    i18n.load("en")
    result = i18n._("btn_save")
    assert isinstance(result, str)
    assert result != "btn_save"


def test_translate_unknown_key_returns_key():
    assert i18n._("nonexistent_key_xyz") == "nonexistent_key_xyz"


def test_translate_switches_on_reload():
    i18n.load("de")
    de_val = i18n._("btn_save")
    i18n.load("en")
    en_val = i18n._("btn_save")
    assert de_val != en_val


# ── list constants ────────────────────────────────────────────────────────────

def test_months_populated_after_load():
    i18n.load("de")
    assert len(i18n.MONTHS) == 13  # index 0 is empty string, 1-12 are month names


def test_wd_short_populated_after_load():
    i18n.load("en")
    assert len(i18n.WD_SHORT) == 7


def test_wd_long_populated_after_load():
    i18n.load("en")
    assert len(i18n.WD_LONG) == 7


def test_freq_opts_populated_after_load():
    i18n.load("de")
    assert len(i18n.FREQ_OPTS) > 0


def test_pos_opts_populated_after_load():
    i18n.load("en")
    assert len(i18n.POS_OPTS) > 0


def test_supported_languages():
    codes = [code for code, _ in i18n.SUPPORTED]
    assert "de" in codes
    assert "en" in codes
