"""Mui #1 — unit tests for the KG→glossary writeback (no Neo4j/DB).

Covers the pure payload builder, the propose orchestration (mocked
find_gap_candidates + glossary client), and the env config loader.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.db.neo4j_repos.entities import Entity
from app.extraction import glossary_writeback as gw

USER_ID = str(uuid4())
PROJECT_ID = str(uuid4())


def _cand(name: str, kind: str, confidence: float, aliases: list[str] | None = None) -> Entity:
    return Entity(
        id=f"canon-{name}",
        user_id=USER_ID,
        project_id=PROJECT_ID,
        name=name,
        canonical_name=name,
        kind=kind,
        confidence=confidence,
        aliases=aliases or [],
        mention_count=99,
    )


def test_build_filters_below_confidence_floor():
    cands = [_cand("姜子牙", "character", 0.9), _cand("噪声", "character", 0.4)]
    out = gw.build_writeback_entities(cands, confidence_floor=0.7)
    assert [e["name"] for e in out] == ["姜子牙"]


def test_build_maps_extractor_kind_to_glossary_kind():
    out = gw.build_writeback_entities([_cand("哪吒", "person", 0.8)], confidence_floor=0.7)
    assert out[0]["kind_code"] == "character"  # person → character


def test_build_drops_canonical_name_from_aliases():
    cand = _cand("太公望", "character", 0.8, aliases=["太公望", "姜尚", ""])
    out = gw.build_writeback_entities([cand], confidence_floor=0.7)
    assert out[0]["attributes"]["aliases"] == ["姜尚"]


def test_build_omits_aliases_attr_when_empty():
    out = gw.build_writeback_entities([_cand("杨戬", "character", 0.8)], confidence_floor=0.7)
    assert out[0]["attributes"] == {}


@pytest.mark.asyncio
async def test_writeback_proposes_with_ai_suggested_tag(monkeypatch):
    cands = [_cand("姜子牙", "person", 0.9), _cand("哪吒", "character", 0.85)]
    monkeypatch.setattr(gw, "find_gap_candidates", AsyncMock(return_value=cands))
    gc = MagicMock()
    gc.propose_entities = AsyncMock(return_value={"created": 2})
    book_id = uuid4()

    n = await gw.writeback_discovered_entities(
        MagicMock(), gc,
        user_id=USER_ID, project_id=PROJECT_ID, book_id=book_id,
        config={"enabled": True, "min_mentions": 10, "confidence_floor": 0.7, "limit": 100},
    )

    assert n == 2
    gc.propose_entities.assert_awaited_once()
    _, kwargs = gc.propose_entities.call_args
    assert kwargs["default_tags"] == ["ai-suggested"]
    assert kwargs["park_unknown_kinds"] is False
    assert {e["name"] for e in kwargs["entities"]} == {"姜子牙", "哪吒"}


@pytest.mark.asyncio
async def test_writeback_no_candidates_skips_call(monkeypatch):
    monkeypatch.setattr(gw, "find_gap_candidates", AsyncMock(return_value=[]))
    gc = MagicMock()
    gc.propose_entities = AsyncMock()

    n = await gw.writeback_discovered_entities(
        MagicMock(), gc,
        user_id=USER_ID, project_id=PROJECT_ID, book_id=uuid4(),
        config={"enabled": True, "min_mentions": 10, "confidence_floor": 0.7, "limit": 100},
    )

    assert n == 0
    gc.propose_entities.assert_not_awaited()


def test_should_writeback_only_at_end_of_book():
    # The HIGH-1 invariant: fire once at book-end, never per-chapter.
    assert gw.should_writeback(enabled=True, project_id="p1", is_last_chapter_of_book=True) is True
    # mid-book chapter → no writeback (avoids re-proposing the whole project gap list)
    assert gw.should_writeback(enabled=True, project_id="p1", is_last_chapter_of_book=False) is False
    # disabled flag
    assert gw.should_writeback(enabled=False, project_id="p1", is_last_chapter_of_book=True) is False
    # no linked project (chat-only / no book glossary)
    assert gw.should_writeback(enabled=True, project_id=None, is_last_chapter_of_book=True) is False


def test_config_defaults_off(monkeypatch):
    for k in (
        "KNOWLEDGE_GLOSSARY_WRITEBACK_ENABLED",
        "KNOWLEDGE_GLOSSARY_WRITEBACK_MIN_MENTIONS",
        "KNOWLEDGE_GLOSSARY_WRITEBACK_CONFIDENCE_FLOOR",
        "KNOWLEDGE_GLOSSARY_WRITEBACK_LIMIT",
    ):
        monkeypatch.delenv(k, raising=False)
    cfg = gw._load_writeback_config()
    assert cfg == {
        "enabled": False,
        "min_mentions": 10,
        "confidence_floor": 0.7,
        "limit": 100,
    }


def test_config_env_overrides(monkeypatch):
    monkeypatch.setenv("KNOWLEDGE_GLOSSARY_WRITEBACK_ENABLED", "true")
    monkeypatch.setenv("KNOWLEDGE_GLOSSARY_WRITEBACK_MIN_MENTIONS", "25")
    monkeypatch.setenv("KNOWLEDGE_GLOSSARY_WRITEBACK_CONFIDENCE_FLOOR", "0.8")
    monkeypatch.setenv("KNOWLEDGE_GLOSSARY_WRITEBACK_LIMIT", "50")
    cfg = gw._load_writeback_config()
    assert cfg == {
        "enabled": True,
        "min_mentions": 25,
        "confidence_floor": 0.8,
        "limit": 50,
    }
