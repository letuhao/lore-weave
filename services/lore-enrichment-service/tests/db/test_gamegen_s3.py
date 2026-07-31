"""S3 — the fold, persisted, against a real Postgres.

``tests/test_gamegen_fold.py`` proves the fold's properties as a pure function.
This file proves the two things that file cannot:

* the S2→S3 hand-off is real — a full approved interrogation folds into a stored
  structure, and an **unapproved** answer does not reach it;
* ``PGN-A9``'s ledger is enforced by the **table**, not only by ``fold()``. The
  fold is a function and a table is a place: a row written by a backfill, a repair
  script, or a future S3b would otherwise carry a ledger nobody checked. Every
  ledger test here writes raw SQL for exactly that reason.

Destructive-ops note: cleanup is the ``pool`` fixture's down→up migration, guarded
by this directory's ``conftest.py`` (``db-safety-gate: guarded-dir``).
"""

from __future__ import annotations

import json

import asyncpg
import pytest

from app.db.repositories.gamegen import GamegenS2Repo
from app.gamegen.fold import FoldRefusal

from .test_gamegen_s2 import BOOK, OTHER_OWNER, OWNER, _cited, _decision, _fixture_rows, _seal

pytestmark = pytest.mark.asyncio

HEX_A = "f" * 64
HEX_B = "e" * 64
FINGERPRINT = "787c69388addda04170236c72ba1dfd8ee3c69d46d705c3739ec50967a8b225b"

#: The brief's real question ids, asserted against the shipped brief below. The
#: PATH MAP is no longer injectable — ``fold_and_store`` loads the brief itself,
#: because a caller-supplied placement map and fingerprint were self-reported in
#: exactly the way the seal's caller-supplied digest was.
BRIEF_QUESTION_IDS = [
    "cardinality", "kind_name", "kind_type", "curve", "cap", "start_tier",
    "tier_count", "tier_order", "tier_name", "tier_shape", "breakthrough",
]


@pytest.mark.asyncio(loop_scope="function")
async def test_the_plan_below_uses_the_SHIPPED_briefs_question_ids():
    """Not a DB test, and deliberately in this file: if the brief renames a
    question, the fold below would silently produce a `q_… not defined` refusal
    that reads like a code bug. This makes it read like what it is."""
    from app.gamegen.brief import load_brief

    assert {q.id for q in load_brief("progression_system").questions} == set(BRIEF_QUESTION_IDS)


STORE_KW = dict(
    owner_user_id=OWNER, book_id=BOOK, element_kind="progression_system",
    created_by=OWNER,
)


