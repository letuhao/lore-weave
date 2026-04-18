"""K18.1 — unit tests for the Mode 3 builder scaffold."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.context.modes.full import build_full_mode
from app.context.selectors.facts import L2FactResult
from app.db.models import Project, Summary


USER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _project(
    *, name: str = "My Novel",
    project_id: UUID | None = None,
    book_id: UUID | None = None,
    instructions: str = "",
    extraction_enabled: bool = True,
) -> Project:
    now = datetime.now(timezone.utc)
    return Project(
        project_id=project_id or uuid4(),
        user_id=USER_ID,
        name=name,
        description="",
        project_type="book",
        book_id=book_id,
        instructions=instructions,
        extraction_enabled=extraction_enabled,
        extraction_status="disabled",
        embedding_model=None,
        extraction_config={},
        last_extracted_at=None,
        estimated_cost_usd=Decimal("0"),
        actual_cost_usd=Decimal("0"),
        is_archived=False,
        version=1,
        created_at=now,
        updated_at=now,
    )


def _summary(content: str, scope_type: str = "global") -> Summary:
    now = datetime.now(timezone.utc)
    return Summary(
        summary_id=uuid4(),
        user_id=USER_ID,
        scope_type=scope_type,
        scope_id=None,
        content=content,
        token_count=None,
        version=1,
        created_at=now,
        updated_at=now,
    )


def _patch_mode3_pieces(
    monkeypatch,
    *,
    l0_summary=None,
    l1_summary=None,
    glossary_entities: list | None = None,
    l2_result: L2FactResult | None = None,
    l2_raises: bool = False,
    l3_passages: list | None = None,
):
    """Patch out all the I/O the Mode 3 builder does."""
    monkeypatch.setattr(
        "app.context.modes.full.load_global_summary",
        AsyncMock(return_value=l0_summary),
    )
    monkeypatch.setattr(
        "app.context.modes.full.load_project_summary",
        AsyncMock(return_value=l1_summary),
    )
    monkeypatch.setattr(
        "app.context.modes.full.select_glossary_for_context",
        AsyncMock(return_value=glossary_entities or []),
    )

    if l2_raises:
        async def raise_l2(*a, **kw):
            raise RuntimeError("neo4j down")
        monkeypatch.setattr(
            "app.context.modes.full.select_l2_facts", raise_l2,
        )
    else:
        monkeypatch.setattr(
            "app.context.modes.full.select_l2_facts",
            AsyncMock(return_value=l2_result or L2FactResult()),
        )

    # L3: patch the lazy-imported symbol inside passages selector module.
    monkeypatch.setattr(
        "app.context.selectors.passages.select_l3_passages",
        AsyncMock(return_value=l3_passages or []),
    )

    # neo4j_session context-manager factory.
    @asynccontextmanager
    async def fake_session():
        yield MagicMock()
    monkeypatch.setattr("app.context.modes.full.neo4j_session", fake_session)


@pytest.mark.asyncio
async def test_empty_everything_still_emits_valid_block(monkeypatch):
    """No L0, no L1, no glossary, no L2, no absences — still a valid
    Mode 3 envelope with just project + instructions."""
    _patch_mode3_pieces(monkeypatch)

    project = _project(name="Test")
    # "greetings" is lowercase → intent classifier extracts no entities,
    # so no absence block is emitted for this "empty-everything" case.
    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=project,
        message="greetings",
    )
    assert result.mode == "full"
    assert result.recent_message_count == 20  # Mode 3 tighter than Mode 2's 50
    assert '<memory mode="full">' in result.context
    assert "<project" in result.context
    assert "<instructions>" in result.context
    assert "<facts>" not in result.context
    assert "<no_memory_for>" not in result.context


@pytest.mark.asyncio
async def test_l2_facts_appear_in_facts_block(monkeypatch):
    l2 = L2FactResult(
        background=["Arthur — trusts — Lancelot"],
        negative=["Arthur does not know Morgana"],
    )
    _patch_mode3_pieces(monkeypatch, l2_result=l2)

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=_project(),
        message="Tell me about Arthur",
    )
    assert "<facts>" in result.context
    assert "<background>" in result.context
    assert "Arthur — trusts — Lancelot" in result.context
    assert "<negative>" in result.context
    assert "Arthur does not know Morgana" in result.context


@pytest.mark.asyncio
async def test_absence_block_appears_when_entities_unknown(monkeypatch):
    """Message mentions entities the L2 selector didn't return facts for."""
    _patch_mode3_pieces(monkeypatch, l2_result=L2FactResult())

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=_project(),
        message="What does Arthur know about Lancelot?",
    )
    assert "<no_memory_for>" in result.context
    assert "Arthur" in result.context
    assert "Lancelot" in result.context


