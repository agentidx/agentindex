"""Unit tests for the L4 `/rating/{slug}.json` endpoint (T210).

The tests exercise the router mounted on `agentindex.api.main:app` and
monkey-patch `_fetch_row` so they never open a Postgres connection.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

import pytest
from starlette.testclient import TestClient

from agentindex.api.endpoints import rating as rating_module
from agentindex.api.main import app


client = TestClient(app, raise_server_exceptions=False)


def _fixture_row(**overrides: Any) -> dict[str, Any]:
    row: dict[str, Any] = {
        "slug": "langchain",
        "registry": "pypi",
        "name": "LangChain",
        "trust_score": 72.0,
        "trust_grade": "B",
        "security_score": 68.5,
        "maintenance_score": 81.0,
        "popularity_score": 95.0,
        "community_score": 74.0,
        "quality_score": 60.0,
        "enriched_at": datetime(2026, 4, 18, 7, 12, 0, tzinfo=timezone.utc),
        "last_updated": None,
        "last_commit": None,
        "homepage_url": "https://python.langchain.com/",
        "repository_url": "https://github.com/langchain-ai/langchain",
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

    monkeypatch.setattr(rating_module, "_fetch_row", _fake_fetch)
    return holder, _set


class TestKnownSlug:
    def test_returns_200(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/rating/langchain.json")
        assert r.status_code == 200

    def test_content_type_is_json(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/rating/langchain.json")
        assert r.headers["content-type"].startswith("application/json")

    def test_schema_version_header(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/rating/langchain.json")
        assert r.headers.get("x-schema-version") == "L4-rating/v1"

    def test_cache_control_header(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        r = client.get("/rating/langchain.json")
        assert "max-age=86400" in r.headers.get("cache-control", "")

    def test_stable_top_level_fields(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/rating/langchain.json").json()
        for key in (
            "@context",
            "@type",
            "@id",
            "schema_version",
            "slug",
            "registry",
            "name",
            "last_updated_at",
            "rating",
            "registry_url",
            "homepage_url",
            "repository_url",
            "data_source",
            "llms_txt",
        ):
            assert key in body, f"missing top-level key {key!r}"
        assert body["@context"] == "https://schema.org"
        assert body["@type"] == "Rating"
        assert body["schema_version"] == "L4-rating/v1"
        assert body["slug"] == "langchain"
        assert body["registry"] == "pypi"

    def test_rating_block_shape(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/rating/langchain.json").json()
        rating = body["rating"]
        assert rating["trust_score"] == 72.0
        assert rating["trust_grade"] == "B"
        assert rating["best_rating"] == 100
        assert rating["worst_rating"] == 0
        assert rating["rating_scheme"] == "nerq-trust-v1"
        assert set(rating["dimensions"]) == {
            "security",
            "maintenance",
            "popularity",
            "community",
            "quality",
        }
        assert rating["dimensions"]["security"] == 68.5

    def test_canonical_id_uses_slug(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/rating/langchain.json").json()
        assert body["@id"] == "https://nerq.ai/rating/langchain.json"

    def test_last_updated_iso8601_utc(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/rating/langchain.json").json()
        assert body["last_updated_at"] == "2026-04-18T07:12:00Z"

    def test_registry_url_for_pypi(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(_fixture_row())
        body = client.get("/rating/langchain.json").json()
        assert body["registry_url"] == "https://pypi.org/project/langchain/"

    def test_slug_is_lowercased_in_lookup(self, stub_fetch):
        holder, set_row = stub_fetch
        set_row(_fixture_row())
        client.get("/rating/LangChain.json")
        assert holder["calls"] == [("langchain", None)]

    def test_registry_query_disambiguates(self, stub_fetch):
        holder, set_row = stub_fetch
        set_row(_fixture_row(registry="npm"))
        client.get("/rating/foo.json?registry=NPM")
        assert holder["calls"] == [("foo", "npm")]

    def test_nulls_preserved_for_missing_scores(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(
            _fixture_row(
                trust_score=None,
                trust_grade=None,
                security_score=None,
                quality_score=None,
            )
        )
        body = client.get("/rating/langchain.json").json()
        assert body["rating"]["trust_score"] is None
        assert body["rating"]["trust_grade"] is None
        assert body["rating"]["dimensions"]["security"] is None
        # Dimensions still present for keys with data.
        assert body["rating"]["dimensions"]["popularity"] == 95.0


class TestUnknownSlug:
    def test_returns_404(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(None)
        r = client.get("/rating/does-not-exist.json")
        assert r.status_code == 404

    def test_error_payload_is_json(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(None)
        r = client.get("/rating/does-not-exist.json")
        assert r.headers["content-type"].startswith("application/json")
        body = r.json()
        assert body == {"detail": "slug_not_found"}


class TestMalformedInput:
    def test_empty_slug_not_matched_by_route(self):
        # Path matcher won't accept an empty component, so FastAPI 404s
        # before our handler runs.
        r = client.get("/rating/.json")
        assert r.status_code == 404

    def test_oversize_slug_is_400(self, stub_fetch):
        _, set_row = stub_fetch
        set_row(None)
        too_long = "a" * 201
        r = client.get(f"/rating/{too_long}.json")
        assert r.status_code == 400
        assert r.json() == {"detail": "invalid_slug"}


class TestOpenAPIDiscovery:
    def test_openapi_json_lists_rating_route(self):
        r = client.get("/v1/openapi.json")
        assert r.status_code == 200
        spec = r.json()
        assert "/rating/{slug}.json" in spec.get("paths", {})
        op = spec["paths"]["/rating/{slug}.json"]["get"]
        assert "L4" in op.get("tags", [])
