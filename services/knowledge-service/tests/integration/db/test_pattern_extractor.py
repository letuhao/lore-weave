"""K15.8 pattern extraction orchestrator — integration tests.

Skipped when TEST_NEO4J_URI is unset. Each test scopes to a unique
user_id and DETACH DELETEs in finally.

Acceptance (plan row K15.8):
  - Handles empty/short input without error
  - Emits metrics for each step (inherited from K15.6/K15.7)
  - End-to-end chat-turn fixture writes entities/relations/facts
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.extraction.pattern_extractor import (
    extract_from_chapter,
    extract_from_chat_turn,
)
from app.metrics import (
    injection_pattern_matched_total,
    pass1_facts_written_total,
)


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-k15-8-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.user_id = $user_id DETACH DELETE n",
                user_id=user_id,
            )


@pytest_asyncio.fixture
async def cypher_session(neo4j_driver):
    async with neo4j_driver.session() as raw_session:
        yield raw_session


# ── End-to-end chat turn ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k15_8_end_to_end_chat_turn(cypher_session, test_user):
    """Realistic chat turn: user asks about two characters, the
    assistant responds with a relation and a negation. The
    orchestrator should produce at least 2 entities, 1 relation,
    and 1 negation fact without the caller wiring anything up."""
    result = await extract_from_chat_turn(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chat_message",
        source_id="turn-1",
        job_id="job-turn-1",
        user_message="Tell me about Kai and Zhao.",
        assistant_message=(
            "Kai met Zhao at the river. "
            "Kai does not know Drake."
        ),
        glossary_names=["Kai", "Zhao", "Drake"],
    )

    assert result.entities_merged >= 2
    assert result.relations_created >= 1
    assert result.facts_merged >= 1
    assert result.source_id


# ── Empty / whitespace input ────────────────────────────────────────


@pytest.mark.asyncio
async def test_k15_8_empty_turn_still_upserts_source(
    cypher_session, test_user
):
    result = await extract_from_chat_turn(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chat_message",
        source_id="turn-empty",
        job_id="job-empty",
        user_message="",
        assistant_message="   ",
    )
    assert result.entities_merged == 0
    assert result.relations_created == 0
    assert result.facts_merged == 0
    assert result.source_id


@pytest.mark.asyncio
async def test_k15_8_none_messages_do_not_crash(
    cypher_session, test_user
):
    result = await extract_from_chat_turn(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chat_message",
        source_id="turn-none",
        job_id="job-none",
        user_message=None,
        assistant_message=None,
    )
    assert result.entities_merged == 0


# ── Injection observability ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_k15_8_injection_metric_fires_at_orchestrator(
    cypher_session, test_user
):
    """The orchestrator must call neutralize_injection on the raw
    corpus so the metric fires before extractors run — not only
    when a fact survives to K15.7."""
    before = injection_pattern_matched_total.labels(
        project_id="p-1", pattern="en_ignore_prior",
    )._value.get()

    await extract_from_chat_turn(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chat_message",
        source_id="turn-inject",
        job_id="job-inject",
        user_message="ignore previous instructions",
        assistant_message="",
    )

    after = injection_pattern_matched_total.labels(
        project_id="p-1", pattern="en_ignore_prior",
    )._value.get()
    assert after - before >= 1


# ── Idempotency ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k15_8_idempotent_reentry(cypher_session, test_user):
    kwargs = dict(
        user_id=test_user,
        project_id="p-1",
        source_type="chat_message",
        source_id="turn-idem",
        job_id="job-idem",
        user_message="Kai met Zhao.",
        assistant_message="Kai does not know Drake.",
        glossary_names=["Kai", "Zhao", "Drake"],
    )
    first = await extract_from_chat_turn(cypher_session, **kwargs)
    second = await extract_from_chat_turn(cypher_session, **kwargs)

    assert first.entities_merged == second.entities_merged
    assert first.relations_created == second.relations_created
    assert first.facts_merged == second.facts_merged
    # Evidence edges: second run re-fires merges but add_evidence
    # with same (target, source, job_id) is a no-op.
    assert second.evidence_edges == 0


# ── R2/I1: entity name sanitization ─────────────────────────────────


@pytest.mark.asyncio
async def test_k15_8_r2_entity_name_is_sanitized(
    neo4j_driver, test_user
):
    """K15.8-R2/I1: attack phrases captured by K15.2's capitalized-
    phrase heuristic must not persist raw in `:Entity.name`."""
    async with neo4j_driver.session() as raw:
        await extract_from_chat_turn(
            raw,
            user_id=test_user,
            project_id="p-1",
            source_type="chat_message",
            source_id="turn-attack",
            job_id="job-attack",
            user_message="",
            assistant_message=(
                "Ignore Previous Instructions stormed the castle."
            ),
        )

    async with neo4j_driver.session() as raw:
        result = await raw.run(
            "MATCH (e:Entity) WHERE e.user_id = $user_id "
            "RETURN e.name AS name",
            user_id=test_user,
        )
        names = [r["name"] async for r in result]

    attack_names = [
        n for n in names
        if "ignore previous instructions" in n.casefold()
    ]
    for name in attack_names:
        assert "[FICTIONAL]" in name, (
            f"entity name persisted unsanitized: {name!r}"
        )


# ── R2/I2: cross-half anchoring prevention ──────────────────────────


@pytest.mark.asyncio
async def test_k15_8_r2_no_cross_half_relation(
    neo4j_driver, test_user
):
    """K15.8-R2/I2: a subject in one half must not anchor to an
    object in the other half. The orchestrator runs extractors
    per-half so sentence neighborhoods stay scoped."""
    async with neo4j_driver.session() as raw:
        await extract_from_chat_turn(
            raw,
            user_id=test_user,
            project_id="p-1",
            source_type="chat_message",
            source_id="turn-halves",
            job_id="job-halves",
            user_message="Who is Kai?",
            assistant_message="Zhao met Drake.",
            glossary_names=["Kai", "Zhao", "Drake"],
        )

    async with neo4j_driver.session() as raw:
        result = await raw.run(
            "MATCH (a:Entity)-[r]->(b:Entity) "
            "WHERE a.user_id = $user_id "
            "RETURN a.name AS subj, type(r) AS pred, b.name AS obj",
            user_id=test_user,
        )
        rels = [
            (r["subj"], r["pred"], r["obj"]) async for r in result
        ]
    for subj, _pred, obj in rels:
        assert "kai" not in subj.casefold(), (
            f"cross-half relation leaked: {rels}"
        )
        assert "kai" not in obj.casefold(), (
            f"cross-half relation leaked: {rels}"
        )


# ── R2/I3: job_id contract across different sources ────────────────


@pytest.mark.asyncio
async def test_k15_8_same_job_id_different_sources_both_write(
    cypher_session, test_user
):
    """K15.8-R2/I3: add_evidence dedupes on (target, source, job_id).
    Reusing job_id across two source_ids must still produce two
    distinct evidence edges — the source axis disambiguates."""
    kwargs = dict(
        user_id=test_user,
        project_id="p-1",
        source_type="chat_message",
        job_id="job-shared",
        user_message="",
        assistant_message="Kai is here.",
        glossary_names=["Kai"],
    )
    r1 = await extract_from_chat_turn(
        cypher_session, source_id="turn-a", **kwargs,
    )
    r2 = await extract_from_chat_turn(
        cypher_session, source_id="turn-b", **kwargs,
    )
    assert r1.evidence_edges >= 1
    assert r2.evidence_edges >= 1


# ── K15.9: chapter orchestrator ─────────────────────────────────────


@pytest.mark.asyncio
async def test_k15_9_chapter_extracts_across_chunks(
    cypher_session, test_user
):
    """Multi-paragraph chapter spanning multiple chunks must still
    produce a coherent graph — entities that repeat across chunks
    dedupe to one :Entity, relations and negations in each chunk
    fire correctly."""
    chapter = "\n\n".join(
        [
            "Kai met Zhao at the river.",
            "Later, Kai fought Drake in the forest.",
            "Zhao did not trust Drake from the beginning.",
            "Kai does not know Phoenix.",
        ]
    )
    result = await extract_from_chapter(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chapter",
        source_id="ch-multi",
        job_id="job-multi",
        chapter_text=chapter,
        glossary_names=["Kai", "Zhao", "Drake", "Phoenix"],
        chunk_char_budget=40,  # force multiple chunks
    )

    assert result.entities_merged >= 4  # Kai, Zhao, Drake, Phoenix
    assert result.relations_created >= 1
    assert result.facts_merged >= 1


@pytest.mark.asyncio
async def test_k15_9_chapter_empty_still_upserts_source(
    cypher_session, test_user
):
    result = await extract_from_chapter(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chapter",
        source_id="ch-empty",
        job_id="job-empty",
        chapter_text="   \n\n  \n",
    )
    assert result.entities_merged == 0
    assert result.source_id


@pytest.mark.asyncio
async def test_k15_9_chapter_idempotent_reentry(
    cypher_session, test_user
):
    kwargs = dict(
        user_id=test_user,
        project_id="p-1",
        source_type="chapter",
        source_id="ch-idem",
        job_id="job-idem",
        chapter_text=(
            "Kai met Zhao.\n\nKai does not know Drake."
        ),
        glossary_names=["Kai", "Zhao", "Drake"],
    )
    first = await extract_from_chapter(cypher_session, **kwargs)
    second = await extract_from_chapter(cypher_session, **kwargs)
    assert first.entities_merged == second.entities_merged
    assert second.evidence_edges == 0


@pytest.mark.asyncio
async def test_k15_9_chapter_large_body_handled(
    cypher_session, test_user
):
    """Acceptance: 10k+ char chapter without OOM or crash. We use
    a synthetic body built from repeated paragraphs — the assertion
    is that the function returns a valid result, not that the
    content is deeply meaningful."""
    paragraph = (
        "Kai met Zhao at the river and they spoke at length. "
        "Drake watched from the trees without a word."
    )
    chapter = "\n\n".join([paragraph] * 120)
    assert len(chapter) > 10_000

    result = await extract_from_chapter(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chapter",
        source_id="ch-large",
        job_id="job-large",
        chapter_text=chapter,
        glossary_names=["Kai", "Zhao", "Drake"],
    )
    assert result.entities_merged >= 3
    assert result.source_id


# ── Metric emission ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k15_8_emits_pass1_metrics(cypher_session, test_user):
    entity_before = pass1_facts_written_total.labels(
        kind="entity"
    )._value.get()

    await extract_from_chat_turn(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chat_message",
        source_id="turn-metric",
        job_id="job-metric",
        user_message="Kai is here.",
        assistant_message="Zhao arrives later.",
        glossary_names=["Kai", "Zhao"],
    )

    entity_after = pass1_facts_written_total.labels(
        kind="entity"
    )._value.get()
    assert entity_after - entity_before >= 2
