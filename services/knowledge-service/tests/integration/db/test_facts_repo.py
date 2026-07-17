"""K11.7 facts repository — integration tests against live Neo4j."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.neo4j_repos.facts import (
    FACT_TYPES,
    delete_facts_with_zero_evidence,
    fact_id,
    get_fact,
    invalidate_fact,
    list_facts_by_type,
    merge_fact,
)


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (f:Fact {user_id: $user_id}) DETACH DELETE f",
                user_id=user_id,
            )


# ── fact_id ───────────────────────────────────────────────────────────


def test_k11_7_fact_id_deterministic():
    a = fact_id("u-1", "p-1", "decision", "Use fire magic")
    b = fact_id("u-1", "p-1", "decision", "Use fire magic")
    assert a == b
    assert len(a) == 32


def test_k11_7_fact_id_canonicalizes_content():
    a = fact_id("u-1", "p-1", "decision", "Use fire magic")
    b = fact_id("u-1", "p-1", "decision", "  USE Fire MAGIC!  ")
    assert a == b


def test_k11_7_fact_id_distinct_per_type():
    a = fact_id("u-1", "p-1", "decision", "Use fire")
    b = fact_id("u-1", "p-1", "preference", "Use fire")
    assert a != b


def test_k11_7_fact_id_rejects_invalid_type():
    with pytest.raises(ValueError, match="type must be one of"):
        fact_id("u-1", "p-1", "decree", "x")


def test_k11_7_fact_id_rejects_empty_inputs():
    for kwargs in (
        dict(user_id="", project_id="p", type="decision", content="x"),
        dict(user_id="u", project_id="p", type="", content="x"),
        dict(user_id="u", project_id="p", type="decision", content=""),
    ):
        with pytest.raises(ValueError):
            fact_id(**kwargs)


def test_k11_7_fact_types_constant_matches_literal():
    # Deliberate change-detector: the vocabulary lives in THREE places that must move
    # together — the FactType Literal (models.py), this constant, and the pending-facts
    # CHECK in migrate.py (test_migrate_ddl pins that one). Widening it here without the
    # DDL would let an unknown type reach merge_fact and 500.
    # WS-2.1 added 'statement' (the diary's coarse fact kind);
    # WS-5.7 added 'commitment' (a promised action + due date).
    assert set(FACT_TYPES) == {
        "decision",
        "preference",
        "milestone",
        "negation",
        "statement",
        "commitment",
    }


# ── merge_fact ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_merge_fact_creates_node(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        f = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Use fire magic",
            confidence=0.85,
            source_chapter="ch-12",
        )
    assert f.user_id == test_user
    assert f.type == "decision"
    assert f.content == "Use fire magic"
    assert f.canonical_content == "use fire magic"
    assert f.confidence == 0.85
    assert f.source_chapter == "ch-12"
    assert f.valid_until is None
    assert f.pending_validation is False


@pytest.mark.asyncio
async def test_k11_7_merge_fact_is_idempotent(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        a = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Use fire magic",
            confidence=0.5,
        )
        b = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="USE fire MAGIC",  # cosmetic diff
            confidence=0.5,
        )
    assert a.id == b.id
    async with neo4j_driver.session() as session:
        result = await session.run(
            "MATCH (f:Fact {id: $id}) RETURN count(f) AS n", id=a.id
        )
        record = await result.single()
    assert record["n"] == 1


@pytest.mark.asyncio
async def test_k11_7_merge_fact_pass2_promotion(neo4j_driver, test_user):
    """Pass 1 quarantined fact (low conf, pending=true) → Pass 2
    LLM promotes (high conf, pending=false). The existing node
    upgrades in place."""
    async with neo4j_driver.session() as session:
        await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Use fire magic",
            confidence=0.4,
            pending_validation=True,
        )
        promoted = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Use fire magic",
            confidence=0.95,
            pending_validation=False,
        )
    assert promoted.confidence == 0.95
    assert promoted.pending_validation is False


@pytest.mark.asyncio
async def test_k11_7_merge_fact_validates_type():
    with pytest.raises(ValueError, match="type"):
        await merge_fact(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            project_id="p-1",
            type="bogus",
            content="x",
        )


@pytest.mark.asyncio
async def test_k11_7_merge_fact_validates_content():
    with pytest.raises(ValueError, match="content"):
        await merge_fact(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            project_id="p-1",
            type="decision",
            content="",
        )


# ── get_fact ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_get_fact_returns_none_when_missing(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        result = await get_fact(session, user_id=test_user, fact_id="0" * 32)
    assert result is None


@pytest.mark.asyncio
async def test_k11_7_get_fact_does_not_cross_user_boundary(neo4j_driver):
    user_a = f"u-test-{uuid.uuid4().hex[:12]}"
    user_b = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        async with neo4j_driver.session() as session:
            f = await merge_fact(
                session,
                user_id=user_a,
                project_id="p-1",
                type="decision",
                content="Secret",
            )
            from_b = await get_fact(
                session, user_id=user_b, fact_id=f.id
            )
        assert from_b is None
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (f:Fact) WHERE f.user_id IN [$ua, $ub] DETACH DELETE f",
                ua=user_a,
                ub=user_b,
            )


# ── list_facts_by_type ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_list_facts_filters_by_type(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="A decision",
            confidence=0.9,
        )
        await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="preference",
            content="A preference",
            confidence=0.9,
        )
        await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="milestone",
            content="A milestone",
            confidence=0.9,
        )
        decisions = await list_facts_by_type(
            session, user_id=test_user, project_id="p-1", type="decision"
        )
        all_facts = await list_facts_by_type(
            session, user_id=test_user, project_id="p-1"
        )
    assert len(decisions) == 1
    assert decisions[0].content == "A decision"
    assert len(all_facts) == 3


@pytest.mark.asyncio
async def test_k11_7_list_facts_excludes_pending_by_default(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Quarantined",
            confidence=0.4,
            pending_validation=True,
        )
        excluded = await list_facts_by_type(
            session, user_id=test_user, project_id="p-1"
        )
        included = await list_facts_by_type(
            session,
            user_id=test_user,
            project_id="p-1",
            min_confidence=0.0,
            exclude_pending=False,
        )
    assert excluded == []
    assert len(included) == 1


@pytest.mark.asyncio
async def test_k11_7_list_facts_excludes_invalidated(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        f = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Will be invalidated",
            confidence=0.9,
        )
        before = await list_facts_by_type(
            session, user_id=test_user, project_id="p-1"
        )
        await invalidate_fact(session, user_id=test_user, fact_id=f.id)
        after = await list_facts_by_type(
            session, user_id=test_user, project_id="p-1"
        )
    assert len(before) == 1
    assert after == []


@pytest.mark.asyncio
async def test_k11_7_list_facts_validates_type():
    with pytest.raises(ValueError, match="type must be one of"):
        await list_facts_by_type(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            project_id="p-1",
            type="bogus",
        )


# ── invalidate_fact ───────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_invalidate_fact_sets_valid_until(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        f = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="X",
            confidence=0.9,
        )
        invalidated = await invalidate_fact(
            session, user_id=test_user, fact_id=f.id
        )
    assert invalidated is not None
    assert invalidated.valid_until is not None


@pytest.mark.asyncio
async def test_k11_7_invalidate_fact_returns_none_for_missing(
    neo4j_driver, test_user
):
    async with neo4j_driver.session() as session:
        result = await invalidate_fact(
            session, user_id=test_user, fact_id="0" * 32
        )
    assert result is None


# ── WS-2.6a leg 3 — invalidate_facts_for_day (D17 no-resurrection) ─────


@pytest.mark.asyncio
async def test_ws26a_invalidate_facts_for_day_retires_only_that_day(neo4j_driver, test_user):
    """D17 leg 3: correcting one diary day invalidates ALL that day's CONFIRMED facts (so the superseded
    fact can't resurrect) while leaving other days / other projects / pending facts untouched."""
    from app.db.neo4j_repos.facts import invalidate_facts_for_day

    proj = "p-assist"
    async with neo4j_driver.session() as session:
        # Two confirmed facts on the corrected day (the wrong one + an unrelated one).
        day_minh = await merge_fact(
            session, user_id=test_user, project_id=proj, type="statement",
            content="Minh froze the budget", confidence=0.5, pending_validation=False,
            event_date_iso="2026-03-10",
        )
        day_other = await merge_fact(
            session, user_id=test_user, project_id=proj, type="statement",
            content="Shipped the redesign", confidence=0.5, pending_validation=False,
            event_date_iso="2026-03-10",
        )
        # A fact on a DIFFERENT day — must survive.
        other_day = await merge_fact(
            session, user_id=test_user, project_id=proj, type="statement",
            content="Reviewed the roadmap", confidence=0.5, pending_validation=False,
            event_date_iso="2026-03-11",
        )
        # A fact in a DIFFERENT project on the same day — must survive (D16 scope isolation).
        other_proj = await merge_fact(
            session, user_id=test_user, project_id="p-novel", type="statement",
            content="Dragon burned the keep", confidence=0.5, pending_validation=False,
            event_date_iso="2026-03-10",
        )

        n = await invalidate_facts_for_day(
            session, user_id=test_user, project_id=proj, event_date="2026-03-10",
        )
        assert n == 2  # only the two confirmed facts of that day+project

        # Re-run is idempotent (nothing active left to invalidate).
        assert await invalidate_facts_for_day(
            session, user_id=test_user, project_id=proj, event_date="2026-03-10",
        ) == 0

        # Verify valid_until state per fact.
        async def _valid_until(fid):
            rec = await (await session.run(
                "MATCH (f:Fact {id:$id}) RETURN f.valid_until AS vu", id=fid)).single()
            return rec["vu"]

        assert await _valid_until(day_minh.id) is not None   # retired
        assert await _valid_until(day_other.id) is not None  # retired (whole day re-derives)
        assert await _valid_until(other_day.id) is None      # different day — untouched
        assert await _valid_until(other_proj.id) is None     # different project — untouched (D16)


