"""Single source of truth for supported languages.

HOW THIS WORKS TODAY (v1 bridge mode):
    This module reads from the existing HREFLANG_LANGS in nerq_design.py
    and validates it against URL_PATTERNS in translations.py. Both must
    agree. If they drift, this module raises ImportError at startup,
    which is a loud failure mode we prefer to silent drift.

    Other modules should import from here, not from nerq_design or
    translations directly.

HOW THIS WILL WORK IN v2:
    This file becomes the primary source. LANGUAGES dict is the canonical
    definition. nerq_design.HREFLANG_LANGS is derived from here.
    translations.URL_PATTERNS is also derived from here.

MIGRATION PATH:
    Phase A (today): This module reads from nerq_design + translations.
    Phase B (Dag 34-35): Consumer code switches to import from here.
    Phase C (v2): Invert imports. nerq_design imports from languages.py.

DESIGN PRINCIPLES:
    1. Adding a new language is a one-line change in one place.
    2. It is impossible for HREFLANG_LANGS and URL_PATTERNS to silently
       disagree about which languages are supported.
    3. RTL information is explicit, not implicit.
    4. The language list order is preserved (it determines the order in
       nav dropdowns and hreflang tags).
"""

from typing import Dict, FrozenSet, Tuple

# Import from existing v1 sources. If either of these imports fails,
# something is badly wrong and we want to know immediately.
try:
    from agentindex.nerq_design import HREFLANG_LANGS as _HREFLANG_LANGS
except ImportError as e:
    raise ImportError(
        "agentindex.i18n.languages requires agentindex.nerq_design.HREFLANG_LANGS. "
        f"Original error: {e}"
    )

try:
    from agentindex.translations import URL_PATTERNS as _URL_PATTERNS
except ImportError as e:
    raise ImportError(
        "agentindex.i18n.languages requires agentindex.translations.URL_PATTERNS. "
        f"Original error: {e}"
    )

# Validation: the two sources must agree on which languages are supported.
# If they drift, refuse to load. This is the single most important
# invariant of the language system.
_hreflang_set = set(_HREFLANG_LANGS)
_url_pattern_set = set(_URL_PATTERNS.keys())
_diff = _hreflang_set ^ _url_pattern_set
if _diff:
    raise ImportError(
        f"Language drift detected between HREFLANG_LANGS and URL_PATTERNS: "
        f"difference = {_diff}. "
        f"HREFLANG_LANGS has {len(_hreflang_set)} languages, "
        f"URL_PATTERNS has {len(_url_pattern_set)} languages. "
        f"These must match exactly. Fix nerq_design.py or translations.py "
        f"before importing from agentindex.i18n."
    )