@pytest.mark.asyncio
async def test_neo4j_failure_degrades_to_mode2_shape(monkeypatch):
    """L2 query throws → Mode 3 still builds, just without facts."""
    _patch_mode3_pieces(monkeypatch, l2_raises=True)

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=_project(),
        message="anything",
    )
    assert result.mode == "full"
    assert "<facts>" not in result.context
    # Instructions still present → LLM gets guidance even without graph.
    assert "<instructions>" in result.context


@pytest.mark.asyncio
async def test_l1_summary_dedupes_l2_facts(monkeypatch):
    """Facts already covered by the L1 summary must be dropped."""
    l1 = _summary(
        "In the court of Camelot, Arthur trusts Lancelot with his life.",
        scope_type="project",
    )
    l2 = L2FactResult(background=[
        "Arthur trusts Lancelot deeply",  # covered by L1 (2+ overlap)
        "Galahad seeks Grail",             # not covered
    ])
    _patch_mode3_pieces(monkeypatch, l1_summary=l1, l2_result=l2)

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=_project(),
        message="Tell me about Arthur and Galahad",
    )
    assert "Galahad seeks Grail" in result.context
    assert "Arthur trusts Lancelot deeply" not in result.context


@pytest.mark.asyncio
async def test_project_instructions_included(monkeypatch):
    _patch_mode3_pieces(monkeypatch)

    project = _project(instructions="Write in formal tone.")
    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=project,
        message="Hi",
    )
    assert "formal tone" in result.context


@pytest.mark.asyncio
async def test_recent_message_count_is_20(monkeypatch):
    """Mode 3 uses 20 messages — verified because chat-service's K18.10
    relies on this value to trim history."""
    _patch_mode3_pieces(monkeypatch)

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=_project(),
        message="Hi",
    )
    assert result.recent_message_count == 20


# ── K18.3 L3 passage integration ────────────────────────────────────


@pytest.mark.asyncio
async def test_l3_passages_rendered_in_block(monkeypatch):
    """L3 selector returns passages → Mode 3 emits a <passages> block."""
    from app.context.selectors.passages import L3Passage
    passages = [
        L3Passage(
            text="Arthur draws Excalibur from the stone.",
            source_type="chapter",
            source_id="chap-1",
            chunk_index=0,
            score=0.92,
            is_hub=False,
            chapter_index=1,
        ),
    ]
    _patch_mode3_pieces(monkeypatch, l3_passages=passages)

    # Project needs an embedding_model so the L3 path doesn't short-circuit.
    project = _project()
    project.embedding_model = "bge-m3"

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=MagicMock(),  # mocked at selector level
        user_id=USER_ID,
        project=project,
        message="Tell me about Arthur",
    )
    assert "<passages>" in result.context
    assert "Arthur draws Excalibur" in result.context
    assert 'source_type="chapter"' in result.context


@pytest.mark.asyncio
async def test_l3_empty_when_no_embedding_client(monkeypatch):
    """No embedding_client → L3 stays empty and <passages> block is absent."""
    _patch_mode3_pieces(monkeypatch)

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=None,   # Track 1 / caller didn't wire one
        user_id=USER_ID,
        project=_project(),
        message="Tell me about Arthur",
    )
    assert "<passages>" not in result.context


@pytest.mark.asyncio
async def test_budget_drops_passages_first(monkeypatch):
    """K18.7: when over budget, passages are dropped before any
    other block (lowest priority)."""
    from app.context.selectors.passages import L3Passage
    # 10 passages × ~50 tokens each = ~500 tokens from passages alone
    passages = [
        L3Passage(
            text=("filler " * 40) + f"passage {i}",
            source_type="chapter", source_id=f"ch-{i}", chunk_index=0,
            score=0.9 - (i * 0.01), is_hub=False, chapter_index=i,
        )
        for i in range(10)
    ]
    _patch_mode3_pieces(monkeypatch, l3_passages=passages)

    project = _project()
    project.embedding_model = "bge-m3"

    # Tight budget forces the trim.
    monkeypatch.setattr(
        "app.context.modes.full.settings.mode3_token_budget", 80,
    )

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=MagicMock(),
        user_id=USER_ID,
        project=project,
        message="Tell me",
    )
    # Passages must be trimmed to fit budget.
    passage_count_in_output = result.context.count("<passage ")
    assert passage_count_in_output < 10
    # Some pieces survive — project block is protected.
    assert "<project" in result.context