# ── WS-2.6b — supersession recall ("it changed") end-to-end ───────────


@pytest.mark.asyncio
async def test_ws26b_recall_surfaces_a_supersession_not_two_truths(neo4j_driver, test_user):
    """spec 07 §Q5: a claim that changed over time (launch Friday → Tuesday) recalls as ONE supersession
    with an ordered chain, not two independent facts. Proves predicate/object PERSIST on the :Fact node
    and that recall carries the :ABOUT subject for grouping."""
    from app.db.neo4j_repos.entities import merge_entity
    from app.db.neo4j_repos.facts import days_since_epoch, group_supersessions, recall_facts

    proj = "p-assist"
    async with neo4j_driver.session() as session:
        launch = await merge_entity(
            session, user_id=test_user, project_id=proj, name="launch", kind="project",
            source_type="assistant_diary_fact", auto_created=True,
        )
        # Two facts, SAME subject+predicate, DIFFERENT object across two days.
        import datetime as _dt
        for obj, d in (("Friday", "2026-03-02"), ("Tuesday", "2026-03-04")):
            await merge_fact(
                session, user_id=test_user, project_id=proj, type="statement",
                content=f"launch scheduled for {obj}", confidence=0.5, pending_validation=False,
                subject_id=launch.id, predicate="scheduled for", object=obj,
                event_date_iso=d, valid_from_ordinal=days_since_epoch(_dt.date.fromisoformat(d)),
            )

        facts = await recall_facts(session, user_id=test_user, project_id=proj)
        # The subject rode through the :ABOUT edge, and predicate/object persisted on the node.
        assert all(f.subject_canonical for f in facts)
        assert {f.object for f in facts} == {"Friday", "Tuesday"}

        sup = group_supersessions(facts)
        assert len(sup) == 1
        assert sup[0]["latest"] == "Tuesday"
        assert [c["object"] for c in sup[0]["chain"]] == ["Friday", "Tuesday"]


