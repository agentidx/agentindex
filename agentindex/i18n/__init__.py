"""Nerq i18n module — single source of truth for languages and URL localization.

This module is the authoritative source for:
- The list of supported languages (see languages.py)
- Internal URL generation with language prefixing (see urls.py)

Any code that generates internal URLs or references the set of supported
languages should import from here, not from nerq_design.py or translations.py
directly. The linter in tests/test_no_hardcoded_links.py enforces this.

This module is designed to move unchanged from v1 to v2. The only coupling
to v1-specific code is the import of HREFLANG_LANGS and URL_PATTERNS in
languages.py, which will be inverted when v2 is built: languages.py will
become the source and nerq_design.py / translations.py will import from here.
"""

from agentindex.i18n.languages import (
    LANGUAGES,
    SUPPORTED_LANGS,
    RTL_LANGS,
    LANG_COUNT,
    is_supported,
    is_rtl,
)
from agentindex.i18n.urls import (
    localize_url,
    LOCALIZED_PREFIXES,
    GLOBAL_PATHS,
)

__all__ = [
    "LANGUAGES",
    "SUPPORTED_LANGS",
    "RTL_LANGS",
    "LANG_COUNT",
    "is_supported",
    "is_rtl",
    "localize_url",
    "LOCALIZED_PREFIXES",
    "GLOBAL_PATHS",
]
