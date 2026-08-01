"""S6 — the pin. **POC-1's chain, closed.**

approved answers → fold → policy → generate → the engine validates → a human
approves → the engine PINS → the ruleset digest moves.

Nothing here is mocked. The artifact goes to `progression-pin`, which resolves it
into a real content-addressed store and reports the ruleset digest it produced.
A mocked pin would prove the plumbing and say nothing about whether bytes landed
— and *bytes landed* is the entire claim.

Destructive-ops note: cleanup is the ``pool`` fixture's down→up migration, guarded
by this directory's ``conftest.py`` (``db-safety-gate: guarded-dir``). The
ruleset store is a per-test temp directory, never a shared one.
"""

from __future__ import annotations

import pytest

from app.db.repositories.gamegen import GamegenS2Repo
from app.gamegen.generate import AdmissionRefusal
from app.gamegen.pinner import STORE_ENV, PinnerUnavailable, pinner_path

from .test_gamegen_s2 import BOOK, OTHER_OWNER, OWNER
from .test_gamegen_s5 import _ready

pytestmark = pytest.mark.asyncio


@pytest.fixture
def store(tmp_path, monkeypatch):
    """A fresh content-addressed store per test. Never shared: two tests pinning
    the same digest into one store would make the second a no-op and the
    assertions would pass for the wrong reason."""
    try:
        pinner_path()
    except PinnerUnavailable as e:
        pytest.skip(str(e))
    root = tmp_path / "ruleset-store"
    monkeypatch.setenv(STORE_ENV, str(root))
    return root


async def _approved(pool, repo=None):
    """A candidate that has passed the engine AND a human."""
    repo, job_id, structure_id, _ = await _ready(pool)
    cid = await repo.admit_candidate(
        job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        element_kind="progression_system", structure_id=structure_id, created_by=OWNER)
    assert await repo.approve_candidate(
        candidate_id=cid, owner_user_id=OWNER, approved_by=OWNER)
    return repo, cid


# ── POC-1's exit criterion ──────────────────────────────────────────────────


async def test_an_approved_candidate_PINS_and_the_ruleset_digest_moves(pool, store):
    """**The chain, closed.** Not *"a table appeared in a directory"* — the claim
    is that the RULESET digest moves, so the pin has to report one."""
    repo, cid = await _approved(pool)
    ruleset_digest = await repo.pin_candidate(
        candidate_id=cid, owner_user_id=OWNER, pinned_by=OWNER)

    assert len(ruleset_digest) == 64
    files = {p.name for p in store.iterdir()}
    assert any(f.endswith(".prog") for f in files), files
    assert any(f.endswith(".labels.toml") for f in files), files
    assert any(f.endswith(".canon") for f in files), f"the ruleset landed: {files}"

    async with pool.acquire() as c:
        r = await c.fetchrow(
            "SELECT pinned_at, pinned_by, ruleset_digest, progression_digest "
            "FROM gamegen_candidate WHERE candidate_id=$1", cid)
    assert r["pinned_at"] is not None and r["pinned_by"] == OWNER
    assert r["ruleset_digest"] == ruleset_digest
    # The progression table is filed under the digest S5 approved.
    assert f"{r['progression_digest']}.prog" in files


async def test_the_artifact_is_REGENERATED_and_the_digest_still_matches(pool, store):
    """S3 and S5 are deterministic, so regeneration must produce the same bytes —
    and ``--expect`` is what turns *must* into *checked*. Storing the TOML and
    replaying it would remove the only place that claim meets reality.

    This passing IS the determinism evidence: the pin would refuse on any drift.
    """
    repo, cid = await _approved(pool)
    await repo.pin_candidate(candidate_id=cid, owner_user_id=OWNER, pinned_by=OWNER)


# ── the chain's last link ───────────────────────────────────────────────────


async def test_an_UNAPPROVED_candidate_cannot_be_pinned(pool, store):
    """`pinned => approved => admitted => the engine ran`. Skipping the middle
    link is how content nobody signed for reaches a reality."""
    repo, job_id, structure_id, _ = await _ready(pool)
    cid = await repo.admit_candidate(
        job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        element_kind="progression_system", structure_id=structure_id, created_by=OWNER)
    with pytest.raises(AdmissionRefusal) as e:
        await repo.pin_candidate(candidate_id=cid, owner_user_id=OWNER, pinned_by=OWNER)
    assert "Only an APPROVED candidate may be pinned" in str(e.value)
    assert not list(store.iterdir()) if store.exists() else True


async def test_the_pin_columns_are_refused_by_the_database_without_approval(pool, store):
    """The CHECK, not just the method. Two constraints make the chain hold end to
    end rather than by the order the code happens to call things in."""
    import asyncpg

    repo, job_id, structure_id, _ = await _ready(pool)
    cid = await repo.admit_candidate(
        job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        element_kind="progression_system", structure_id=structure_id, created_by=OWNER)
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            await c.execute(
                "UPDATE gamegen_candidate SET pinned_at=now(), pinned_by=$2, "
                "ruleset_digest=$3 WHERE candidate_id=$1", cid, OWNER, "a" * 64)
    assert "pin_coherent" in str(e.value)


