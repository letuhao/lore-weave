"""F0 — MotifRepo behavior tests (real Postgres).

The migration test (test_motif_migrate.py) proves the SCHEMA + the read predicate
via direct SQL. THIS file proves the repo WRITE methods — create/patch/archive and
the load-bearing clone primitive (W1/W3 depend on clone being real). Gated on
TEST_COMPOSITION_DB_URL; the fixture drops the motif tables on setup/teardown.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.models import InfoAsymmetry, MotifBeat, MotifCreateArgs, MotifPatchArgs, MotifRole
from app.db.repositories import VersionMismatchError
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
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)

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
    base = dict(code="cultivation.fortuitous_encounter", name="Lucky Break")
    base.update(kw)
    return MotifCreateArgs(**base)


async def test_create_stamps_owner_and_roundtrips_jsonb(repo):
    r, _ = repo
    u = uuid.uuid4()
    m = await r.create(
        u,
        _args(
            roles=[MotifRole(key="hero", actant="subject", label="Protagonist")],
            beats=[MotifBeat(key="b1", label="Discovery", tension_target=3, order=1)],
            info_asymmetry=InfoAsymmetry(knows=["hero"], deceived=["rival"], gap="the map"),
            annotations={"scheme": "info_gap"},
            genre_tags=["xianxia"],
            tension_target=4,
        ),
    )
    assert m.owner_user_id == u           # STAMPED, never an arg
    assert m.visibility == "private"      # default
    assert m.source == "authored"
    assert m.version == 1
    assert m.roles[0]["actant"] == "subject"
    assert m.beats[0]["tension_target"] == 3
    assert m.info_asymmetry["gap"] == "the map"
    assert m.annotations == {"scheme": "info_gap"}   # RECONCILE D1
    # embedding starts NULL (W3 fills it) — never projected, so verify via SQL.
    _, pool = repo
    async with pool.acquire() as c:
        emb = await c.fetchval("SELECT embedding FROM motif WHERE id = $1", m.id)
    assert emb is None


async def test_create_mined_and_imported_columns_roundtrip(repo):
    """D-WAVE2-DB-ROUNDTRIP-TEST — the serially-edited create() (W9 source/imported_derived/
    status + W8 judge_score/mining_support) writes each additive column to the RIGHT place.
    The unit tests use fakes that never hit the real 23-col INSERT, so a placeholder/column
    misalignment ships green; this round-trips against real Postgres."""
    from decimal import Decimal

    r, pool = repo
    u = uuid.uuid4()

    mined = await r.create(
        u, _args(code="mined.shape"), source="mined", status="draft",
        judge_score=Decimal("0.875"), mining_support=3,
    )
    assert mined.source == "mined" and mined.status == "draft"
    assert mined.imported_derived is False
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT source, status, judge_score, mining_support, imported_derived "
            "FROM motif WHERE id=$1", mined.id)
    assert row["source"] == "mined" and row["status"] == "draft"
    assert float(row["judge_score"]) == 0.875   # judge_score → judge_score, not mining_support
    assert row["mining_support"] == 3
    assert row["imported_derived"] is False

    imported = await r.create(
        u, _args(code="imported.shape"), source="imported", imported_derived=True, status="draft")
    assert imported.source == "imported" and imported.imported_derived is True

    # an authored create leaves the mined columns NULL (the default path is unchanged).
    auth = await r.create(u, _args(code="authored.shape"))
    async with pool.acquire() as c:
        arow = await c.fetchrow(
            "SELECT source, judge_score, mining_support, imported_derived FROM motif WHERE id=$1",
            auth.id)
    assert arow["source"] == "authored"
    assert arow["judge_score"] is None and arow["mining_support"] is None
    assert arow["imported_derived"] is False


async def test_clone_captures_adopted_base_snapshot(repo):
    """D-MOTIF-SYNC-3WAY-BASE: clone snapshots the source's mergeable fields into
    adopted_base (the true 3-way merge base) — verified against real Postgres incl. the
    additive ALTER for the column."""
    import json

    from app.db.models import MotifBeat, MotifRole

    r, pool = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    src = await r.create(
        u2, _args(code="src", visibility="public", summary="upstream summary",
                  genre_tags=["xianxia"],
                  roles=[MotifRole(key="hero", actant="subject", label="Hero")],
                  beats=[MotifBeat(key="b1", label="Discovery", order=1)]))
    clone = await r.clone(u1, src.id, target_owner=u1)
    async with pool.acquire() as c:
        raw = await c.fetchval("SELECT adopted_base FROM motif WHERE id=$1", clone.id)
    base = json.loads(raw) if isinstance(raw, str) else raw
    assert base["summary"] == "upstream summary"
    assert base["genre_tags"] == ["xianxia"]
    assert base["roles"][0]["key"] == "hero"
    assert base["beats"][0]["label"] == "Discovery"
    # a non-adopted (created, not cloned) motif has no base.
    async with pool.acquire() as c:
        nb = await c.fetchval("SELECT adopted_base FROM motif WHERE id=$1", src.id)
    assert nb is None


async def test_create_unique_per_owner_code_language(repo):
    r, _ = repo
    u = uuid.uuid4()
    await r.create(u, _args(code="dup", language="en"))
    with pytest.raises(asyncpg.UniqueViolationError):
        await r.create(u, _args(code="dup", language="en"))
    # N-1: same code, different language → OK (language is in the dedup key).
    await r.create(u, _args(code="dup", language="vi"))


async def test_create_then_idor_visibility(repo):
    r, _ = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    priv = await r.create(u2, _args(code="p", visibility="private"))
    unlisted = await r.create(u2, _args(code="u", visibility="unlisted"))
    pub = await r.create(u2, _args(code="pub", visibility="public"))
    # U1 cannot see U2's private OR unlisted motif (predicate = system|public|owner).
    assert await r.get_visible(u1, priv.id) is None
    assert await r.get_visible(u1, unlisted.id) is None      # finding #4
    assert (await r.get_visible(u1, pub.id)) is not None     # public is visible
    listed = {m.id for m in await r.list_for_caller(u1)}
    assert priv.id not in listed and unlisted.id not in listed
    assert pub.id in listed


async def test_patch_version_owner_and_summary_hash(repo):
    r, pool = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    m = await r.create(u1, _args(code="e", summary="old"))
    # seed a fake embedding hash so we can prove a summary edit clears it.
    async with pool.acquire() as c:
        await c.execute("UPDATE motif SET embedded_summary_hash = 'abc' WHERE id = $1", m.id)

    updated = await r.patch(u1, m.id, MotifPatchArgs(summary="new"), expected_version=1)
    assert updated is not None and updated.version == 2 and updated.summary == "new"
    async with pool.acquire() as c:
        h = await c.fetchval("SELECT embedded_summary_hash FROM motif WHERE id = $1", m.id)
    assert h is None  # summary changed → re-embed staleness flag cleared

    # stale version → VersionMismatchError carrying current.
    with pytest.raises(VersionMismatchError) as ei:
        await r.patch(u1, m.id, MotifPatchArgs(name="x"), expected_version=1)
    assert ei.value.current.version == 2

    # a foreign caller cannot patch → None (no oracle), and the row is unchanged.
    assert await r.patch(u2, m.id, MotifPatchArgs(name="hax"), expected_version=2) is None
    assert (await r.get_visible(u1, m.id)).name == "Lucky Break"


async def test_archive_owner_only(repo):
    r, _ = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    m = await r.create(u1, _args(code="a"))
    await r.archive(u2, m.id)                       # foreign → no-op
    assert (await r.get_visible(u1, m.id)).status == "active"
    await r.archive(u1, m.id)                       # owner → archived
    assert (await r.get_visible(u1, m.id)).status == "archived"


async def test_restore_owner_roundtrip_preserves_id_and_version(repo):
    # S-08: archive→restore is a lossless round-trip (id + version survive — the whole point of
    # soft-delete), owner-scoped, and idempotent-guarded (a non-archived row is a no-op → None).
    r, _ = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    m = await r.create(u1, _args(code="r"))
    assert m.version == 1
    await r.archive(u1, m.id)
    assert (await r.get_visible(u1, m.id)).status == "archived"

    assert await r.restore(u2, m.id) is None                     # foreign → None (no oracle)
    assert (await r.get_visible(u1, m.id)).status == "archived"  # still archived

    restored = await r.restore(u1, m.id)                          # owner → active
    assert restored is not None
    assert restored.id == m.id and restored.status == "active"
    assert restored.version == 1                                  # restore must NOT bump version

    assert await r.restore(u1, m.id) is None                      # already active → None


async def test_restore_shared_book_tier(repo):
    # The SHARED tier mirrors archive_shared: keyed on book_shared AND book_id, any EDIT-grantee.
    r, pool = repo
    owner, grantee = uuid.uuid4(), uuid.uuid4()
    book = uuid.uuid4()
    m = await r.create(owner, _args(code="rs"))
    async with pool.acquire() as c:  # promote to the shared book tier (what adopt target='book_shared' does)
        await c.execute("UPDATE motif SET book_shared = true, book_id = $2 WHERE id = $1", m.id, book)
    await r.archive_shared(grantee, m.id, book)
    assert (await r.get_visible(owner, m.id)).status == "archived"

    assert await r.restore_shared(grantee, m.id, uuid.uuid4()) is None   # wrong book → None
    restored = await r.restore_shared(grantee, m.id, book)               # right book → active
    assert restored is not None and restored.status == "active" and restored.id == m.id


async def test_clone_copies_fields_vector_and_lineage(repo):
    r, pool = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    src = await r.create(
        u2,
        _args(code="s", visibility="public", genre_tags=["xianxia"],
              beats=[MotifBeat(key="b", label="L", order=1)]),
    )
    # give the source a real vector + fresh hash (the W3 state clone must copy).
    async with pool.acquire() as c:
        await c.execute(
            "UPDATE motif SET embedding = $2, embedding_model = 'plat', embedding_dim = 3, "
            "embedded_summary_hash = 'h1' WHERE id = $1",
            src.id, [0.1, 0.2, 0.3],
        )

    cloned = await r.clone(u1, src.id, target_owner=u1, retag_genres=["wuxia"])
    assert cloned.id != src.id
    assert cloned.owner_user_id == u1
    assert cloned.visibility == "private"           # a clone is private until republished
    assert cloned.source == "adopted"
    assert cloned.source_ref == f"lineage:{src.id}"
    assert cloned.source_version == src.version
    assert cloned.version == 1
    assert cloned.genre_tags == ["wuxia"]           # cross-genre retag (R2.2)
    assert cloned.beats[0]["key"] == "b"            # JSONB carried over
    # the vector AND the fresh hash are COPIED (no redundant re-embed — finding #2).
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT embedding, embedded_summary_hash FROM motif WHERE id = $1", cloned.id
        )
    assert [round(x, 3) for x in row["embedding"]] == [0.1, 0.2, 0.3]
    assert row["embedded_summary_hash"] == "h1"


async def test_list_for_caller_every_scope(repo):
    """R-NODE-P1 regression: list_for_caller must work for EVERY scope, not just the
    default 'all'. 'system'/'public' don't reference caller_id ($1) — binding it unused
    made asyncpg raise IndeterminateDatatypeError (a live 500 on GET /motifs?scope=system).
    Also exercises a genre filter under each scope (the param-numbering shift)."""
    r, pool = repo
    u1 = uuid.uuid4()
    # a system motif (owner NULL, unlisted — the seed path), a public user motif, and
    # the caller's own private motif.
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO motif (owner_user_id, code, visibility, name, genre_tags) "
            "VALUES (NULL,'sys.m','unlisted','Sys', ARRAY['xianxia'])"
        )
    await r.create(uuid.uuid4(), _args(code="pub.m", visibility="public", genre_tags=["xianxia"]))
    await r.create(u1, _args(code="own.m", visibility="private", genre_tags=["xianxia"]))

    # NB: the fixture ran run_migrations, so the W7 system seeds are present too —
    # assert MEMBERSHIP, not equality. The point is each scope QUERY RUNS (no
    # IndeterminateDatatypeError 500) and returns the right tier.
    sys_codes = {m.code for m in await r.list_for_caller(u1, scope="system")}
    pub_codes = {m.code for m in await r.list_for_caller(u1, scope="public")}
    user_codes = {m.code for m in await r.list_for_caller(u1, scope="user")}
    all_codes = {m.code for m in await r.list_for_caller(u1, scope="all")}

    assert "sys.m" in sys_codes and "pub.m" not in sys_codes and "own.m" not in sys_codes
    assert "pub.m" in pub_codes and "sys.m" not in pub_codes and "own.m" not in pub_codes
    assert user_codes == {"own.m"}  # only the caller's own tier (seeds are owner NULL)
    assert {"sys.m", "pub.m", "own.m"} <= all_codes
    # the genre filter must not break param-numbering under a caller-less scope.
    sys_xianxia = {m.code for m in await r.list_for_caller(u1, scope="system", genre="xianxia")}
    assert "sys.m" in sys_xianxia
    assert await r.list_for_caller(u1, scope="system", genre="zzz_nonexistent_genre") == []


async def test_clone_of_invisible_source_raises(repo):
    r, _ = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    src = await r.create(u2, _args(code="hidden", visibility="private"))
    with pytest.raises(LookupError):
        await r.clone(u1, src.id, target_owner=u1)


async def test_clone_code_collision_raises(repo):
    r, _ = repo
    u1 = uuid.uuid4()
    src = await r.create(u1, _args(code="own", visibility="private"))
    # cloning into the same tier with the same code collides on uq_motif_user.
    with pytest.raises(asyncpg.UniqueViolationError):
        await r.clone(u1, src.id, target_owner=u1)


async def _seed_imported(pool, owner, *, code, examples):
    """Seed a private imported motif (create() always stamps 'authored', so the
    import path — W9 — is simulated here with a direct INSERT)."""
    import json

    async with pool.acquire() as c:
        return await c.fetchval(
            "INSERT INTO motif (owner_user_id, code, visibility, source, name, examples) "
            "VALUES ($1,$2,'private','imported','Imported',$3::jsonb) RETURNING id",
            owner, code, json.dumps(examples),
        )


async def test_clone_of_imported_is_tainted_and_strips_on_publish(repo):
    """B-3 (review #3): an adopted clone of an imported motif carries the lineage
    taint, so publishing the clone strips its copied source passages — even though
    its source is now 'adopted', not 'imported'. (caller≠target_owner here purely to
    dodge the own-code collision that W1 adopt resolves by suffixing the code.)"""
    r, pool = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    src = await _seed_imported(pool, u1, code="imp", examples=[{"text": "stolen passage"}])

    cloned = await r.clone(u1, src, target_owner=u2)
    assert cloned.source == "adopted"
    assert cloned.imported_derived is True          # taint propagated
    assert cloned.examples == [{"text": "stolen passage"}]  # kept while private

    # publishing the adopted-from-imported clone strips the copied source prose.
    async with pool.acquire() as c:
        await c.execute("UPDATE motif SET visibility = 'public' WHERE id = $1", cloned.id)
    after = await r.get_visible(u2, cloned.id)
    assert after.examples == []
    assert after.source_ref.startswith("lineage:")


async def test_clone_of_authored_not_tainted_keeps_examples_on_publish(repo):
    """The control: an adopted clone of an AUTHORED motif is NOT tainted, so its
    examples survive publish (the strip is not over-broad — only imported lineage)."""
    r, pool = repo
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    src = await r.create(
        u1, _args(code="auth", visibility="public", examples=[{"text": "my example"}]),
    )
    cloned = await r.clone(u1, src.id, target_owner=u2)
    assert cloned.imported_derived is False
    async with pool.acquire() as c:
        await c.execute("UPDATE motif SET visibility = 'public' WHERE id = $1", cloned.id)
    after = await r.get_visible(u2, cloned.id)
    assert after.examples == [{"text": "my example"}]
