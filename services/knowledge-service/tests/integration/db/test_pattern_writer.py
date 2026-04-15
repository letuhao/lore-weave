"""K15.7 pattern extraction writer — integration tests vs live Neo4j.

Skipped when TEST_NEO4J_URI is unset. Each test scopes to a unique
user_id and DETACH DELETEs in finally.

Acceptance (plan row K15.7):
  - All writes parameterized (inherited from K11 repo primitives)
  - Idempotent: re-running same input → same counts, no duplicates
  - pass1_facts_written_total metric incremented
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.extraction.entity_detector import EntityCandidate
from app.extraction.negation import NegationFact
from app.extraction.pattern_writer import write_extraction
from app.extraction.triple_extractor import Triple
from app.metrics import pass1_facts_written_total


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-k15-7-{uuid.uuid4().hex[:12]}"
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


def _kai() -> EntityCandidate:
    return EntityCandidate(
        name="Kai", confidence=0.9, kind_hint="character",
        signals={"glossary": 0.45},
    )


def _zhao() -> EntityCandidate:
    return EntityCandidate(
        name="Zhao", confidence=0.85, kind_hint="character",
        signals={"glossary": 0.45},
    )


def _drake() -> EntityCandidate:
    return EntityCandidate(
        name="Drake", confidence=0.8, kind_hint="character",
        signals={"glossary": 0.45},
    )


# ── Entities only ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k15_7_writes_entities_and_evidence(
    cypher_session, test_user
):
    result = await write_extraction(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chapter",
        source_id="ch-1",
        job_id="job-entities",
        entities=[_kai(), _zhao()],
    )
    assert result.entities_merged == 2
    assert result.evidence_edges == 2
    assert result.relations_created == 0
    assert result.facts_merged == 0
    assert result.skipped_missing_endpoint == 0


# ── R1/I1: duplicate candidate dedupe ───────────────────────────────


@pytest.mark.asyncio
async def test_k15_7_r1_duplicate_candidates_are_deduped(
    cypher_session, test_user
):
    """K15.7-R1/I1: three candidates folding to the same
    (folded_name, kind_hint) key must collapse to a single
    merge_entity call and a single evidence edge. entities_merged
    reports the deduped count, not the raw input count, so metrics
    and dashboards stay honest."""
    dupes = [
        EntityCandidate(
            name="Kai", confidence=0.7, kind_hint="character",
            signals={"glossary": 0.4},
        ),
        EntityCandidate(
            name="kai", confidence=0.9, kind_hint="character",
            signals={"glossary": 0.4},
        ),
        EntityCandidate(
            name="KAI", confidence=0.5, kind_hint="character",
            signals={"glossary": 0.4},
        ),
    ]
    result = await write_extraction(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chapter",
        source_id="ch-dedupe",
        job_id="job-dedupe",
        entities=dupes,
    )
    assert result.entities_merged == 1
    assert result.evidence_edges == 1


# ── Entities + triples ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k15_7_writes_relations_between_candidates(
    cypher_session, test_user
):
    triples = [
        Triple(
            subject="Kai", predicate="met", object="Zhao",
            confidence=0.5, pending_validation=True,
            sentence="Kai met Zhao at the river.",
        ),
    ]
    result = await write_extraction(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chapter",
        source_id="ch-2",
        job_id="job-triples",
        entities=[_kai(), _zhao()],
        triples=triples,
    )
    assert result.entities_merged == 2
    assert result.relations_created == 1
    assert result.skipped_missing_endpoint == 0


@pytest.mark.asyncio
async def test_k15_7_triple_missing_endpoint_is_skipped(
    cypher_session, test_user
):
    """Subject is in the candidate list but object is not — the
    writer must drop the triple and bump `skipped_missing_endpoint`
    rather than synthesize a new :Entity on the fly."""
    triples = [
        Triple(
            subject="Kai", predicate="met", object="Phoenix",
            confidence=0.5, pending_validation=True,
            sentence="Kai met Phoenix.",
        ),
    ]
    result = await write_extraction(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chapter",
        source_id="ch-3",
        job_id="job-missing",
        entities=[_kai()],
        triples=triples,
    )
    assert result.relations_created == 0
    assert result.skipped_missing_endpoint == 1


# ── Entities + negations ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k15_7_writes_negation_facts(cypher_session, test_user):
    negations = [
        NegationFact(
            subject="Kai",
            marker="does not know",
            object="Zhao",
            confidence=0.5,
            pending_validation=True,
            fact_type="negation",
            sentence="Kai does not know Zhao.",
        ),
    ]
    result = await write_extraction(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chapter",
        source_id="ch-4",
        job_id="job-negations",
        entities=[_kai(), _zhao()],
        negations=negations,
    )
    assert result.facts_merged == 1
    # Entity evidence (2) + fact evidence (1)
    assert result.evidence_edges == 3


@pytest.mark.asyncio
async def test_k15_7_negation_missing_subject_is_skipped(
    cypher_session, test_user
):
    negations = [
        NegationFact(
            subject="Phoenix",
            marker="is unaware",
            object=None,
            confidence=0.5,
            pending_validation=True,
            fact_type="negation",
            sentence="Phoenix is unaware of the plot.",
        ),
    ]
    result = await write_extraction(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chapter",
        source_id="ch-5",
        job_id="job-neg-missing",
        entities=[_kai()],
        negations=negations,
    )
    assert result.facts_merged == 0
    assert result.skipped_missing_endpoint == 1


# ── Idempotency ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k15_7_idempotent_reentry(cypher_session, test_user):
    """Acceptance criterion: re-running the same input produces no
    duplicates. We run the same batch twice with the same job_id
    and assert the second run adds ZERO new evidence edges."""
    entities = [_kai(), _zhao(), _drake()]
    triples = [
        Triple(
            subject="Kai", predicate="met", object="Zhao",
            confidence=0.5, pending_validation=True,
            sentence="Kai met Zhao.",
        ),
        Triple(
            subject="Drake", predicate="fought", object="Kai",
            confidence=0.5, pending_validation=True,
            sentence="Drake fought Kai.",
        ),
    ]
    negations = [
        NegationFact(
            subject="Kai", marker="does not know", object="Drake",
            confidence=0.5, pending_validation=True,
            fact_type="negation",
            sentence="Kai does not know Drake.",
        ),
    ]

    kwargs = dict(
        user_id=test_user,
        project_id="p-1",
        source_type="chapter",
        source_id="ch-idempotent",
        job_id="job-idempotent",
        entities=entities,
        triples=triples,
        negations=negations,
    )

    first = await write_extraction(cypher_session, **kwargs)
    second = await write_extraction(cypher_session, **kwargs)

    assert first.entities_merged == 3
    assert first.relations_created == 2
    assert first.facts_merged == 1
    assert first.evidence_edges == 4  # 3 entities + 1 fact

    # Second run: primitives re-fire the merge, but add_evidence
    # recognizes (target, source, job_id) and returns created=False,
    # so evidence_edges == 0.
    assert second.entities_merged == 3
    assert second.relations_created == 2
    assert second.facts_merged == 1
    assert second.evidence_edges == 0


# ── Verify no duplicate nodes/edges after re-run ───────────────────


@pytest.mark.asyncio
async def test_k15_7_idempotent_graph_shape_unchanged(
    neo4j_driver, test_user
):
    """Beyond counters: actually count nodes/edges in Neo4j before
    and after re-run. Must not grow."""
    entities = [_kai(), _zhao()]
    triples = [
        Triple(
            subject="Kai", predicate="met", object="Zhao",
            confidence=0.5, pending_validation=True,
            sentence="Kai met Zhao.",
        ),
    ]
    negations = [
        NegationFact(
            subject="Kai", marker="does not know", object="Zhao",
            confidence=0.5, pending_validation=True,
            fact_type="negation",
            sentence="Kai does not know Zhao.",
        ),
    ]

    async with neo4j_driver.session() as raw:
        await write_extraction(
            raw,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-graph",
            job_id="job-graph",
            entities=entities,
            triples=triples,
            negations=negations,
        )

    async with neo4j_driver.session() as raw:
        result = await raw.run(
            "MATCH (n) WHERE n.user_id = $user_id "
            "RETURN labels(n)[0] AS label, count(n) AS c",
            user_id=test_user,
        )
        counts_1 = {r["label"]: r["c"] async for r in result}

    async with neo4j_driver.session() as raw:
        await write_extraction(
            raw,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-graph",
            job_id="job-graph",
            entities=entities,
            triples=triples,
            negations=negations,
        )

    async with neo4j_driver.session() as raw:
        result = await raw.run(
            "MATCH (n) WHERE n.user_id = $user_id "
            "RETURN labels(n)[0] AS label, count(n) AS c",
            user_id=test_user,
        )
        counts_2 = {r["label"]: r["c"] async for r in result}

    assert counts_1 == counts_2, (
        f"graph grew on re-run: {counts_1} → {counts_2}"
    )
    # Sanity: expected shape
    assert counts_1.get("Entity") == 2
    assert counts_1.get("Fact") == 1
    assert counts_1.get("ExtractionSource") == 1


# ── Metric emission ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k15_7_metric_pass1_facts_written(
    cypher_session, test_user
):
    entity_before = pass1_facts_written_total.labels(
        kind="entity"
    )._value.get()
    relation_before = pass1_facts_written_total.labels(
        kind="relation"
    )._value.get()
    fact_before = pass1_facts_written_total.labels(
        kind="fact"
    )._value.get()

    await write_extraction(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chapter",
        source_id="ch-metric",
        job_id="job-metric",
        entities=[_kai(), _zhao()],
        triples=[
            Triple(
                subject="Kai", predicate="met", object="Zhao",
                confidence=0.5, pending_validation=True,
                sentence="Kai met Zhao.",
            ),
        ],
        negations=[
            NegationFact(
                subject="Kai", marker="does not know",
                object="Zhao", confidence=0.5,
                pending_validation=True, fact_type="negation",
                sentence="Kai does not know Zhao.",
            ),
        ],
    )

    assert pass1_facts_written_total.labels(
        kind="entity"
    )._value.get() - entity_before >= 2
    assert pass1_facts_written_total.labels(
        kind="relation"
    )._value.get() - relation_before >= 1
    assert pass1_facts_written_total.labels(
        kind="fact"
    )._value.get() - fact_before >= 1


# ── Empty input ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k15_7_empty_input_still_upserts_source(
    cypher_session, test_user
):
    """Even with no entities/triples/negations, the writer still
    creates the :ExtractionSource node so later calls with the same
    source_id don't create duplicates."""
    result = await write_extraction(
        cypher_session,
        user_id=test_user,
        project_id="p-1",
        source_type="chapter",
        source_id="ch-empty",
        job_id="job-empty",
    )
    assert result.entities_merged == 0
    assert result.relations_created == 0
    assert result.facts_merged == 0
    assert result.source_id  # non-empty id returned
