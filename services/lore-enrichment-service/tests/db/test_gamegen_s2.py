"""S2 — the interrogation tier, against a real Postgres.

Doc 39 §3.3/§3.4/§4.2/§4.3. These tests exist because every invariant in that
section is a **schema** invariant: the point of putting `PGN-A3`'s split, `PGN-A4`'s
closed set, `PGN-A14`'s seal requirement and `PGN-A9`'s append-only rule in
``CHECK``s and triggers rather than in the repository is that a writer who
bypasses the repository still cannot evade them. A test that only exercised
``GamegenS2Repo`` would prove nothing about that — so most of what follows writes
raw SQL, deliberately, and asserts the DB refuses it.

Destructive-ops note: cleanup is the ``pool`` fixture's down→up migration, which
this directory's ``conftest.py`` guards with ``_guard_throwaway`` before the first
DROP (``db-safety-gate: guarded-dir``). No test here issues a bare DELETE.
"""

from __future__ import annotations

import json
from uuid import UUID, uuid4

import asyncpg
import pytest

from app.db.repositories.gamegen import BatchSizeMismatch, GamegenS2Repo
from app.gamegen.answer_hash import AnswerEvidence, Citation

pytestmark = pytest.mark.asyncio

OWNER = UUID("019d5e3c-7cc5-7e6a-8b27-1344e148bf7c")
OTHER_OWNER = UUID("019d5e3c-7cc5-7e6a-8b27-000000000002")
BOOK = UUID("019d5e3c-7cc5-7e6a-8b27-000000000003")
ROOT = "a" * 64


CHUNK = "019fb600-0000-7000-8000-00000000000a"
CHUNK_B = "019fb600-0000-7000-8000-00000000000b"


async def _fixture_rows(pool, *, owner: UUID = OWNER, chunks: int = 3) -> tuple[UUID, UUID]:
    """A job and a chunked corpus to hang the S2 rows off.

    The corpus gets real chunks because ``seal_corpus`` DERIVES ``chunk_count``
    from them — a fixture that skipped them would make every seal fail, which is
    the check doing its job.
    """
    async with pool.acquire() as c:
        corpus_id = await c.fetchval(
            "INSERT INTO source_corpus (project_id, user_id, name, kind) "
            "VALUES ($1,$2,'寒潭劍錄 wiki','other') RETURNING corpus_id",
            BOOK, owner,
        )
        for i in range(chunks):
            await c.execute(
                "INSERT INTO source_corpus_chunk "
                "(corpus_id, project_id, chunk_index, content, content_sha256) "
                "VALUES ($1,$2,$3,$4,$5)",
                corpus_id, BOOK, i, f"內功分為九層，第{i}章", f"{i:064d}",
            )
        job_id = await c.fetchval(
            "INSERT INTO enrichment_job (project_id, user_id, technique, book_id) "
            "VALUES ($1,$2,'retrieval',$3) RETURNING job_id",
            BOOK, owner, BOOK,
        )
    return job_id, corpus_id


async def _seal(pool, corpus_id: UUID) -> UUID:
    return await GamegenS2Repo(pool).seal_corpus(
        corpus_id=corpus_id, owner_user_id=OWNER, book_id=BOOK, sealed_by=OWNER,
    )


async def _decision(pool, job_id: UUID, *, klass="tier_name_pattern", target="kind:internal_energy"):
    return await GamegenS2Repo(pool).propose_decision(
        job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        element_kind="progression_system", question_class=klass, target_ref=target,
    )


def _cited(seal: UUID, **kw) -> AnswerEvidence:
    base = dict(
        question_id="q_tier_count",
        target_ref="kind:internal_energy",
        value="stage",
        # 6 CHARACTERS, span 6 wide. In UTF-8 these are 18 bytes — the check that
        # `len(quote) == end - start` is what makes that distinction load-bearing
        # instead of a comment.
        says=(Citation(CHUNK, 10, 16, "內功分為九層"),),
        proposed_text=None,
        not_stated=False,
        not_stated_reason=None,
        verified_against_seal_id=str(seal),
    )
    base.update(kw)
    return AnswerEvidence(**base)


