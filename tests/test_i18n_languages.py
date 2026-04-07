"""Tests for agentindex.i18n.languages — the single source of truth for supported languages."""
import pytest

from agentindex.i18n.languages import (
    LANGUAGES,
    SUPPORTED_LANGS,
    RTL_LANGS,
    LANG_COUNT,
    is_supported,
    is_rtl,
)


class TestLanguageConstants:
    """Tests for the basic constants exported by the module."""

    def test_lang_count_is_23(self):
        """We currently support exactly 23 languages. Update this test
        when adding languages — the new count is the new invariant."""
        assert LANG_COUNT == 23

    def test_supported_langs_is_tuple(self):
        """SUPPORTED_LANGS must be immutable."""
        assert isinstance(SUPPORTED_LANGS, tuple)

    def test_supported_langs_matches_languages_dict(self):
        """SUPPORTED_LANGS must exactly match the keys of LANGUAGES dict."""
        assert set(SUPPORTED_LANGS) == set(LANGUAGES.keys())

    def test_supported_langs_has_no_duplicates(self):
        """Each language appears exactly once."""
        assert len(SUPPORTED_LANGS) == len(set(SUPPORTED_LANGS))

    def test_english_is_supported(self):
        """English is the base language and must always be present."""
        assert "en" in SUPPORTED_LANGS
        assert "en" in LANGUAGES

    def test_norwegian_is_supported(self):
        """Norwegian was added on Dag 31 as language #23."""
        assert "no" in SUPPORTED_LANGS
        assert LANGUAGES["no"]["native"] == "Norsk bokmål"


class TestRTLLanguages:
    """Tests for right-to-left language handling."""

    def test_rtl_langs_is_frozenset(self):
        """RTL_LANGS must be immutable."""
        assert isinstance(RTL_LANGS, frozenset)

    def test_arabic_is_rtl(self):
        """Arabic is the only RTL language currently supported."""
        assert "ar" in RTL_LANGS
        assert is_rtl("ar") is True

    def test_english_is_not_rtl(self):
        assert "en" not in RTL_LANGS
        assert is_rtl("en") is False

    def test_unknown_lang_is_not_rtl(self):
        """Unknown languages default to LTR (safer default)."""
        assert is_rtl("xx") is False


class TestIsSupported:
    """Tests for the is_supported() helper."""

    def test_known_language_returns_true(self):
        assert is_supported("en") is True
        assert is_supported("no") is True
        assert is_supported("ar") is True

    def test_unknown_language_returns_false(self):
        assert is_supported("xx") is False
        assert is_supported("zz") is False

    def test_empty_string_returns_false(self):
        assert is_supported("") is False

    def test_none_returns_false(self):
        """None input must not crash."""
        assert is_supported(None) is False

    def test_non_string_returns_false(self):
        """Non-string inputs must not crash."""
        assert is_supported(42) is False
        assert is_supported(["en"]) is False


class TestLanguageMetadata:
    """Tests that every language has complete metadata."""

    def test_every_language_has_all_fields(self):
        """Every entry in LANGUAGES must have name_en, native, rtl, reference."""
        required_fields = {"name_en", "native", "rtl", "reference"}
        for code, meta in LANGUAGES.items():
            assert set(meta.keys()) == required_fields, (
                f"Language {code!r} is missing or has extra fields: "
                f"expected {required_fields}, got {set(meta.keys())}"
            )

    def test_every_rtl_field_is_bool(self):
        for code, meta in LANGUAGES.items():
            assert isinstance(meta["rtl"], bool), (
                f"Language {code!r} has non-bool rtl field: {meta['rtl']!r}"
            )

    def test_every_native_name_is_nonempty(self):
        for code, meta in LANGUAGES.items():
            assert meta["native"], f"Language {code!r} has empty native name"

    def test_reference_languages_exist_if_set(self):
        """If a language has a 'reference' language, that reference
        must also be in LANGUAGES (can't reference unknown language)."""
        for code, meta in LANGUAGES.items():
            ref = meta["reference"]
            if ref is not None:
                assert ref in LANGUAGES, (
                    f"Language {code!r} references unknown language {ref!r}"
                )

    def test_english_has_no_reference(self):
        """English is the root — it has no reference language."""
        assert LANGUAGES["en"]["reference"] is None

    def test_norwegian_references_danish(self):
        """Norwegian bokmål is linguistically closest to Danish, so Danish
        is the reference for NO translations."""
        assert LANGUAGES["no"]["reference"] == "da"


class TestDriftProtection:
    """Tests that verify the drift protection between LANGUAGES,
    HREFLANG_LANGS, and URL_PATTERNS is functioning. These tests
    don't test the drift check directly (it runs at import time),
    but they verify the result."""

    def test_languages_matches_hreflang(self):
        """Imported LANGUAGES keys must match HREFLANG_LANGS."""
        from agentindex.nerq_design import HREFLANG_LANGS
        assert set(LANGUAGES.keys()) == set(HREFLANG_LANGS)

    def test_languages_matches_url_patterns(self):
        """Imported LANGUAGES keys must match URL_PATTERNS keys."""
        from agentindex.translations import URL_PATTERNS
        assert set(LANGUAGES.keys()) == set(URL_PATTERNS.keys())
