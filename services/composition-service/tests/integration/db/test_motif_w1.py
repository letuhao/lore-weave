"""W1 — MotifRepo adopt/catalog/quota DB tests (real Postgres).

The router test (tests/unit/test_motif_router.py) proves the HTTP layer with a
stub repo; THIS file proves the W1 repo methods against a real DB — the SQL-level
audit guards that a stub cannot:
  - adopt: per-owner advisory lock, deterministic code suffix on collision,
    idempotent re-adopt (same source → same clone, no duplicate), the B-3 lineage
    taint + publish-strip on an adopted-from-imported publish (H-7 + B-3);
  - catalog: visibility/status filter + the EXPLICIT allow-list (no embedding /
    examples / raw source_ref ever in a row — B-3);
  - quotas: the count helpers feeding the N+1 ceilings (B-4);
  - pattern adopt: the composed_of subgraph clone re-points edges at the caller's
    OWN copies (H-3).

Gated on TEST_COMPOSITION_DB_URL; the fixture drops the motif tables on
setup/teardown (mirrors test_motif_repo.py).
"""

from __future__ import annotations

import asyncio
import json
import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.models import MotifCreateArgs
from app.db.repositories.motif_repo import MotifRepo

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # MANDATORY (CLAUDE.md test-parallelization): this file DROPs/re-migrates tables on the
    # shared dev PG. Without the group, xdist schedules it on a DIFFERENT worker than the
    # other real-DB files and they drop each other's tables mid-run — the counts then lie.
    pytest.mark.xdist_group("pg"),
]

_MOTIF_TABLES = [
    "consumed_tokens", "motif_application", "motif_link",
    "import_source", "arc_template", "motif",
]


@pytest.fixture
async def repo():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=6)

    async def _drop():
        async with p.acquire() as c:
            for t in _MOTIF_TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")

    try:
        await _drop()
        await run_migrations(p)
        yield MotifRepo(p), p
    finally:
        await _drop()
        await p.close()


def _args(**kw) -> MotifCreateArgs:
    base = dict(code="cult.fortuitous", name="Lucky Break")
    base.update(kw)
    return MotifCreateArgs(**base)


# ── adopt: idempotency + suffix + advisory lock (H-7) ─────────────────────────


async def test_adopt_resets_identity_and_copies(repo):
    r, pool = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    src = await r.create(u2, _args(code="s", visibility="public", genre_tags=["xianxia"]))
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE motif SET embedding=$2, embedding_model='plat', embedding_dim=3, "
            "embedded_summary_hash='h1' WHERE id=$1", src.id, [0.1, 0.2, 0.3])
    adopted, created = await r.adopt(u1, src.id, retag_genres=["wuxia"])
    assert created is True
    assert adopted.id != src.id
    assert adopted.owner_user_id == u1
    assert adopted.visibility == "private"
    assert adopted.source == "adopted"
    assert adopted.source_ref == f"lineage:{src.id}"
    assert adopted.source_version == src.version
    assert adopted.version == 1
    assert adopted.genre_tags == ["wuxia"]
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT embedding, embedded_summary_hash, embedding_model FROM motif WHERE id=$1",
            adopted.id)
    assert [round(x, 3) for x in row["embedding"]] == [0.1, 0.2, 0.3]
    assert row["embedded_summary_hash"] == "h1"          # copied, no re-embed (B-1)
    assert row["embedding_model"] == "plat"


async def test_adopt_idempotent_same_source(repo):
    r, _ = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    src = await r.create(u2, _args(code="s", visibility="public"))
    first, c1 = await r.adopt(u1, src.id)
    second, c2 = await r.adopt(u1, src.id)
    assert c1 is True and c2 is False
    assert first.id == second.id                         # same clone, no duplicate


async def test_adopt_own_motif_suffixes_code(repo):
    r, _ = repo
    u1 = uuid.uuid4()
    # adopting your OWN public motif collides on (owner, code, lang) → suffix.
    src = await r.create(u1, _args(code="own", visibility="public"))
    adopted, created = await r.adopt(u1, src.id)
    assert created is True
    assert adopted.code == "own-2"                        # deterministic suffix
    assert adopted.source == "adopted"
    # adopting a DIFFERENT visible source whose base code is free in this tier
    # keeps the base code (suffix only fires on a real collision).
    other_owner = uuid.uuid4()
    src2 = await r.create(other_owner, _args(code="fresh", visibility="public"))
    a2, _ = await r.adopt(u1, src2.id)
    assert a2.code == "fresh"                             # no collision → base code