async def _raw_answer(pool, *, decision_id, job_id, **overrides):
    """Insert straight into the table, bypassing the repository. This is the
    point: the repository's validation is a courtesy, the schema is the rule."""
    row = dict(
        question_id="q_raw",
        target_ref="kind:internal_energy",
        says_json="[]",
        # value XOR silence: a raw row that is not `not_stated` must carry one.
        value_json='"stage"',
        proposed_text="something",
        verified_against_seal_id=None,
        not_stated=False,
        not_stated_reason=None,
        answer_hash="b" * 64,
    )
    row.update(overrides)
    if row["not_stated"] and "value_json" not in overrides:
        row["value_json"] = None
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO gamegen_answer
              (decision_id, job_id, owner_user_id, book_id, question_id, target_ref,
               says_json, value_json, proposed_text, verified_against_seal_id,
               not_stated, not_stated_reason, answer_hash, created_by)
            VALUES ($1,$2,$3,$4,$5,$6,$7::jsonb,$8::jsonb,$9,$10,$11,$12,$13,$3)
            RETURNING answer_id
            """,
            decision_id, job_id, OWNER, BOOK, row["question_id"], row["target_ref"],
            row["says_json"], row["value_json"], row["proposed_text"],
            row["verified_against_seal_id"],
            row["not_stated"], row["not_stated_reason"], row["answer_hash"],
        )


# ── the migration itself ────────────────────────────────────────────────────


async def test_the_gamegen_tier_survives_a_down_up_roundtrip(pool):
    """The fixture down-migrates then up-migrates before every test in this
    directory. If the gamegen tables were missing from ``DOWN_DDL``, dropping
    ``enrichment_job`` and ``source_corpus`` would fail with
    DependentObjectsStillExists and take the whole tests/db tree with it — so this
    passing at all is the round-trip evidence. The assertion pins WHICH objects."""
    async with pool.acquire() as c:
        tables = {
            r["tablename"]
            for r in await c.fetch(
                "SELECT tablename FROM pg_tables WHERE tablename LIKE 'gamegen%'"
            )
        }
        funcs = {
            r["proname"]
            for r in await c.fetch("SELECT proname FROM pg_proc WHERE proname LIKE 'gamegen%'")
        }
    assert tables == {
        "gamegen_corpus_seal",
        "gamegen_decision",
        "gamegen_answer",
        "gamegen_creative_structure",
    }
    assert funcs == {
        "gamegen_says_wellformed",
        "gamegen_answer_append_only",
        "gamegen_decision_batch_honest",
        "gamegen_ledger_is_total",
    }


# ── PGN-A1: this is not enrichment_proposal ─────────────────────────────────


async def test_the_gamegen_tier_is_a_separate_table_from_enrichment_proposal(pool):
    """`PGN-A1`. ``enrichment_proposal`` is non-canon by construction — its
    ``confidence`` CHECK forbids 1.0. This pipeline's output is canon by
    construction. Sharing a table would make one of those a lie, and the CHECK
    says which breaks first."""
    async with pool.acquire() as c:
        cols = {
            r["column_name"]
            for r in await c.fetch(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'gamegen_answer'"
            )
        }
    assert "confidence" not in cols and "origin" not in cols


# ── T5: an approved decision names a person ─────────────────────────────────


async def test_an_approved_decision_with_no_approver_is_refused(pool):
    """The T5 hole this closes: every hop of the chain still resolves and the
    last one names nobody."""
    job_id, _ = await _fixture_rows(pool)
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO gamegen_decision "
                "(job_id, owner_user_id, element_kind, question_class, target_ref, review_status) "
                "VALUES ($1,$2,'progression_system','cap_rule','kind:x','approved')",
                job_id, OWNER,
            )
    assert "status_coherent" in str(e.value)


async def test_a_rejection_with_no_reason_is_refused(pool):
    job_id, _ = await _fixture_rows(pool)
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO gamegen_decision "
                "(job_id, owner_user_id, element_kind, question_class, target_ref, review_status) "
                "VALUES ($1,$2,'progression_system','cap_rule','kind:x','rejected')",
                job_id, OWNER,
            )
    assert "status_coherent" in str(e.value)


async def test_a_decision_is_born_proposed_and_reaches_approved_only_through_approve(pool):
    job_id, _ = await _fixture_rows(pool)
    repo = GamegenS2Repo(pool)
    d = await _decision(pool, job_id)
    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT review_status FROM gamegen_decision WHERE decision_id=$1", d
        ) == "proposed"
    assert await repo.approve(decision_ids=[d], owner_user_id=OWNER, approved_by=OWNER) is None
    async with pool.acquire() as c:
        r = await c.fetchrow(
            "SELECT review_status, approved_by, batch_id FROM gamegen_decision "
            "WHERE decision_id=$1", d
        )
    assert r["review_status"] == "approved" and r["approved_by"] == OWNER
    assert r["batch_id"] is None, "a single approval is not a batch"


async def test_one_decision_per_assertion_class_per_target(pool):
    """Two would let one reviewer approve and another reject the same assertion
    with nothing downstream able to say which won."""
    job_id, _ = await _fixture_rows(pool)
    await _decision(pool, job_id)
    with pytest.raises(asyncpg.UniqueViolationError):
        await _decision(pool, job_id)


# ── T3: bulk is VISIBLE ─────────────────────────────────────────────────────


async def test_a_bulk_approval_records_its_real_size(pool):
    job_id, _ = await _fixture_rows(pool)
    repo = GamegenS2Repo(pool)
    ds = [await _decision(pool, job_id, target=f"kind:k{i}") for i in range(5)]
    batch = await repo.approve(decision_ids=ds, owner_user_id=OWNER, approved_by=OWNER)
    assert batch is not None
    async with pool.acquire() as c:
        sizes = {
            r["batch_size"]
            for r in await c.fetch(
                "SELECT batch_size FROM gamegen_decision WHERE batch_id=$1", batch
            )
        }
    assert sizes == {5}


async def test_an_understated_batch_size_is_refused_at_commit(pool):
    """**The bite.** Approving 5 while declaring ``batch_size = 1`` is the exact
    move that makes T3's "bulk is visible" false — it renders as five careful
    individual reviews. The check is DEFERRED, so it fires at COMMIT with all
    five rows present; an immediate one would see a count of 1 on row 1 and pass."""
    job_id, _ = await _fixture_rows(pool)
    ds = [await _decision(pool, job_id, target=f"kind:k{i}") for i in range(5)]
    fake_batch = uuid4()
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            async with c.transaction():
                await c.execute(
                    "UPDATE gamegen_decision SET review_status='approved', approved_by=$2, "
                    "approved_at=now(), batch_id=$3, batch_size=1 "
                    "WHERE decision_id = ANY($1::uuid[])",
                    ds, OWNER, fake_batch,
                )
    assert "declares batch_size=1 but holds 5" in str(e.value)


async def test_enlarging_a_committed_batch_afterwards_is_refused(pool):
    """The half the repository cannot see: the batch was honest when written, and
    a sixth decision is added to it later. That back-dates an approval onto an
    assertion nobody was shown."""
    job_id, _ = await _fixture_rows(pool)
    repo = GamegenS2Repo(pool)
    ds = [await _decision(pool, job_id, target=f"kind:k{i}") for i in range(5)]
    batch = await repo.approve(decision_ids=ds, owner_user_id=OWNER, approved_by=OWNER)
    late = await _decision(pool, job_id, target="kind:late")
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            async with c.transaction():
                await c.execute(
                    "UPDATE gamegen_decision SET review_status='approved', approved_by=$2, "
                    "approved_at=now(), batch_id=$3, batch_size=5 WHERE decision_id=$1",
                    late, OWNER, batch,
                )
    assert "holds 6" in str(e.value)


async def test_a_partial_batch_approval_rolls_back(pool):
    """Approving 4 of 5 and reporting success would record a ``batch_size`` nobody
    reviewed. The repo refuses instead."""
    job_id, _ = await _fixture_rows(pool)
    repo = GamegenS2Repo(pool)
    ds = [await _decision(pool, job_id, target=f"kind:k{i}") for i in range(4)]
    with pytest.raises(BatchSizeMismatch):
        await repo.approve(
            decision_ids=ds + [uuid4()], owner_user_id=OWNER, approved_by=OWNER
        )
    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT count(*) FROM gamegen_decision WHERE review_status='approved' "
            "AND job_id=$1", job_id
        ) == 0


async def test_a_batch_on_an_unapproved_decision_is_refused(pool):
    """Stamping a batch on a ``proposed`` row would pre-declare a click that has
    not happened."""
    job_id, _ = await _fixture_rows(pool)
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO gamegen_decision "
                "(job_id, owner_user_id, element_kind, question_class, target_ref, "
                " batch_id, batch_size) VALUES ($1,$2,'p','c','t',$3,2)",
                job_id, OWNER, uuid4(),
            )
    assert "batch_needs_approval" in str(e.value)


# ── PGN-A3 / PGN-A14: the evidence, checked by the SCHEMA ───────────────────


async def test_a_citation_with_no_span_is_refused_by_the_database(pool):
    """`PGN-A3`. A citation to a whole document verifies nothing, and the
    repository is not the thing standing in the way."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    d = await _decision(pool, job_id)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_answer(
            pool, decision_id=d, job_id=job_id,
            says_json=json.dumps([{"chunk_id": CHUNK, "quote": "x"}]),
            verified_against_seal_id=seal, proposed_text=None,
        )
    assert "says_wellformed" in str(e.value)


