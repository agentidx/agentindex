"""Unit tests for the L4 `/dependencies/{slug}.json` endpoint (T212).

The tests exercise the router mounted on `agentindex.api.main:app` and
monkey-patch `_fetch_row` so they never open a Postgres connection.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import pytest
from starlette.testclient import TestClient

from agentindex.api.endpoints import dependencies as dependencies_module
from agentindex.api.main import app


client = TestClient(app, raise_server_exceptions=False)


def _fixture_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "slug": "espeak",
        "registry": "homebrew",
        "name": "espeak",
        "dependencies_count": 1,
        "deprecated": False,
        "enriched_at": datetime(2026, 3, 20, 10, 53, 6, tzinfo=timezone.utc),
        "last_updated": None,
        "last_commit": datetime(2026, 4, 1, 0, 0, 0, tzinfo=timezone.utc),
        "last_release_date": None,
        "homepage_url": None,
        "repository_url": None,
        "trust_score": 62.5,
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

    monkeypatch.setattr(dependencies_module, "_fetch_row", _fake_fetch)
    return holder, _set


class TestKnownSlug:
    def test_returns_200(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/dependencies/espeak.json")
        assert r.status_code == 200

    def test_content_type_is_json(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/dependencies/espeak.json")
        assert r.headers["content-type"].startswith("application/json")

    def test_schema_version_header(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/dependencies/espeak.json")
        assert r.headers.get("x-schema-version") == "L4-dependencies/v1"

    def test_cache_control_header(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/dependencies/espeak.json")
        assert "max-age=86400" in r.headers.get("cache-control", "")
        assert "immutable" in r.headers.get("cache-control", "")

    def test_describedby_link_header(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/dependencies/espeak.json")
        assert "llms.txt" in r.headers.get("nerq:data", "")

    def test_stable_top_level_fields(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/dependencies/espeak.json").json()
        for key in (
            "@context",
            "@type",
            "@id",
            "schema_version",
            "slug",
            "registry",
            "name",
            "last_updated_at",
            "dependencies",
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
        assert body["schema_version"] == "L4-dependencies/v1"
        assert body["slug"] == "espeak"
        assert body["registry"] == "homebrew"
        assert body["sameAs"] == []
        assert body["data_source"] == "nerq.software_registry"

    def test_dependencies_block_shape(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row(dependencies_count=5))
        deps = client.get("/dependencies/espeak.json").json()["dependencies"]
        assert set(deps) == {
            "direct_count",
            "transitive_count",
            "transitive_known",
            "dormant",
            "dormant_reason",
            "dormant_threshold_days",
        }
        assert deps["direct_count"] == 5
        assert deps["transitive_count"] is None
        assert deps["transitive_known"] is False
        assert deps["dormant_threshold_days"] == 365

    def test_direct_count_null_becomes_zero(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row(dependencies_count=None))
        deps = client.get("/dependencies/espeak.json").json()["dependencies"]
        assert deps["direct_count"] == 0

    def test_dormant_false_when_recent_commit(self, stub_fetch):
        _, set_row = stub_fetch
        recent = datetime.now(timezone.utc) - timedelta(days=30)
        set_row(_fixture_row(last_commit=recent))
        deps = client.get("/dependencies/espeak.json").json()["dependencies"]
        assert deps["dormant"] is False
        assert deps["dormant_reason"] is None

    def test_dormant_true_when_deprecated(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row(deprecated=True))
        deps = client.get("/dependencies/espeak.json").json()["dependencies"]
        assert deps["dormant"] is True
        assert deps["dormant_reason"] == "deprecated"

    def test_dormant_true_when_no_signal(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(
            _fixture_row(
                last_commit=None,
                last_release_date=None,
                last_updated=None,
            )
        )
        deps = client.get("/dependencies/espeak.json").json()["dependencies"]
        assert deps["dormant"] is True
        assert deps["dormant_reason"] == "no_signal"

    def test_dormant_true_when_old_commit(self, stub_fetch):
        _, set_row = stub_fetch
        stale = datetime.now(timezone.utc) - timedelta(days=400)
        set_row(_fixture_row(last_commit=stale))
        deps = client.get("/dependencies/espeak.json").json()["dependencies"]
        assert deps["dormant"] is True
        assert deps["dormant_reason"] is not None
        assert deps["dormant_reason"].startswith("no_commit_in_")

    def test_dormant_true_when_old_release_only(self, stub_fetch):
        _, set_row = stub_fetch
        stale = datetime.now(timezone.utc) - timedelta(days=400)
        set_row(
            _fixture_row(
                last_commit=None,
                last_release_date=stale,
                last_updated=None,
            )
        )
        deps = client.get("/dependencies/espeak.json").json()["dependencies"]
        assert deps["dormant"] is True
        assert deps["dormant_reason"].startswith("no_release_in_")

    def test_canonical_id_uses_slug(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/dependencies/espeak.json").json()
        assert body["@id"] == "https://nerq.ai/dependencies/espeak.json"

    def test_last_updated_iso8601_utc(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/dependencies/espeak.json").json()
        assert body["last_updated_at"] == "2026-03-20T10:53:06Z"

    def test_registry_url_for_homebrew(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/dependencies/espeak.json").json()
        assert body["registry_url"] == "https://formulae.brew.sh/formula/espeak"

    def test_registry_url_for_unknown_registry_is_null(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row(registry="someoddregistry"))
        body = client.get("/dependencies/espeak.json").json()
        assert body["registry_url"] is None

    def test_slug_is_lowercased_in_lookup(self, stub_fetch):
        holder, set_row = stub_fetch
        set_row(_fixture_row())
        client.get("/dependencies/eSpeak.json")
        assert holder["calls"] == [("espeak", None)]

    def test_registry_query_disambiguates(self, stub_fetch):
        holder, set_row = stub_fetch
        set_row(_fixture_row(registry="npm"))
        client.get("/dependencies/foo.json?registry=NPM")
        assert holder["calls"] == [("foo", "npm")]


class TestUnknownSlug:
    def test_returns_404(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(None)
        r = client.get("/dependencies/does-not-exist.json")
        assert r.status_code == 404

    def test_error_payload_is_json(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(None)
        r = client.get("/dependencies/does-not-exist.json")
        assert r.headers["content-type"].startswith("application/json")
        assert r.json() == {"detail": "slug_not_found"}


class TestMalformedInput:
    def test_empty_slug_not_matched_by_route(self):
        r = client.get("/dependencies/.json")
        assert r.status_code == 404

    def test_oversize_slug_is_400(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(None)
        too_long = "a" * 201
        r = client.get(f"/dependencies/{too_long}.json")
        assert r.status_code == 400
        assert r.json() == {"detail": "invalid_slug"}


class TestOpenAPIDiscovery:
    def test_openapi_json_lists_dependencies_route(self):
        r = client.get("/v1/openapi.json")
        assert r.status_code == 200
        spec = r.json()
        assert "/dependencies/{slug}.json" in spec.get("paths", {})
        op = spec["paths"]["/dependencies/{slug}.json"]["get"]
        assert "L4" in op.get("tags", [])
