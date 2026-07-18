"""K18.1 — unit tests for the Mode 3 builder scaffold.

Phase 4a-δ: rerank now routes through the loreweave_llm SDK
(``llm_client.submit_and_wait`` returning a Job) instead of the
removed ``provider_client.chat_completion`` path."""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.context.modes.full import build_full_mode
from app.context.selectors.facts import L2FactResult
# Capture the REAL select_l3_passages at module import time — helpers
# that re-import it later would pick up whichever mock a previous
# `_patch_mode3_pieces` call installed (the AsyncMock), not the real
# function, and the rerank-propagation tests would silently stub out
# the code path they're trying to exercise.
from app.context.selectors.passages import (
    select_l3_passages as _REAL_SELECT_L3_PASSAGES,
)
from app.db.models import Project, Summary
from loreweave_llm.models import Job


class _FakeLLMClient:
    """Stand-in for ``app.clients.llm_client.LLMClient`` exposing only
    the ``submit_and_wait`` surface the rerank path uses."""

    def __init__(self, *, content: str = '{"order": []}') -> None:
        self.calls: list[dict[str, Any]] = []
        self._content = content

    async def submit_and_wait(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        return Job(
            job_id="00000000-0000-0000-0000-000000000001",
            operation="chat",
            status="completed",
            result={
                "messages": [{"role": "assistant", "content": self._content}],
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
            error=None,
            submitted_at="2026-04-27T00:00:00Z",
        )


USER_ID = UUID("11111111-1111-1111-1111-111111111111")


def _project(
    *, name: str = "My Novel",
    project_id: UUID | None = None,
    book_id: UUID | None = None,
    instructions: str = "",
    extraction_enabled: bool = True,
    tool_calling_enabled: bool = True,
    canon_capture_enabled: bool = True,
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
        tool_calling_enabled=tool_calling_enabled,
        canon_capture_enabled=canon_capture_enabled,
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
    # Mode 3 uses its own tighter constant (20) independent of the
    # D-T2-03 RECENT_MESSAGE_COUNT env knob — by design.
    assert result.recent_message_count == 20
    assert '<memory mode="full">' in result.context
    assert "<project" in result.context
    assert "<instructions>" in result.context
    assert "<facts>" not in result.context
    assert "<no_memory_for>" not in result.context


@pytest.mark.asyncio
async def test_built_context_surfaces_tool_calling_enabled(monkeypatch):
    """K21.12-BE (design D9) — Mode 3 carries the project's
    tool_calling_enabled onto BuiltContext so chat-service can gate its
    tool-calling loop. Both flag states must round-trip from the
    loaded project."""
    _patch_mode3_pieces(monkeypatch)

    enabled = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=_project(tool_calling_enabled=True),
        message="greetings",
    )
    assert enabled.tool_calling_enabled is True

    disabled = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=_project(tool_calling_enabled=False),
        message="greetings",
    )
    assert disabled.tool_calling_enabled is False


@pytest.mark.asyncio
async def test_built_context_surfaces_canon_capture_enabled(monkeypatch):
    """WS-4C Half A — Mode 3 carries the project's canon_capture_enabled onto
    BuiltContext so chat can gate its post-turn capture task. A setting that is
    stored but never read back is a bug, not a feature: assert BOTH states
    round-trip, so a hardcoded `True` (or a dropped field) reds this test."""
    _patch_mode3_pieces(monkeypatch)

    enabled = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=_project(canon_capture_enabled=True),
        message="greetings",
    )
    assert enabled.canon_capture_enabled is True

    disabled = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=_project(canon_capture_enabled=False),
        message="greetings",
    )
    assert disabled.canon_capture_enabled is False


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
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024  # D-EMB-MODEL-REF-01

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
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024  # D-EMB-MODEL-REF-01

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
async def test_context_length_scales_up_the_flat_budget(monkeypatch):
    """A 1M-context session must NOT get the same Mode-3 budget a small/unknown
    window would — passing context_length must scale mode3_token_budget UP,
    surviving more passages than the flat default alone would."""
    from app.context.selectors.passages import L3Passage
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
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024

    monkeypatch.setattr("app.context.modes.full.settings.mode3_token_budget", 80)

    flat = await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(), user_id=USER_ID, project=project,
        message="Tell me",
    )
    scaled = await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(), user_id=USER_ID, project=project,
        message="Tell me", context_length=1_000_000,
    )
    flat_count = flat.context.count("<passage ")
    scaled_count = scaled.context.count("<passage ")
    assert scaled_count > flat_count


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
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024  # D-EMB-MODEL-REF-01
    # Budget chosen so ~2 passages fit — forces the trimmer to drop the
    # lowest-score ones first. Must clear the fixed project+instructions
    # overhead (~184-209 tokens as of 2026-07-06 — grown from earlier
    # feature additions to the CoT instruction block) with room left for
    # at least one passage (~30-40 tokens each); re-tune if this drifts.
    monkeypatch.setattr(
        "app.context.modes.full.settings.mode3_token_budget", 320,
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


def _p4_entity(name: str, desc_words: int = 40):
    e = MagicMock()
    e.cached_name = name
    e.cached_aliases = []
    e.short_description = "lore " * desc_words
    e.kind_code = "character"
    e.tier = "fts"
    e.rank_score = 0.9
    e.entity_id = f"gid-{name}"
    e.is_pinned = False
    return e


@pytest.mark.asyncio
async def test_budget_demotes_glossary_to_entity_refs_not_drop(monkeypatch):
    """P4 (R-T4-05): when glossary must shrink to fit, tail entities are demoted
    to one-line <entity_refs> pointers (expandable via memory_recall_entity),
    NOT silently dropped — breadth survives the trim."""
    entities = [_p4_entity(f"Hero{i}") for i in range(8)]
    _patch_mode3_pieces(monkeypatch, glossary_entities=entities)

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024
    # Budget small enough to force glossary trimming, big enough for refs to
    # fit. Must clear the fixed project+instructions overhead (~184 tokens as
    # of 2026-07-06 — grown from earlier feature additions to the CoT
    # instruction block) with room for the entity_refs tier; re-tune if this drifts.
    monkeypatch.setattr("app.context.modes.full.settings.mode3_token_budget", 320)

    result = await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(),
        user_id=USER_ID, project=project, message="Tell me",
    )
    assert "<entity_refs" in result.context          # pointer tier rendered
    assert "memory_recall_entity" in result.context  # expand affordance named
    # every entity is present SOMEWHERE (full block or as a ref) — none vanished
    for i in range(8):
        assert f"Hero{i}" in result.context
    # and it still fits the budget
    assert result.token_count <= 320