async def test_a_zero_width_span_is_refused_by_the_database(pool):
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    d = await _decision(pool, job_id)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_answer(
            pool, decision_id=d, job_id=job_id,
            says_json=json.dumps([{"chunk_id": CHUNK, "span": [7, 7], "quote": ""}]),
            verified_against_seal_id=seal, proposed_text=None,
        )
    assert "says_wellformed" in str(e.value)


async def test_overlapping_spans_on_one_chunk_are_refused_by_the_database(pool):
    """One span cited N times is one piece of evidence dressed as N — the shape
    `PGN-A14` names when it says the citation count must not fall below the item
    count."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    d = await _decision(pool, job_id)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_answer(
            pool, decision_id=d, job_id=job_id,
            says_json=json.dumps([
                {"chunk_id": CHUNK, "span": [0, 30], "quote": "一" * 30},
                {"chunk_id": CHUNK, "span": [20, 50], "quote": "二" * 30},
            ]),
            verified_against_seal_id=seal, proposed_text=None,
        )
    assert "says_wellformed" in str(e.value)


async def test_disjoint_spans_on_the_same_chunk_are_accepted(pool):
    """The check has to admit the legitimate case or it is just a ban on
    citations. Two tier names in one paragraph is the normal shape."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    d = await _decision(pool, job_id)
    await _raw_answer(
        pool, decision_id=d, job_id=job_id,
        says_json=json.dumps([
            {"chunk_id": CHUNK, "span": [0, 10], "quote": "一層" * 5},
            {"chunk_id": CHUNK, "span": [10, 20], "quote": "二層" * 5},
        ]),
        verified_against_seal_id=seal, proposed_text=None,
    )


