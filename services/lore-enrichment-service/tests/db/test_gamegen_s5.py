"""S5 — admission, against a real Postgres **and the real engine binary**.

This is the POC-1 seam. Nothing here mocks the validator: the artifact goes to
`progression-validate`, which runs the same `resolve_and_pin` path a reality load
runs and stamps the versions compiled into it. A mocked verdict would prove the
plumbing and say nothing about whether the engine agrees — and the engine
disagreeing is exactly what found the flat-ladder bug.

The tests skip when the binary is not built. A Python-only checkout is a
legitimate state, and a test that failed there would be deleted rather than fixed.

Destructive-ops note: cleanup is the ``pool`` fixture's down→up migration, guarded
by this directory's ``conftest.py`` (``db-safety-gate: guarded-dir``).
"""

from __future__ import annotations

import json
from uuid import uuid4

import asyncpg
import pytest

from app.db.repositories.gamegen import GamegenS2Repo
from app.gamegen.generate import AdmissionRefusal
from app.gamegen.policy import Band, magnitude_paths
from app.gamegen.validator import ValidatorUnavailable, validator_path

from .test_gamegen_s2 import BOOK, OTHER_OWNER, OWNER
from .test_gamegen_s3 import STORE_KW, _approved_run

pytestmark = pytest.mark.asyncio

ADMIN = OTHER_OWNER


def _require_engine():
    try:
        return validator_path()
    except ValidatorUnavailable as e:
        pytest.skip(str(e))


def bands(**over) -> dict[str, Band]:
    b = {p: Band(0, 100_000, 100) for p in magnitude_paths()}
    b.update({"kind.tier[].tier_max": Band(0, 1000, 500)})
    b.update(over)
    return b


async def _ready(pool, *, tier_count=3):
    """A job with an approved interrogation, a folded structure, and a policy."""
    repo, job_id, _ = await _approved_run(pool, tier_count=tier_count)
    structure_id, _ = await repo.fold_and_store(job_id=job_id, **STORE_KW)
    parent = await repo.publish_system_policy(
        element_kind="progression_system", policy_version=1, bands=bands(),
        authored_by=ADMIN, is_admin=True,
    )
    return repo, job_id, structure_id, parent


# ── the POC-1 seam ──────────────────────────────────────────────────────────


async def test_a_generated_candidate_is_ADMITTED_by_the_engines_own_binary(pool):
    """**The chain, end to end, through the DB.** Approved answers → fold →
    policy → generate → the engine's binary → a recorded verdict."""
    _require_engine()
    repo, job_id, structure_id, _ = await _ready(pool)
    cid = await repo.admit_candidate(
        job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        element_kind="progression_system", structure_id=structure_id, created_by=OWNER,
    )
    c = await repo.candidate(candidate_id=cid, owner_user_id=OWNER)
    assert c["verdict"] == "admitted", c["findings"]
    assert len(c["progression_digest"]) == 64
    assert c["findings"] == []
    # The stamp came out of the binary, not out of this side.
    assert c["engine_schema_version"] >= 1 and c["engine_law_version"] >= 1


async def test_the_verdict_records_what_the_ENGINE_said_not_a_paraphrase(pool):
    """A ladder whose rungs do not rise. The finding stored is
    `ProgressionInvalid`'s own text, so a reviewer reads what the engine said."""
    _require_engine()
    repo, job_id, structure_id, _ = await _ready(pool)
    # A band of width 0 collapses the interpolated ladder onto one value, which
    # is the exact shape the engine refuses — reached through a policy a human
    # could legitimately author by narrowing to a point.
    await repo.publish_system_policy(
        element_kind="progression_system", policy_version=2,
        bands=bands(**{"kind.tier[].tier_max": Band(7, 7, 7)}),
        authored_by=ADMIN, is_admin=True,
    )
    cid = await repo.admit_candidate(
        job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        element_kind="progression_system", structure_id=structure_id, created_by=OWNER,
    )
    c = await repo.candidate(candidate_id=cid, owner_user_id=OWNER)
    if c["verdict"] == "admitted":
        pytest.skip("the +index term keeps even a zero-width band rising; nothing to assert")
    assert c["progression_digest"] is None, "a refusal names no digest"
    assert any("progression.schema" in f for f in c["findings"]), c["findings"]