@pytest.mark.asyncio
async def test_widened_l2_retry_recovers_facts_on_miss(monkeypatch):
    """P4 (R-T4-06): SPECIFIC_ENTITY query + empty first-pass facts → ONE
    relational 2-hop retry; recovered facts land in the block."""
    _patch_mode3_pieces(monkeypatch)  # base: everything empty
    calls: list = []

    async def fake_l2(*, user_id, project, intent):
        calls.append(intent)
        if intent.hop_count >= 2:
            return L2FactResult(current=["Alice rules the northern keep"])
        return L2FactResult()

    monkeypatch.setattr("app.context.modes.full._safe_l2_facts", fake_l2)

    project = _project()
    result = await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(),
        user_id=USER_ID, project=project, message="Tell me about Alice",
    )
    assert len(calls) == 2                       # first pass + ONE widened retry
    assert calls[1].hop_count == 2               # widened to relational 2-hop
    assert "l2_retry_widened" in calls[1].signals
    assert "northern keep" in result.context     # recovered facts rendered


@pytest.mark.asyncio
async def test_widened_retry_skipped_when_first_pass_has_facts(monkeypatch):
    _patch_mode3_pieces(monkeypatch)
    calls: list = []

    async def fake_l2(*, user_id, project, intent):
        calls.append(intent)
        # entity-anchored relation found → no need to widen
        return L2FactResult(background=["Alice — trusts — Bob"])

    monkeypatch.setattr("app.context.modes.full._safe_l2_facts", fake_l2)
    project = _project()
    await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(),
        user_id=USER_ID, project=project, message="Tell me about Alice",
    )
    assert len(calls) == 1  # no retry when the entity-anchored pass found facts


@pytest.mark.asyncio
async def test_widened_retry_fires_when_only_tool_facts(monkeypatch):
    """WS-4C — project-level tool facts (in `current`) must NOT mask an empty
    entity-relation walk: the widened retry still fires to try to recover
    relations for the named entity."""
    _patch_mode3_pieces(monkeypatch)
    calls: list = []

    async def fake_l2(*, user_id, project, intent):
        calls.append(intent)
        return L2FactResult(current=["the user wants a grimdark tone"])

    monkeypatch.setattr("app.context.modes.full._safe_l2_facts", fake_l2)
    project = _project()
    await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(),
        user_id=USER_ID, project=project, message="Tell me about Alice",
    )
    assert len(calls) == 2  # tool facts present but relations empty → still retry


@pytest.mark.asyncio
async def test_widened_retry_kill_switch(monkeypatch):
    _patch_mode3_pieces(monkeypatch)
    monkeypatch.setattr(
        "app.context.modes.full.settings.context_l2_retry_widened", False,
    )
    calls: list = []

    async def fake_l2(*, user_id, project, intent):
        calls.append(intent)
        return L2FactResult()

    monkeypatch.setattr("app.context.modes.full._safe_l2_facts", fake_l2)
    project = _project()
    await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(),
        user_id=USER_ID, project=project, message="Tell me about Alice",
    )
    assert len(calls) == 1  # switch off → no retry even on a miss


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
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024  # D-EMB-MODEL-REF-01
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
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024  # D-EMB-MODEL-REF-01

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
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024  # D-EMB-MODEL-REF-01

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


