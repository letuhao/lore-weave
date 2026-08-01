"""S4 — the numeric policy at rest, and the tenancy boundary it introduces.

``tests/test_gamegen_policy.py`` proves coverage, narrowing and `PGN-A16` as pure
functions. This file proves what that file cannot: **`gamegen_numeric_policy` is
the first System-tier table in this pipeline**, and CLAUDE.md's rule — *a regular
user MUST NOT mutate a System-tier row* — is enforced at the door and encoded in
the schema, not left as "the code does not do that today".

Every shape test writes raw SQL, for the reason the S2/S3 files do: the repository
is a courtesy, the schema is the rule.

Destructive-ops note: cleanup is the ``pool`` fixture's down→up migration, guarded
by this directory's ``conftest.py`` (``db-safety-gate: guarded-dir``).
"""

from __future__ import annotations

import json
from uuid import uuid4

import asyncpg
import pytest

from app.db.repositories.gamegen import GamegenS2Repo
from app.gamegen.brief import load_contract
from app.gamegen.policy import Band, PolicyError, magnitude_paths, policy_hash

from .test_gamegen_s2 import BOOK, OTHER_OWNER, OWNER

pytestmark = pytest.mark.asyncio

ADMIN = OTHER_OWNER
FP = load_contract()["fingerprint"]


def bands(**over) -> dict[str, Band]:
    b = {p: Band(0, 1000, 100) for p in magnitude_paths()}
    b.update(over)
    return b


async def _job_for(pool, owner, book):
    """`narrow_for_book` now requires local evidence that this user works on this
    book — an enrichment job. `book_id` has no FK (books live in another service),
    so the tenant boundary has to be checked rather than assumed."""
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO enrichment_job (project_id, user_id, technique, book_id) "
            "VALUES ($1,$2,'retrieval',$3)", book, owner, book)


async def _baseline(pool, version: int = 1, *, with_job_for=(OWNER, BOOK)):
    repo = GamegenS2Repo(pool)
    if with_job_for:
        await _job_for(pool, *with_job_for)
    pid = await repo.publish_system_policy(
        element_kind="progression_system", policy_version=version, bands=bands(),
        authored_by=ADMIN, is_admin=True,
    )
    return repo, pid


# ── the tenancy boundary ────────────────────────────────────────────────────


async def test_a_regular_user_cannot_publish_a_system_policy(pool):
    """CLAUDE.md › User Boundaries: *a write endpoint on a shared resource that any
    authenticated user can call is a tenancy defect, not a feature.* This is the
    only door into the System tier."""
    repo = GamegenS2Repo(pool)
    with pytest.raises(PermissionError) as e:
        await repo.publish_system_policy(
            element_kind="progression_system", policy_version=1, bands=bands(),
            authored_by=OWNER, is_admin=False,
        )
    assert "narrows it per book" in str(e.value)
    async with pool.acquire() as c:
        assert await c.fetchval("SELECT count(*) FROM gamegen_numeric_policy") == 0


async def test_is_admin_has_no_default(pool):
    """A default of ``False`` would be safe and a default of ``True``
    catastrophic — but either way a caller could forget the argument exists.
    Required means every call site has stated whose authority it acts under."""
    import inspect

    p = inspect.signature(GamegenS2Repo.publish_system_policy).parameters["is_admin"]
    assert p.default is inspect.Parameter.empty


async def test_an_admin_publishes_the_baseline(pool):
    repo, pid = await _baseline(pool)
    async with pool.acquire() as c:
        r = await c.fetchrow(
            "SELECT tier, owner_user_id, book_id, parent_policy_id, policy_hash "
            "FROM gamegen_numeric_policy WHERE policy_id=$1", pid)
    assert r["tier"] == "system"
    assert r["owner_user_id"] is None and r["book_id"] is None
    assert r["parent_policy_id"] is None, "the baseline narrows nothing"
    assert len(r["policy_hash"]) == 64


# ── PGN-A15 as a SCHEMA fact ────────────────────────────────────────────────


async def test_a_book_policy_cannot_exist_without_a_parent(pool):
    """**`PGN-A15` encoded in the schema.** You may narrow a shipped baseline; you
    may not author from scratch. Without this, a *"book policy"* is a second
    global policy with extra steps — exactly what v1 shipped by declaring no tier
    at all."""
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO gamegen_numeric_policy (element_kind, tier, policy_version, "
                "owner_user_id, book_id, schema_fingerprint, body_json, policy_hash, "
                "authored_by) VALUES ('progression_system','book',1,$1,$2,$3,'{}'::jsonb,$4,$1)",
                OWNER, BOOK, FP, "a" * 64,
            )
    assert "tier_shape" in str(e.value)


