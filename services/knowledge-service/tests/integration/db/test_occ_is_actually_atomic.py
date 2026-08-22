"""T80 — optimistic concurrency must actually be optimistic concurrency.

⚠️ **The shipped `FOREACH` form was not atomic, and its own comment said it was** — *"Single
round-trip, atomic under `run_write`'s transaction"*. Neo4j takes no write lock at `MATCH`, so
`current_version` was read unlocked. Two concurrent editors both read version 1, both passed
the `CASE`, both wrote version 2, and **both were told `applied: true`**. One person's edit is
discarded and their client gets a 200.

Measured on a real Neo4j, 40 barrier-synchronised pairs both sending `expected_version=1`:

    no lock write (the shipped shape)          double-apply 39/40   final version 2, never 3
    one statement, lock-first                  double-apply  0/40   BUT deadlock 20/40
    two statements, one explicit transaction   double-apply  0/40   deadlock  0/40
    ...the same transaction with NO lock write double-apply 39/40   <- the CONTROL

The control is the load-bearing row: the transaction on its own changes nothing. What removes
the race is writing to the node *before* reading its version, which takes the exclusive lock,
and the transaction is what holds that lock across the second statement.

**Why no unit test could have caught this.** The OCC path is covered by mocks in
`test_entities_mutations.py` and `test_event_correction.py`, and a mock has no lock — it will
happily replay whatever `applied` flag the test author wrote down. The property is about two
real transactions meeting in a real database, so it is pinned here and nowhere else.
"""

from __future__ import annotations

import asyncio
import uuid

import pytest
import pytest_asyncio

from app.db.repositories import VersionMismatchError

#: Enough pairs that a flake cannot masquerade as a pass — the unfixed shape scores 39/40 here,
#: so anything above zero is the bug, not noise.
_PAIRS = 20


@pytest_asyncio.fixture
async def test_user(neo4j_driver):
    user_id = f"u-test-{uuid.uuid4().hex[:12]}"
    try:
        yield user_id
    finally:
        async with neo4j_driver.session() as session:
            await session.run(
                "MATCH (n {user_id: $user_id}) DETACH DELETE n", user_id=user_id,
            )


async def _edit(driver, user_id, entity_id, name, barrier):
    """One editor, released with the other by the barrier. Returns 'applied' or 'rejected'."""
    from app.db.neo4j_repos.entities import update_entity_fields

    async with driver.session() as session:
        await barrier.wait()
        try:
            await update_entity_fields(
                session=session, user_id=user_id, entity_id=entity_id,
                name=name, kind=None, aliases=None, expected_version=1,
            )
            return "applied"
        except VersionMismatchError:
            return "rejected"


@pytest.mark.asyncio
async def test_two_concurrent_edits_at_the_same_version_cannot_BOTH_apply(
    neo4j_driver, test_user,
):
    """Exactly one editor wins; the loser gets `VersionMismatchError`, which the router turns
    into a 412 with a refreshed baseline. Both winning is silent data loss."""
    from app.db.neo4j_repos.entities import merge_entity

    proj = f"p-{uuid.uuid4().hex[:8]}"
    both_applied = 0
    both_rejected = 0
    async with neo4j_driver.session() as session:
        entities = [
            await merge_entity(session, user_id=test_user, project_id=proj,
                               name=f"Kai{i}", kind="person", source_type="chapter")
            for i in range(_PAIRS)
        ]

    for i, e in enumerate(entities):
        barrier = asyncio.Barrier(2)
        outcomes = await asyncio.gather(
            _edit(neo4j_driver, test_user, e.id, f"A{i}", barrier),
            _edit(neo4j_driver, test_user, e.id, f"B{i}", barrier),
        )
        if outcomes == ["applied", "applied"]:
            both_applied += 1
        elif outcomes == ["rejected", "rejected"]:
            both_rejected += 1

    assert both_applied == 0, (
        f"{both_applied} of {_PAIRS} concurrent pairs BOTH reported success at the same "
        f"expected_version. One of those two edits is gone and its author was told it landed. "
        f"The version is being read before anything locks the node — the write in the locked "
        f"read (`SET e.version = coalesce(e.version, 1)`) is what takes that lock, and the "
        f"explicit transaction is what holds it across the apply."
    )
    assert both_rejected == 0, (
        f"{both_rejected} of {_PAIRS} pairs rejected BOTH edits — the guard over-corrected "
        f"and neither author's change landed, which is a different way to lose a write"
    )

    async with neo4j_driver.session() as session:
        row = await (await session.run(
            "MATCH (e:Entity {user_id: $u}) WHERE e.project_id = $p "
            "RETURN count(CASE WHEN e.version = 2 THEN 1 END) AS at2, "
            "count(CASE WHEN e.version <> 2 THEN 1 END) AS other",
            u=test_user, p=proj,
        )).single()
    assert row["at2"] == _PAIRS and row["other"] == 0, (
        f"exactly one edit per entity must land, so every node ends at version 2: "
        f"at2={row['at2']} other={row['other']}"
    )


