"""A2-S1b-2 — status backfill: parser units + live-Neo4j core integration."""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio

from app.db.migrations.backfill_status import (
    EventToClassify,
    _extract_content,
    _parse_classify_json,
    run_status_backfill,
)
from app.db.neo4j_repos.entities import merge_entity
from app.db.neo4j_repos.entity_status import status_at_order
from app.db.neo4j_repos.events import merge_event
from app.db.neo4j_repos.provenance import add_evidence, upsert_extraction_source


# ── pure parser units ─────────────────────────────────────────────────


def test_extract_content_messages_array():
    assert _extract_content({"messages": [{"content": "hi"}]}) == "hi"
    assert _extract_content({"content": "fallback"}) == "fallback"
    assert _extract_content({}) == ""


def test_parse_classify_json_plain_and_fenced():
    plain = '{"results": [{"event_id": "e1", "status_effects": [{"entity_ref": "Kai", "status": "gone"}]}]}'
    assert _parse_classify_json(plain)[0]["event_id"] == "e1"
    fenced = "```json\n" + plain + "\n```"
    assert _parse_classify_json(fenced)[0]["event_id"] == "e1"


def test_parse_classify_json_garbage_returns_empty():
    assert _parse_classify_json("no json here") == []
    assert _parse_classify_json("") == []


# ── live Neo4j core ───────────────────────────────────────────────────


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n) WHERE n.user_id = $u DETACH DELETE n", u=user_id,
            )


async def _seed_event(session, *, user_id, project_id, title, participants, order, src_id):
    """Create an event with an evidence edge to a source (so the backfill can
    ride that source). Returns the event id."""
    ev = await merge_event(
        session, user_id=user_id, project_id=project_id,
        title=title, summary=f"{title} summary",
        event_order=order, participants=participants,
        source_type="chapter", confidence=0.9,
    )
    if src_id is not None:
        await add_evidence(
            session, user_id=user_id, target_label="Event", target_id=ev.id,
            source_id=src_id, extraction_model="x", confidence=0.9, job_id="seed",
        )
    return ev.id


@pytest.mark.asyncio
async def test_backfill_writes_status_rides_event_source(neo4j_driver, test_user):
    P = "p-1"
    async with neo4j_driver.session() as session:
        await merge_entity(session, user_id=test_user, project_id=P,
                           name="Kai", kind="character", source_type="book_content")
        src = await upsert_extraction_source(
            session, user_id=test_user, project_id=P,
            source_type="chapter", source_id="ch-1")
        ev_id = await _seed_event(session, user_id=test_user, project_id=P,
                                  title="Kai dies", participants=["Kai"],
                                  order=5_000_000, src_id=src.id)

    async def classify(events: list[EventToClassify]):
        return {ev_id: [("Kai", "gone")]}

    async with neo4j_driver.session() as session:
        res = await run_status_backfill(
            session, user_id=test_user, project_id=P, classify_fn=classify)
    assert res.events_scanned == 1
    assert res.statuses_written == 1

    # status visible at a later position; default active before.
    async with neo4j_driver.session() as session:
        before = await status_at_order(session, user_id=test_user, project_id=P,
                                       entity_ids=["__resolve__"], at_order=1)
        kai_id = (await (await session.run(
            "MATCH (e:Entity {user_id:$u, canonical_name:'kai'}) RETURN e.id AS id",
            u=test_user)).single())["id"]
        after = await status_at_order(session, user_id=test_user, project_id=P,
                                      entity_ids=[kai_id], at_order=9_000_000)
        early = await status_at_order(session, user_id=test_user, project_id=P,
                                      entity_ids=[kai_id], at_order=1)
    assert after == {kai_id: "gone"}
    assert early == {kai_id: "active"}

    # idempotent re-run: same node, evidence not doubled (still visible, one node).
    async def classify2(events): return {ev_id: [("Kai", "gone")]}
    async with neo4j_driver.session() as session:
        res2 = await run_status_backfill(
            session, user_id=test_user, project_id=P, classify_fn=classify2)
        n = (await (await session.run(
            "MATCH (s:EntityStatus {user_id:$u}) RETURN count(s) AS n",
            u=test_user)).single())["n"]
        ev_count = (await (await session.run(
            "MATCH (s:EntityStatus {user_id:$u}) RETURN collect(s.evidence_count) AS c",
            u=test_user)).single())["c"]
    assert res2.statuses_written == 1  # merged again
    assert n == 1                       # no duplicate node
    assert ev_count == [1]              # stable job_id → edge not doubled


