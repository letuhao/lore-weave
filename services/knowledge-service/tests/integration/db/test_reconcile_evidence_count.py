"""K11.9 integration tests — evidence_count drift reconciler.

Skipped when TEST_NEO4J_URI is unset. Each test creates nodes under
a unique user_id and cleans them up in a finally block so parallel
runs don't collide.

Acceptance criteria (from K11.9 plan):
  - Drift in test data gets corrected
  - Normal run (no drift) fixes zero nodes
  - Metric `evidence_count_drift_fixed_total` increments
  - Multi-tenant safe — reconcile against user A does not touch user B
  - Optional project_id filter narrows the sweep
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.entities import merge_entity
from app.db.neo4j_repos.events import merge_event
from app.db.neo4j_repos.facts import merge_fact
from app.db.neo4j_repos.provenance import add_evidence, upsert_extraction_source
from app.jobs.reconcile_evidence_count import (
    RECONCILE_LABELS,
    ReconcileResult,
    reconcile_evidence_count,
)
from app.metrics import evidence_count_drift_fixed_total


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-k119-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                """
                MATCH (n) WHERE n.user_id = $user_id
                DETACH DELETE n
                """,
                user_id=user_id,
            )


async def _read_counter(label: str) -> float:
    return evidence_count_drift_fixed_total.labels(node_label=label)._value.get()


# ── clean run ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_9_clean_run_fixes_nothing(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
            confidence=0.8,
        )
        result = await reconcile_evidence_count(session, user_id=test_user)
    assert isinstance(result, ReconcileResult)
    assert result.entities_fixed == 0
    assert result.events_fixed == 0
    assert result.facts_fixed == 0
    assert result.total == 0


@pytest.mark.asyncio
async def test_k11_9_clean_run_with_real_evidence_fixes_nothing(
    neo4j_driver, test_user
):
    """Full write-path happy case: merge entity, upsert source,
    add_evidence → counter should already match. Reconciler no-op."""
    async with neo4j_driver.session() as session:
        entity = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
            confidence=0.9,
        )
        src = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-001",
        )
        ev = await add_evidence(
            session,
            user_id=test_user,
            target_label="Entity",
            target_id=entity.id,
            source_id=src.id,
            extraction_model="test-model",
            confidence=0.9,
            job_id="job-1",
        )
        assert ev is not None and ev.evidence_count == 1

        result = await reconcile_evidence_count(session, user_id=test_user)

    assert result.total == 0


# ── drift correction per label ────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_9_reconciles_entity_drift(neo4j_driver, test_user):
    """Entity with cached count = 5 but zero actual edges → fix to 0."""
    async with neo4j_driver.session() as session:
        entity = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Drake",
            kind="character",
            source_type="book_content",
            confidence=0.7,
        )
        # Bypass add_evidence to inject drift: set counter without edges
        await session.run(
            """
            MATCH (e:Entity {id: $id})
            WHERE e.user_id = $user_id
            SET e.evidence_count = 5
            """,
            id=entity.id,
            user_id=test_user,
        )

        before = await _read_counter("Entity")
        result = await reconcile_evidence_count(session, user_id=test_user)
        after = await _read_counter("Entity")

        # Verify the node was actually corrected
        row = await (await session.run(
            "MATCH (e:Entity {id: $id}) RETURN e.evidence_count AS c",
            id=entity.id,
        )).single()

    assert result.entities_fixed == 1
    assert result.events_fixed == 0
    assert result.facts_fixed == 0
    assert result.total == 1
    assert row["c"] == 0
    assert after - before == 1


@pytest.mark.asyncio
async def test_k11_9_reconciles_event_drift(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        event = await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Drake arrives at dusk",
            chapter_id="ch-1",
            event_order=1,
            confidence=0.8,
        )
        await session.run(
            """
            MATCH (e:Event {id: $id}) WHERE e.user_id = $user_id
            SET e.evidence_count = 3
            """,
            id=event.id,
            user_id=test_user,
        )

        before = await _read_counter("Event")
        result = await reconcile_evidence_count(session, user_id=test_user)
        after = await _read_counter("Event")

        # K11.9-R2/I2: verify the node's cached counter actually
        # landed at 0. Returned count + metric delta alone would
        # stay green even if the SET clause ever regressed.
        row = await (await session.run(
            "MATCH (e:Event {id: $id}) RETURN e.evidence_count AS c",
            id=event.id,
        )).single()

    assert result.events_fixed == 1
    assert result.entities_fixed == 0
    assert after - before == 1
    assert row["c"] == 0


@pytest.mark.asyncio
async def test_k11_9_reconciles_fact_drift(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        fact = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Kai decided to flee east",
            confidence=0.8,
        )
        await session.run(
            """
            MATCH (f:Fact {id: $id}) WHERE f.user_id = $user_id
            SET f.evidence_count = 7
            """,
            id=fact.id,
            user_id=test_user,
        )

        before = await _read_counter("Fact")
        result = await reconcile_evidence_count(session, user_id=test_user)
        after = await _read_counter("Fact")

        # K11.9-R2/I2: same as Event — read back the node.
        row = await (await session.run(
            "MATCH (f:Fact {id: $id}) RETURN f.evidence_count AS c",
            id=fact.id,
        )).single()

    assert result.facts_fixed == 1
    assert after - before == 1
    assert row["c"] == 0


# ── under-count drift (edges exist, counter lags) ─────────────────────


@pytest.mark.asyncio
async def test_k11_9_reconciles_under_count(neo4j_driver, test_user):
    """Counter says 0 but one EVIDENCED_BY edge exists → fix to 1.

    Simulates a write-path bug that creates an edge without
    incrementing the counter.
    """
    async with neo4j_driver.session() as session:
        entity = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Phoenix",
            kind="character",
            source_type="book_content",
            confidence=0.8,
        )
        src = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-002",
        )
        # Bypass add_evidence: create edge directly, leave counter at 0
        await session.run(
            """
            MATCH (e:Entity {id: $eid}), (s:ExtractionSource {id: $sid})
            WHERE e.user_id = $u AND s.user_id = $u
            MERGE (e)-[r:EVIDENCED_BY {job_id: 'bypass-job'}]->(s)
              ON CREATE SET r.extracted_at = datetime(),
                            r.extraction_model = 'bypass',
                            r.confidence = 0.5
            """,
            eid=entity.id,
            sid=src.id,
            u=test_user,
        )

        result = await reconcile_evidence_count(session, user_id=test_user)

        row = await (await session.run(
            "MATCH (e:Entity {id: $id}) RETURN e.evidence_count AS c",
            id=entity.id,
        )).single()

    assert result.entities_fixed == 1
    assert row["c"] == 1


# ── multi-tenant isolation ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_9_does_not_touch_other_user(neo4j_driver, test_user):
    other_user = f"u-k119-other-{uuid.uuid4().hex[:8]}"
    try:
        async with neo4j_driver.session() as session:
            mine = await merge_entity(
                session,
                user_id=test_user,
                project_id="p-1",
                name="Kai",
                kind="character",
                source_type="book_content",
                confidence=0.8,
            )
            theirs = await merge_entity(
                session,
                user_id=other_user,
                project_id="p-1",
                name="Kai",
                kind="character",
                source_type="book_content",
                confidence=0.8,
            )
            # Inject drift in BOTH
            await session.run(
                "MATCH (e:Entity) WHERE e.id IN [$a, $b] SET e.evidence_count = 9",
                a=mine.id,
                b=theirs.id,
            )

            # Reconcile only test_user
            result = await reconcile_evidence_count(session, user_id=test_user)

            rows = await (await session.run(
                """
                MATCH (e:Entity) WHERE e.id IN [$a, $b]
                RETURN e.id AS id, e.evidence_count AS c
                """,
                a=mine.id,
                b=theirs.id,
            )).data()
        by_id = {r["id"]: r["c"] for r in rows}
        assert result.entities_fixed == 1
        assert by_id[mine.id] == 0
        assert by_id[theirs.id] == 9  # untouched
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.user_id = $u DETACH DELETE n",
                u=other_user,
            )


# ── defensive: cross-user edge should not inflate count (R1/R1) ──────


@pytest.mark.asyncio
async def test_k11_9_r1_ignores_cross_user_evidenced_by(neo4j_driver, test_user):
    """K11.9-R1/R1: if a write-path bug ever creates an EVIDENCED_BY
    edge from user A's entity to user B's ExtractionSource, the
    reconciler must NOT count that edge toward user A's actual count.
    Otherwise it would 'correct' user A's counter up to match the
    cross-user edge, masking the real drift.
    """
    other_user = f"u-k119-xbug-{uuid.uuid4().hex[:8]}"
    try:
        async with neo4j_driver.session() as session:
            entity = await merge_entity(
                session,
                user_id=test_user,
                project_id="p-1",
                name="Kai",
                kind="character",
                source_type="book_content",
                confidence=0.9,
            )
            # Source owned by OTHER user
            other_src = await upsert_extraction_source(
                session,
                user_id=other_user,
                project_id="p-1",
                source_type="chapter",
                source_id="ch-x",
            )
            # Inject cross-user edge + cached count=1 on test_user's
            # entity. A reconciler that filters only by relationship
            # type would see 1 actual edge, match the cache, report
            # "no drift" — which is wrong. A paranoid reconciler
            # filters the src endpoint's user_id and sees 0 actual
            # edges, correcting the cache down to 0.
            await session.run(
                """
                MATCH (e:Entity {id: $eid}), (s:ExtractionSource {id: $sid})
                MERGE (e)-[r:EVIDENCED_BY {job_id: 'xbug'}]->(s)
                  ON CREATE SET r.extracted_at = datetime(),
                                r.extraction_model = 'xbug',
                                r.confidence = 0.5
                SET e.evidence_count = 1
                """,
                eid=entity.id,
                sid=other_src.id,
            )

            result = await reconcile_evidence_count(session, user_id=test_user)

            row = await (await session.run(
                "MATCH (e:Entity {id: $id}) RETURN e.evidence_count AS c",
                id=entity.id,
            )).single()

        assert result.entities_fixed == 1
        assert row["c"] == 0  # reconciler ignored the cross-user edge
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.user_id = $u DETACH DELETE n",
                u=other_user,
            )


# ── compositional: drift on all three labels in one call ─────────────


@pytest.mark.asyncio
async def test_k11_9_r3_fixes_all_three_labels_in_one_run(neo4j_driver, test_user):
    """K11.9-R3/I1: inject drift on Entity + Event + Fact
    simultaneously and verify a single reconcile call fixes all
    three. Guards the sequential composition in
    reconcile_evidence_count — a regression that passed the same
    label to all three _reconcile_label calls would not be caught
    by the per-label tests above.
    """
    async with neo4j_driver.session() as session:
        entity = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Mira",
            kind="character",
            source_type="book_content",
            confidence=0.8,
        )
        event = await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Mira crosses the river",
            chapter_id="ch-1",
            event_order=1,
            confidence=0.8,
        )
        fact = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Mira swore fealty",
            confidence=0.8,
        )
        await session.run(
            """
            MATCH (n) WHERE n.id IN [$e, $v, $f] AND n.user_id = $u
            SET n.evidence_count = 9
            """,
            e=entity.id,
            v=event.id,
            f=fact.id,
            u=test_user,
        )

        result = await reconcile_evidence_count(session, user_id=test_user)

        rows = await (await session.run(
            """
            MATCH (n) WHERE n.id IN [$e, $v, $f] AND n.user_id = $u
            RETURN n.id AS id, n.evidence_count AS c
            """,
            e=entity.id,
            v=event.id,
            f=fact.id,
            u=test_user,
        )).data()

    assert result.entities_fixed == 1
    assert result.events_fixed == 1
    assert result.facts_fixed == 1
    assert result.total == 3
    by_id = {r["id"]: r["c"] for r in rows}
    assert by_id[entity.id] == 0
    assert by_id[event.id] == 0
    assert by_id[fact.id] == 0


# ── legacy node: evidence_count property absent ──────────────────────


@pytest.mark.asyncio
async def test_k11_9_r3_normalizes_missing_evidence_count(neo4j_driver, test_user):
    """K11.9-R3/I2: a legacy node that pre-dates the counter field
    has NO `evidence_count` property at all (not 0, absent).
    `coalesce(n.evidence_count, 0)` should treat it as 0; if the
    node has one real EVIDENCED_BY edge, reconcile should bump it
    to 1. Guards the coalesce path documented in the query comment.
    """
    async with neo4j_driver.session() as session:
        entity = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Legacy",
            kind="character",
            source_type="book_content",
            confidence=0.8,
        )
        # Remove the property entirely (simulates legacy node).
        await session.run(
            """
            MATCH (e:Entity {id: $id}) WHERE e.user_id = $u
            REMOVE e.evidence_count
            """,
            id=entity.id,
            u=test_user,
        )
        # Sanity check — property is really gone.
        row0 = await (await session.run(
            """
            MATCH (e:Entity {id: $id})
            RETURN e.evidence_count AS c, 'evidence_count' IN keys(e) AS present
            """,
            id=entity.id,
        )).single()
        assert row0["present"] is False

        # Case A: no edges at all → coalesce(NULL, 0) == 0 == actual
        # → NO drift, no fix. The reconciler must not SET
        # evidence_count back onto a legacy node that still has
        # zero edges (would be churn).
        result_a = await reconcile_evidence_count(session, user_id=test_user)
        assert result_a.entities_fixed == 0

        # Case B: attach one real edge, run again → drift (0 vs 1)
        src = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-legacy",
        )
        await session.run(
            """
            MATCH (e:Entity {id: $eid}), (s:ExtractionSource {id: $sid})
            WHERE e.user_id = $u AND s.user_id = $u
            MERGE (e)-[r:EVIDENCED_BY {job_id: 'legacy-job'}]->(s)
              ON CREATE SET r.extracted_at = datetime(),
                            r.extraction_model = 'legacy',
                            r.confidence = 0.5
            """,
            eid=entity.id,
            sid=src.id,
            u=test_user,
        )

        result_b = await reconcile_evidence_count(session, user_id=test_user)

        row = await (await session.run(
            "MATCH (e:Entity {id: $id}) RETURN e.evidence_count AS c",
            id=entity.id,
        )).single()

    assert result_b.entities_fixed == 1
    assert row["c"] == 1


# ── project_id filter ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_9_project_id_narrows_scope(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        e1 = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-A",
            name="Kai",
            kind="character",
            source_type="book_content",
            confidence=0.8,
        )
        e2 = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-B",
            name="Drake",
            kind="character",
            source_type="book_content",
            confidence=0.8,
        )
        await session.run(
            "MATCH (e:Entity) WHERE e.id IN [$a, $b] SET e.evidence_count = 4",
            a=e1.id,
            b=e2.id,
        )

        # Reconcile only project p-A
        result = await reconcile_evidence_count(
            session, user_id=test_user, project_id="p-A"
        )

        rows = await (await session.run(
            """
            MATCH (e:Entity) WHERE e.id IN [$a, $b]
            RETURN e.id AS id, e.evidence_count AS c
            """,
            a=e1.id,
            b=e2.id,
        )).data()
    by_id = {r["id"]: r["c"] for r in rows}
    assert result.entities_fixed == 1
    assert by_id[e1.id] == 0
    assert by_id[e2.id] == 4  # untouched, different project


# ── closed-enum guard ─────────────────────────────────────────────────


def test_k11_9_reconcile_labels_is_closed_enum():
    # If a new label is ever added, the test must be updated too
    # so the metric pre-init loop + dispatch table stay in sync.
    assert RECONCILE_LABELS == ("Entity", "Event", "Fact")


@pytest.mark.asyncio
async def test_k11_9_empty_user_id_rejected():
    """K11.9-R1/R3: pure guard test — no Neo4j needed. The ValueError
    fires before any driver call, so the test should stay green even
    when TEST_NEO4J_URI is unset."""

    class _ShouldNeverRun:
        async def run(self, *_a, **_k):  # pragma: no cover
            raise AssertionError(
                "session.run() should not be called when user_id is empty"
            )

    with pytest.raises(ValueError, match="user_id is required"):
        await reconcile_evidence_count(_ShouldNeverRun(), user_id="")