async def test_a_citation_with_no_seal_is_refused_by_the_database(pool):
    """`PGN-A14` made structural: an answer that names no seal is one nobody could
    have checked, and it cannot be stored."""
    job_id, _ = await _fixture_rows(pool)
    d = await _decision(pool, job_id)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_answer(
            pool, decision_id=d, job_id=job_id,
            says_json=json.dumps([{"chunk_id": CHUNK, "span": [0, 5], "quote": "xxxxx"}]),
            verified_against_seal_id=None, proposed_text=None,
        )
    assert "citation_needs_seal" in str(e.value)


async def test_an_answer_that_states_nothing_is_refused_by_the_database(pool):
    job_id, _ = await _fixture_rows(pool)
    d = await _decision(pool, job_id)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_answer(pool, decision_id=d, job_id=job_id, proposed_text=None)
    assert "says_something" in str(e.value)


# ── PGN-A4: not_stated is complete, and accountable ─────────────────────────


async def test_a_free_text_not_stated_reason_is_refused_by_the_database(pool):
    job_id, _ = await _fixture_rows(pool)
    d = await _decision(pool, job_id)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_answer(
            pool, decision_id=d, job_id=job_id,
            not_stated=True, not_stated_reason="couldn't find it", proposed_text=None,
        )
    assert "not_stated_reason_closed" in str(e.value)


async def test_a_not_stated_answer_hiding_a_proposal_is_refused_by_the_database(pool):
    """The cheap path that also launders an invention: ``not_stated`` costs ~2 s,
    verifying a span ~60–90 s."""
    job_id, _ = await _fixture_rows(pool)
    d = await _decision(pool, job_id)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_answer(
            pool, decision_id=d, job_id=job_id,
            not_stated=True, not_stated_reason="absent_from_corpus",
            proposed_text="nine tiers, probably",
        )
    assert "not_stated_shape" in str(e.value)


async def test_not_stated_ratio_is_reported_per_question_class(pool):
    """`PGN-A4` third constraint. A single global ratio averages *"silent about a
    magnitude"* (expected) into *"silent about tier names"* (a red flag against a
    corpus whose fixture requirement says it names them)."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    repo = GamegenS2Repo(pool)
    d_names = await _decision(pool, job_id, klass="tier_name_pattern", target="kind:ie")
    d_mag = await _decision(pool, job_id, klass="tier_max", target="kind:ie")
    await repo.record_answer(
        decision_id=d_names, job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        created_by=OWNER, evidence=_cited(seal, question_id="q_names"),
    )
    await repo.record_answer(
        decision_id=d_mag, job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        created_by=OWNER,
        evidence=AnswerEvidence(
            question_id="q_max", target_ref="kind:ie", value=None, says=(), proposed_text=None,
            not_stated=True, not_stated_reason="absent_from_corpus",
            verified_against_seal_id=None,
        ),
    )
    ratio = await repo.not_stated_ratio(job_id=job_id, owner_user_id=OWNER)
    assert ratio == {"tier_name_pattern": (0, 1), "tier_max": (1, 1)}


# ── PGN-A9: append-only ─────────────────────────────────────────────────────


async def test_editing_an_answers_evidence_is_refused(pool):
    """**The attack `PGN-A9` names.** Flip ``proposed_text`` into ``says_json``
    after the structure is pinned and an invented tier becomes an extracted one
    with every hop of the chain still green."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    d = await _decision(pool, job_id)
    a = await _raw_answer(pool, decision_id=d, job_id=job_id)
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            await c.execute(
                "UPDATE gamegen_answer SET says_json=$2::jsonb, proposed_text=NULL, "
                "verified_against_seal_id=$3 WHERE answer_id=$1",
                a, json.dumps([{"chunk_id": CHUNK, "span": [0, 5], "quote": "xxxxx"}]), seal,
            )
    assert "append-only" in str(e.value)


