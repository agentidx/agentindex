"""Tests for agentindex.i18n.urls.localize_url() — the single authorized
function for generating internal URLs."""
import pytest

from agentindex.i18n.urls import (
    localize_url,
    LOCALIZED_PREFIXES,
    GLOBAL_PATHS,
)


class TestEnglishPassthrough:
    """English is served from the root — never prefixed, regardless of path."""

    def test_safe_page_unchanged(self):
        assert localize_url("/safe/nordvpn", "en") == "/safe/nordvpn"

    def test_best_page_unchanged(self):
        assert localize_url("/best/safest-vpns", "en") == "/best/safest-vpns"

    def test_compare_page_unchanged(self):
        assert localize_url("/compare/a-vs-b", "en") == "/compare/a-vs-b"

    def test_homepage_unchanged(self):
        assert localize_url("/", "en") == "/"

    def test_global_path_unchanged(self):
        assert localize_url("/dashboard", "en") == "/dashboard"


class TestLocalizedContent:
    """Non-English languages prefix localized content paths."""

    def test_safe_page_prefixed_no(self):
        assert localize_url("/safe/nordvpn", "no") == "/no/safe/nordvpn"

    def test_safe_page_prefixed_de(self):
        assert localize_url("/safe/nordvpn", "de") == "/de/safe/nordvpn"

    def test_safe_page_prefixed_ja(self):
        assert localize_url("/safe/nordvpn", "ja") == "/ja/safe/nordvpn"

    def test_safe_page_prefixed_ar(self):
        """Arabic is RTL but URL structure is the same."""
        assert localize_url("/safe/nordvpn", "ar") == "/ar/safe/nordvpn"

    def test_best_page_prefixed(self):
        assert localize_url("/best/safest-vpns", "no") == "/no/best/safest-vpns"

    def test_compare_page_prefixed(self):
        assert localize_url("/compare/nordvpn-vs-protonvpn", "no") == "/no/compare/nordvpn-vs-protonvpn"

    def test_alternatives_page_prefixed(self):
        assert localize_url("/alternatives/nordvpn", "no") == "/no/alternatives/nordvpn"

    def test_is_safe_question_prefixed(self):
        assert localize_url("/is-nordvpn-safe", "no") == "/no/is-nordvpn-safe"

    def test_is_legit_question_prefixed(self):
        assert localize_url("/is-nordvpn-legit", "no") == "/no/is-nordvpn-legit"

    def test_is_scam_question_prefixed(self):
        assert localize_url("/is-nordvpn-a-scam", "no") == "/no/is-nordvpn-a-scam"

    def test_does_question_prefixed(self):
        assert localize_url("/does-nordvpn-sell-your-data", "no") == "/no/does-nordvpn-sell-your-data"

    def test_review_page_prefixed(self):
        assert localize_url("/review/nordvpn", "no") == "/no/review/nordvpn"

    def test_who_owns_page_prefixed(self):
        assert localize_url("/who-owns/nordvpn", "no") == "/no/who-owns/nordvpn"

    def test_pros_cons_page_prefixed(self):
        assert localize_url("/pros-cons/nordvpn", "no") == "/no/pros-cons/nordvpn"

    def test_categories_page_prefixed(self):
        assert localize_url("/categories", "no") == "/no/categories"

    def test_homepage_prefixed(self):
        """Homepage is localized content — it should be prefixed."""
        assert localize_url("/", "no") == "/no/"


class TestGlobalPaths:
    """Global paths are never prefixed even on non-English languages."""

    def test_v1_api_unchanged(self):
        assert localize_url("/v1/preflight", "no") == "/v1/preflight"

    def test_v1_api_with_query_unchanged(self):
        assert localize_url("/v1/preflight?target=nordvpn", "no") == "/v1/preflight?target=nordvpn"

    def test_api_unchanged(self):
        assert localize_url("/api/badge/nordvpn", "no") == "/api/badge/nordvpn"

    def test_static_unchanged(self):
        assert localize_url("/static/nerq.css", "no") == "/static/nerq.css"

    def test_static_with_version_unchanged(self):
        assert localize_url("/static/nerq.css?v=13", "no") == "/static/nerq.css?v=13"

    def test_feed_unchanged(self):
        assert localize_url("/feed/recent", "no") == "/feed/recent"

    def test_sitemap_unchanged(self):
        assert localize_url("/sitemap-index.xml", "no") == "/sitemap-index.xml"

    def test_robots_txt_unchanged(self):
        assert localize_url("/robots.txt", "no") == "/robots.txt"

    def test_llms_txt_unchanged(self):
        assert localize_url("/llms.txt", "no") == "/llms.txt"

    def test_methodology_unchanged(self):
        assert localize_url("/methodology", "no") == "/methodology"

    def test_about_unchanged(self):
        """Exact match on /about must not localize."""
        assert localize_url("/about", "no") == "/about"

    def test_dashboard_unchanged(self):
        assert localize_url("/dashboard", "no") == "/dashboard"

    def test_discover_unchanged(self):
        assert localize_url("/discover", "no") == "/discover"

    def test_claim_unchanged(self):
        assert localize_url("/claim", "no") == "/claim"

    def test_nerq_docs_unchanged(self):
        assert localize_url("/nerq/docs", "no") == "/nerq/docs"

    def test_badge_subpath_unchanged(self):
        assert localize_url("/badge/NordVPN", "no") == "/badge/NordVPN"

    def test_mcp_unchanged(self):
        assert localize_url("/mcp", "no") == "/mcp"

    def test_crypto_unchanged(self):
        """Crypto is a vertical root page, not an entity page."""
        assert localize_url("/crypto", "no") == "/crypto"

    def test_vpn_root_unchanged(self):
        """/vpn is the vertical landing page, /safe/nordvpn is the entity."""
        assert localize_url("/vpn", "no") == "/vpn"