async def test_adopt_not_visible_raises(repo):
    r, _ = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    src = await r.create(u2, _args(code="hidden", visibility="private"))
    with pytest.raises(LookupError):
        await r.adopt(u1, src.id)


async def test_adopt_concurrent_same_user_one_row(repo):
    """The owner-keyed advisory lock (NOT hash(NULL)): two concurrent adopts by
    the SAME user of the same source yield exactly ONE clone (the second waits,
    re-reads the idempotent existing row). Different users → two rows, no block."""
    r, pool = repo
    u1, u2, owner = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    src = await r.create(owner, _args(code="s", visibility="public"))
    # same user, concurrent → one row.
    res = await asyncio.gather(r.adopt(u1, src.id), r.adopt(u1, src.id))
    ids = {m.id for m, _ in res}
    assert len(ids) == 1
    async with pool.acquire() as c:
        n = await c.fetchval(
            "SELECT count(*) FROM motif WHERE owner_user_id=$1 AND source='adopted'", u1)
    assert n == 1
    # different users, concurrent → two rows, no cross-block.
    res2 = await asyncio.gather(r.adopt(u1, src.id), r.adopt(u2, src.id))
    owners = {m.owner_user_id for m, _ in res2}
    assert owners == {u1, u2}


# ── B-3 publish-strip on an adopted-from-imported clone ───────────────────────


async def _seed_imported(pool, owner, *, code, examples):
    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO motif (owner_user_id, code, visibility, source, name, examples) "
            "VALUES ($1,$2,'private','imported','Imported',$3::jsonb) RETURNING id",
            owner, code, json.dumps(examples))


async def test_adopt_of_imported_strips_examples_on_publish(repo):
    r, pool = repo
    u1 = uuid.uuid4()
    # an import_source-derived motif is per-user + private (un-shareable raw). The
    # owner adopts its OWN imported motif (visible because owner) → the adopt
    # suffixes the code on the self-collision; the lineage taint propagates so
    # publishing the adopted copy strips the copied source prose (B-3).
    src = await _seed_imported(pool, u1, code="imp", examples=[{"text": "stolen"}])
    adopted, _ = await r.adopt(u1, src)
    assert adopted.imported_derived is True
    assert adopted.code == "imp-2"                        # self-collision suffix
    assert adopted.examples == [{"text": "stolen"}]      # kept while private
    # publish via the repo patch path (the trigger fires on the visibility flip).
    from app.db.models import MotifPatchArgs
    await r.patch(u1, adopted.id, MotifPatchArgs(visibility="public"), expected_version=1)
    after = await r.get_visible(u1, adopted.id)
    assert after.examples == []                          # B-3 strip fired
    assert after.source_ref.startswith("lineage:")


async def test_adopt_of_authored_keeps_examples_on_publish(repo):
    r, pool = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    src = await r.create(u1, _args(code="auth", visibility="public",
                                   examples=[{"text": "mine"}]))
    adopted, _ = await r.adopt(u2, src.id)
    assert adopted.imported_derived is False
    from app.db.models import MotifPatchArgs
    await r.patch(u2, adopted.id, MotifPatchArgs(visibility="public"), expected_version=1)
    after = await r.get_visible(u2, adopted.id)
    assert after.examples == [{"text": "mine"}]          # not over-broad


# ── catalog allow-list no-leak (B-3) ──────────────────────────────────────────


async def test_catalog_only_public_active(repo):
    r, pool = repo
    owner = uuid.uuid4()
    pub = await r.create(owner, _args(code="pub", visibility="public"))
    await r.create(owner, _args(code="unl", visibility="unlisted"))
    await r.create(owner, _args(code="priv", visibility="private"))
    arch = await r.create(owner, _args(code="arch", visibility="public"))
    async with pool.acquire() as c:
        await c.execute("UPDATE motif SET status='archived' WHERE id=$1", arch.id)
        # a SYSTEM public row (owner NULL) must also surface in the catalog.
        await c.execute(
            "INSERT INTO motif (owner_user_id, code, visibility, name) "
            "VALUES (NULL,'sys','public','Sys')")
    rows, total = await r.list_public()
    codes = {row["code"] for row in rows}
    assert "pub" in codes
    assert "sys" in codes                                # system-public is discoverable
    assert "unl" not in codes                            # unlisted is link-only
    assert "priv" not in codes
    assert "arch" not in codes                           # archived excluded
    assert total == len(rows)
    assert total == 2