async def test_editing_an_answer_alongside_a_supersession_is_refused(pool):
    """The subtler version: the UPDATE *does* set ``superseded_by_answer_id``, and
    quietly rewrites the quote in the same statement. A trigger that only checked
    "is supersession being set?" would wave this through."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    d = await _decision(pool, job_id)
    old = await _raw_answer(pool, decision_id=d, job_id=job_id, question_id="q1")
    new = await _raw_answer(pool, decision_id=d, job_id=job_id, question_id="q2")
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            await c.execute(
                "UPDATE gamegen_answer SET superseded_by_answer_id=$2, "
                "proposed_text='rewritten' WHERE answer_id=$1",
                old, new,
            )
    assert "NOTHING else" in str(e.value)


async def test_deleting_an_answer_is_refused(pool):
    job_id, _ = await _fixture_rows(pool)
    d = await _decision(pool, job_id)
    a = await _raw_answer(pool, decision_id=d, job_id=job_id)
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            await c.execute("DELETE FROM gamegen_answer WHERE answer_id=$1", a)
    assert "cannot be DELETEd" in str(e.value)


async def test_un_superseding_an_answer_is_refused(pool):
    """History rewritten by a sequence of individually-legal steps."""
    job_id, _ = await _fixture_rows(pool)
    d = await _decision(pool, job_id)
    old = await _raw_answer(pool, decision_id=d, job_id=job_id, question_id="q1")
    new = await _raw_answer(pool, decision_id=d, job_id=job_id, question_id="q2")
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE gamegen_answer SET superseded_by_answer_id=$2 WHERE answer_id=$1", old, new
        )
        with pytest.raises(asyncpg.PostgresError) as e:
            await c.execute(
                "UPDATE gamegen_answer SET superseded_by_answer_id=NULL WHERE answer_id=$1", old
            )
    assert "already superseded" in str(e.value)


async def test_two_live_answers_for_one_question_cannot_coexist(pool):
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    repo = GamegenS2Repo(pool)
    d = await _decision(pool, job_id)
    kw = dict(decision_id=d, job_id=job_id, owner_user_id=OWNER, book_id=BOOK, created_by=OWNER)
    await repo.record_answer(evidence=_cited(seal), **kw)
    with pytest.raises(asyncpg.UniqueViolationError):
        await repo.record_answer(evidence=_cited(seal, proposed_text="different"), **kw)


async def test_supersession_frees_the_slot_and_keeps_the_history(pool):
    """The doc's plain ``UNIQUE (job_id, question_id, target_ref)`` would have made
    this impossible — the only way to correct an answer would be the UPDATE the
    append-only rule forbids. The partial index is what lets both rules hold."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    repo = GamegenS2Repo(pool)
    d = await _decision(pool, job_id)
    kw = dict(decision_id=d, job_id=job_id, owner_user_id=OWNER, book_id=BOOK, created_by=OWNER)
    first = await repo.record_answer(evidence=_cited(seal), **kw)
    second = await repo.record_answer(
        evidence=_cited(seal, says=(Citation(CHUNK, 10, 16, "內功分為十層"),)),
        supersedes=first, **kw,
    )
    live = await repo.live_answers(job_id=job_id, owner_user_id=OWNER)
    assert [a.answer_id for a in live] == [second]
    async with pool.acquire() as c:
        assert await c.fetchval("SELECT count(*) FROM gamegen_answer WHERE job_id=$1", job_id) == 2


