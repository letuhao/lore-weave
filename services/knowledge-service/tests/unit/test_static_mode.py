"""Unit tests for Mode 2 (static) builder with mocked dependencies."""

import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.clients.glossary_client import GlossaryEntityForContext
from app.context.modes.static import build_static_mode
from app.db.models import Project, Summary


def _project(**overrides) -> Project:
    now = datetime.now(timezone.utc)
    base = dict(
        project_id=uuid4(),
        user_id=uuid4(),
        name="My Novel",
        description="",
        project_type="book",
        book_id=uuid4(),
        instructions="Be terse and avoid adverbs.",
        extraction_enabled=False,
        extraction_status="disabled",
        embedding_model=None,
        extraction_config={},
        last_extracted_at=None,
        estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"),
        is_archived=False,
        created_at=now,
        updated_at=now,
    )
    base.update(overrides)
    return Project(**base)


def _summary(content: str, scope_type="global", scope_id=None) -> Summary:
    now = datetime.now(timezone.utc)
    return Summary(
        summary_id=uuid4(),
        user_id=uuid4(),
        scope_type=scope_type,
        scope_id=scope_id,
        content=content,
        token_count=len(content) // 4,
        version=1,
        created_at=now,
        updated_at=now,
    )


def _entity(**overrides) -> GlossaryEntityForContext:
    base = dict(
        entity_id=str(uuid4()),
        cached_name="Alice",
        cached_aliases=["Al"],
        short_description="A wandering swordsman.",
        kind_code="character",
        is_pinned=True,
        tier="pinned",
        rank_score=1.0,
    )
    base.update(overrides)
    return GlossaryEntityForContext(**base)


@pytest.mark.asyncio
async def test_full_block_with_l0_l1_and_glossary():
    summaries = AsyncMock()
    summaries.get = AsyncMock(side_effect=[
        _summary("I am a fantasy novelist."),          # L0
        _summary("Book 1 of 5.", "project", uuid4()),   # L1
    ])
    glossary_client = AsyncMock()
    glossary_client.select_for_context = AsyncMock(return_value=[
        _entity(),
        _entity(cached_name="李雲", cached_aliases=["小李"], tier="exact", rank_score=0.9),
    ])

    project = _project()
    built = await build_static_mode(
        summaries, glossary_client,
        user_id=uuid4(), project=project, message="who is Alice?",
    )

    assert built.mode == "static"
    assert built.recent_message_count == 50

    root = ET.fromstring(built.context)
    assert root.tag == "memory"
    assert root.attrib == {"mode": "static"}

    # L0 present
    assert root.find("user") is not None
    assert "fantasy novelist" in (root.find("user").text or "")

    # project present with instructions + summary
    proj = root.find("project")
    assert proj is not None
    assert proj.attrib.get("name") == "My Novel"
    instr = proj.find("instructions")
    assert instr is not None
    assert "terse" in (instr.text or "")
    summary = proj.find("summary")
    assert summary is not None
    assert "Book 1" in (summary.text or "")

    # glossary with two entities
    gloss = root.find("glossary")
    assert gloss is not None
    entities = gloss.findall("entity")
    assert len(entities) == 2
    alice = entities[0]
    assert alice.attrib["kind"] == "character"
    assert alice.attrib["tier"] == "pinned"
    assert alice.find("name").text == "Alice"
    assert alice.find("aliases").text == "Al"
    assert "swordsman" in (alice.find("description").text or "")
    # CJK entity preserved
    liyun = entities[1]
    assert liyun.find("name").text == "李雲"

    # mode instructions always present
    assert root.findall("instructions")[-1] is not None


@pytest.mark.asyncio
async def test_no_l0_omits_user_element():
    summaries = AsyncMock()
    summaries.get = AsyncMock(side_effect=[None, None])  # no L0, no L1
    glossary = AsyncMock()
    glossary.select_for_context = AsyncMock(return_value=[])

    built = await build_static_mode(
        summaries, glossary,
        user_id=uuid4(), project=_project(), message="",
    )
    root = ET.fromstring(built.context)
    assert root.find("user") is None
    # project still renders (with instructions at least)
    assert root.find("project") is not None


@pytest.mark.asyncio
async def test_no_l1_summary_project_still_renders():
    summaries = AsyncMock()
    summaries.get = AsyncMock(side_effect=[None, None])
    glossary = AsyncMock()
    glossary.select_for_context = AsyncMock(return_value=[])

    built = await build_static_mode(
        summaries, glossary,
        user_id=uuid4(), project=_project(), message="",
    )
    root = ET.fromstring(built.context)
    proj = root.find("project")
    assert proj is not None
    assert proj.attrib.get("name") == "My Novel"
    assert proj.find("summary") is None  # L1 missing
    assert proj.find("instructions") is not None


@pytest.mark.asyncio
async def test_project_without_book_omits_glossary():
    summaries = AsyncMock()
    summaries.get = AsyncMock(side_effect=[None, None])
    glossary = AsyncMock()
    glossary.select_for_context = AsyncMock(return_value=[])

    built = await build_static_mode(
        summaries, glossary,
        user_id=uuid4(), project=_project(book_id=None), message="hi",
    )
    # glossary client should not be called at all
    glossary.select_for_context.assert_not_called()

    root = ET.fromstring(built.context)
    assert root.find("glossary") is None


@pytest.mark.asyncio
async def test_glossary_down_returns_no_glossary_element():
    summaries = AsyncMock()
    summaries.get = AsyncMock(side_effect=[None, None])
    glossary = AsyncMock()
    glossary.select_for_context = AsyncMock(return_value=[])  # simulate down

    built = await build_static_mode(
        summaries, glossary,
        user_id=uuid4(), project=_project(), message="hi",
    )
    root = ET.fromstring(built.context)
    assert root.find("glossary") is None


@pytest.mark.asyncio
async def test_project_name_with_xml_chars_escaped():
    summaries = AsyncMock()
    summaries.get = AsyncMock(side_effect=[None, None])
    glossary = AsyncMock()
    glossary.select_for_context = AsyncMock(return_value=[])

    built = await build_static_mode(
        summaries, glossary,
        user_id=uuid4(),
        project=_project(name='A&B <novel>'),
        message="",
    )
    # Raw XML must be parseable
    root = ET.fromstring(built.context)
    proj = root.find("project")
    assert proj is not None
    # ET.parse reverses the escape for us
    assert proj.attrib.get("name") == "A&B <novel>"


@pytest.mark.asyncio
async def test_whitespace_only_l1_summary_treated_as_missing():
    summaries = AsyncMock()
    summaries.get = AsyncMock(side_effect=[None, _summary("   \t\n   ", "project", uuid4())])
    glossary = AsyncMock()
    glossary.select_for_context = AsyncMock(return_value=[])

    built = await build_static_mode(
        summaries, glossary,
        user_id=uuid4(), project=_project(), message="",
    )
    root = ET.fromstring(built.context)
    assert root.find("project/summary") is None