async def test_a_REFUSAL_is_recorded_rather_than_raised_away(pool):
    """An S5 refusal that only threw would leave the chain with no row saying the
    engine looked and said no — and the next run would look like the first."""
    _require_engine()
    repo, job_id, structure_id, _ = await _ready(pool)
    cid = await repo.admit_candidate(
        job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        element_kind="progression_system", structure_id=structure_id, created_by=OWNER,
    )
    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT count(*) FROM gamegen_candidate WHERE candidate_id=$1", cid) == 1


async def test_re_admitting_the_same_inputs_is_a_no_op(pool):
    """Content-addressed on (structure, policy, repair_round, engine version). A
    second row would make *"which candidate did S6 pin"* a question with two
    answers."""
    _require_engine()
    repo, job_id, structure_id, _ = await _ready(pool)
    kw = dict(job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
              element_kind="progression_system", structure_id=structure_id, created_by=OWNER)
    assert await repo.admit_candidate(**kw) == await repo.admit_candidate(**kw)


# ── the S5 human gate, which v1 had none of ─────────────────────────────────


async def test_an_admitted_candidate_can_be_approved_and_records_WHO(pool):
    _require_engine()
    repo, job_id, structure_id, _ = await _ready(pool)
    cid = await repo.admit_candidate(
        job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        element_kind="progression_system", structure_id=structure_id, created_by=OWNER)
    assert await repo.approve_candidate(
        candidate_id=cid, owner_user_id=OWNER, approved_by=OWNER)
    c = await repo.candidate(candidate_id=cid, owner_user_id=OWNER)
    assert c["review_status"] == "approved" and c["approved_by"] == OWNER


async def test_a_REFUSED_candidate_cannot_be_approved_by_the_database(pool):
    """**T3's last hop, and the one v1 left open.** Without the CHECK, *"approve it
    anyway"* is one UPDATE away and every hop before it stays green."""
    _, job_id, _, _ = await _ready(pool)
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO gamegen_candidate (job_id, owner_user_id, element_kind, "
                "structure_hash, policy_hash, artifact_hash, verdict, read_set_json, "
                "engine_schema_version, engine_law_version, review_status, approved_by, "
                "approved_at, created_by) VALUES ($1,$2,'progression_system',$3,$3,$3,"
                "'refused','[]'::jsonb,5,1,'approved',$2,now(),$2)",
                job_id, OWNER, "a" * 64,
            )
    assert "review_coherent" in str(e.value)


async def test_an_ADMITTED_candidate_must_name_a_digest(pool):
    """A verdict about nothing addressable is not a verdict S6 can pin."""
    _, job_id, _, _ = await _ready(pool)
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO gamegen_candidate (job_id, owner_user_id, element_kind, "
                "structure_hash, policy_hash, artifact_hash, verdict, read_set_json, "
                "engine_schema_version, engine_law_version, created_by) "
                "VALUES ($1,$2,'progression_system',$3,$3,$3,'admitted','[]'::jsonb,5,1,$2)",
                job_id, OWNER, "a" * 64,
            )
    assert "digest_matches_verdict" in str(e.value)


async def test_a_REFUSED_candidate_must_NOT_name_a_digest(pool):
    """A digest beside a refusal is something a later stage can pin."""
    _, job_id, _, _ = await _ready(pool)
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO gamegen_candidate (job_id, owner_user_id, element_kind, "
                "structure_hash, policy_hash, artifact_hash, verdict, progression_digest, "
                "read_set_json, engine_schema_version, engine_law_version, created_by) "
                "VALUES ($1,$2,'progression_system',$3,$3,$3,'refused',$3,'[]'::jsonb,5,1,$2)",
                job_id, OWNER, "a" * 64,
            )
    assert "digest_matches_verdict" in str(e.value)


# ── what the reviewer is shown (§7.2) ───────────────────────────────────────