# ── K18.9 prompt-caching split ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_mode3_splits_at_project_boundary(monkeypatch):
    """K18.9: stable_context ends at `</project>`; glossary/facts/
    passages/absences/instructions are volatile. Invariant:
    context == stable + volatile."""
    _patch_mode3_pieces(
        monkeypatch,
        l0_summary=_summary("I am a novelist."),
        l1_summary=_summary("Book 1."),
    )

    project = _project(instructions="Write terse prose.")
    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=None,
        user_id=USER_ID,
        project=project,
        message="tell me about someone",
    )

    assert result.context == result.stable_context + result.volatile_context
    assert result.stable_context.rstrip().endswith("</project>")
    # Volatile starts with one of the per-message sections.
    volatile_head = result.volatile_context.lstrip()
    assert volatile_head.startswith(("<glossary>", "<facts>", "<passages>", "<no_memory_for>", "<instructions>"))


def _patch_l3_with_hits(monkeypatch, n: int = 3):
    """Let the REAL select_l3_passages run end-to-end by un-patching
    the AsyncMock that `_patch_mode3_pieces` installed for it, and
    instead patch the deeper Neo4j `find_passages_by_vector` to
    return in-memory hits. Used by the rerank propagation tests
    where we need build_full_mode → selector → rerank_passages →
    provider.chat_completion to actually fire."""
    from app.db.neo4j_repos.passages import Passage, PassageSearchHit

    # Undo the AsyncMock that _patch_mode3_pieces installed for
    # select_l3_passages so the real function runs. Use the module-
    # level _REAL_SELECT_L3_PASSAGES captured at import time — a
    # fresh `from ... import` here would bind to whatever was last
    # patched (i.e., the AsyncMock we're trying to undo).
    monkeypatch.setattr(
        "app.context.selectors.passages.select_l3_passages",
        _REAL_SELECT_L3_PASSAGES,
    )
    hits = [
        PassageSearchHit(
            passage=Passage(
                id=f"p{i}", user_id=str(USER_ID), project_id="p-1",
                source_type="chapter", source_id=f"c{i}", chunk_index=0,
                text=f"passage {i} content", embedding_model="bge-m3",
                is_hub=False, chapter_index=i,
            ),
            raw_score=0.9 - i * 0.01,
            vector=None,
        )
        for i in range(n)
    ]
    monkeypatch.setattr(
        "app.context.selectors.passages.find_passages_by_vector",
        AsyncMock(return_value=hits),
    )


@pytest.mark.asyncio
async def test_rerank_model_from_extraction_config_triggers_rerank(monkeypatch):
    """D-K18.3-02: project.extraction_config['rerank_model'] flows all
    the way from build_full_mode -> _safe_l3_passages -> real
    select_l3_passages -> rerank_passages -> llm_client.submit_and_wait.
    Proves the opt-in config key reaches the LLM call site."""
    # Full Mode 3 pipeline — but we use a REAL select_l3_passages, not
    # a mock, so the rerank code path executes.
    _patch_mode3_pieces(monkeypatch)  # L0/L1/L2 stubs
    _patch_l3_with_hits(monkeypatch, n=3)

    from app.clients.embedding_client import EmbeddingResult
    fake_llm = _FakeLLMClient(content='{"order": [2, 0, 1]}')

    embedding = MagicMock()
    embedding.embed = AsyncMock(return_value=EmbeddingResult(
        embeddings=[[0.1] * 1024], dimension=1024, model="bge-m3",
    ))

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024  # D-EMB-MODEL-REF-01
    project.extraction_config = {"rerank_model": "llama-3-rerank"}

    await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=embedding,
        llm_client=fake_llm,
        user_id=USER_ID,
        project=project,
        message="who is arthur",
    )
    assert len(fake_llm.calls) == 1
    assert fake_llm.calls[0]["model_ref"] == "llama-3-rerank"
    assert fake_llm.calls[0]["operation"] == "chat"


@pytest.mark.asyncio
async def test_rerank_skipped_when_extraction_config_has_no_rerank_model(
    monkeypatch,
):
    """Default config (no rerank_model key) must not invoke the LLM
    gateway. Projects without opt-in pay zero LLM cost."""
    from app.clients.embedding_client import EmbeddingResult
    _patch_mode3_pieces(monkeypatch)
    _patch_l3_with_hits(monkeypatch, n=3)

    fake_llm = _FakeLLMClient()
    embedding = MagicMock()
    embedding.embed = AsyncMock(return_value=EmbeddingResult(
        embeddings=[[0.1] * 1024], dimension=1024, model="bge-m3",
    ))

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024  # D-EMB-MODEL-REF-01
    project.extraction_config = {}  # no rerank_model key

    await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=embedding,
        llm_client=fake_llm,
        user_id=USER_ID,
        project=project,
        message="test",
    )
    assert fake_llm.calls == []