# Per-language metadata. The code is the authoritative identifier; the
# other fields are for display and logic decisions.
#
# Fields:
#   code: ISO 639-1 language code (matches HREFLANG_LANGS entry)
#   name_en: English name of the language (for admin UI, logs)
#   native: Native-script name (for user-facing language picker)
#   rtl: True if the script is right-to-left
#   reference: Which existing language to use as a translation reference
#              (helpful when adding new languages; None for base languages)
#
# Adding a new language: add one entry here, AND update HREFLANG_LANGS in
# nerq_design.py AND URL_PATTERNS in translations.py. The drift check
# above will fail loudly if you forget one of the three.
LANGUAGES: Dict[str, Dict] = {
    "en": {"name_en": "English", "native": "English", "rtl": False, "reference": None},
    "es": {"name_en": "Spanish", "native": "Español", "rtl": False, "reference": "en"},
    "pt": {"name_en": "Portuguese", "native": "Português", "rtl": False, "reference": "es"},
    "fr": {"name_en": "French", "native": "Français", "rtl": False, "reference": "en"},
    "de": {"name_en": "German", "native": "Deutsch", "rtl": False, "reference": "en"},
    "ja": {"name_en": "Japanese", "native": "日本語", "rtl": False, "reference": "en"},
    "ru": {"name_en": "Russian", "native": "Русский", "rtl": False, "reference": "en"},
    "ko": {"name_en": "Korean", "native": "한국어", "rtl": False, "reference": "ja"},
    "it": {"name_en": "Italian", "native": "Italiano", "rtl": False, "reference": "es"},
    "tr": {"name_en": "Turkish", "native": "Türkçe", "rtl": False, "reference": "en"},
    "nl": {"name_en": "Dutch", "native": "Nederlands", "rtl": False, "reference": "de"},
    "pl": {"name_en": "Polish", "native": "Polski", "rtl": False, "reference": "cs"},
    "id": {"name_en": "Indonesian", "native": "Bahasa Indonesia", "rtl": False, "reference": "en"},
    "th": {"name_en": "Thai", "native": "ไทย", "rtl": False, "reference": "en"},
    "vi": {"name_en": "Vietnamese", "native": "Tiếng Việt", "rtl": False, "reference": "en"},
    "hi": {"name_en": "Hindi", "native": "हिन्दी", "rtl": False, "reference": "en"},
    "sv": {"name_en": "Swedish", "native": "Svenska", "rtl": False, "reference": "de"},
    "cs": {"name_en": "Czech", "native": "Čeština", "rtl": False, "reference": "pl"},
    "ro": {"name_en": "Romanian", "native": "Română", "rtl": False, "reference": "it"},
    "zh": {"name_en": "Chinese", "native": "中文", "rtl": False, "reference": "en"},
    "da": {"name_en": "Danish", "native": "Dansk", "rtl": False, "reference": "sv"},
    "no": {"name_en": "Norwegian Bokmål", "native": "Norsk bokmål", "rtl": False, "reference": "da"},
    "ar": {"name_en": "Arabic", "native": "العربية", "rtl": True, "reference": "en"},
}

# Validate LANGUAGES dict against the imported sources. If someone adds
# a language to HREFLANG_LANGS but forgets to add it to LANGUAGES here,
# we want a loud error.
_languages_keys = set(LANGUAGES.keys())
if _languages_keys != _hreflang_set:
    _missing_in_dict = _hreflang_set - _languages_keys
    _extra_in_dict = _languages_keys - _hreflang_set
    raise ImportError(
        f"LANGUAGES dict in i18n/languages.py is out of sync with HREFLANG_LANGS. "
        f"Missing from LANGUAGES dict: {_missing_in_dict}. "
        f"Extra in LANGUAGES dict: {_extra_in_dict}. "
        f"Add or remove entries in LANGUAGES to match HREFLANG_LANGS."
    )

# Derived constants. These are the main things other code should import.
# Using tuples/frozensets so they cannot be accidentally mutated.
SUPPORTED_LANGS: Tuple[str, ...] = tuple(_HREFLANG_LANGS)
RTL_LANGS: FrozenSet[str] = frozenset(
    code for code, meta in LANGUAGES.items() if meta["rtl"]
)
LANG_COUNT: int = len(LANGUAGES)


def is_supported(lang: str) -> bool:
    """Return True if lang is a supported language code.

    >>> is_supported("en")
    True
    >>> is_supported("no")
    True
    >>> is_supported("xx")
    False
    >>> is_supported("")
    False
    >>> is_supported(None)
    False
    """
    if not isinstance(lang, str):
        return False
    return lang in LANGUAGES


def is_rtl(lang: str) -> bool:
    """Return True if lang uses right-to-left script.

    >>> is_rtl("ar")
    True
    >>> is_rtl("en")
    False
    >>> is_rtl("xx")
    False
    """
    return lang in RTL_LANGS


# Self-test on import: if any of these invariants are wrong, fail loudly.
assert LANG_COUNT == 23, f"Expected 23 languages, got {LANG_COUNT}"
assert "en" in LANGUAGES, "English must always be supported"
assert "no" in LANGUAGES, "Norwegian must be supported (added Dag 31)"
assert is_rtl("ar"), "Arabic must be marked as RTL"
assert not is_rtl("en"), "English must not be marked as RTL"
