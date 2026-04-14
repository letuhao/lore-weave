"""K11.8 provenance repository — integration tests against live Neo4j.

Skipped when TEST_NEO4J_URI is unset. Each test scopes to a unique
user_id and DETACH DELETEs in finally.

Acceptance:
  - evidence_count stays in sync with actual edge count
  - Partial re-extract cascade works: delete source → orphans
    cleaned (KSA §3.8.5)
  - Parameterized Cypher only (no f-strings)
  - Cross-user safe
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.entities import get_entity, merge_entity
from app.db.neo4j_repos.events import get_event, merge_event
from app.db.neo4j_repos.facts import get_fact, merge_fact
from app.db.neo4j_repos.provenance import (
    SOURCE_TYPES,
    TARGET_LABELS,
    add_evidence,
    cleanup_zero_evidence_nodes,
    delete_source_cascade,
    extraction_source_id,
    get_extraction_source,
    remove_evidence_for_source,
    upsert_extraction_source,
)


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.user_id = $user_id DETACH DELETE n",
                user_id=user_id,
            )


# ── extraction_source_id ──────────────────────────────────────────────


def test_k11_8_extraction_source_id_deterministic():
    a = extraction_source_id("u-1", "p-1", "chapter", "ch-12")
    b = extraction_source_id("u-1", "p-1", "chapter", "ch-12")
    assert a == b
    assert len(a) == 32


def test_k11_8_extraction_source_id_distinct_per_source_type():
    a = extraction_source_id("u-1", "p-1", "chapter", "ch-12")
    b = extraction_source_id("u-1", "p-1", "chat_message", "ch-12")
    assert a != b


def test_k11_8_extraction_source_id_rejects_invalid_source_type():
    with pytest.raises(ValueError, match="source_type"):
        extraction_source_id("u-1", "p-1", "bogus", "ch-12")


def test_k11_8_extraction_source_id_rejects_empty_inputs():
    for kwargs in (
        dict(user_id="", project_id="p", source_type="chapter", source_id="x"),
        dict(user_id="u", project_id="p", source_type="", source_id="x"),
        dict(user_id="u", project_id="p", source_type="chapter", source_id=""),
    ):
        with pytest.raises(ValueError):
            extraction_source_id(**kwargs)


def test_k11_8_source_types_constant():
    assert set(SOURCE_TYPES) == {
        "chapter",
        "chat_message",
        "glossary_entity",
        "manual",
    }


def test_k11_8_target_labels_constant():
    assert set(TARGET_LABELS) == {"Entity", "Event", "Fact"}


# ── upsert_extraction_source ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_8_upsert_source_creates_node(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        src = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-12",
        )
    assert src.user_id == test_user
    assert src.project_id == "p-1"
    assert src.source_type == "chapter"
    assert src.source_id == "ch-12"
    assert src.id == extraction_source_id(test_user, "p-1", "chapter", "ch-12")


@pytest.mark.asyncio
async def test_k11_8_upsert_source_is_idempotent(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        a = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-12",
        )
        b = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-12",
        )
    assert a.id == b.id
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (s:ExtractionSource {id: $id}) RETURN count(s) AS n",
            id=a.id,
        )
        record = await result.single()
    assert record["n"] == 1


@pytest.mark.asyncio
async def test_k11_8_get_source_by_natural_key(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-99",
        )
        found = await get_extraction_source(
            session,
            user_id=test_user,
            source_type="chapter",
            source_id="ch-99",
        )
    assert found is not None
    assert found.source_id == "ch-99"


@pytest.mark.asyncio
async def test_k11_8_get_source_does_not_cross_user_boundary(neo4j_driver):
    user_a = f"u-test-{uuid.uuid4().hex[:12]}"
    user_b = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        async with neo4j_driver.session() as session:
            await upsert_extraction_source(
                session,
                user_id=user_a,
                project_id="p-1",
                source_type="chapter",
                source_id="ch-shared",
            )
            from_b = await get_extraction_source(
                session,
                user_id=user_b,
                source_type="chapter",
                source_id="ch-shared",
            )
        assert from_b is None
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.user_id IN [$ua, $ub] DETACH DELETE n",
                ua=user_a,
                ub=user_b,
            )


# ── add_evidence ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_8_add_evidence_increments_entity_counter(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        kai = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
        )
        src = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-1",
        )
        result = await add_evidence(
            session,
            user_id=test_user,
            target_label="Entity",
            target_id=kai.id,
            source_id=src.id,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="job-1",
        )
    assert result is not None
    assert result.evidence_count == 1
    assert result.mention_count == 1
    assert result.created is True


@pytest.mark.asyncio
async def test_k11_8_add_evidence_is_idempotent_per_job(neo4j_driver, test_user):
    """Re-running the same job_id is a no-op — counter does NOT
    double-increment."""
    async with neo4j_driver.session() as session:
        kai = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
        )
        src = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-1",
        )
        first = await add_evidence(
            session,
            user_id=test_user,
            target_label="Entity",
            target_id=kai.id,
            source_id=src.id,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="job-rerun",
        )
        second = await add_evidence(
            session,
            user_id=test_user,
            target_label="Entity",
            target_id=kai.id,
            source_id=src.id,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="job-rerun",
        )
    assert first.evidence_count == 1
    assert second.evidence_count == 1  # NOT 2
    assert first.created is True
    assert second.created is False


@pytest.mark.asyncio
async def test_k11_8_add_evidence_distinct_jobs_accumulate(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        kai = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
        )
        src = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-1",
        )
        for jid in ("job-1", "job-2", "job-3"):
            result = await add_evidence(
                session,
                user_id=test_user,
                target_label="Entity",
                target_id=kai.id,
                source_id=src.id,
                extraction_model="gpt-4",
                confidence=0.9,
                job_id=jid,
            )
    assert result.evidence_count == 3
    assert result.mention_count == 3


@pytest.mark.asyncio
async def test_k11_8_add_evidence_works_for_event_and_fact(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        ev = await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="Battle",
            chapter_id="ch-1",
        )
        fact = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Use fire",
        )
        src = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-1",
        )
        ev_result = await add_evidence(
            session,
            user_id=test_user,
            target_label="Event",
            target_id=ev.id,
            source_id=src.id,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="job-1",
        )
        fact_result = await add_evidence(
            session,
            user_id=test_user,
            target_label="Fact",
            target_id=fact.id,
            source_id=src.id,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="job-1",
        )
    assert ev_result.evidence_count == 1
    assert fact_result.evidence_count == 1


@pytest.mark.asyncio
async def test_k11_8_add_evidence_returns_none_for_missing_target(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        src = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-1",
        )
        result = await add_evidence(
            session,
            user_id=test_user,
            target_label="Entity",
            target_id="0" * 32,
            source_id=src.id,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="job-1",
        )
    assert result is None


@pytest.mark.asyncio
async def test_k11_8_add_evidence_returns_none_for_missing_source(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        kai = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
        )
        result = await add_evidence(
            session,
            user_id=test_user,
            target_label="Entity",
            target_id=kai.id,
            source_id="0" * 32,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="job-1",
        )
    assert result is None


@pytest.mark.asyncio
async def test_k11_8_add_evidence_validates_inputs():
    for kwargs, match in (
        (
            dict(target_label="Bogus", target_id="x", source_id="s",
                 extraction_model="m", confidence=0.5, job_id="j"),
            "target_label",
        ),
        (
            dict(target_label="Entity", target_id="", source_id="s",
                 extraction_model="m", confidence=0.5, job_id="j"),
            "target_id",
        ),
        (
            dict(target_label="Entity", target_id="x", source_id="",
                 extraction_model="m", confidence=0.5, job_id="j"),
            "source_id",
        ),
        (
            dict(target_label="Entity", target_id="x", source_id="s",
                 extraction_model="", confidence=0.5, job_id="j"),
            "extraction_model",
        ),
        (
            dict(target_label="Entity", target_id="x", source_id="s",
                 extraction_model="m", confidence=0.5, job_id=""),
            "job_id",
        ),
        (
            dict(target_label="Entity", target_id="x", source_id="s",
                 extraction_model="m", confidence=1.5, job_id="j"),
            "confidence",
        ),
    ):
        with pytest.raises(ValueError, match=match):
            await add_evidence(
                session=None,  # type: ignore[arg-type]
                user_id="u-1",
                **kwargs,
            )


# ── remove_evidence_for_source ────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_8_remove_evidence_decrements_counters(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        kai = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
        )
        src = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-1",
        )
        # Add three pieces of evidence (different jobs).
        for jid in ("job-1", "job-2", "job-3"):
            await add_evidence(
                session,
                user_id=test_user,
                target_label="Entity",
                target_id=kai.id,
                source_id=src.id,
                extraction_model="gpt-4",
                confidence=0.9,
                job_id=jid,
            )
        # Remove all evidence from this source.
        removed = await remove_evidence_for_source(
            session,
            user_id=test_user,
            source_id=src.id,
        )
        after = await get_entity(
            session, user_id=test_user, canonical_id=kai.id
        )
    assert removed == 3
    assert after.evidence_count == 0
    # mention_count is monotonic — NOT decremented.
    assert after.mention_count == 3


@pytest.mark.asyncio
async def test_k11_8_remove_evidence_returns_zero_for_missing_source(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        result = await remove_evidence_for_source(
            session,
            user_id=test_user,
            source_id="0" * 32,
        )
    assert result == 0


# ── delete_source_cascade ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_8_delete_source_cascade_removes_node_and_edges(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        kai = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
        )
        src = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-cascade",
        )
        await add_evidence(
            session,
            user_id=test_user,
            target_label="Entity",
            target_id=kai.id,
            source_id=src.id,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="job-1",
        )
        removed = await delete_source_cascade(
            session,
            user_id=test_user,
            source_type="chapter",
            source_id="ch-cascade",
        )
        # Source is gone.
        gone = await get_extraction_source(
            session,
            user_id=test_user,
            source_type="chapter",
            source_id="ch-cascade",
        )
        # Entity is still here but evidence_count back to 0.
        kai_after = await get_entity(
            session, user_id=test_user, canonical_id=kai.id
        )
    assert removed == 1
    assert gone is None
    assert kai_after is not None
    assert kai_after.evidence_count == 0


@pytest.mark.asyncio
async def test_k11_8_delete_source_cascade_idempotent(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        # Source doesn't exist.
        result = await delete_source_cascade(
            session,
            user_id=test_user,
            source_type="chapter",
            source_id="never-existed",
        )
    assert result == 0


# ── cleanup_zero_evidence_nodes ───────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_8_cleanup_returns_per_label_counts(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        # Create one of each, all with evidence_count=0 (the
        # default after merge; no add_evidence call).
        await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Orphan",
            kind="character",
            source_type="book_content",
        )
        await merge_event(
            session,
            user_id=test_user,
            project_id="p-1",
            title="OrphanEvent",
            chapter_id="ch-1",
        )
        await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Orphan fact",
        )
        result = await cleanup_zero_evidence_nodes(
            session, user_id=test_user, project_id="p-1"
        )
    assert result.entities == 1
    assert result.events == 1
    assert result.facts == 1
    assert result.total == 3


# ── KSA §3.8.5 partial-extraction cascade scenario ────────────────────


@pytest.mark.asyncio
async def test_k11_8_partial_reextract_cascade_scenario(
    neo4j_driver, test_user
):
    """KSA §3.8.5 end-to-end: a user re-extracts chapter 12 after
    editing it. The orchestrator:

      1. Removes all EVIDENCED_BY edges from ch-12's source
         (counter decrements)
      2. Sweeps zero-evidence orphans (entities/events/facts that
         existed only because of ch-12)
      3. Re-runs extraction → calls add_evidence again with new
         job_id → counter increments back up

    Verifies that:
      - An entity that ALSO had evidence from ch-13 survives the
        sweep (its counter dropped from 2 to 1, not to 0).
      - An entity that ONLY had evidence from ch-12 is deleted
        by the sweep.
      - Re-running extraction restores the counter for survivors.
    """
    async with neo4j_driver.session() as session:
        # Setup: two entities, two source chapters.
        survivor = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Survivor",
            kind="character",
            source_type="book_content",
        )
        deletable = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Deletable",
            kind="character",
            source_type="book_content",
        )
        ch12 = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-12",
        )
        ch13 = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-13",
        )
        # Survivor has evidence in BOTH chapters.
        await add_evidence(
            session,
            user_id=test_user,
            target_label="Entity",
            target_id=survivor.id,
            source_id=ch12.id,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="initial-ch12",
        )
        await add_evidence(
            session,
            user_id=test_user,
            target_label="Entity",
            target_id=survivor.id,
            source_id=ch13.id,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="initial-ch13",
        )
        # Deletable has evidence only in ch-12.
        await add_evidence(
            session,
            user_id=test_user,
            target_label="Entity",
            target_id=deletable.id,
            source_id=ch12.id,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="initial-ch12-deletable",
        )

        # Verify initial counters.
        survivor_initial = await get_entity(
            session, user_id=test_user, canonical_id=survivor.id
        )
        deletable_initial = await get_entity(
            session, user_id=test_user, canonical_id=deletable.id
        )
        assert survivor_initial.evidence_count == 2
        assert deletable_initial.evidence_count == 1

        # Step 1: re-extract ch-12 → remove its evidence.
        removed = await remove_evidence_for_source(
            session, user_id=test_user, source_id=ch12.id
        )
        assert removed == 2  # survivor + deletable both lost one edge

        survivor_mid = await get_entity(
            session, user_id=test_user, canonical_id=survivor.id
        )
        deletable_mid = await get_entity(
            session, user_id=test_user, canonical_id=deletable.id
        )
        assert survivor_mid.evidence_count == 1  # ch-13 still holds
        assert deletable_mid.evidence_count == 0  # orphan now

        # Step 2: cleanup orphans.
        cleanup = await cleanup_zero_evidence_nodes(
            session, user_id=test_user, project_id="p-1"
        )
        assert cleanup.entities == 1  # only deletable
        assert cleanup.events == 0
        assert cleanup.facts == 0

        survivor_after = await get_entity(
            session, user_id=test_user, canonical_id=survivor.id
        )
        deletable_after = await get_entity(
            session, user_id=test_user, canonical_id=deletable.id
        )
        assert survivor_after is not None  # safe
        assert deletable_after is None  # gone

        # Step 3: re-run extraction on ch-12 → re-add edge.
        await add_evidence(
            session,
            user_id=test_user,
            target_label="Entity",
            target_id=survivor.id,
            source_id=ch12.id,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="reextract-ch12",
        )
        survivor_final = await get_entity(
            session, user_id=test_user, canonical_id=survivor.id
        )
    assert survivor_final.evidence_count == 2
    # mention_count is monotonic — counts initial + reextract.
    assert survivor_final.mention_count == 3


# ── K11.8-R1 review-fix tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_8_r1_get_source_project_id_filter(neo4j_driver, test_user):
    """K11.8-R1/R1 fix. Two ExtractionSource nodes with the same
    (user, source_type, source_id) but different project_ids
    have different hash ids — both can exist. Without the
    project_id filter on the natural-key lookup, single() would
    raise ResultNotSingleError."""
    async with neo4j_driver.session() as session:
        await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-shared",
        )
        await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-2",
            source_type="chapter",
            source_id="ch-shared",
        )
        # Without project_id filter — would crash via single().
        # With project_id — picks the right one.
        p1 = await get_extraction_source(
            session,
            user_id=test_user,
            source_type="chapter",
            source_id="ch-shared",
            project_id="p-1",
        )
        p2 = await get_extraction_source(
            session,
            user_id=test_user,
            source_type="chapter",
            source_id="ch-shared",
            project_id="p-2",
        )
    assert p1 is not None
    assert p1.project_id == "p-1"
    assert p2 is not None
    assert p2.project_id == "p-2"
    assert p1.id != p2.id


@pytest.mark.asyncio
async def test_k11_8_r1_get_source_without_project_warns_on_collision(
    neo4j_driver, test_user
):
    """Without the project_id filter, two same-natural-key
    sources make `result.single()` emit a UserWarning AND
    return a non-deterministic first record. neo4j 6.x driver
    softened the contract from "raise" to "warn", but the
    underlying bug is the same: the caller can't predict which
    project's source it gets back. With project_id passed, no
    warning fires."""
    import warnings

    async with neo4j_driver.session() as session:
        await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-collide",
        )
        await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-2",
            source_type="chapter",
            source_id="ch-collide",
        )
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            await get_extraction_source(
                session,
                user_id=test_user,
                source_type="chapter",
                source_id="ch-collide",
            )
        # The neo4j driver warns about multi-record single().
        assert any(
            "single record" in str(w.message).lower() for w in caught
        ), f"expected single-record warning, got {[str(w.message) for w in caught]}"

        # With project_id passed, no warning fires.
        with warnings.catch_warnings(record=True) as caught_clean:
            warnings.simplefilter("always")
            result = await get_extraction_source(
                session,
                user_id=test_user,
                source_type="chapter",
                source_id="ch-collide",
                project_id="p-1",
            )
        assert result is not None
        assert result.project_id == "p-1"
        assert not any(
            "single record" in str(w.message).lower() for w in caught_clean
        )


@pytest.mark.asyncio
async def test_k11_8_r1_delete_source_cascade_project_id_filter(
    neo4j_driver, test_user
):
    """K11.8-R1/R1 fix. The cascade must target the right
    source when a user has the same source_id across projects.
    Cascading p-1 must NOT touch p-2's source."""
    async with neo4j_driver.session() as session:
        kai_p1 = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-1",
            name="Kai",
            kind="character",
            source_type="book_content",
        )
        kai_p2 = await merge_entity(
            session,
            user_id=test_user,
            project_id="p-2",
            name="Kai",
            kind="character",
            source_type="book_content",
        )
        src_p1 = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-1",
            source_type="chapter",
            source_id="ch-collide",
        )
        src_p2 = await upsert_extraction_source(
            session,
            user_id=test_user,
            project_id="p-2",
            source_type="chapter",
            source_id="ch-collide",
        )
        await add_evidence(
            session,
            user_id=test_user,
            target_label="Entity",
            target_id=kai_p1.id,
            source_id=src_p1.id,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="j-p1",
        )
        await add_evidence(
            session,
            user_id=test_user,
            target_label="Entity",
            target_id=kai_p2.id,
            source_id=src_p2.id,
            extraction_model="gpt-4",
            confidence=0.9,
            job_id="j-p2",
        )
        # Cascade only p-1.
        removed = await delete_source_cascade(
            session,
            user_id=test_user,
            source_type="chapter",
            source_id="ch-collide",
            project_id="p-1",
        )
        # p-1 source gone, p-2 source still here.
        gone_p1 = await get_extraction_source(
            session,
            user_id=test_user,
            source_type="chapter",
            source_id="ch-collide",
            project_id="p-1",
        )
        kept_p2 = await get_extraction_source(
            session,
            user_id=test_user,
            source_type="chapter",
            source_id="ch-collide",
            project_id="p-2",
        )
        # p-1 entity counter back to 0; p-2 entity still at 1.
        kai_p1_after = await get_entity(
            session, user_id=test_user, canonical_id=kai_p1.id
        )
        kai_p2_after = await get_entity(
            session, user_id=test_user, canonical_id=kai_p2.id
        )
    assert removed == 1
    assert gone_p1 is None
    assert kept_p2 is not None
    assert kai_p1_after.evidence_count == 0
    assert kai_p2_after.evidence_count == 1