@pytest.mark.asyncio
async def test_mode3_split_preserved_after_budget_trim(monkeypatch):
    """K18.9: even when budget enforcer trims passages/glossary, the
    stable prefix (L0 + project) is protected so stable_context is
    identical to the non-trimmed case and the invariant holds."""
    from app.context.selectors.passages import L3Passage

    # Big passage payload so enforce_budget actually trims.
    passages = [
        L3Passage(
            text=f"Passage {i} — " + ("filler content " * 20),
            source_type="chapter", source_id=f"chap-{i}",
            chunk_index=0, score=0.5 - i * 0.01,
            is_hub=False, chapter_index=i,
        )
        for i in range(10)
    ]
    _patch_mode3_pieces(
        monkeypatch,
        l0_summary=_summary("Novelist."),
        l1_summary=_summary("Project summary."),
        l3_passages=passages,
    )
    # Force a tight budget so trimming fires.
    monkeypatch.setattr(
        "app.context.modes.full.settings.mode3_token_budget", 200,
    )

    project = _project(instructions="Be terse.")
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024  # D-EMB-MODEL-REF-01

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=MagicMock(),
        user_id=USER_ID,
        project=project,
        message="tell me",
    )
    # Stable prefix survives; invariant holds post-trim.
    assert result.context == result.stable_context + result.volatile_context
    assert result.stable_context.rstrip().endswith("</project>")
    # Prove trim actually fired: some passages were dropped. The input
    # had 10 passages totalling far more than the 200-token budget — at
    # least one had to go. If the trim logic ever regresses to a
    # no-op, this assertion catches it before the invariant check does.
    passage_count_in_output = result.volatile_context.count("<passage ")
    assert passage_count_in_output < 10


# ── P3 D5 summary_blend wire-up ─────────────────────────────────────────────


def _embed_returning(dim: int = 1024):
    """Build a MagicMock embedding_client whose .embed returns a vector."""
    from app.clients.embedding_client import EmbeddingResult
    embedding = MagicMock()
    embedding.embed = AsyncMock(return_value=EmbeddingResult(
        embeddings=[[0.1] * dim], dimension=dim, model="bge-m3",
    ))
    return embedding


def _patch_summary_blend(monkeypatch, *, hits=None, raises=False):
    """Patch the lazy-imported select_summary_blend symbol."""
    if raises:
        async def _raise(*a, **kw):
            raise RuntimeError("neo4j index missing")
        monkeypatch.setattr(
            "app.context.selectors.summary_blend.select_summary_blend",
            _raise,
        )
        return None
    mock = AsyncMock(return_value=hits or [])
    monkeypatch.setattr(
        "app.context.selectors.summary_blend.select_summary_blend",
        mock,
    )
    return mock


@pytest.mark.asyncio
async def test_specific_query_skips_summary_blend(monkeypatch):
    """is_abstract_query=False → selector never called, no <summaries>."""
    _patch_mode3_pieces(monkeypatch)
    blend_mock = _patch_summary_blend(monkeypatch, hits=[])

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=_embed_returning(),
        user_id=USER_ID,
        project=project,
        message="What did Arthur say?",  # short + specific
    )
    assert "<summaries>" not in result.context
    assert blend_mock.await_count == 0


@pytest.mark.asyncio
async def test_abstract_query_keyword_renders_summaries_block(monkeypatch):
    """Abstract keyword 'themes' → selector fires, <summaries> rendered."""
    from app.context.selectors.summary_blend import LevelSummaryHit
    hits = [
        LevelSummaryHit(
            level="book", node_id="b1", node_path="book",
            summary_text="The whole book is about redemption.",
            raw_score=0.9, weighted_score=0.36,
        ),
        LevelSummaryHit(
            level="part", node_id="p1", node_path="book/part-1",
            summary_text="Part 1 sets the protagonist's fall.",
            raw_score=0.8, weighted_score=0.24,
        ),
    ]
    _patch_mode3_pieces(monkeypatch)
    _patch_summary_blend(monkeypatch, hits=hits)

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=_embed_returning(),
        user_id=USER_ID,
        project=project,
        message="What are the themes of this book?",
    )
    assert "<summaries>" in result.context
    assert "redemption" in result.context
    assert "Part 1 sets" in result.context
    assert 'level="book"' in result.context
    assert 'path="book/part-1"' in result.context


@pytest.mark.asyncio
async def test_abstract_query_no_embedding_client_skips_block(monkeypatch):
    """Abstract query but caller passed embedding_client=None → no block."""
    _patch_mode3_pieces(monkeypatch)
    blend_mock = _patch_summary_blend(monkeypatch, hits=[])

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=None,
        user_id=USER_ID,
        project=_project(),
        message="Give me a summary of chapter 5.",
    )
    assert "<summaries>" not in result.context
    assert blend_mock.await_count == 0


@pytest.mark.asyncio
async def test_abstract_query_no_embedding_model_skips_block(monkeypatch):
    """Project has no embedding_model configured → no block."""
    _patch_mode3_pieces(monkeypatch)
    blend_mock = _patch_summary_blend(monkeypatch, hits=[])

    # _project() defaults embedding_model=None
    project = _project()
    assert project.embedding_model is None

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=_embed_returning(),
        user_id=USER_ID,
        project=project,
        message="Walk me through the plot arc.",
    )
    assert "<summaries>" not in result.context
    assert blend_mock.await_count == 0