# ── WS-2.6d — merge a renamed entity (diary colleagues) ───────────────


@pytest.mark.asyncio
async def test_ws26d_merge_renamed_entity_repoints_facts_to_the_winner(neo4j_driver, test_user):
    """D17 merge-a-renamed-entity: 'Minh' and 'Minh Nguyen' are the same person. After merge_entities, the
    loser's facts re-point to the winner (recall attributes BOTH to one) and the loser :Entity is gone."""
    from app.db.neo4j_repos.entities import find_entities_by_name, merge_entities, merge_entity
    from app.db.neo4j_repos.facts import list_facts_for_entity

    proj = "p-assist"
    async with neo4j_driver.session() as session:
        minh = await merge_entity(session, user_id=test_user, project_id=proj, name="Minh",
                                  kind="person", source_type="assistant_diary_fact", auto_created=True)
        minh_full = await merge_entity(session, user_id=test_user, project_id=proj, name="Minh Nguyen",
                                       kind="person", source_type="assistant_diary_fact", auto_created=True)
        await merge_fact(session, user_id=test_user, project_id=proj, type="statement",
                         content="Minh froze the budget", confidence=0.9, subject_id=minh.id)
        await merge_fact(session, user_id=test_user, project_id=proj, type="statement",
                         content="Minh Nguyen approved the plan", confidence=0.9, subject_id=minh_full.id)

        target = await merge_entities(session, user_id=test_user, source_id=minh.id, target_id=minh_full.id)
        assert target.id == minh_full.id

        # The loser is gone; "Minh" now resolves to the winner (moved as an alias).
        remaining = await find_entities_by_name(session, user_id=test_user, project_id=proj, name="Minh")
        assert all(e.id != minh.id for e in remaining)

        # BOTH facts now hang off the winner (the loser's :ABOUT was re-pointed, not orphaned).
        winner_facts = await list_facts_for_entity(session, user_id=test_user, entity_id=minh_full.id)
        contents = {f.content for f in winner_facts}
        assert "Minh froze the budget" in contents and "Minh Nguyen approved the plan" in contents