async def test_catalog_row_has_no_leak_fields(repo):
    r, pool = repo
    owner = uuid.uuid4()
    m = await r.create(owner, _args(code="c", visibility="public",
                                    examples=[{"text": "secret"}]))
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE motif SET embedding=$2, source_ref='import:rawid' WHERE id=$1",
            m.id, [0.5, 0.5])
    rows, _ = await r.list_public()
    row = rows[0]
    # the three never-leak fields are structurally absent from the allow-list.
    assert "embedding" not in row
    assert "examples" not in row
    assert "source_ref" not in row
    # AND the roles/beats/preconditions/effects are absent from the light list.
    for heavy in ("roles", "beats", "preconditions", "effects", "owner_user_id"):
        assert heavy not in row


async def test_catalog_filters_and_pagination(repo):
    r, _ = repo
    owner = uuid.uuid4()
    for i in range(5):
        await r.create(owner, _args(code=f"x{i}", name=f"M{i}", visibility="public",
                                    genre_tags=["xianxia"] if i % 2 == 0 else ["wuxia"]))
    xianxia, total = await r.list_public(genre="xianxia")
    assert total == 3 and all("x" in row["code"] for row in xianxia)
    page1, t1 = await r.list_public(limit=2, offset=0, sort="name")
    page2, _ = await r.list_public(limit=2, offset=2, sort="name")
    assert t1 == 5 and len(page1) == 2
    assert {row["id"] for row in page1}.isdisjoint({row["id"] for row in page2})


# ── quota count helpers (B-4) ─────────────────────────────────────────────────


async def test_count_shared_and_adopted(repo):
    r, pool = repo
    owner, src_owner = uuid.uuid4(), uuid.uuid4()
    await r.create(owner, _args(code="a", visibility="public"))
    await r.create(owner, _args(code="b", visibility="unlisted"))
    await r.create(owner, _args(code="c", visibility="private"))
    arch = await r.create(owner, _args(code="d", visibility="public"))
    async with pool.acquire() as c:
        await c.execute("UPDATE motif SET status='archived' WHERE id=$1", arch.id)
    assert await r.count_shared_by_owner(owner) == 2     # public+unlisted, archived excluded

    pub_src = await r.create(src_owner, _args(code="s1", visibility="public"))
    pub_src2 = await r.create(src_owner, _args(code="s2", visibility="public"))
    await r.adopt(owner, pub_src.id)
    await r.adopt(owner, pub_src2.id)
    assert await r.count_adopted_by_owner(owner) == 2


# ── pattern subgraph adopt (H-3) ──────────────────────────────────────────────


async def test_adopt_pattern_clones_members_and_repoints_edges(repo):
    r, pool = repo
    sys_owner, caller = None, uuid.uuid4()
    # seed a SYSTEM pattern with two composed_of members (system tier, public).
    async with pool.acquire() as c:
        root = await c.fetchval(
            "INSERT INTO motif (owner_user_id, code, visibility, kind, name) "
            "VALUES (NULL,'pat','public','pattern','Pattern') RETURNING id")
        m1 = await c.fetchval(
            "INSERT INTO motif (owner_user_id, code, visibility, name) "
            "VALUES (NULL,'mem1','public','Member 1') RETURNING id")
        m2 = await c.fetchval(
            "INSERT INTO motif (owner_user_id, code, visibility, name) "
            "VALUES (NULL,'mem2','public','Member 2') RETURNING id")
        await c.execute(
            "INSERT INTO motif_link (from_motif_id, to_motif_id, kind, ord) "
            "VALUES ($1,$2,'composed_of',0),($1,$3,'composed_of',1)", root, m1, m2)

    adopted_root, created = await r.adopt(caller, root)
    assert created and adopted_root.kind == "pattern"
    n = await r.adopt_pattern_members(caller, root, adopted_root.id)
    assert n == 2
    async with pool.acquire() as c:
        # the caller now owns the two members, and the edges point at HIS copies.
        member_owners = await c.fetch(
            "SELECT m.owner_user_id FROM motif_link ml JOIN motif m ON m.id = ml.to_motif_id "
            "WHERE ml.from_motif_id = $1 AND ml.kind = 'composed_of'", adopted_root.id)
        assert len(member_owners) == 2
        assert all(row["owner_user_id"] == caller for row in member_owners)
        # the F0 same-tier guard would have REJECTED an edge to a system member —
        # so the fact these inserted proves the re-point is correct (H-3).
    # idempotent: re-running re-uses the members + edges, no duplication.
    n2 = await r.adopt_pattern_members(caller, root, adopted_root.id)
    assert n2 == 2
    async with pool.acquire() as c:
        total_members = await c.fetchval(
            "SELECT count(*) FROM motif WHERE owner_user_id=$1 AND source='adopted' "
            "AND code IN ('mem1','mem2')", caller)
    assert total_members == 2                             # not duplicated