@pytest.mark.asyncio
async def test_abstract_query_selector_raises_degrades_gracefully(monkeypatch):
    """Selector raises (e.g., index missing on legacy graph) → no block,
    Mode 3 still builds."""
    _patch_mode3_pieces(monkeypatch)
    _patch_summary_blend(monkeypatch, raises=True)

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=_embed_returning(),
        user_id=USER_ID,
        project=project,
        message="Give me an overview of the plot.",
    )
    assert "<summaries>" not in result.context
    assert "<memory" in result.context  # Mode 3 still rendered


@pytest.mark.asyncio
async def test_abstract_query_empty_hits_no_block(monkeypatch):
    """Selector returns [] (no summaries yet) → no <summaries> block."""
    _patch_mode3_pieces(monkeypatch)
    _patch_summary_blend(monkeypatch, hits=[])

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=_embed_returning(),
        user_id=USER_ID,
        project=project,
        message="Summarize the synopsis briefly.",
    )
    assert "<summaries>" not in result.context


@pytest.mark.asyncio
async def test_abstract_query_with_glossary_entity_short_circuits(monkeypatch):
    """Long query that mentions a glossary entity stays specific
    (entity match wins long-query branch); selector not called."""
    from app.context.modes.no_project import BuiltContext as _  # noqa
    # Provide a glossary entity with cached_name="Holmes" so the
    # entity-name list passed to is_abstract_query matches the message.
    entity = MagicMock()
    entity.cached_name = "Holmes"
    entity.cached_aliases = []
    entity.short_description = ""
    entity.kind_code = "char"
    entity.tier = "primary"
    entity.rank_score = 1.0

    _patch_mode3_pieces(monkeypatch, glossary_entities=[entity])
    blend_mock = _patch_summary_blend(monkeypatch, hits=[])

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024

    # 25 tokens + entity match — no abstract keyword, so Branch 2 runs
    # and the Holmes match keeps it specific.
    long_msg = (
        "Tell me everything that happened to Holmes during the events "
        "of the third chapter of the second volume of the novel."
    )
    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=_embed_returning(),
        user_id=USER_ID,
        project=project,
        message=long_msg,
    )
    assert "<summaries>" not in result.context
    assert blend_mock.await_count == 0


@pytest.mark.asyncio
async def test_summaries_dropped_after_passages_under_budget(monkeypatch):
    """K18.7 + P3 D5: passages drop first, summaries drop second,
    glossary/facts protected ahead of both."""
    from app.context.selectors.passages import L3Passage
    from app.context.selectors.summary_blend import LevelSummaryHit
    passages = [
        L3Passage(
            text=("filler " * 30) + f"passage {i}",
            source_type="chapter", source_id=f"ch-{i}", chunk_index=0,
            score=0.9 - i * 0.05, is_hub=False, chapter_index=i,
        )
        for i in range(5)
    ]
    summaries = [
        LevelSummaryHit(
            level="book", node_id="b1", node_path="book",
            summary_text=("summary text " * 20),
            raw_score=0.9, weighted_score=0.36,
        ),
        LevelSummaryHit(
            level="chapter", node_id="c1", node_path="book/p1/c1",
            summary_text=("summary text " * 20),
            raw_score=0.5, weighted_score=0.15,
        ),
    ]
    _patch_mode3_pieces(monkeypatch, l3_passages=passages)
    _patch_summary_blend(monkeypatch, hits=summaries)

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024

    # Budget tight enough to drop most passages + some summaries.
    monkeypatch.setattr(
        "app.context.modes.full.settings.mode3_token_budget", 200,
    )

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=_embed_returning(),
        user_id=USER_ID,
        project=project,
        message="What are the central themes of the book?",
    )
    # Token-count contract.
    assert result.token_count <= 200, (
        f"budget violated: {result.token_count} > 200"
    )
    # Passages drop before summaries — when both pressured, passage
    # count drops faster (priority 1 vs priority 2).
    passage_count = result.context.count("<passage ")
    assert passage_count < 5


@pytest.mark.asyncio
async def test_summaries_lowest_weighted_score_dropped_first(monkeypatch):
    """When trimming summaries, lowest weighted_score (chapter weight=0.3)
    drops before higher weighted_score (book weight=0.4)."""
    from app.context.selectors.summary_blend import LevelSummaryHit
    hits = [
        LevelSummaryHit(
            level="book", node_id="b1", node_path="book",
            summary_text=("book content " * 80) + "BOOK_MARKER",
            raw_score=0.9, weighted_score=0.36,
        ),
        LevelSummaryHit(
            level="chapter", node_id="c1", node_path="book/p1/c1",
            summary_text=("chapter content " * 80) + "CHAPTER_MARKER",
            raw_score=0.5, weighted_score=0.15,
        ),
    ]
    _patch_mode3_pieces(monkeypatch)
    _patch_summary_blend(monkeypatch, hits=hits)

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024

    # Each summary payload ≈ 195-200 tokens rendered; two together don't fit
    # alongside the fixed project+absences+instructions overhead for this
    # "synopsis" message (~308 tokens as of 2026-07-06 — this message's intent
    # classification pulls in a heavier CoT/absence block than a plain "Tell
    # me"). Budget 650 fits one summary (~503) but not both (~698); re-tune if
    # this drifts.
    monkeypatch.setattr(
        "app.context.modes.full.settings.mode3_token_budget", 650,
    )

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=_embed_returning(),
        user_id=USER_ID,
        project=project,
        message="Give me a synopsis of the book.",
    )
    # Higher weighted_score (book) survives; chapter trimmed.
    assert "BOOK_MARKER" in result.context
    assert "CHAPTER_MARKER" not in result.context


