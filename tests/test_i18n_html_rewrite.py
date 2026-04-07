"""Tests for agentindex.i18n.html_rewrite.localize_internal_links()."""
import pytest

from agentindex.i18n.html_rewrite import localize_internal_links


class TestBasicLocalization:
    def test_safe_path_prefixed(self):
        assert localize_internal_links('<a href="/safe/x">x</a>', 'no') == '<a href="/no/safe/x">x</a>'

    def test_best_path_prefixed(self):
        assert localize_internal_links('<a href="/best/y">y</a>', 'no') == '<a href="/no/best/y">y</a>'

    def test_compare_path_prefixed(self):
        assert localize_internal_links('<a href="/compare/a-vs-b">x</a>', 'no') == '<a href="/no/compare/a-vs-b">x</a>'

    def test_is_safe_path_prefixed(self):
        assert localize_internal_links('<a href="/is-x-safe">x</a>', 'no') == '<a href="/no/is-x-safe">x</a>'

    def test_does_path_prefixed(self):
        assert localize_internal_links('<a href="/does-x-sell-data">x</a>', 'no') == '<a href="/no/does-x-sell-data">x</a>'


class TestPassthrough:
    def test_global_path_unchanged(self):
        assert localize_internal_links('<a href="/v1/api">api</a>', 'no') == '<a href="/v1/api">api</a>'

    def test_static_unchanged(self):
        assert localize_internal_links('<a href="/static/x.css">css</a>', 'no') == '<a href="/static/x.css">css</a>'

    def test_dashboard_unchanged(self):
        assert localize_internal_links('<a href="/dashboard">x</a>', 'no') == '<a href="/dashboard">x</a>'

    def test_external_unchanged(self):
        assert localize_internal_links('<a href="https://ex.com">x</a>', 'no') == '<a href="https://ex.com">x</a>'

    def test_already_prefixed_unchanged(self):
        assert localize_internal_links('<a href="/no/safe/x">x</a>', 'no') == '<a href="/no/safe/x">x</a>'

    def test_english_passthrough(self):
        """English never gets prefixed regardless of path."""
        html = '<a href="/safe/x">x</a> <a href="/best/y">y</a>'
        assert localize_internal_links(html, 'en') == html


class TestQuoteHandling:
    def test_double_quotes(self):
        assert localize_internal_links('<a href="/safe/x">x</a>', 'no') == '<a href="/no/safe/x">x</a>'

    def test_single_quotes(self):
        assert localize_internal_links("<a href='/safe/x'>x</a>", 'no') == "<a href='/no/safe/x'>x</a>"

    def test_mixed_quotes_in_same_doc(self):
        html = '''<a href="/safe/a">a</a> and <a href='/best/b'>b</a>'''
        result = localize_internal_links(html, 'no')
        assert '<a href="/no/safe/a">' in result
        assert "<a href='/no/best/b'>" in result


class TestEdgeCases:
    def test_empty_html(self):
        assert localize_internal_links('', 'no') == ''

    def test_no_hrefs(self):
        assert localize_internal_links('<p>no links here</p>', 'no') == '<p>no links here</p>'

    def test_multiple_links(self):
        html = '<a href="/safe/a">a</a> | <a href="/safe/b">b</a> | <a href="/safe/c">c</a>'
        result = localize_internal_links(html, 'no')
        assert result.count('href="/no/safe/') == 3

    def test_mix_localized_and_global(self):
        html = '<a href="/safe/a">a</a> <a href="/v1/api">api</a> <a href="/best/b">b</a>'
        result = localize_internal_links(html, 'no')
        assert '<a href="/no/safe/a">' in result
        assert '<a href="/v1/api">' in result  # unchanged
        assert '<a href="/no/best/b">' in result

    def test_unterminated_href_does_not_crash(self):
        """Malformed HTML should not raise — best effort."""
        html = '<a href="/safe/x>broken'
        result = localize_internal_links(html, 'no')
        # We don't care exactly what it returns, only that it didn't crash
        assert isinstance(result, str)

    def test_unquoted_href_skipped(self):
        """Unquoted href is unusual but should not crash."""
        html = '<a href=/safe/x>x</a>'
        result = localize_internal_links(html, 'no')
        assert isinstance(result, str)


class TestRealWorldHTML:
    def test_realistic_page_fragment(self):
        """Mini-version of /no/safe/nordvpn fragment."""
        html = '''
<nav>
  <a href="/no/">Home</a>
  <a href="/no/discover">Discover</a>
</nav>
<main>
  <a href="/safe/protonvpn">ProtonVPN</a>
  <a href="/safe/mullvad">Mullvad</a>
  <a href="/best/safest-vpns">Best VPNs</a>
  <a href="/compare/nordvpn-vs-protonvpn">Compare</a>
  <a href="/is-nordvpn-safe">Is it safe?</a>
  <a href="/v1/preflight?target=nordvpn">API</a>
  <a href="/static/nerq.css">CSS</a>
  <a href="https://example.com">External</a>
</main>
'''
        result = localize_internal_links(html, 'no')
        # Already-prefixed should stay
        assert '<a href="/no/">Home</a>' in result
        assert '<a href="/no/discover">' in result
        # Localized content should be prefixed
        assert '<a href="/no/safe/protonvpn">' in result
        assert '<a href="/no/safe/mullvad">' in result
        assert '<a href="/no/best/safest-vpns">' in result
        assert '<a href="/no/compare/nordvpn-vs-protonvpn">' in result
        assert '<a href="/no/is-nordvpn-safe">' in result
        # Global paths must NOT be prefixed
        assert '<a href="/v1/preflight?target=nordvpn">' in result
        assert '<a href="/static/nerq.css">' in result
        # External must NOT be touched
        assert '<a href="https://example.com">' in result


class TestPerformance:
    def test_large_page_under_50ms(self):
        """A 40KB page with 250 hrefs should localize in well under 50ms."""
        import time
        big_html = '<html>' + ''.join(f'<a href="/safe/entity-{i}">x</a>' for i in range(250)) + '</html>'
        start = time.time()
        result = localize_internal_links(big_html, 'no')
        elapsed_ms = (time.time() - start) * 1000
        assert elapsed_ms < 50, f"Too slow: {elapsed_ms:.2f}ms"
        assert result.count('href="/no/safe/') == 250