@pytest.mark.asyncio
async def test_a_SEQUENTIAL_pair_still_behaves_as_before(neo4j_driver, test_user):
    """Non-vacuity in the other direction, on the ordinary path the concurrency fix must not
    have changed: a correct `expected_version` applies and bumps, and re-sending the stale one
    is refused with the CURRENT entity attached for the 412 body."""
    from app.db.neo4j_repos.entities import merge_entity, update_entity_fields

    proj = f"p-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        e = await merge_entity(session, user_id=test_user, project_id=proj,
                               name="Rin", kind="person", source_type="chapter")

        updated, before = await update_entity_fields(
            session=session, user_id=test_user, entity_id=e.id,
            name="Rin Zhou", kind=None, aliases=None, expected_version=1,
        )
        assert updated is not None and updated.version == 2
        assert updated.name == "Rin Zhou"
        assert updated.user_edited is True
        assert before is not None and before["name"] == "Rin", (
            "the pre-edit snapshot must come from the LOCKED READ — the correction event "
            "carries it, and reading it after the write would report the new name as the old"
        )

    async with neo4j_driver.session() as session:
        with pytest.raises(VersionMismatchError) as exc:
            await update_entity_fields(
                session=session, user_id=test_user, entity_id=e.id,
                name="Rin Again", kind=None, aliases=None, expected_version=1,
            )
        assert exc.value.current.version == 2, (
            "the 412 body must carry the CURRENT entity so the client can retry against a "
            "baseline that exists"
        )

    async with neo4j_driver.session() as session:
        missing, before = await update_entity_fields(
            session=session, user_id=test_user, entity_id="no-such-id",
            name="X", kind=None, aliases=None, expected_version=1,
        )
        assert missing is None and before is None


@pytest.mark.asyncio
async def test_erasing_an_entity_with_NO_facts_still_deletes_it(neo4j_driver, test_user):
    """The third FOREACH was `FOREACH (x IN facts | DETACH DELETE x)`, and the obvious rewrite
    — `UNWIND facts AS x` — is wrong in the empty case: zero rows out, so the `DETACH DELETE e`
    after it never runs. A forget would silently do nothing for exactly the entities that are
    easiest to forget, and report success."""
    from app.db.neo4j_repos.entities import erase_entity_subgraph, get_entity, merge_entity

    proj = f"p-{uuid.uuid4().hex[:8]}"
    async with neo4j_driver.session() as session:
        e = await merge_entity(session, user_id=test_user, project_id=proj,
                               name="Nobody", kind="person", source_type="chapter")
        out = await erase_entity_subgraph(
            session=session, user_id=test_user, entity_id=e.id, project_id=proj)
        assert out == {"entities_deleted": 1, "facts_deleted": 0}, out
        assert await get_entity(session, user_id=test_user, canonical_id=e.id) is None, (
            "the entity survived a forget that reported it deleted"
        )

        # ...and erasing something that is not there stays idempotent rather than raising.
        again = await erase_entity_subgraph(
            session=session, user_id=test_user, entity_id=e.id, project_id=proj)
        assert again == {"entities_deleted": 0, "facts_deleted": 0}, again

# ── the same bug, the same shape, on :Event ────────────────────────────────────────────────


async def _edit_event(driver, user_id, event_id, title, barrier):
    from app.db.neo4j_repos.events import update_event_fields

    async with driver.session() as session:
        await barrier.wait()
        try:
            await update_event_fields(
                session=session, user_id=user_id, event_id=event_id,
                title=title, summary=None, time_cue=None, event_date_iso=None,
                expected_version=1,
            )
            return "applied"
        except VersionMismatchError:
            return "rejected"


@pytest.mark.asyncio
async def test_two_concurrent_EVENT_edits_at_the_same_version_cannot_BOTH_apply(
    neo4j_driver, test_user,
):
    """⚠️ Added because bite 2 showed the event path had no live proof at all.

    Deleting the lock-taking write from `_LOCK_AND_READ_EVENT_CYPHER` reddened exactly one
    test, and it was a STRING MATCH on the query text. A text assertion cannot tell whether
    the transaction still holds the lock across the apply — it only says the line is present.
    The entity half had this test; the event half, which carries the identical bug in the
    identical shape, had a substring.
    """
    from app.db.neo4j_repos.events import merge_event

    proj = f"p-{uuid.uuid4().hex[:8]}"
    both_applied = 0
    async with neo4j_driver.session() as session:
        events = [
            await merge_event(session, user_id=test_user, project_id=proj,
                              title=f"The Oath {i}", chapter_id=f"ch-{i}")
            for i in range(_PAIRS)
        ]

    for i, ev in enumerate(events):
        barrier = asyncio.Barrier(2)
        outcomes = await asyncio.gather(
            _edit_event(driver=neo4j_driver, user_id=test_user, event_id=ev.id,
                        title=f"A{i}", barrier=barrier),
            _edit_event(driver=neo4j_driver, user_id=test_user, event_id=ev.id,
                        title=f"B{i}", barrier=barrier),
        )
        if outcomes == ["applied", "applied"]:
            both_applied += 1

    assert both_applied == 0, (
        f"{both_applied} of {_PAIRS} concurrent event edits BOTH reported success at the same "
        f"expected_version — one author's correction is gone and they were told it landed"
    )
    async with neo4j_driver.session() as session:
        row = await (await session.run(
            "MATCH (e:Event {user_id: $u}) WHERE e.project_id = $p "
            "RETURN count(CASE WHEN e.version = 2 THEN 1 END) AS at2, "
            "count(CASE WHEN e.version <> 2 THEN 1 END) AS other",
            u=test_user, p=proj,
        )).single()
    assert row["at2"] == _PAIRS and row["other"] == 0, (
        f"exactly one edit per event must land: at2={row['at2']} other={row['other']}"
    )