@pytest.mark.asyncio
async def test_budget_drops_lowest_score_passages_first(monkeypatch):
    """K18.7: when trimming passages, lowest-score ones go first."""
    from app.context.selectors.passages import L3Passage
    passages = [
        L3Passage(
            text=("word " * 30) + f"top-{i}",
            source_type="chapter", source_id=f"ch-{i}", chunk_index=0,
            score=(0.3 + i * 0.1),  # 0.3, 0.4, 0.5, 0.6, 0.7
            is_hub=False, chapter_index=i,
        )
        for i in range(5)
    ]
    _patch_mode3_pieces(monkeypatch, l3_passages=passages)

    project = _project()
    project.embedding_model = "bge-m3"
    # Budget chosen so ~2 passages fit — forces the trimmer to drop
    # the lowest-score ones first.
    monkeypatch.setattr(
        "app.context.modes.full.settings.mode3_token_budget", 200,
    )

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=MagicMock(),
        user_id=USER_ID,
        project=project,
        message="Tell me",
    )
    # Highest-score passage (top-4, score=0.7) survives. Lowest-score
    # (top-0, score=0.3) is trimmed first.
    assert "top-4" in result.context
    assert "top-0" not in result.context


@pytest.mark.asyncio
async def test_budget_token_count_respects_budget(monkeypatch):
    """K18.7 — the contract: after trimming, token_count <= budget.

    This explicitly exercises the primary K18.7 invariant rather than
    inferring it from content presence/absence."""
    from app.context.selectors.passages import L3Passage
    passages = [
        L3Passage(
            text=("filler " * 30) + f"passage {i}",
            source_type="chapter", source_id=f"ch-{i}", chunk_index=0,
            score=0.9 - (i * 0.05), is_hub=False, chapter_index=i,
        )
        for i in range(10)
    ]
    _patch_mode3_pieces(monkeypatch, l3_passages=passages)

    project = _project()
    project.embedding_model = "bge-m3"
    budget = 250
    monkeypatch.setattr(
        "app.context.modes.full.settings.mode3_token_budget", budget,
    )

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=MagicMock(),
        user_id=USER_ID,
        project=project,
        message="Tell me",
    )
    # Core K18.7 invariant.
    assert result.token_count <= budget, (
        f"budget violated: {result.token_count} > {budget}\n"
        f"context=\n{result.context}"
    )


@pytest.mark.asyncio
async def test_budget_keeps_l0_l1_instructions_protected(monkeypatch):
    """K18.7: L0, L1, project instructions, and mode-instructions are
    NEVER dropped even under extreme budget pressure."""
    from app.context.selectors.passages import L3Passage
    l0 = _summary("User bio: I am a novelist.")
    l1 = _summary("Project summary: a fantasy epic.", scope_type="project")
    big_passage = L3Passage(
        text="huge passage " * 200,
        source_type="chapter", source_id="ch-1", chunk_index=0,
        score=0.99, is_hub=False, chapter_index=1,
    )
    _patch_mode3_pieces(
        monkeypatch,
        l0_summary=l0, l1_summary=l1,
        l3_passages=[big_passage],
    )

    project = _project(instructions="Always be formal.")
    project.embedding_model = "bge-m3"

    # Unreasonably small budget — forces every drop path to run.
    monkeypatch.setattr(
        "app.context.modes.full.settings.mode3_token_budget", 50,
    )

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=MagicMock(),
        user_id=USER_ID,
        project=project,
        message="hi",
    )
    # Protected layers remain.
    assert "User bio" in result.context
    assert "Project summary" in result.context
    assert "Always be formal." in result.context
    assert "<instructions>" in result.context  # CoT block
    # Passage was dropped.
    assert "<passage " not in result.context


@pytest.mark.asyncio
async def test_l3_hits_count_as_absence_coverage(monkeypatch):
    """Entity mentioned in a passage but not in L2 facts should NOT
    land in <no_memory_for>."""
    from app.context.selectors.passages import L3Passage
    passages = [
        L3Passage(
            text="Morgana cast her shadow over the realm.",
            source_type="chapter",
            source_id="chap-5",
            chunk_index=3,
            score=0.80,
            is_hub=False,
            chapter_index=5,
        ),
    ]
    _patch_mode3_pieces(monkeypatch, l3_passages=passages)

    project = _project()
    project.embedding_model = "bge-m3"

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=MagicMock(),
        user_id=USER_ID,
        project=project,
        message="Tell me about Morgana",
    )
    # Morgana IS in a passage — absence detection should NOT flag it.
    assert "<no_memory_for>" not in result.context