async def test_pinning_twice_is_refused(pool, store):
    """The store is content-addressed so the write would be a no-op — but a second
    pin record would make *"when did this reach the world"* a question with two
    answers."""
    repo, cid = await _approved(pool)
    await repo.pin_candidate(candidate_id=cid, owner_user_id=OWNER, pinned_by=OWNER)
    with pytest.raises(AdmissionRefusal) as e:
        await repo.pin_candidate(candidate_id=cid, owner_user_id=OWNER, pinned_by=OWNER)
    assert "already pinned" in str(e.value)


async def test_a_cross_tenant_caller_cannot_pin(pool, store):
    repo, cid = await _approved(pool)
    with pytest.raises(AdmissionRefusal) as e:
        await repo.pin_candidate(
            candidate_id=cid, owner_user_id=OTHER_OWNER, pinned_by=OTHER_OWNER)
    assert "not visible" in str(e.value)


# ── the seam refuses rather than pretending ─────────────────────────────────


async def test_a_missing_store_root_is_an_ERROR_never_a_default(pool, monkeypatch):
    """A pin that succeeds and vanishes leaves every hop upstream green and a
    reality that cannot resolve its own table. That is the worst failure available
    here, so the temp-dir fallback does not exist."""
    try:
        pinner_path()
    except PinnerUnavailable as e:
        pytest.skip(str(e))
    monkeypatch.delenv(STORE_ENV, raising=False)
    repo, cid = await _approved(pool)
    with pytest.raises(PinnerUnavailable) as e:
        await repo.pin_candidate(candidate_id=cid, owner_user_id=OWNER, pinned_by=OWNER)
    assert "succeeds and vanishes" in str(e.value)

    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT pinned_at FROM gamegen_candidate WHERE candidate_id=$1", cid) is None


# ── pin what was APPROVED, inputs included ──────────────────────────────────


async def test_a_policy_that_MOVED_since_approval_refuses_the_pin(pool, store):
    """**Found by probe, and the silent case is the point.**

    `pin_candidate` regenerates, and it was regenerating with the *current*
    effective policy. `--expect` only notices when the bytes differ — so narrowing
    a band the artifact never reads (`kind.curve.rate_milli` on a `stage` curve)
    moved `policy_hash` and **not** the generated TOML, and the pin succeeded:

    ``approved under a3872516a7d1… ; in force now 77adcc430867…``

    The candidate then recorded one policy while the numbers came from another.
    T2 is *"I can tell where a number came from"*, and the recorded answer was
    wrong. The digest check is about the OUTPUT; this is about the INPUTS, and
    neither implies the other.
    """
    from app.gamegen.policy import Band

    repo, job_id, structure_id, parent = await _ready(pool)
    cid = await repo.admit_candidate(
        job_id=job_id, owner_user_id=OWNER, book_id=BOOK,
        element_kind="progression_system", structure_id=structure_id, created_by=OWNER)
    assert await repo.approve_candidate(
        candidate_id=cid, owner_user_id=OWNER, approved_by=OWNER)

    # A band the artifact never reads: same bytes, different policy.
    await repo.narrow_for_book(
        parent_policy_id=parent, owner_user_id=OWNER, book_id=BOOK, policy_version=1,
        bands={"kind.curve.rate_milli": Band(1, 2, 1)}, authored_by=OWNER)

    with pytest.raises(AdmissionRefusal) as e:
        await repo.pin_candidate(candidate_id=cid, owner_user_id=OWNER, pinned_by=OWNER)
    assert "policy has MOVED" in str(e.value)
    assert "nobody signed for even when the bytes happen to match" in str(e.value)

    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT pinned_at FROM gamegen_candidate WHERE candidate_id=$1", cid) is None


async def test_an_unchanged_policy_still_pins(pool, store):
    """The guard must not fire on the normal path, or it gets removed the first
    time a legitimate pin trips it."""
    repo, cid = await _approved(pool)
    assert await repo.pin_candidate(
        candidate_id=cid, owner_user_id=OWNER, pinned_by=OWNER)


async def test_a_policy_DELETED_before_the_pin_is_a_refusal_not_a_crash(pool, store):
    """`admit_candidate` guarded this; `pin_candidate` did not, and the result was
    a bare ``AttributeError: 'NoneType' object has no attribute 'bands'`` — a crash
    where a refusal belongs."""
    repo, cid = await _approved(pool)
    async with pool.acquire() as c:
        await c.execute("DELETE FROM gamegen_numeric_policy WHERE tier='system'")
    with pytest.raises(AdmissionRefusal) as e:
        await repo.pin_candidate(candidate_id=cid, owner_user_id=OWNER, pinned_by=OWNER)
    assert "no longer exists" in str(e.value)
    assert "invent every magnitude" in str(e.value)