async def test_a_system_policy_cannot_carry_an_owner(pool):
    """The platform owns it; no user does. An owned System row is the shared-row-
    with-a-user-attached shape that produced the `entity_kinds` bug."""
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO gamegen_numeric_policy (element_kind, tier, policy_version, "
                "owner_user_id, schema_fingerprint, body_json, policy_hash, authored_by) "
                "VALUES ('progression_system','system',1,$1,$2,'{}'::jsonb,$3,$1)",
                OWNER, FP, "a" * 64,
            )
    assert "tier_shape" in str(e.value)


async def test_a_book_policy_needs_both_an_owner_and_a_book(pool):
    _, parent = await _baseline(pool)
    with pytest.raises(asyncpg.PostgresError) as e:
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO gamegen_numeric_policy (element_kind, tier, policy_version, "
                "owner_user_id, parent_policy_id, schema_fingerprint, body_json, "
                "policy_hash, authored_by) "
                "VALUES ('progression_system','book',1,$1,$2,$3,'{}'::jsonb,$4,$1)",
                OWNER, parent, FP, "a" * 64,
            )
    assert "tier_shape" in str(e.value)


async def test_an_unknown_tier_is_refused_by_the_database(pool):
    with pytest.raises(asyncpg.PostgresError):
        async with pool.acquire() as c:
            await c.execute(
                "INSERT INTO gamegen_numeric_policy (element_kind, tier, policy_version, "
                "schema_fingerprint, body_json, policy_hash, authored_by) "
                "VALUES ('progression_system','global',1,$1,'{}'::jsonb,$2,$3)",
                FP, "a" * 64, OWNER,
            )


async def test_one_system_baseline_per_element_and_version(pool):
    await _baseline(pool, version=1)
    with pytest.raises(asyncpg.UniqueViolationError):
        await _baseline(pool, version=1)


async def test_a_new_version_is_a_new_baseline(pool):
    repo, _ = await _baseline(pool, version=1)
    await repo.publish_system_policy(
        element_kind="progression_system", policy_version=2, bands=bands(),
        authored_by=ADMIN, is_admin=True,
    )
    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT count(*) FROM gamegen_numeric_policy WHERE tier='system'") == 2


# ── narrowing, through the database ─────────────────────────────────────────


async def test_a_book_narrows_the_published_baseline(pool):
    repo, parent = await _baseline(pool)
    child = await repo.narrow_for_book(
        parent_policy_id=parent, owner_user_id=OWNER, book_id=BOOK, policy_version=1,
        bands={"kind.tier[].tier_max": Band(200, 400, 300)}, authored_by=OWNER,
    )
    async with pool.acquire() as c:
        body = json.loads(await c.fetchval(
            "SELECT body_json FROM gamegen_numeric_policy WHERE policy_id=$1", child))
    assert body["kind.tier[].tier_max"] == {"min": 200, "max": 400, "default": 300}
    assert body["kind.initial_value"] == {"min": 0, "max": 1000, "default": 100}, "inherited"


async def test_narrowing_reads_the_parent_from_the_DATABASE(pool):
    """**Not passed in.** Narrowing must be checked against what was actually
    published, not against what the caller believes was — the self-reported-input
    class this run has now removed four times."""
    import inspect

    sig = inspect.signature(GamegenS2Repo.narrow_for_book)
    assert "parent" not in sig.parameters and "parent_policy" not in sig.parameters
    assert "parent_policy_id" in sig.parameters

    repo, parent = await _baseline(pool)
    with pytest.raises(PolicyError) as e:
        await repo.narrow_for_book(
            parent_policy_id=uuid4(), owner_user_id=OWNER, book_id=BOOK, policy_version=1,
            bands={"kind.cap_rule.cap": Band(0, 10, 5)}, authored_by=OWNER,
        )
    assert "does not exist" in str(e.value)


async def test_a_widening_book_policy_never_reaches_the_table(pool):
    repo, parent = await _baseline(pool)
    with pytest.raises(PolicyError) as e:
        await repo.narrow_for_book(
            parent_policy_id=parent, owner_user_id=OWNER, book_id=BOOK, policy_version=1,
            bands={"kind.cap_rule.cap": Band(0, 99999, 100)}, authored_by=OWNER,
        )
    assert "WIDENS" in str(e.value)
    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT count(*) FROM gamegen_numeric_policy WHERE tier='book'") == 0


