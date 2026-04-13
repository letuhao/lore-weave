"""Unit tests for K4-I2 per-candidate budget allocation."""

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.clients.glossary_client import GlossaryEntityForContext
from app.context.selectors.glossary import select_glossary_for_context
from app.db.models import Project


def _project(book_id=None) -> Project:
    now = datetime.now(timezone.utc)
    return Project(
        project_id=uuid4(),
        user_id=uuid4(),
        name="P",
        description="",
        project_type="book",
        book_id=book_id or uuid4(),
        instructions="",
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


@pytest.mark.asyncio
async def test_per_candidate_limit_divides_max_entities():
    """K4-I2: when 5 candidates are extracted with max_entities=20,
    each K2b call should ask for ~6 entities (20/5 + 2 cushion), not 20.
    """
    client = AsyncMock()
    client.select_for_context = AsyncMock(return_value=[])

    await select_glossary_for_context(
        client,
        user_id=uuid4(),
        project=_project(),
        message='"Alice" "Bob" "Carol" "Dave" "Eve"',  # 5 quoted candidates
        max_entities=20,
        max_tokens=800,
    )

    assert client.select_for_context.call_count == 5
    for call in client.select_for_context.call_args_list:
        per_call = call.kwargs["max_entities"]
        assert per_call < 20, f"expected smaller per-call limit, got {per_call}"
        # Math: 20 // 5 + 2 = 6
        assert per_call == 6


@pytest.mark.asyncio
async def test_per_candidate_limit_floor_is_5():
    """K4-I2: when many candidates make the integer division collapse,
    the per-call limit floors at 5 to keep each call useful."""
    client = AsyncMock()
    client.select_for_context = AsyncMock(return_value=[])

    # 5 candidates, max_entities=10 → 10//5+2 = 4. Floor kicks in → 5.
    await select_glossary_for_context(
        client,
        user_id=uuid4(),
        project=_project(),
        message='"Alice" "Bob" "Carol" "Dave" "Eve"',
        max_entities=10,
        max_tokens=800,
    )
    for call in client.select_for_context.call_args_list:
        assert call.kwargs["max_entities"] == 5


@pytest.mark.asyncio
async def test_single_candidate_uses_full_budget():
    """One candidate → no division benefit, but the per-call math still
    gives at least floor(20/1)+2 = 22 (above the requested 20)."""
    client = AsyncMock()
    client.select_for_context = AsyncMock(return_value=[])

    await select_glossary_for_context(
        client,
        user_id=uuid4(),
        project=_project(),
        message="Tell me about Alice",  # 1 candidate
        max_entities=20,
        max_tokens=800,
    )
    assert client.select_for_context.call_count == 1
    assert client.select_for_context.call_args.kwargs["max_entities"] == 22


@pytest.mark.asyncio
async def test_no_candidates_uses_full_budget():
    """No candidates → single empty-query call with the FULL budget
    (no division applies)."""
    client = AsyncMock()
    client.select_for_context = AsyncMock(return_value=[])

    await select_glossary_for_context(
        client,
        user_id=uuid4(),
        project=_project(),
        message="hello world",  # no proper nouns
        max_entities=20,
        max_tokens=800,
    )
    assert client.select_for_context.call_count == 1
    assert client.select_for_context.call_args.kwargs["max_entities"] == 20


@pytest.mark.asyncio
async def test_dedupe_across_parallel_calls():
    """K4.3 merge step: if two candidate calls return the SAME entity
    (e.g. via pinned tier), it appears once in the merged result."""
    same_id = str(uuid4())

    def make_entity():
        return GlossaryEntityForContext(
            entity_id=same_id,
            cached_name="Alice",
            cached_aliases=[],
            short_description=None,
            kind_code="character",
            is_pinned=True,
            tier="pinned",
            rank_score=1.0,
        )

    client = AsyncMock()
    client.select_for_context = AsyncMock(return_value=[make_entity()])

    result = await select_glossary_for_context(
        client,
        user_id=uuid4(),
        project=_project(),
        message="Tell me about Alice and Bob",  # 2 candidates
        max_entities=20,
        max_tokens=800,
    )
    assert len(result) == 1
    assert result[0].entity_id == same_id
