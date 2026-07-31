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

#: ``question_id -> schema path``, the map S1's brief supplies. Deliberately NOT
#: stored on the answer row: the answer knows which question it answers, and the
#: brief is the only thing that decides where that answer belongs.
QUESTION_PATHS = {
    "q_quantity": "kind.quantity",
    "q_name": "kind.name",
    "q_type": "kind.progression_type",
    "q_curve": "kind.curve",
    "q_cap": "kind.cap_rule",
    "q_start": "kind.initial_tier",
    "q_count": "kind.tier_count",
    "q_order": "kind.tier[].tier_index",
    "q_tname": "kind.tier[].name",
    "q_shape": "kind.tier[].within_tier_curve",
    "q_break": "kind.tier[].breakthrough",
}

STORE_KW = dict(
    owner_user_id=OWNER, book_id=BOOK, element_kind="progression_system",
    created_by=OWNER, schema_fingerprint=FINGERPRINT, question_paths=QUESTION_PATHS,
)


async def _approved_run(pool, *, tier_count=9, breakthrough="at_max"):
    """A complete, approved interrogation for one kind — the S2 output S3 folds."""
    job_id, corpus = await _fixture_rows(pool)
    seal = await _seal(pool, corpus)
    repo = GamegenS2Repo(pool)
    plan = [
        ("q_quantity", "element:progression_system", ["internal_energy"]),
        ("q_name", "kind:internal_energy", "內功"),
        ("q_type", "kind:internal_energy", "stage"),
        ("q_curve", "kind:internal_energy", "stage"),
        ("q_cap", "kind:internal_energy", "tier_based"),
        ("q_start", "kind:internal_energy", 0),
        ("q_count", "kind:internal_energy", tier_count),
        ("q_order", "kind:internal_energy", "ascending"),
        ("q_tname", "kind:internal_energy", "{n}層"),
        ("q_shape", "kind:internal_energy", "linear"),
        ("q_break", "kind:internal_energy", breakthrough),
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
    sid, _ = await repo.fold_and_store(
        job_id=job_id, **{**STORE_KW,
                          "question_paths": {**QUESTION_PATHS, "q_extra": "kind.name"}},
    )
    async with pool.acquire() as c:
        refs = json.loads(await c.fetchval(
            "SELECT answer_refs_json FROM gamegen_creative_structure WHERE structure_id=$1",
            sid))
    assert len(refs) == 11, "the unapproved answer is absent, and is NOT an unconsumed refusal"


async def test_an_answer_to_a_question_the_brief_does_not_define_is_refused(pool):
    """The brief is version-pinned by ``schema_fingerprint``. Folding an answer
    against a brief that never asked would place it at a position nobody chose."""
    repo, job_id, _ = await _approved_run(pool)
    thin = {k: v for k, v in QUESTION_PATHS.items() if k != "q_cap"}
    with pytest.raises(FoldRefusal) as e:
        await repo.fold_and_store(job_id=job_id, **{**STORE_KW, "question_paths": thin})
    assert "q_cap" in str(e.value)


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