async def test_superseding_an_answer_to_a_DIFFERENT_question_is_refused(pool):
    """A silent drop reachable through a legal API: retire q1's only live answer
    and replace it with one about q2. q1 now has no answer, and S3's consumption
    ledger cannot notice — the row it would have counted is gone, not
    unconsumed."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    repo = GamegenS2Repo(pool)
    d = await _decision(pool, job_id)
    kw = dict(decision_id=d, job_id=job_id, owner_user_id=OWNER, book_id=BOOK, created_by=OWNER)
    q1 = await repo.record_answer(evidence=_cited(seal, question_id="q_tier_count"), **kw)
    with pytest.raises(ValueError, match="DIFFERENT question"):
        await repo.record_answer(
            evidence=_cited(seal, question_id="q_cap_rule"), supersedes=q1, **kw
        )
    live = await repo.live_answers(job_id=job_id, owner_user_id=OWNER)
    assert [a.question_id for a in live] == ["q_tier_count"], "the rollback held"


async def test_deferring_the_supersession_fk_did_not_weaken_it(pool):
    """``superseded_by_answer_id`` is DEFERRABLE so that retire-then-insert is
    possible. Deferred is not disabled: a supersession pointing at an answer that
    never arrives still fails, at COMMIT rather than at statement time. Without
    this the deferral would be a hole dressed as an ordering fix."""
    job_id, _ = await _fixture_rows(pool)
    d = await _decision(pool, job_id)
    a = await _raw_answer(pool, decision_id=d, job_id=job_id)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        async with pool.acquire() as c:
            async with c.transaction():
                await c.execute(
                    "UPDATE gamegen_answer SET superseded_by_answer_id=$2 WHERE answer_id=$1",
                    a, uuid4(),
                )


async def test_the_repository_computes_the_hash_and_never_takes_one(pool):
    """A caller-supplied hash is a hash of whatever the caller says the answer is,
    and S5's recompute-and-compare would then compare the row against a number
    from the same source that wrote it."""
    import inspect

    sig = inspect.signature(GamegenS2Repo.record_answer)
    assert "answer_hash" not in sig.parameters and "hash" not in sig.parameters

    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    d = await _decision(pool, job_id)
    ev = _cited(seal)
    await GamegenS2Repo(pool).record_answer(
        decision_id=d, job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        created_by=OWNER, evidence=ev,
    )
    from app.gamegen.answer_hash import answer_hash

    async with pool.acquire() as c:
        stored = await c.fetchval(
            "SELECT answer_hash FROM gamegen_answer WHERE job_id=$1", job_id
        )
    assert stored == answer_hash(ev)


async def test_supersession_does_not_move_the_superseded_answers_hash(pool):
    """The hash covers evidence, not lineage. If supersession moved it, S5's
    recompute would refuse every correctly-superseded answer."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    repo = GamegenS2Repo(pool)
    d = await _decision(pool, job_id)
    kw = dict(decision_id=d, job_id=job_id, owner_user_id=OWNER, book_id=BOOK, created_by=OWNER)
    first = await repo.record_answer(evidence=_cited(seal), **kw)
    async with pool.acquire() as c:
        before = await c.fetchval(
            "SELECT answer_hash FROM gamegen_answer WHERE answer_id=$1", first
        )
    await repo.record_answer(
        evidence=_cited(seal, proposed_text="revised"), supersedes=first, **kw
    )
    async with pool.acquire() as c:
        after = await c.fetchval(
            "SELECT answer_hash FROM gamegen_answer WHERE answer_id=$1", first
        )
    assert before == after


# ── integrity of the join, and of the tenant boundary ───────────────────────


async def test_an_answers_job_cannot_disagree_with_its_decisions(pool):
    """The composite FK. A denormalized ``job_id`` that could drift would let an
    answer be counted under one job's consumption ledger while its approval lives
    under another's."""
    job_a, _ = await _fixture_rows(pool)
    job_b, _ = await _fixture_rows(pool)
    d = await _decision(pool, job_a)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_answer(pool, decision_id=d, job_id=job_b)
    assert "decision_fk" in str(e.value)


async def test_a_cross_tenant_read_returns_nothing(pool):
    """Per-book tier. Self-hosted is not single-user."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    repo = GamegenS2Repo(pool)
    d = await _decision(pool, job_id)
    await repo.record_answer(
        decision_id=d, job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        created_by=OWNER, evidence=_cited(seal),
    )
    assert await repo.live_answers(job_id=job_id, owner_user_id=OWNER)
    assert await repo.live_answers(job_id=job_id, owner_user_id=OTHER_OWNER) == []
    assert await repo.not_stated_ratio(job_id=job_id, owner_user_id=OTHER_OWNER) == {}


async def test_a_cross_tenant_approval_is_refused(pool):
    """The tenancy defect this shape would otherwise have: an authenticated user
    approving another user's assertions."""
    job_id, _ = await _fixture_rows(pool)
    repo = GamegenS2Repo(pool)
    d = await _decision(pool, job_id)
    with pytest.raises(BatchSizeMismatch):
        await repo.approve(
            decision_ids=[d], owner_user_id=OTHER_OWNER, approved_by=OTHER_OWNER
        )
    assert await repo.reject(decision_id=d, owner_user_id=OTHER_OWNER, reason="no") is False
    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT review_status FROM gamegen_decision WHERE decision_id=$1", d
        ) == "proposed"


# ── the tenant boundary as a FOREIGN KEY, not a query convention ────────────
#
# Every test below reproduces a hole an adversarial probe found and DEMONSTRATED
# on the first implementation, which had owner filters on every read and was
# still wrong — because the rows themselves were inconsistent.


async def test_a_decision_cannot_be_created_on_another_users_job(pool):
    """PROBE 1. A plain FK on ``job_id`` proves the job exists, not that it is
    this owner's."""
    job_id, _ = await _fixture_rows(pool)  # owned by OWNER
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO gamegen_decision (job_id, owner_user_id, element_kind, "
                "question_class, target_ref) VALUES ($1,$2,'p','c','t')",
                job_id, OTHER_OWNER,
            )