async def _approved_run(pool, *, tier_count=9, breakthrough="at_max"):
    """A complete, approved interrogation for one kind — the S2 output S3 folds."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    repo = GamegenS2Repo(pool)
    plan = [
        ("cardinality", "element:progression_system", ["internal_energy"]),
        ("kind_name", "kind:internal_energy", "內功"),
        ("kind_type", "kind:internal_energy", "stage"),
        ("curve", "kind:internal_energy", "stage"),
        ("cap", "kind:internal_energy", "tier_based"),
        ("start_tier", "kind:internal_energy", 0),
        ("tier_count", "kind:internal_energy", tier_count),
        ("tier_order", "kind:internal_energy", "ascending"),
        ("tier_name", "kind:internal_energy", "{n}層"),
        ("tier_shape", "kind:internal_energy", "linear"),
        ("breakthrough", "kind:internal_energy", breakthrough),
    ]
    ds = []
    for qid, target, value in plan:
        d = await _decision(pool, job_id, klass=qid, target=target)
        await repo.record_answer(
            decision_id=d, job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
            created_by=OWNER,
            evidence=_cited(seal, question_id=qid, target_ref=target, value=value),
        )
        ds.append(d)
    await repo.approve(decision_ids=ds, owner_user_id=OWNER, approved_by=OWNER)
    return repo, job_id, seal


async def _raw_structure(pool, job_id, *, owner=OWNER, consumption, refs, body="{}"):
    async with pool.acquire() as c:
        await c.execute(
            """
            INSERT INTO gamegen_creative_structure
              (job_id, owner_user_id, element_kind, schema_fingerprint, content_hash,
               body_json, consumption_json, answer_refs_json, created_by)
            VALUES ($1,$2,'progression_system',$3,$4,$5::jsonb,$6::jsonb,$7::jsonb,$2)
            """,
            job_id, owner, FINGERPRINT, "a" * 64, body, consumption, refs,
        )


# ── the S2 -> S3 hand-off ───────────────────────────────────────────────────


async def test_the_fold_persists_a_dense_structure(pool):
    repo, job_id, _ = await _approved_run(pool, tier_count=9)
    sid, chash = await repo.fold_and_store(job_id=job_id, **STORE_KW)
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT body_json, consumption_json, answer_refs_json FROM "
            "gamegen_creative_structure WHERE structure_id=$1", sid,
        )
    body = json.loads(row["body_json"])
    assert len(body["kinds"][0]["tiers"]) == 9
    assert [t["name"]["value"] for t in body["kinds"][0]["tiers"]][:3] == ["1層", "2層", "3層"]
    assert len(chash) == 64
    assert len(json.loads(row["answer_refs_json"])) == 11
    assert len(json.loads(row["consumption_json"])) == 11


async def test_re_folding_unchanged_answers_is_a_no_op(pool):
    """Content-addressed within the job. A second row for the same hash would make
    *"which structure did S5 read"* a question with two answers."""
    repo, job_id, _ = await _approved_run(pool)
    first = await repo.fold_and_store(job_id=job_id, **STORE_KW)
    assert await repo.fold_and_store(job_id=job_id, **STORE_KW) == first
    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT count(*) FROM gamegen_creative_structure WHERE job_id=$1", job_id
        ) == 1


async def test_an_UNAPPROVED_answer_is_not_folded(pool):
    """S3 folds ``approved_answers``, not ``live_answers``. An answer recorded and
    never approved reaching the structure would be T3 defeated at the last hop —
    every earlier gate green, and content in the artifact nobody signed for."""
    repo, job_id, seal = await _approved_run(pool)
    d = await _decision(pool, job_id, klass="q_extra", target="kind:internal_energy")
    await repo.record_answer(
        decision_id=d, job_id=job_id, owner_user_id=OWNER, book_id=BOOK, created_by=OWNER,
        evidence=_cited(seal, question_id="q_extra", target_ref="kind:internal_energy",
                        value="unapproved"),
    )
    sid, _ = await repo.fold_and_store(job_id=job_id, **STORE_KW)
    async with pool.acquire() as c:
        refs = json.loads(await c.fetchval(
            "SELECT answer_refs_json FROM gamegen_creative_structure WHERE structure_id=$1",
            sid))
    assert len(refs) == 11, "the unapproved answer is absent, and is NOT an unconsumed refusal"


async def test_an_APPROVED_answer_to_a_question_the_brief_does_not_define_is_refused(pool):
    """An approved answer whose question the shipped brief never asked. Folding it
    would place an answer at a position nobody chose; refused, and the fingerprint
    is named so the message reads as *"the brief moved"* rather than *"bad id"*."""
    repo, job_id, seal = await _approved_run(pool)
    d = await _decision(pool, job_id, klass="ghost", target="kind:internal_energy")
    await repo.record_answer(
        decision_id=d, job_id=job_id, owner_user_id=OWNER, book_id=BOOK, created_by=OWNER,
        evidence=_cited(seal, question_id="a_question_no_brief_asked",
                        target_ref="kind:internal_energy", value="x"),
    )
    await repo.approve(decision_ids=[d], owner_user_id=OWNER, approved_by=OWNER)
    with pytest.raises(FoldRefusal) as e:
        await repo.fold_and_store(job_id=job_id, **STORE_KW)
    assert "a_question_no_brief_asked" in str(e.value)


async def test_the_stored_fingerprint_comes_from_the_BRIEF_not_the_caller(pool):
    """**Found by probe.** The signature used to take ``schema_fingerprint``, so a
    caller could assert any value and nothing checked it against the shipped
    brief — the seal's caller-supplied-digest class, one tier up. It is now loaded
    from ``load_brief``, which ``assert_covers`` at load."""
    import inspect

    from app.gamegen.brief import load_brief

    sig = inspect.signature(GamegenS2Repo.fold_and_store)
    assert "schema_fingerprint" not in sig.parameters
    assert "question_paths" not in sig.parameters

    repo, job_id, _ = await _approved_run(pool)
    sid, _ = await repo.fold_and_store(job_id=job_id, **STORE_KW)
    async with pool.acquire() as c:
        stored = await c.fetchval(
            "SELECT schema_fingerprint FROM gamegen_creative_structure WHERE structure_id=$1",
            sid)
    assert stored == load_brief("progression_system").schema_fingerprint


async def test_a_MOVED_schema_yields_a_new_structure_rather_than_silently_keeping_the_old(pool):
    """**The probe's finding.** ``schema_fingerprint`` sat outside the content
    hash, so re-folding the same answers after the schema moved produced the same
    ``content_hash``, ``ON CONFLICT`` returned the OLD row, and the new fingerprint
    was silently discarded — the row then claimed a schema nobody asserted, which
    is precisely the drift the column exists to make loud.

    Asserted at the hash, because the fingerprint is no longer injectable through
    the repository (which is the other half of the fix)."""
    from app.gamegen.fold import content_hash

    body = {"element_kind": "progression_system", "kinds": []}
    assert content_hash("progression_system", "a" * 64, body) != content_hash(
        "progression_system", "b" * 64, body
    )


async def test_a_batch_above_the_ceiling_refuses_the_whole_fold(pool):
    """T3's remaining arm, end to end: the 11 decisions were approved in ONE
    action, and a deployment that caps a review batch at 3 refuses the run rather
    than folding content nobody read."""
    repo, job_id, _ = await _approved_run(pool)
    with pytest.raises(FoldRefusal) as e:
        await repo.fold_and_store(job_id=job_id, max_batch_size=3, **STORE_KW)
    assert "ceiling is 3" in str(e.value)
    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT count(*) FROM gamegen_creative_structure WHERE job_id=$1", job_id
        ) == 0


async def test_an_out_of_scope_breakthrough_survives_into_the_stored_structure(pool):
    """`PGN-A20` end to end, through the DB. 寒潭 is a *place*; no place module
    exists; the artifact says so and names the owner rather than going quiet. A
    pipeline that silently generated a place-less rule would be the `QTY-Q5` class
    shipping in the POC that exists to prove it cannot."""
    repo, job_id, _ = await _approved_run(
        pool, tier_count=3,
        breakthrough={"out_of_scope": "place", "requirement": "寒潭 — a sealed place"},
    )
    sid, _ = await repo.fold_and_store(job_id=job_id, **STORE_KW)
    async with pool.acquire() as c:
        body = json.loads(await c.fetchval(
            "SELECT body_json FROM gamegen_creative_structure WHERE structure_id=$1", sid))
    cell = body["kinds"][0]["tiers"][0]["breakthrough"]
    assert cell["state"] == "refused"
    assert "place element module" in cell["owner"]
    assert "寒潭" in cell["requirement"]


# ── the ledger is enforced by the TABLE, not only by fold() ─────────────────


async def test_a_ref_that_consumed_nothing_is_refused_by_the_database(pool):
    """**The bite.** ``a2`` is hash-linked and reaches no pointer — an approved
    answer recorded as part of the structure that shaped none of it."""
    _, job_id, _ = await _approved_run(pool)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_structure(
            pool, job_id,
            consumption='{"a1": ["/kinds/0"]}',
            refs=json.dumps([["a1", HEX_A], ["a2", HEX_B]]),
        )
    assert "ledger_total" in str(e.value)


async def test_a_consumed_answer_with_no_ref_is_refused_by_the_database(pool):
    """The other direction: ``a2`` shaped the structure and nothing pins WHICH
    version of it did. That is exactly the id-linking `PGN-A9` replaced."""
    _, job_id, _ = await _approved_run(pool)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_structure(
            pool, job_id,
            consumption='{"a1": ["/kinds/0"], "a2": ["/kinds/1"]}',
            refs=json.dumps([["a1", HEX_A]]),
        )
    assert "ledger_total" in str(e.value)


async def test_matching_COUNTS_over_different_answers_is_refused_by_the_database(pool):
    """**Found by a bite-test, not by design.** Two refs, two consumption keys —
    and they are not the same two: ``a2`` is hash-linked and consumed nothing while
    ``a3`` shaped the structure with nothing pinning it. Both directions are
    broken at once and the CARDINALITIES agree, so a count check waves it through.

    The two tests either side of this one both happened to change the count, so
    removing the membership arm from ``gamegen_ledger_is_total`` left them green —
    the arm was load-bearing and nothing proved it. That is `PGN-A9`'s own point
    arriving one tier down: *rows-in equals rows-out while a leaf vanishes*."""
    _, job_id, _ = await _approved_run(pool)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_structure(
            pool, job_id,
            consumption='{"a1": ["/kinds/0"], "a3": ["/kinds/1"]}',
            refs=json.dumps([["a1", HEX_A], ["a2", HEX_B]]),
        )
    assert "ledger_total" in str(e.value)


async def test_an_empty_pointer_list_is_refused_by_the_database(pool):
    """Present in the map with zero pointers reads as consumed and is not."""
    _, job_id, _ = await _approved_run(pool)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_structure(
            pool, job_id, consumption='{"a1": []}', refs=json.dumps([["a1", HEX_A]]),
        )
    assert "ledger_total" in str(e.value)


async def test_an_id_linked_ref_is_refused_by_the_database(pool):
    """Hash-linked, not id-linked. A ref whose second element is not a 64-hex
    digest pins nothing, and an UPDATE could then move what it points at."""
    _, job_id, _ = await _approved_run(pool)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_structure(
            pool, job_id, consumption='{"a1": ["/kinds/0"]}',
            refs=json.dumps([["a1", "not-a-hash"]]),
        )
    assert "ledger_total" in str(e.value)


async def test_a_structure_folded_from_no_answers_is_refused_by_the_database(pool):
    """Authored by nobody. Structurally valid, and it would carry a content hash
    and a fingerprint that both look exactly like a real one's."""
    _, job_id, _ = await _approved_run(pool)
    with pytest.raises(asyncpg.PostgresError) as e:
        await _raw_structure(pool, job_id, consumption="{}", refs="[]")
    assert "ledger_total" in str(e.value)


async def test_a_well_formed_ledger_is_accepted(pool):
    """The check has to admit the legitimate shape, or it is a ban on structures
    and every test above passes for the wrong reason."""
    _, job_id, _ = await _approved_run(pool)
    await _raw_structure(
        pool, job_id,
        consumption='{"a1": ["/kinds/0/name", "/kinds/0/curve"], "a2": ["/kinds/1"]}',
        refs=json.dumps([["a1", HEX_A], ["a2", HEX_B]]),
    )


async def test_a_structure_cannot_be_stored_against_another_users_job(pool):
    """The same composite FK that closed S2's PROBE 1, on the S3 table."""
    _, job_id, _ = await _approved_run(pool)
    with pytest.raises(asyncpg.ForeignKeyViolationError):
        await _raw_structure(
            pool, job_id, owner=OTHER_OWNER,
            consumption='{"a1": ["/kinds/0"]}', refs=json.dumps([["a1", HEX_A]]),
        )