class TestAlreadyLocalized:
    """URLs that already have a language prefix must not be double-prefixed."""

    def test_no_prefix_passthrough(self):
        assert localize_url("/no/safe/nordvpn", "no") == "/no/safe/nordvpn"

    def test_de_prefix_passthrough(self):
        assert localize_url("/de/safe/nordvpn", "de") == "/de/safe/nordvpn"

    def test_cross_lang_prefix_passthrough(self):
        """If path is /de/... but lang is 'no', we should not re-prefix.
        The caller made a conscious choice to link to the German version."""
        assert localize_url("/de/safe/nordvpn", "no") == "/de/safe/nordvpn"

    def test_bare_lang_path_passthrough(self):
        """/no (without trailing slash) is the Norwegian homepage."""
        assert localize_url("/no", "no") == "/no"


class TestExternalURLs:
    """External URLs must never be modified."""

    def test_https_unchanged(self):
        assert localize_url("https://example.com/foo", "no") == "https://example.com/foo"

    def test_http_unchanged(self):
        assert localize_url("http://example.com/foo", "no") == "http://example.com/foo"

    def test_protocol_relative_unchanged(self):
        assert localize_url("//example.com/foo", "no") == "//example.com/foo"

    def test_mailto_unchanged(self):
        assert localize_url("mailto:anders@nerq.ai", "no") == "mailto:anders@nerq.ai"

    def test_tel_unchanged(self):
        assert localize_url("tel:+46701234567", "no") == "tel:+46701234567"

    def test_javascript_unchanged(self):
        """javascript: URLs are a security smell but we don't break them."""
        assert localize_url("javascript:void(0)", "no") == "javascript:void(0)"


class TestEdgeCases:
    """Edge cases: empty, None, fragments, relative URLs."""

    def test_empty_string_unchanged(self):
        assert localize_url("", "no") == ""

    def test_fragment_only_unchanged(self):
        assert localize_url("#top", "no") == "#top"

    def test_fragment_with_content_unchanged(self):
        assert localize_url("#section-2", "no") == "#section-2"

    def test_relative_url_unchanged(self):
        """Relative URLs like 'foo.html' are unusual but safe to leave alone."""
        assert localize_url("foo.html", "no") == "foo.html"

    def test_none_input_safe(self):
        """None input must not crash, must return empty string."""
        assert localize_url(None, "no") == ""

    def test_non_string_input_safe(self):
        """Non-string input must not crash — returns empty string as safe fallback."""
        assert localize_url(42, "no") == ""
        assert localize_url([1,2,3], "no") == ""
        assert localize_url({}, "no") == ""


class TestUnknownLanguages:
    """Unknown language codes must not break — they are treated as no-op."""

    def test_unknown_lang_returns_unchanged(self):
        """Unknown lang: passthrough, do not prefix."""
        assert localize_url("/safe/nordvpn", "xx") == "/safe/nordvpn"

    def test_empty_lang_returns_unchanged(self):
        assert localize_url("/safe/nordvpn", "") == "/safe/nordvpn"


class TestQueryAndFragment:
    """Query strings and fragments should be preserved when prefixing."""

    def test_prefix_with_query_string(self):
        assert localize_url("/safe/nordvpn?ref=claude", "no") == "/no/safe/nordvpn?ref=claude"

    def test_prefix_with_fragment(self):
        assert localize_url("/safe/nordvpn#verdict", "no") == "/no/safe/nordvpn#verdict"

    def test_prefix_with_query_and_fragment(self):
        assert localize_url("/safe/nordvpn?ref=claude#verdict", "no") == "/no/safe/nordvpn?ref=claude#verdict"


class TestAllSupportedLanguages:
    """Every supported language should prefix correctly."""

    def test_every_non_english_language_prefixes(self):
        """Parametric test: every non-English supported language must
        prefix /safe/nordvpn correctly."""
        from agentindex.i18n.languages import SUPPORTED_LANGS
        for lang in SUPPORTED_LANGS:
            if lang == "en":
                continue
            result = localize_url("/safe/nordvpn", lang)
            assert result == f"/{lang}/safe/nordvpn", (
                f"Language {lang!r} failed: got {result!r}"
            )

    def test_every_language_leaves_v1_api_alone(self):
        """Parametric test: every language must leave /v1/preflight alone."""
        from agentindex.i18n.languages import SUPPORTED_LANGS
        for lang in SUPPORTED_LANGS:
            assert localize_url("/v1/preflight", lang) == "/v1/preflight"


class TestModuleConstants:
    """Sanity checks on the module constants."""

    def test_localized_prefixes_is_tuple(self):
        assert isinstance(LOCALIZED_PREFIXES, tuple)

    def test_global_paths_is_tuple(self):
        assert isinstance(GLOBAL_PATHS, tuple)

    def test_localized_prefixes_all_start_with_slash(self):
        for prefix in LOCALIZED_PREFIXES:
            assert prefix.startswith("/"), f"Prefix {prefix!r} must start with /"

    def test_global_paths_all_start_with_slash(self):
        for path in GLOBAL_PATHS:
            assert path.startswith("/"), f"Global path {path!r} must start with /"

    def test_no_overlap_between_localized_and_global(self):
        """A prefix should not be both localized and global."""
        localized_set = set(LOCALIZED_PREFIXES)
        global_set = set(GLOBAL_PATHS)
        overlap = localized_set & global_set
        assert not overlap, f"Overlap between LOCALIZED_PREFIXES and GLOBAL_PATHS: {overlap}"
