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


@pytest.mark.asyncio
async def test_merge_key_is_project_scoped_and_on_match_keeps_project_id():
    """D-KG-GLOSSARY-FK-GLOBAL-UNIQUE — `project_id` is part of the MERGE KEY, so a
    node is per (user, project, glossary entity) and its project_id must NEVER be
    overwritten on ON MATCH.

    This test previously locked the OPPOSITE (C12c-a "latest-sync wins"): the MERGE
    key was (user_id, glossary_entity_id), so a user's second project re-used the
    FIRST project's node and had to stomp its project_id — which made the field
    meaningless while every read (salience, coref, graph views) filters on it.
    Source-scan regression lock on the Cypher literal.
    """
    mock_result = AsyncMock()
    mock_result.single = AsyncMock(return_value={"id": "g1", "created": False})
    mock_session = AsyncMock()
    mock_session.run = AsyncMock(return_value=mock_result)

    await sync_glossary_entity_to_neo4j(
        mock_session,
        user_id=str(uuid4()),
        project_id=str(uuid4()),
        glossary_entity_id="g1",
        name="Alice",
        kind="character",
    )

    cypher = mock_session.run.call_args.args[0]
    merge_line = next(l for l in cypher.splitlines() if "MERGE (e:Entity" in l)
    assert "project_id: $project_id" in merge_line, (
        f"MERGE key must include project_id: {merge_line}"
    )
    assert "ON MATCH SET" in cypher
    on_match_block = cypher.split("ON MATCH SET", 1)[1].split("RETURN", 1)[0]
    assert "e.project_id" not in on_match_block, (
        f"ON MATCH must not overwrite project_id (it is in the MERGE key): {on_match_block}"
    )