# ── WS-2.6c — forget a person (entity-scoped KG cascade) ──────────────


@pytest.mark.asyncio
async def test_ws26c_erase_entity_subgraph_removes_entity_and_its_facts(neo4j_driver, test_user):
    """D17 forget-a-person (KG leg): DETACH DELETE the :Entity + every :Fact ABOUT it, scoped to the
    assistant project. A DIFFERENT person's facts survive. Idempotent re-forget deletes nothing more."""
    from app.db.neo4j_repos.entities import erase_entity_subgraph, find_entities_by_name, merge_entity
    from app.db.neo4j_repos.facts import list_facts_for_entity, recall_facts

    proj = "p-assist"
    async with neo4j_driver.session() as session:
        minh = await merge_entity(session, user_id=test_user, project_id=proj, name="Minh",
                                  kind="person", source_type="assistant_diary_fact", auto_created=True)
        alice = await merge_entity(session, user_id=test_user, project_id=proj, name="Alice",
                                   kind="person", source_type="assistant_diary_fact", auto_created=True)
        for c, subj in (("Minh froze the budget", minh.id), ("Minh missed standup", minh.id),
                        ("Alice approved the plan", alice.id)):
            await merge_fact(session, user_id=test_user, project_id=proj, type="statement",
                             content=c, confidence=0.9, pending_validation=False, subject_id=subj,
                             event_date_iso="2026-03-10")

        cascade = await erase_entity_subgraph(session, user_id=test_user, entity_id=minh.id, project_id=proj)
        assert cascade == {"entities_deleted": 1, "facts_deleted": 2}

        # Minh is gone; Alice + her fact remain.
        assert await find_entities_by_name(session, user_id=test_user, project_id=proj, name="Minh") == []
        alice_facts = await list_facts_for_entity(session, user_id=test_user, entity_id=alice.id)
        assert {f.content for f in alice_facts} == {"Alice approved the plan"}
        # Recall no longer surfaces any Minh fact.
        remaining = await recall_facts(session, user_id=test_user, project_id=proj)
        assert all("Minh" not in f.content for f in remaining)

        # Idempotent re-forget.
        assert await erase_entity_subgraph(
            session, user_id=test_user, entity_id=minh.id, project_id=proj,
        ) == {"entities_deleted": 0, "facts_deleted": 0}


# ── WS-2.10 — employment epoch (close / export / cross-epoch isolation) ─


