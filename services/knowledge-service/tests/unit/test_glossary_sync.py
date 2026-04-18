"""K15.11 — Unit tests for glossary sync handler."""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.extraction.glossary_sync import sync_glossary_entity_to_neo4j


@pytest.mark.asyncio
async def test_sync_creates_entity():
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value={"id": "g1", "created": True})
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)

    result = await sync_glossary_entity_to_neo4j(
        mock_session,
        user_id=str(uuid4()),
        project_id=str(uuid4()),
        glossary_entity_id="g1",
        name="Alice",
        kind="character",
        aliases=["Al"],
        short_description="The protagonist",
    )

    assert result["action"] == "created"
    assert result["glossary_entity_id"] == "g1"
    mock_session.run.assert_called_once()
    # Verify the Cypher contains MERGE
    cypher = mock_session.run.call_args.args[0]
    assert "MERGE" in cypher


@pytest.mark.asyncio
async def test_sync_updates_existing_entity():
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value={"id": "g1", "created": False})
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)

    result = await sync_glossary_entity_to_neo4j(
        mock_session,
        user_id=str(uuid4()),
        project_id=None,
        glossary_entity_id="g1",
        name="Alice Updated",
        kind="character",
    )

    assert result["action"] == "updated"


@pytest.mark.asyncio
async def test_sync_uses_canonical_name():
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value={"id": "g1", "created": True})
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)

    result = await sync_glossary_entity_to_neo4j(
        mock_session,
        user_id=str(uuid4()),
        project_id=None,
        glossary_entity_id="g1",
        name="Dr. Watson",
        kind="character",
    )

    # canonicalize_entity_name strips "dr. " honorific
    assert result["canonical_name"] == "watson"