@pytest.mark.asyncio
async def test_summaries_block_triggers_with_summaries_instruction(monkeypatch):
    """has_summaries=True must add the <summaries>-specific guidance to
    the CoT instructions block."""
    from app.context.selectors.summary_blend import LevelSummaryHit
    hits = [
        LevelSummaryHit(
            level="book", node_id="b1", node_path="book",
            summary_text="A short summary.",
            raw_score=0.9, weighted_score=0.36,
        ),
    ]
    _patch_mode3_pieces(monkeypatch)
    _patch_summary_blend(monkeypatch, hits=hits)

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024

    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        embedding_client=_embed_returning(),
        user_id=USER_ID,
        project=project,
        message="What are the recurring themes?",
    )
    # The _WITH_SUMMARIES instruction line mentions "high-level overviews".
    assert "high-level overviews" in result.context


@pytest.mark.asyncio
async def test_glossary_timeout_increments_intent_classifier_metric(monkeypatch):
    """D-P3-INTENT-CLASSIFIER-GLOSSARY-METRIC regression-lock.

    When glossary lookup times out in `build_full_mode`, BOTH
    `layer_timeout_total{layer="glossary"}` AND
    `mode3_intent_classifier_glossary_unavailable_total` must
    increment. The new counter exists because the layer_timeout
    counter is shared with the static-mode builder; a Mode-3
    operator dashboard needs to split "intent classifier degraded"
    from "any glossary timeout anywhere".
    """
    import asyncio as _asyncio
    from app.config import settings
    from app.metrics import (
        layer_timeout_total,
        mode3_intent_classifier_glossary_unavailable_total,
    )

    monkeypatch.setattr(settings, "context_glossary_timeout_s", 0.05)
    _patch_mode3_pieces(monkeypatch)

    async def slow_glossary(*_a, **_kw):
        await _asyncio.sleep(0.5)
        return []

    monkeypatch.setattr(
        "app.context.modes.full.select_glossary_for_context",
        slow_glossary,
    )

    project = _project(name="t")
    before_layer = layer_timeout_total.labels(layer="glossary")._value.get()
    before_intent = mode3_intent_classifier_glossary_unavailable_total._value.get()

    await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=project,
        message="hello world",
    )

    after_layer = layer_timeout_total.labels(layer="glossary")._value.get()
    after_intent = mode3_intent_classifier_glossary_unavailable_total._value.get()

    assert after_layer == before_layer + 1, "general glossary timeout counter must fire"
    assert after_intent == before_intent + 1, (
        "Mode-3-specific intent classifier degradation counter must also fire"
    )


# ── W1 — per-section token map (additive) ────────────────────────────────────


@pytest.mark.asyncio
async def test_mode3_sections_cover_rendered_blocks(monkeypatch):
    l2 = L2FactResult(current=["Arthur — trusts — Lancelot"])
    _patch_mode3_pieces(
        monkeypatch,
        l0_summary=_summary("I am a novelist."),
        l1_summary=_summary("Book 1 of 5.", scope_type="project"),
        l2_result=l2,
    )
    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=_project(instructions="Be terse."),
        message="Tell me about Arthur",
    )
    # rendered blocks each get a positive per-section entry
    assert result.sections["user"] > 0
    assert result.sections["project"] > 0
    assert result.sections["facts"] > 0
    assert result.sections["instructions"] > 0
    # blocks that did NOT render are absent, not zero
    assert "passages" not in result.sections
    assert "summaries" not in result.sections
    assert "glossary_entities" not in result.sections
    # each section counted once → the split never exceeds the whole block
    assert sum(result.sections.values()) <= result.token_count


@pytest.mark.asyncio
async def test_mode3_sections_empty_everything_still_has_project_and_instructions(monkeypatch):
    _patch_mode3_pieces(monkeypatch)
    result = await build_full_mode(
        summaries_repo=MagicMock(),
        glossary_client=MagicMock(),
        user_id=USER_ID,
        project=_project(),
        message="greetings",
    )
    assert set(result.sections) >= {"project", "instructions"}
    assert "facts" not in result.sections


# ── M1a: passage→graph anchor bridge wiring ──────────────────────────

@pytest.mark.asyncio
async def test_m1a_bridge_facts_appear_in_context(monkeypatch):
    """When passages are present, bridge-expanded facts land in the facts block."""
    from app.context.selectors.passages import L3Passage
    passages = [
        L3Passage(
            text="He arrived at the inn late at night.",
            source_type="chapter", source_id="chap-1", chunk_index=0,
            score=0.9, is_hub=False, chapter_index=1,
        ),
    ]
    # Message-anchored L2 finds nothing (natural query) → bridge is the only source.
    _patch_mode3_pieces(monkeypatch, l3_passages=passages, l2_result=L2FactResult())
    monkeypatch.setattr(
        "app.context.modes.full._safe_expand_from_passages",
        AsyncMock(return_value=["Count Dracula — hosts — Jonathan Harker"]),
    )
    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024

    result = await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(), user_id=USER_ID, project=project,
        message="Who did he meet at the inn?",
    )
    assert "Count Dracula — hosts — Jonathan Harker" in result.context
    assert "<facts>" in result.context


