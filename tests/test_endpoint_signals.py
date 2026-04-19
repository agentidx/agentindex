"""Unit tests for the L4 `/signals/{slug}.json` endpoint (T211).

The tests exercise the router mounted on `agentindex.api.main:app` and
monkey-patch `_fetch_row` so they never open a Postgres connection.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

import pytest
from starlette.testclient import TestClient

from agentindex.api.endpoints import signals as signals_module
from agentindex.api.main import app


client = TestClient(app, raise_server_exceptions=False)


def _fixture_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "slug": "espeak",
        "registry": "homebrew",
        "name": "espeak",
        "trust_score": 62.5,
        "trust_grade": "B",
        "security_score": 90.0,
        "maintenance_score": 50.0,
        "popularity_score": 30.0,
        "community_score": 35.0,
        "quality_score": 50.0,
        "openssf_score": None,
        "privacy_score": None,
        "transparency_score": None,
        "reliability_score": None,
        "cve_count": 0,
        "cve_critical": 0,
        "stars": 0,
        "forks": 0,
        "open_issues": 0,
        "contributors": 0,
        "maintainer_count": 0,
        "release_count": 0,
        "deprecated": False,
        "has_types": None,
        "has_independent_audit": None,
        "has_soc2": None,
        "has_iso27001": None,
        "jurisdiction": None,
        "enriched_at": datetime(2026, 3, 20, 10, 53, 6, tzinfo=timezone.utc),
        "last_updated": None,
        "last_commit": None,
        "last_release_date": None,
        "homepage_url": None,
        "repository_url": None,
        "data_sources": ["github", "homebrew"],
    }
    row.update(overrides)
    return row


@pytest.fixture
def stub_fetch(monkeypatch):
    """Yield a setter that installs a deterministic _fetch_row stub."""
    holder: dict[str, Any] = {"row": None, "calls": []}

    def _set(row: Optional[dict[str, Any]]):
        holder["row"] = row

    def _fake_fetch(slug: str, registry: Optional[str]):
        holder["calls"].append((slug, registry))
        return holder["row"]

    monkeypatch.setattr(signals_module, "_fetch_row", _fake_fetch)
    return holder, _set


class TestKnownSlug:
    def test_returns_200(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/signals/espeak.json")
        assert r.status_code == 200

    def test_content_type_is_json(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/signals/espeak.json")
        assert r.headers["content-type"].startswith("application/json")

    def test_schema_version_header(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/signals/espeak.json")
        assert r.headers.get("x-schema-version") == "L4-signals/v1"

    def test_cache_control_header(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/signals/espeak.json")
        assert "max-age=86400" in r.headers.get("cache-control", "")
        assert "immutable" in r.headers.get("cache-control", "")

    def test_describedby_link_header(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/signals/espeak.json")
        assert "llms.txt" in r.headers.get("nerq:data", "")

    def test_stable_top_level_fields(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/signals/espeak.json").json()
        for key in (
            "@context",
            "@type",
            "@id",
            "schema_version",
            "slug",
            "registry",
            "name",
            "last_updated_at",
            "external_trust_signals",
            "registry_url",
            "homepage_url",
            "repository_url",
            "sameAs",
            "data_source",
            "llms_txt",
        ):
            assert key in body, f"missing top-level key {key!r}"
        assert body["@context"] == "https://schema.org"
        assert body["@type"] == "SoftwareApplication"
        assert body["schema_version"] == "L4-signals/v1"
        assert body["slug"] == "espeak"
        assert body["registry"] == "homebrew"
        assert body["sameAs"] == []
        assert body["data_source"] == "nerq.software_registry"

    def test_signals_block_dimensions_shape(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/signals/espeak.json").json()
        ets = body["external_trust_signals"]
        assert ets["trust_score"] == 62.5
        assert ets["trust_grade"] == "B"
        # All 8 dimensions present.
        assert set(ets["dimensions"]) == {
            "security",
            "maintenance",
            "popularity",
            "community",
            "quality",
            "privacy",
            "transparency",
            "reliability",
        }
        assert ets["dimensions"]["security"] == 90.0
        assert ets["dimensions"]["privacy"] is None

    def test_security_block_shape(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(
            _fixture_row(
                cve_count=3,
                cve_critical=1,
                has_independent_audit=True,
                has_soc2=False,
            )
        )
        ets = client.get("/signals/espeak.json").json()["external_trust_signals"]
        assert ets["security"] == {
            "cve_count": 3,
            "cve_critical": 1,
            "has_independent_audit": True,
            "has_soc2": False,
            "has_iso27001": None,
        }

    def test_activity_block_shape(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(
            _fixture_row(
                stars=1200,
                forks=42,
                open_issues=7,
                contributors=15,
                maintainer_count=3,
                release_count=11,
                last_commit=datetime(2026, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
                last_release_date=datetime(2026, 2, 1, 0, 0, 0, tzinfo=timezone.utc),
            )
        )
        activity = client.get("/signals/espeak.json").json()[
            "external_trust_signals"
        ]["activity"]
        assert activity["stars"] == 1200
        assert activity["forks"] == 42
        assert activity["open_issues"] == 7
        assert activity["contributors"] == 15
        assert activity["maintainer_count"] == 3
        assert activity["release_count"] == 11
        assert activity["last_commit"] == "2026-03-15T12:00:00Z"
        assert activity["last_release_date"] == "2026-02-01T00:00:00Z"

    def test_bare_date_last_release_is_null(self, stub_fetch):
        # software_registry.last_release_date is a `date` column, not
        # `timestamp`. _to_iso only narrows datetime, so bare dates
        # surface as null — documenting current behavior.
        _, set_row = stub_fetch
        set_row(_fixture_row(last_release_date=date(2026, 2, 1)))
        body = client.get("/signals/espeak.json").json()
        assert (
            body["external_trust_signals"]["activity"]["last_release_date"]
            is None
        )

    def test_lifecycle_block_shape(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(
            _fixture_row(
                deprecated=True,
                has_types=False,
                jurisdiction="US",
            )
        )
        lifecycle = client.get("/signals/espeak.json").json()[
            "external_trust_signals"
        ]["lifecycle"]
        assert lifecycle == {
            "deprecated": True,
            "has_types": False,
            "jurisdiction": "US",
        }

    def test_data_sources_list_of_strings(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row(data_sources=["github", "openssf", "homebrew"]))
        body = client.get("/signals/espeak.json").json()
        assert body["external_trust_signals"]["data_sources"] == [
            "github",
            "openssf",
            "homebrew",
        ]

    def test_data_sources_json_string_parsed(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row(data_sources='["github","npm"]'))
        body = client.get("/signals/espeak.json").json()
        assert body["external_trust_signals"]["data_sources"] == ["github", "npm"]

    def test_data_sources_null_becomes_empty_list(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row(data_sources=None))
        body = client.get("/signals/espeak.json").json()
        assert body["external_trust_signals"]["data_sources"] == []

    def test_canonical_id_uses_slug(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/signals/espeak.json").json()
        assert body["@id"] == "https://nerq.ai/signals/espeak.json"

    def test_last_updated_iso8601_utc(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/signals/espeak.json").json()
        assert body["last_updated_at"] == "2026-03-20T10:53:06Z"

    def test_registry_url_for_homebrew(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/signals/espeak.json").json()
        assert body["registry_url"] == "https://formulae.brew.sh/formula/espeak"

    def test_slug_is_lowercased_in_lookup(self, stub_fetch):
        holder, set_row = stub_fetch
        set_row(_fixture_row())
        client.get("/signals/eSpeak.json")
        assert holder["calls"] == [("espeak", None)]

    def test_registry_query_disambiguates(self, stub_fetch):
        holder, set_row = stub_fetch
        set_row(_fixture_row(registry="npm"))
        client.get("/signals/foo.json?registry=NPM")
        assert holder["calls"] == [("foo", "npm")]


class TestUnknownSlug:
    def test_returns_404(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(None)
        r = client.get("/signals/does-not-exist.json")
        assert r.status_code == 404

    def test_error_payload_is_json(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(None)
        r = client.get("/signals/does-not-exist.json")
        assert r.headers["content-type"].startswith("application/json")
        assert r.json() == {"detail": "slug_not_found"}


class TestMalformedInput:
    def test_empty_slug_not_matched_by_route(self):
        # Path matcher won't accept an empty component, so FastAPI 404s
        # before our handler runs.
        r = client.get("/signals/.json")
        assert r.status_code == 404

    def test_oversize_slug_is_400(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(None)
        too_long = "a" * 201
        r = client.get(f"/signals/{too_long}.json")
        assert r.status_code == 400
        assert r.json() == {"detail": "invalid_slug"}


class TestOpenAPIDiscovery:
    def test_openapi_json_lists_signals_route(self):
        r = client.get("/v1/openapi.json")
        assert r.status_code == 200
        spec = r.json()
        assert "/signals/{slug}.json" in spec.get("paths", {})
        op = spec["paths"]["/signals/{slug}.json"]["get"]
        assert "L4" in op.get("tags", [])