async def test_a_published_parent_cannot_be_deleted_out_from_under_a_book(pool):
    """ON DELETE RESTRICT. Removing the baseline would leave a book policy whose
    narrowing is measured against nothing."""
    repo, parent = await _baseline(pool)
    await repo.narrow_for_book(
        parent_policy_id=parent, owner_user_id=OWNER, book_id=BOOK, policy_version=1,
        bands={"kind.cap_rule.cap": Band(10, 20, 15)}, authored_by=OWNER,
    )
    with pytest.raises(asyncpg.PostgresError):
        async with pool.acquire() as c:
            await c.execute("DELETE FROM gamegen_numeric_policy WHERE policy_id=$1", parent)


# ── the resolution cascade ──────────────────────────────────────────────────


async def test_a_book_with_no_narrowing_resolves_to_the_system_baseline(pool):
    """The tier cascade: System defaults, then a book's narrowing shadowing them.
    A book that never authored a policy still gets a reviewed baseline rather than
    engine defaults."""
    repo, _ = await _baseline(pool)
    eff = await repo.effective_policy(element_kind="progression_system", book_id=BOOK,
                                      owner_user_id=OWNER)
    assert eff is not None and eff.tier == "system"


async def test_a_books_narrowing_shadows_the_baseline(pool):
    repo, parent = await _baseline(pool)
    await repo.narrow_for_book(
        parent_policy_id=parent, owner_user_id=OWNER, book_id=BOOK, policy_version=1,
        bands={"kind.cap_rule.cap": Band(10, 20, 15)}, authored_by=OWNER,
    )
    eff = await repo.effective_policy(element_kind="progression_system", book_id=BOOK,
                                      owner_user_id=OWNER)
    assert eff.tier == "book"
    assert eff.bands["kind.cap_rule.cap"] == Band(10, 20, 15)


async def test_one_books_narrowing_does_not_reach_ANOTHER_book(pool):
    """The tenancy check that matters for a per-book tier sitting beside a shared
    System row: book A's balance must not become book B's."""
    repo, parent = await _baseline(pool)
    other_book = uuid4()
    await repo.narrow_for_book(
        parent_policy_id=parent, owner_user_id=OWNER, book_id=BOOK, policy_version=1,
        bands={"kind.cap_rule.cap": Band(10, 20, 15)}, authored_by=OWNER,
    )
    eff = await repo.effective_policy(element_kind="progression_system", book_id=other_book,
                                      owner_user_id=OWNER)
    assert eff.tier == "system"
    assert eff.bands["kind.cap_rule.cap"] == Band(0, 1000, 100)


async def test_the_stored_hash_is_the_one_the_module_derives(pool):
    """``policy_hash`` is DERIVED, never accepted — the same rule as
    ``answer_hash``, ``content_hash``, and the corpus seal's digest."""
    import inspect

    assert "policy_hash" not in inspect.signature(
        GamegenS2Repo.publish_system_policy).parameters

    repo, pid = await _baseline(pool)
    stored = await repo.get_policy(pid)
    async with pool.acquire() as c:
        on_disk = await c.fetchval(
            "SELECT policy_hash FROM gamegen_numeric_policy WHERE policy_id=$1", pid)
    assert on_disk == policy_hash(stored)


# ── the tenant boundary a probe found, and the ceiling that stopped being one ──


async def test_a_user_cannot_author_a_policy_for_ANOTHER_users_book(pool):
    """**PROBE 1/2 — the serious one.** `book_id` carries no foreign key (books
    live in another service's database), so nothing in this schema said the book
    was this user's. B authored a policy for A's book and it became **A's
    effective balance**: a cross-tenant write that a cross-tenant read then
    served."""
    repo, parent = await _baseline(pool)  # OWNER has a job on BOOK
    with pytest.raises(PermissionError) as e:
        await repo.narrow_for_book(
            parent_policy_id=parent, owner_user_id=OTHER_OWNER, book_id=BOOK,
            policy_version=1, bands={"kind.cap_rule.cap": Band(1, 1, 1)},
            authored_by=OTHER_OWNER,
        )
    assert "no enrichment job on book" in str(e.value)
    async with pool.acquire() as c:
        assert await c.fetchval(
            "SELECT count(*) FROM gamegen_numeric_policy WHERE tier='book'") == 0