@pytest.mark.asyncio
async def test_m1a_bridge_kill_switch_disables_expansion(monkeypatch):
    """context_passage_graph_expansion_enabled=False → bridge is never called."""
    from app.context.selectors.passages import L3Passage
    passages = [
        L3Passage(
            text="He arrived at the inn.", source_type="chapter",
            source_id="chap-1", chunk_index=0, score=0.9, is_hub=False,
            chapter_index=1,
        ),
    ]
    _patch_mode3_pieces(monkeypatch, l3_passages=passages, l2_result=L2FactResult())
    bridge = AsyncMock(return_value=["SHOULD — not — APPEAR"])
    monkeypatch.setattr("app.context.modes.full._safe_expand_from_passages", bridge)
    monkeypatch.setattr(
        "app.context.modes.full.settings.context_passage_graph_expansion_enabled", False
    )
    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024

    result = await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(), user_id=USER_ID, project=project,
        message="Who did he meet at the inn?",
    )
    bridge.assert_not_called()
    assert "SHOULD — not — APPEAR" not in result.context


# ── M1b working-scope boost wiring (_safe_l3_passages) ──────────────────────
# These guard the resolve→thread SEAM that lives only in _safe_l3_passages: a
# future edit dropping `current_chapter_index=working_chapter_index` (or the
# boost knobs) would pass every select_l3_passages unit test yet silently
# disable the boost in production. The one-shot live smoke can't catch a
# regression; a spy at the call site can (nil-tolerant-decorator wiring lesson).


def _fake_neo4j_session(monkeypatch):
    @asynccontextmanager
    async def fake_session():
        yield MagicMock()
    monkeypatch.setattr("app.context.modes.full.neo4j_session", fake_session)


@pytest.mark.asyncio
async def test_safe_l3_resolves_chapter_and_threads_boost(monkeypatch):
    """boost>0 + current_chapter_id set → resolve chapter_index and pass it +
    the boost knobs to select_l3_passages."""
    from app.context.modes.full import _safe_l3_passages
    from app.context.intent.classifier import classify

    _fake_neo4j_session(monkeypatch)
    resolve = AsyncMock(return_value=7)
    monkeypatch.setattr(
        "app.db.neo4j_repos.passages.get_chapter_index_for_source", resolve,
    )
    spy = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.context.selectors.passages.select_l3_passages", spy,
    )
    monkeypatch.setattr("app.context.modes.full.settings.context_working_scope_boost", 0.30)
    monkeypatch.setattr("app.context.modes.full.settings.context_working_scope_window", 2)

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024
    chap = uuid4()

    await _safe_l3_passages(
        _embed_returning(), user_id=USER_ID, project=project,
        message="what happens here", intent=classify("what happens here"),
        current_chapter_id=chap,
    )
    # the resolver was called, scoped to owner + project + the open chapter …
    resolve.assert_awaited_once()
    assert resolve.await_args.kwargs["chapter_id"] == str(chap)
    assert resolve.await_args.kwargs["project_id"] == str(project.project_id)
    # … and the resolved index + boost knobs reached the selector.
    kw = spy.await_args.kwargs
    assert kw["current_chapter_index"] == 7
    assert kw["working_scope_boost"] == 0.30
    assert kw["working_scope_window"] == 2


@pytest.mark.asyncio
async def test_safe_l3_killswitch_skips_resolution(monkeypatch):
    """boost=0.0 → the resolution query is skipped entirely and the selector
    gets current_chapter_index=None (byte-identical to pre-M1b)."""
    from app.context.modes.full import _safe_l3_passages
    from app.context.intent.classifier import classify

    _fake_neo4j_session(monkeypatch)
    resolve = AsyncMock(return_value=7)
    monkeypatch.setattr(
        "app.db.neo4j_repos.passages.get_chapter_index_for_source", resolve,
    )
    spy = AsyncMock(return_value=[])
    monkeypatch.setattr(
        "app.context.selectors.passages.select_l3_passages", spy,
    )
    monkeypatch.setattr("app.context.modes.full.settings.context_working_scope_boost", 0.0)

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024

    await _safe_l3_passages(
        _embed_returning(), user_id=USER_ID, project=project,
        message="q", intent=classify("q"),
        current_chapter_id=uuid4(),
    )
    resolve.assert_not_called()
    kw = spy.await_args.kwargs
    assert kw["current_chapter_index"] is None
    assert kw["working_scope_boost"] == 0.0