async def test_an_answer_cannot_hang_off_another_users_decision(pool):
    """**PROBE 2/3 — the worst one.** Before the owner column entered the
    composite FK, user B could insert an answer under user A's *approved*
    decision, and B's own owner-scoped read returned B's invented text joined to
    A's ``approved_by``. B's invention wore A's signature: T5 naming the WRONG
    person, which is worse than naming nobody."""
    job_id, _ = await _fixture_rows(pool)
    repo = GamegenS2Repo(pool)
    d = await _decision(pool, job_id)
    await repo.approve(decision_ids=[d], owner_user_id=OWNER, approved_by=OWNER)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO gamegen_answer (decision_id, job_id, owner_user_id, book_id, "
                "question_id, target_ref, says_json, value_json, proposed_text, "
                "not_stated, answer_hash, created_by) "
                "VALUES ($1,$2,$3,$4,'q','kind:internal_energy','[]'::jsonb,'\"x\"'::jsonb,"
                "'B INVENTED THIS',false,$5,$3)",
                d, job_id, OTHER_OWNER, BOOK, "b" * 64,
            )
    # and the consequence that came free: A's live slot is no longer stealable
    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT count(*) FROM gamegen_answer WHERE owner_user_id=$1", OTHER_OWNER
        ) == 0


# ── the span UNIT, which the corpus makes load-bearing ──────────────────────


async def test_a_chunk_id_that_is_not_a_uuid_is_refused(pool):
    """PROBE 5. ``chunk_id`` names a ``source_corpus_chunk`` and cannot be a
    foreign key — it lives inside JSONB — so the format check is the only thing
    between a citation and a chunk that does not exist."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    d = await _decision(pool, job_id)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_answer(
            pool, decision_id=d, job_id=job_id, proposed_text=None,
            says_json=json.dumps(
                [{"chunk_id": "not-a-uuid-at-all", "span": [0, 1], "quote": "x"}]
            ),
            verified_against_seal_id=seal,
        )
    assert "says_wellformed" in str(e.value)


async def test_a_byte_offset_span_over_chinese_text_is_refused(pool):
    """**The multilingual bite.** 六 characters of Chinese are 18 UTF-8 bytes. A
    model (or a tokenizer) emitting byte offsets produces ``[10, 28)`` for a
    six-character quote, and nothing else in the schema says which unit a span
    is — so it would verify against the wrong substring the moment the corpus is
    ingested. ``len(quote) == end - start`` makes it fail here instead."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    d = await _decision(pool, job_id)
    quote = "內功分為九層"
    assert len(quote) == 6 and len(quote.encode("utf-8")) == 18
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_answer(
            pool, decision_id=d, job_id=job_id, proposed_text=None,
            says_json=json.dumps([{"chunk_id": CHUNK, "span": [10, 28], "quote": quote}]),
            verified_against_seal_id=seal,
        )
    assert "says_wellformed" in str(e.value)
    # the CHARACTER span is accepted, so this is a unit check and not a ban
    await _raw_answer(
        pool, decision_id=d, job_id=job_id, proposed_text=None,
        says_json=json.dumps([{"chunk_id": CHUNK, "span": [10, 16], "quote": quote}]),
        verified_against_seal_id=seal,
    )


# ── the S3 hand-off ─────────────────────────────────────────────────────────


async def test_approved_answers_are_exactly_the_live_answers_of_approved_decisions(pool):
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    repo = GamegenS2Repo(pool)
    d_ok = await _decision(pool, job_id, klass="a", target="kind:ie")
    d_no = await _decision(pool, job_id, klass="b", target="kind:ie")
    a_ok = await repo.record_answer(
        decision_id=d_ok, job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        created_by=OWNER, evidence=_cited(seal, question_id="q_ok"),
    )
    await repo.record_answer(
        decision_id=d_no, job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        created_by=OWNER, evidence=_cited(seal, question_id="q_no"),
    )
    await repo.approve(decision_ids=[d_ok], owner_user_id=OWNER, approved_by=OWNER)
    assert len(await repo.live_answers(job_id=job_id, owner_user_id=OWNER)) == 2
    assert [a.answer_id for a in
            await repo.approved_answers(job_id=job_id, owner_user_id=OWNER)] == [a_ok]


# ── the seal ────────────────────────────────────────────────────────────────


async def test_resealing_an_unchanged_corpus_is_idempotent(pool):
    """Two rows with the same root and different ``sealed_at`` would let byte-
    identical evidence sit under two seals, and the difference would look like it
    meant something."""
    _, corpus = await _fixture_rows(pool)
    assert await _seal(pool, corpus) == await _seal(pool, corpus)