@pytest.mark.asyncio
async def test_ws210_close_epoch_invalidates_but_export_still_reads(neo4j_driver, test_user):
    """T18: closing an epoch bulk-invalidates its facts so DEFAULT recall (valid_until IS NULL) returns
    none, while the EXPORT read still dumps them (incl. invalidated) for the export-then-purge boundary."""
    from app.db.neo4j_repos.facts import (
        export_facts_for_project,
        invalidate_all_facts_for_project,
        recall_facts,
    )

    epoch_a = "p-epoch-a"
    async with neo4j_driver.session() as session:
        for c in ("Acme: shipped v1", "Acme: hired Bob"):
            await merge_fact(session, user_id=test_user, project_id=epoch_a, type="statement",
                             content=c, confidence=0.7, pending_validation=False, event_date_iso="2026-01-05")

        assert len(await recall_facts(session, user_id=test_user, project_id=epoch_a)) == 2

        n = await invalidate_all_facts_for_project(session, user_id=test_user, project_id=epoch_a)
        assert n == 2
        # Default recall no longer surfaces the closed epoch's facts.
        assert await recall_facts(session, user_id=test_user, project_id=epoch_a) == []
        # But the export read still dumps them (for the user's export before purge).
        exported = await export_facts_for_project(session, user_id=test_user, project_id=epoch_a)
        assert {f.content for f in exported} == {"Acme: shipped v1", "Acme: hired Bob"}
        # Idempotent close.
        assert await invalidate_all_facts_for_project(session, user_id=test_user, project_id=epoch_a) == 0


@pytest.mark.asyncio
async def test_ws210_recall_is_epoch_scoped_by_project(neo4j_driver, test_user):
    """T18 recall-defaults-to-current: each epoch is its own project, and recall is project-scoped, so the
    ex-employer's (old-epoch) facts never blend into the new job's recall."""
    from app.db.neo4j_repos.facts import recall_facts

    old_epoch, new_epoch = "p-acme", "p-globex"
    async with neo4j_driver.session() as session:
        await merge_fact(session, user_id=test_user, project_id=old_epoch, type="statement",
                         content="Acme secret roadmap", confidence=0.7, pending_validation=False)
        await merge_fact(session, user_id=test_user, project_id=new_epoch, type="statement",
                         content="Globex onboarding", confidence=0.7, pending_validation=False)
        # Recall in the NEW epoch never surfaces the OLD employer's confidential fact.
        new_facts = await recall_facts(session, user_id=test_user, project_id=new_epoch)
        assert {f.content for f in new_facts} == {"Globex onboarding"}


# ── delete_facts_with_zero_evidence ───────────────────────────────────


# ── K11.7-R1 review-fix tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_k11_7_r1_merge_fact_rejects_empty_source_type():
    """K11.7-R1/R3 fix."""
    with pytest.raises(ValueError, match="source_type"):
        await merge_fact(
            session=None,  # type: ignore[arg-type]
            user_id="u-1",
            project_id="p-1",
            type="decision",
            content="Use fire",
            source_type="",
        )


@pytest.mark.asyncio
async def test_k11_7_r1_merge_fact_empty_source_chapter_normalized(
    neo4j_driver, test_user
):
    """K11.7-R1/R4 fix. Empty source_chapter normalizes to None
    so the stored value is NULL, not "" — keeps downstream
    chapter-id filters honest."""
    async with neo4j_driver.session() as session:
        f = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Use fire",
            confidence=0.9,
            source_chapter="",
        )
    assert f.source_chapter is None


@pytest.mark.asyncio
async def test_k11_7_delete_facts_zero_evidence(neo4j_driver, test_user):
    async with neo4j_driver.session() as session:
        a = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="A",
            confidence=0.9,
        )
        survivor = await merge_fact(
            session,
            user_id=test_user,
            project_id="p-1",
            type="decision",
            content="Survivor",
            confidence=0.9,
        )
        await session.run(
            "MATCH (f:Fact {id: $id}) SET f.evidence_count = 1",
            id=survivor.id,
        )
        deleted = await delete_facts_with_zero_evidence(
            session, user_id=test_user, project_id="p-1"
        )
    assert deleted == 1
    async with neo4j_driver.session() as session:
        gone = await get_fact(session, user_id=test_user, fact_id=a.id)
        kept = await get_fact(
            session, user_id=test_user, fact_id=survivor.id
        )
    assert gone is None
    assert kept is not None
