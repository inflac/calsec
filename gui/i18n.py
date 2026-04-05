"""
Internationalization support.

Call load() once at startup (before any UI imports) with the language code
stored in settings. After that, use _() to look up translated strings and
access the module-level list constants (MONTHS, WD_SHORT, etc.).
"""

_strings: dict = {}
_lang: str = "de"

# Translatable list/dict constants — populated by load()
MONTHS: list[str]    = []
WD_SHORT: list[str]  = []
WD_LONG: list[str]   = []
FREQ_OPTS: list      = []
FREQ_UNITS: dict     = {}
POS_OPTS: list       = []

SUPPORTED: list[tuple[str, str]] = [("de", "Deutsch"), ("en", "English")]


def load(lang: str) -> None:
    """Load the given language. Falls back to German for unknown codes."""
    global _strings, _lang, MONTHS, WD_SHORT, WD_LONG, FREQ_OPTS, FREQ_UNITS, POS_OPTS
    _lang = lang if lang in {code for code, _ in SUPPORTED} else "de"
    if _lang == "en":
        from locales import en as _mod
    else:
        from locales import de as _mod
    _strings   = _mod.STRINGS
    MONTHS     = _mod.MONTHS
    WD_SHORT   = _mod.WD_SHORT
    WD_LONG    = _mod.WD_LONG
    FREQ_OPTS  = _mod.FREQ_OPTS
    FREQ_UNITS = _mod.FREQ_UNITS
    POS_OPTS   = _mod.POS_OPTS


def _(key: str) -> str:
    """Return the translated string for *key*, falling back to the key itself."""
    return _strings.get(key, key)


def get() -> str:
    """Return the currently active language code."""
    return _lang