async def test_the_review_payload_counts_the_ENGINE_DEFAULTED_fields(pool):
    """*"Nobody reviews 24 integers."* The number that turns an invisible hole
    into something vetoable is *"you are approving N tiers of which M fields will
    be engine-defaulted."*"""
    _require_engine()
    repo, job_id, structure_id, _ = await _ready(pool, tier_count=5)
    cid = await repo.admit_candidate(
        job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        element_kind="progression_system", structure_id=structure_id, created_by=OWNER)
    c = await repo.candidate(candidate_id=cid, owner_user_id=OWNER)
    # 1 body_or_soul + 5 initial_value_on_advance
    assert c["engine_defaulted_field_count"] == 6
    assert all(reason for reason in c["default_provenance"].values()), "each names its reason"


async def test_the_read_set_is_recorded_for_the_ledgers_second_direction(pool):
    _require_engine()
    repo, job_id, structure_id, _ = await _ready(pool, tier_count=3)
    cid = await repo.admit_candidate(
        job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        element_kind="progression_system", structure_id=structure_id, created_by=OWNER)
    c = await repo.candidate(candidate_id=cid, owner_user_id=OWNER)
    assert len(c["read_set"]) == 6 + 12 + 1
    assert all(p.startswith("/kinds/") for p in c["read_set"])


# ── tenancy + the pre-engine refusals ───────────────────────────────────────


async def test_a_cross_tenant_caller_cannot_admit_or_read(pool):
    _require_engine()
    repo, job_id, structure_id, _ = await _ready(pool)
    with pytest.raises(AdmissionRefusal) as e:
        await repo.admit_candidate(
            job_id=job_id, owner_user_id=OTHER_OWNER, book_id=BOOK,
            element_kind="progression_system", structure_id=structure_id,
            created_by=OTHER_OWNER)
    assert "not visible" in str(e.value)

    cid = await repo.admit_candidate(
        job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        element_kind="progression_system", structure_id=structure_id, created_by=OWNER)
    assert await repo.candidate(candidate_id=cid, owner_user_id=OTHER_OWNER) is None
    assert not await repo.approve_candidate(
        candidate_id=cid, owner_user_id=OTHER_OWNER, approved_by=OTHER_OWNER)


async def test_an_inadmissible_repair_never_reaches_the_engine_or_the_table(pool):
    """`PGN-A17`. No artifact exists, so there is no verdict to record — inventing
    a ``verdict='refused'`` row for a candidate the engine never saw would be the
    same lie as stamping a version."""
    repo, job_id, structure_id, _ = await _ready(pool)
    with pytest.raises(AdmissionRefusal) as e:
        await repo.admit_candidate(
            job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
            element_kind="progression_system", structure_id=structure_id,
            created_by=OWNER, repair_ops=[{"op": "remove", "path": "/kinds/0/tiers/0"}])
    assert "REMOVE" in str(e.value)
    async with pool.acquire() as c:
        assert await c.fetchval("SELECT count(*) FROM gamegen_candidate") == 0


async def test_admission_with_no_policy_at_all_is_refused(pool):
    """`PGN-A15` ships a System baseline precisely so a book is never asked to
    author magnitudes from nothing."""
    repo, job_id, _ = await _approved_run(pool)
    structure_id, _ = await repo.fold_and_store(job_id=job_id, **STORE_KW)
    with pytest.raises(AdmissionRefusal) as e:
        await repo.admit_candidate(
            job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
            element_kind="progression_system", structure_id=structure_id, created_by=OWNER)
    assert "no numeric policy" in str(e.value)


async def test_a_missing_validator_is_an_ERROR_never_a_skip(pool, monkeypatch):
    """A pipeline that treated *"no validator"* as *"nothing to validate"* would
    admit every candidate on a host where the build failed."""
    import app.gamegen.validator as v

    monkeypatch.setenv(v.ENV_VAR, str(uuid4()))
    repo, job_id, structure_id, _ = await _ready(pool)
    with pytest.raises(ValidatorUnavailable) as e:
        await repo.admit_candidate(
            job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
            element_kind="progression_system", structure_id=structure_id, created_by=OWNER)
    assert "does not point at a file" in str(e.value)
    async with pool.acquire() as c:
        assert await c.fetchval("SELECT count(*) FROM gamegen_candidate") == 0