async def test_the_effective_policy_read_is_owner_scoped(pool):
    """The read half. Even if a book row for this book existed under another
    owner, it is not this owner's effective policy."""
    repo, parent = await _baseline(pool)
    await repo.narrow_for_book(
        parent_policy_id=parent, owner_user_id=OWNER, book_id=BOOK, policy_version=1,
        bands={"kind.cap_rule.cap": Band(1, 1, 1)}, authored_by=OWNER,
    )
    mine = await repo.effective_policy(
        element_kind="progression_system", book_id=BOOK, owner_user_id=OWNER)
    theirs = await repo.effective_policy(
        element_kind="progression_system", book_id=BOOK, owner_user_id=OTHER_OWNER)
    assert mine.tier == "book" and mine.bands["kind.cap_rule.cap"] == Band(1, 1, 1)
    assert theirs.tier == "system", "another user sees the baseline, not my narrowing"


async def test_two_owners_can_hold_a_policy_for_the_same_book_id_without_colliding(pool):
    """The unique index carries ``owner_user_id``. Without it, whoever writes
    first takes the ``(book, version)`` slot and the real owner's write fails with
    a unique violation — a cross-tenant denial reachable by guessing a book id."""
    repo, parent = await _baseline(pool)
    await _job_for(pool, OTHER_OWNER, BOOK)
    await repo.narrow_for_book(
        parent_policy_id=parent, owner_user_id=OTHER_OWNER, book_id=BOOK,
        policy_version=1, bands={"kind.cap_rule.cap": Band(1, 1, 1)},
        authored_by=OTHER_OWNER,
    )
    await repo.narrow_for_book(
        parent_policy_id=parent, owner_user_id=OWNER, book_id=BOOK, policy_version=1,
        bands={"kind.cap_rule.cap": Band(900, 950, 920)}, authored_by=OWNER,
    )
    eff = await repo.effective_policy(
        element_kind="progression_system", book_id=BOOK, owner_user_id=OWNER)
    assert eff.bands["kind.cap_rule.cap"] == Band(900, 950, 920)


async def test_a_TIGHTENED_baseline_refuses_a_stale_book_narrowing(pool):
    """**PROBE 3.** ``effective = AND(deploy_allows, user_enables)`` is not an AND
    if it is evaluated once at write time and cached. A narrowing authored against
    v1 can fall outside a v2 baseline the admin published later, and the
    write-time check passed long ago."""
    repo, parent = await _baseline(pool, version=1)
    await repo.narrow_for_book(
        parent_policy_id=parent, owner_user_id=OWNER, book_id=BOOK, policy_version=1,
        bands={"kind.cap_rule.cap": Band(1, 10, 5)}, authored_by=OWNER,
    )
    await repo.publish_system_policy(
        element_kind="progression_system", policy_version=2,
        bands=bands(**{"kind.cap_rule.cap": Band(500, 600, 550)}),
        authored_by=ADMIN, is_admin=True,
    )
    with pytest.raises(PolicyError) as e:
        await repo.effective_policy(
            element_kind="progression_system", book_id=BOOK, owner_user_id=OWNER)
    assert "no longer fits the current System baseline" in str(e.value)
    assert "kind.cap_rule.cap" in str(e.value)
    assert "re-narrow" in str(e.value)


async def test_a_still_contained_narrowing_survives_a_baseline_change(pool):
    """The re-check must not fire on a baseline that moved compatibly, or the
    first admin publish turns every book policy into an outage and the check gets
    removed."""
    repo, parent = await _baseline(pool, version=1)
    await repo.narrow_for_book(
        parent_policy_id=parent, owner_user_id=OWNER, book_id=BOOK, policy_version=1,
        bands={"kind.cap_rule.cap": Band(500, 550, 520)}, authored_by=OWNER,
    )
    await repo.publish_system_policy(
        element_kind="progression_system", policy_version=2,
        bands=bands(**{"kind.cap_rule.cap": Band(400, 700, 550)}),
        authored_by=ADMIN, is_admin=True,
    )
    eff = await repo.effective_policy(
        element_kind="progression_system", book_id=BOOK, owner_user_id=OWNER)
    assert eff.tier == "book" and eff.bands["kind.cap_rule.cap"] == Band(500, 550, 520)


async def test_the_containment_rule_has_ONE_implementation(pool):
    """Write-time and read-time both call ``containment_violations``. Two copies
    of a containment rule are two chances to disagree about what `PGN-A15` means,
    and the read-time half is the one nobody would have written twice."""
    import inspect

    from app.db.repositories import gamegen as repo_mod
    from app.gamegen import policy as policy_mod

    assert "containment_violations" in inspect.getsource(policy_mod.narrow)
    assert "containment_violations" in inspect.getsource(
        repo_mod.GamegenS2Repo.effective_policy)