@pytest.mark.asyncio
async def test_backfill_skips_null_order_unresolved_and_non_participant(
    neo4j_driver, test_user,
):
    P = "p-1"
    async with neo4j_driver.session() as session:
        # Kai is a participant AND a project entity. Bob is a project entity but
        # NOT a participant of this event. "Lost" is a participant but has no
        # :Entity.
        await merge_entity(session, user_id=test_user, project_id=P,
                           name="Kai", kind="character", source_type="book_content")
        await merge_entity(session, user_id=test_user, project_id=P,
                           name="Bob", kind="character", source_type="book_content")
        src = await upsert_extraction_source(
            session, user_id=test_user, project_id=P,
            source_type="chapter", source_id="ch-1")
        positioned = await _seed_event(
            session, user_id=test_user, project_id=P, title="Kai dies",
            participants=["Kai", "Lost"], order=5_000_000, src_id=src.id)
        # null-order event (legacy/chat) — must be skipped + counted.
        await _seed_event(session, user_id=test_user, project_id=P,
                          title="Legacy event", participants=["Kai"],
                          order=None, src_id=src.id)

    async def classify(events: list[EventToClassify]):
        return {positioned: [
            ("Kai", "gone"),    # participant + resolves → written
            ("Lost", "gone"),   # participant + no entity → unresolved
            ("Bob", "gone"),    # /review-impl #1: project entity but NOT a
                                #   participant → must be rejected, NOT written
        ]}

    async with neo4j_driver.session() as session:
        res = await run_status_backfill(
            session, user_id=test_user, project_id=P, classify_fn=classify)

    assert res.events_skipped_no_order == 1      # the null-order event
    assert res.events_scanned == 1               # only the positioned one
    assert res.statuses_written == 1             # Kai only
    assert res.skipped_not_participant == 1      # Bob — the #1 guard
    assert res.skipped_unresolved_entity == 1    # Lost — participant, no entity

    # Exactly one EntityStatus total (Kai's) — none for the non-participant Bob.
    async with neo4j_driver.session() as session:
        total = (await (await session.run(
            "MATCH (s:EntityStatus {user_id:$u}) RETURN count(s) AS n",
            u=test_user)).single())["n"]
    assert total == 1


@pytest.mark.asyncio
async def test_make_llm_classify_fn_parses_job_result(test_user):
    """/review-impl #5 — the real classify_fn path: extracts content from the
    gateway's messages[0].content shape, parses results[], and filters out
    event_ids not in the batch (hallucinations)."""
    from types import SimpleNamespace
    from app.db.migrations.backfill_status import EventToClassify, make_llm_classify_fn

    class FakeLLM:
        def __init__(self, content):
            self._content = content
            self.calls = []

        async def submit_and_wait(self, **kwargs):
            self.calls.append(kwargs)
            return SimpleNamespace(
                status="completed",
                result={"messages": [{"content": self._content}]},
            )

    content = (
        '{"results": ['
        '{"event_id": "e1", "status_effects": [{"entity_ref": "Kai", "status": "gone"}]},'
        '{"event_id": "HALLUCINATED", "status_effects": [{"entity_ref": "X", "status": "gone"}]},'
        '{"event_id": "e2", "status_effects": [{"entity_ref": "Bob", "status": "bogus"}]}'
        ']}'
    )
    fn = make_llm_classify_fn(FakeLLM(content), user_id=test_user,
                              model_source="user_model", model_ref="m")
    out = await fn([
        EventToClassify(event_id="e1", summary="Kai dies", participants=["Kai"]),
        EventToClassify(event_id="e2", summary="Bob walks", participants=["Bob"]),
    ])
    assert out == {"e1": [("Kai", "gone")]}  # e2 dropped (bogus status), HALLUCINATED filtered


@pytest.mark.asyncio
async def test_make_llm_classify_fn_tolerates_incomplete_job(test_user):
    """A non-completed job (LLM failure) yields an empty map, not a crash."""
    from types import SimpleNamespace
    from app.db.migrations.backfill_status import EventToClassify, make_llm_classify_fn

    class FailLLM:
        async def submit_and_wait(self, **kwargs):
            return SimpleNamespace(status="failed", result=None)

    fn = make_llm_classify_fn(FailLLM(), user_id=test_user,
                              model_source="user_model", model_ref="m")
    out = await fn([EventToClassify(event_id="e1", summary="x", participants=["Kai"])])
    assert out == {}


@pytest.mark.asyncio
async def test_backfill_skips_event_with_no_source(neo4j_driver, test_user):
    P = "p-1"
    async with neo4j_driver.session() as session:
        await merge_entity(session, user_id=test_user, project_id=P,
                           name="Kai", kind="character", source_type="book_content")
        # event has an order but NO EVIDENCED_BY source → can't be made
        # retract-safe → skipped.
        ev_id = await _seed_event(session, user_id=test_user, project_id=P,
                                  title="Orphan event", participants=["Kai"],
                                  order=5_000_000, src_id=None)

    async def classify(events): return {ev_id: [("Kai", "gone")]}
    async with neo4j_driver.session() as session:
        res = await run_status_backfill(
            session, user_id=test_user, project_id=P, classify_fn=classify)
    assert res.statuses_written == 0
    assert res.skipped_no_source == 1