async def test_a_changed_corpus_gets_a_new_seal(pool):
    """The digest is derived from the chunks, so this needs no cooperation from
    the caller: adding a chunk moves it. If the digest were still a parameter,
    the same call would have re-returned the OLD seal over a corpus that had
    changed underneath it — a citation checked against a snapshot that no longer
    exists, which is `PGN-A14` inverted."""
    _, corpus = await _fixture_rows(pool, chunks=3)
    before = await _seal(pool, corpus)
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO source_corpus_chunk "
            "(corpus_id, project_id, chunk_index, content, content_sha256) "
            "VALUES ($1,$2,99,'罡元非內功也',$3)",
            corpus, BOOK, "9" * 64,
        )
    after = await _seal(pool, corpus)
    assert before != after
    async with pool.acquire() as c:
        rows = await c.fetch(
            "SELECT corpus_digest, chunk_count FROM gamegen_corpus_seal "
            "WHERE corpus_id=$1 ORDER BY chunk_count", corpus
        )
    assert [r["chunk_count"] for r in rows] == [3, 4]
    assert rows[0]["corpus_digest"] != rows[1]["corpus_digest"]


async def test_the_digest_depends_on_chunk_content_not_only_on_the_count(pool):
    """A count-only digest would be identical for two corpora of the same size,
    and every citation would verify against either."""
    _, a = await _fixture_rows(pool, chunks=2)
    _, b = await _fixture_rows(pool, chunks=2)
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE source_corpus_chunk SET content='完全不同的內容' "
            "WHERE corpus_id=$1 AND chunk_index=0", b,
        )
        d_a = await c.fetchval(
            "SELECT encode(sha256(convert_to(string_agg("
            "chunk_id::text || ':' || chunk_index::text || ':' || content, E'\\n' "
            "ORDER BY chunk_index), 'UTF8')), 'hex') "
            "FROM source_corpus_chunk WHERE corpus_id=$1", a,
        )
    seal_a, seal_b = await _seal(pool, a), await _seal(pool, b)
    async with pool.acquire() as c:
        digests = [
            await c.fetchval(
                "SELECT corpus_digest FROM gamegen_corpus_seal WHERE seal_id=$1", s
            )
            for s in (seal_a, seal_b)
        ]
    assert digests[0] == d_a, "the stored digest is the one the SQL derives"
    assert digests[0] != digests[1]


async def test_a_seal_cited_by_an_answer_cannot_be_deleted(pool):
    """ON DELETE RESTRICT. Removing the seal would strand every citation checked
    against it — the row would still say 'verified' and name nothing."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    d = await _decision(pool, job_id)
    await GamegenS2Repo(pool).record_answer(
        decision_id=d, job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        created_by=OWNER, evidence=_cited(seal),
    )
    with pytest.raises(asyncpg.PostgresError):
        async with pool.acquire() as c:
            await c.execute("DELETE FROM gamegen_corpus_seal WHERE seal_id=$1", seal)


async def test_sealing_another_users_corpus_is_refused(pool):
    """The FK proves the corpus exists, not that it is the caller's. A seal any
    user can mint over any user's bytes grounds nothing — and `PGN-A14` grounds
    every citation in exactly that."""
    _, corpus = await _fixture_rows(pool)
    repo = GamegenS2Repo(pool)
    with pytest.raises(PermissionError):
        await repo.seal_corpus(
            corpus_id=corpus, owner_user_id=OTHER_OWNER, book_id=BOOK,
            sealed_by=OTHER_OWNER,
        )
    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT count(*) FROM gamegen_corpus_seal WHERE corpus_id=$1", corpus
        ) == 0


async def test_a_seal_derives_its_chunk_count_and_never_takes_one(pool):
    """A seal is an attestation about what the corpus contained. A caller-supplied
    count is the attestation attesting to itself — one claiming 9 chunks over a
    corpus of 300 would look exactly like one that read the whole thing."""
    import inspect

    sig = inspect.signature(GamegenS2Repo.seal_corpus)
    assert "chunk_count" not in sig.parameters

    _, corpus = await _fixture_rows(pool, chunks=7)
    seal = await _seal(pool, corpus)
    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT chunk_count FROM gamegen_corpus_seal WHERE seal_id=$1", seal
        ) == 7


async def test_sealing_an_empty_corpus_is_refused(pool):
    """It would attest to nothing, and every citation against it would name a
    chunk the seal never covered."""
    _, corpus = await _fixture_rows(pool, chunks=0)
    with pytest.raises(ValueError, match="no chunks"):
        await _seal(pool, corpus)


async def test_a_seal_derives_its_digest_and_never_takes_one(pool):
    """The same argument as ``chunk_count``, and the sharper one: a
    caller-supplied digest lets a citation be checked against a snapshot that
    never existed. Both are now derived **in the same statement as the insert**,
    so a concurrent ingest cannot slip a chunk in between computing and
    recording."""
    import inspect

    sig = inspect.signature(GamegenS2Repo.seal_corpus)
    assert "merkle_root" not in sig.parameters and "corpus_digest" not in sig.parameters

    _, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    async with pool.acquire() as c:
        digest = await c.fetchval(
            "SELECT corpus_digest FROM gamegen_corpus_seal WHERE seal_id=$1", seal
        )
    assert len(digest) == 64 and all(ch in "0123456789abcdef" for ch in digest)