# ── M-recall CJK dict-anchor merge wiring (build_full_mode) ──────────────────
# Guards the seam: on a non-Latin message, dictionary anchors are UNIONed into
# intent.entities BEFORE select_l2_facts runs. A regression dropping the merge
# would silently revert CJK L2-recall to 0 facts (all unit mocks still green).


@pytest.mark.asyncio
async def test_cjk_dict_anchors_merged_into_l2(monkeypatch):
    from unittest.mock import AsyncMock as _AM
    _patch_mode3_pieces(monkeypatch)
    l2_spy = _AM(return_value=L2FactResult())
    monkeypatch.setattr("app.context.modes.full.select_l2_facts", l2_spy)
    monkeypatch.setattr("app.context.modes.full.settings.context_dict_anchor_enabled", True)
    monkeypatch.setattr("app.context.modes.full.get_anchor_index", _AM(return_value=MagicMock()))
    monkeypatch.setattr("app.context.modes.full.resolve_anchors", lambda *a, **k: ["九王子"])

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024
    await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(), user_id=USER_ID, project=project,
        message="九王子修炼什么武功？",
    )
    # the (first) L2 call saw the merged anchor, not just the classifier's clause.
    intent_arg = l2_spy.await_args_list[0].kwargs["intent"]
    assert "九王子" in intent_arg.entities


@pytest.mark.asyncio
async def test_english_message_skips_dict_anchoring(monkeypatch):
    from unittest.mock import AsyncMock as _AM
    _patch_mode3_pieces(monkeypatch)
    monkeypatch.setattr("app.context.modes.full.settings.context_dict_anchor_enabled", True)
    idx_spy = _AM(return_value=MagicMock())
    monkeypatch.setattr("app.context.modes.full.get_anchor_index", idx_spy)

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024
    await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(), user_id=USER_ID, project=project,
        message="who does the girl marry",  # pure ASCII → gate off
    )
    idx_spy.assert_not_called()


@pytest.mark.asyncio
async def test_role_message_anchors_protagonist_into_l2(monkeypatch):
    """A protagonist role-term ('主角') with no named person anchors the project's
    most-central entity, so select_l2_facts can resolve the role."""
    from unittest.mock import AsyncMock as _AM
    _patch_mode3_pieces(monkeypatch)
    l2_spy = _AM(return_value=L2FactResult())
    monkeypatch.setattr("app.context.modes.full.select_l2_facts", l2_spy)
    monkeypatch.setattr("app.context.modes.full.settings.context_role_anchor_enabled", True)
    # keep dict-anchoring inert so the test isolates the role path
    monkeypatch.setattr("app.context.modes.full.get_anchor_index", _AM(return_value=None))
    monkeypatch.setattr("app.context.modes.full.get_project_protagonist", _AM(return_value="张若尘"))

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024
    await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(), user_id=USER_ID, project=project,
        message="主角的母亲是谁？",
    )
    intent_arg = l2_spy.await_args_list[0].kwargs["intent"]
    assert "张若尘" in intent_arg.entities


@pytest.mark.asyncio
async def test_non_role_message_skips_protagonist(monkeypatch):
    from unittest.mock import AsyncMock as _AM
    _patch_mode3_pieces(monkeypatch)
    monkeypatch.setattr("app.context.modes.full.settings.context_role_anchor_enabled", True)
    prot_spy = _AM(return_value="张若尘")
    monkeypatch.setattr("app.context.modes.full.get_project_protagonist", prot_spy)
    monkeypatch.setattr("app.context.modes.full.get_anchor_index", _AM(return_value=None))

    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024
    await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(), user_id=USER_ID, project=project,
        message="张若尘的父亲是谁？",  # named, no role term
    )
    prot_spy.assert_not_called()


@pytest.mark.asyncio
async def test_zero_anchor_meter_fires_on_unanchored_question(monkeypatch):
    """A grounded question that resolves no L2 anchors bumps the zero-anchor meter
    under question='true' (the deferred generic-noun-coref frequency signal)."""
    from app.metrics import mode3_grounding_zero_anchor_total
    _patch_mode3_pieces(monkeypatch)  # select_l2_facts → empty (total()==0)
    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024
    before = mode3_grounding_zero_anchor_total.labels(question="true")._value.get()
    # English, no role term, no CJK → dict/role anchor paths stay inert.
    await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(), user_id=USER_ID, project=project,
        message="what happens next?",
    )
    after = mode3_grounding_zero_anchor_total.labels(question="true")._value.get()
    assert after == before + 1


@pytest.mark.asyncio
async def test_zero_anchor_meter_labels_non_question_false(monkeypatch):
    from app.metrics import mode3_grounding_zero_anchor_total
    _patch_mode3_pieces(monkeypatch)
    project = _project()
    project.embedding_model = "bge-m3"; project.embedding_dimension = 1024
    before = mode3_grounding_zero_anchor_total.labels(question="false")._value.get()
    await build_full_mode(
        summaries_repo=MagicMock(), glossary_client=MagicMock(),
        embedding_client=MagicMock(), user_id=USER_ID, project=project,
        message="remember this setting please",  # statement, not a question
    )
    after = mode3_grounding_zero_anchor_total.labels(question="false")._value.get()
    assert after == before + 1
