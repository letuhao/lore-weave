"""Tests for catalog router (story 04)."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest


class TestCatalogRouter:
    @pytest.mark.asyncio
    async def test_skills_catalog(self, client):
        resp = await client.get("/v1/chat/skills/catalog")
        assert resp.status_code == 200
        data = resp.json()
        assert "items" in data
        assert any(i["id"] == "universal" for i in data["items"])

    @pytest.mark.asyncio
    async def test_tools_catalog_filters_tier_s(self, client):
        catalog = [
            {
                "type": "function",
                "function": {
                    "name": "safe_read",
                    "description": "read",
                    "_meta": {"tier": "R"},
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "danger_write",
                    "description": "write",
                    "_meta": {"tier": "S"},
                },
            },
        ]
        with patch(
            "app.routers.catalog.get_knowledge_client",
        ) as mock_get:
            kc = AsyncMock()
            kc.get_tool_definitions = AsyncMock(return_value=catalog)
            mock_get.return_value = kc
            resp = await client.get("/v1/chat/tools/catalog")
        assert resp.status_code == 200
        names = {i["name"] for i in resp.json()["items"]}
        assert "safe_read" in names
        assert "danger_write" not in names

    @pytest.mark.asyncio
    async def test_tools_catalog_defaults_exclude_legacy(self, client):
        """CAT-4 Part D — the curated enabled_tools picker must not surface a
        superseded tool by default (pinning one there would silently flip the
        whole session into curated mode — an oversized side effect for what
        should stay a scoped `pinned_legacy_tools` escape hatch)."""
        catalog = [
            {"type": "function", "function": {
                "name": "glossary_ontology_upsert", "description": "new",
                "_meta": {"tier": "A"},
            }},
            {"type": "function", "function": {
                "name": "glossary_book_create", "description": "old",
                "_meta": {"tier": "A", "visibility": "legacy"},
            }},
        ]
        with patch("app.routers.catalog.get_knowledge_client") as mock_get:
            kc = AsyncMock()
            kc.get_tool_definitions = AsyncMock(return_value=catalog)
            mock_get.return_value = kc

            resp = await client.get("/v1/chat/tools/catalog")
            assert resp.status_code == 200
            names = {i["name"] for i in resp.json()["items"]}
            assert names == {"glossary_ontology_upsert"}

            resp2 = await client.get("/v1/chat/tools/catalog?visibility=legacy")
            assert resp2.status_code == 200
            items2 = resp2.json()["items"]
            assert {i["name"] for i in items2} == {"glossary_book_create"}
            assert items2[0]["visibility"] == "legacy"

    @pytest.mark.asyncio
    async def test_tools_catalog_domain_resolves_kg_and_memory_alias(self, client):
        """review-impl fix (2026-07-07) — the FE tool-picker's `domain` field must
        resolve through the same alias `find_tools`/hot-seeding use: a kg_*/memory_*
        tool's real domain is "knowledge", not the literal "kg"/"memory" prefix."""
        catalog = [
            {"type": "function", "function": {
                "name": "kg_graph_query", "description": "query", "_meta": {"tier": "R"},
            }},
            {"type": "function", "function": {
                "name": "memory_search", "description": "search", "_meta": {"tier": "R"},
            }},
        ]
        with patch("app.routers.catalog.get_knowledge_client") as mock_get:
            kc = AsyncMock()
            kc.get_tool_definitions = AsyncMock(return_value=catalog)
            mock_get.return_value = kc
            resp = await client.get("/v1/chat/tools/catalog")
        assert resp.status_code == 200
        domains = {i["name"]: i["domain"] for i in resp.json()["items"]}
        assert domains["kg_graph_query"] == "knowledge"
        assert domains["memory_search"] == "knowledge"
