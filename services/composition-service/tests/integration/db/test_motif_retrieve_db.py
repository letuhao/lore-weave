"""W3 — MotifRetriever behavior against real Postgres (the data-R1 + B-2 guards).

The unit tests (tests/unit/test_motif_retrieve.py) prove the scoring/degrade/NULL-skip
logic with a fake pool. THIS file proves the SQL pre-filter against a real DB:
  - data-R1  : the pre-filter loads ONLY active + in-language + genre-overlapping +
               visible rows — NOT the whole table. A draft / wrong-language / disjoint-
               genre / foreign-private row is NOT a candidate (so its vector is never
               loaded for the cosine pass).
  - B-2      : the retrieve tier predicate == MotifRepo.get_visible — every retrieved
               candidate is also fetchable by id (no ghost, no IDOR via the rank path).
  - MD-2     : a genre-less call still retrieves (the && clause is omitted).

Gated on TEST_COMPOSITION_DB_URL; the fixture drops the motif tables on setup/teardown.
The query embed is patched to a fixed vector so the test is deterministic + offline (no
provider-registry hop); the SQL pre-filter is the thing under test here.
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.motif_repo import MotifRepo
from app.db.repositories.motif_retrieve import MotifRetriever

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

_VEC = [1.0, 0.0, 0.0]


@pytest.fixture
async def stack():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)

    async def _drop():
        async with p.acquire() as c:
            for t in _MOTIF_TABLES:
                await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")

    try:
        await _drop()
        await run_migrations(p)
        yield p
    finally:
        await _drop()
        await p.close()


async def _insert_motif(
    pool, *, owner, code, language="en", visibility="public", genres=("xianxia",),
    status="active", embedding=_VEC, tension_target=3,
):
    """Direct INSERT so we can seed system rows (owner NULL) + arbitrary status/lang."""
    async with pool.acquire() as c:
        return await c.fetchval(
            """
            INSERT INTO motif
              (owner_user_id, code, language, visibility, name, summary, genre_tags,
               tension_target, embedding, embedding_model, embedded_summary_hash, status)
            VALUES ($1,$2,$3,$4,$5,'a summary',$6,$7,$8,'platform-embed-v1','h',$9)
            RETURNING id
            """,
            owner, code, language, visibility, code, list(genres),
            tension_target, embedding, status,
        )


def _patch_query_embed(monkeypatch, vector=_VEC):
    async def _fake(_text):
        return vector
    monkeypatch.setattr("app.db.repositories.motif_retrieve.embed_query", _fake)


async def test_prefilter_bounds_the_load(stack, monkeypatch):
    """data-R1, as amended by D-MOTIF-HARD-FILTERS-HIDE-HALF-THE-LIBRARY.

    STATUS and VISIBILITY still bound the load — a draft is not a candidate, and a foreign-private
    row must never have its vector read. GENRE and LANGUAGE no longer do: they moved to the
    pre-RANK, because as WHERE clauses they could only subtract, and on live data they subtracted
    52% of the library (`'{}' && '{fantasy}'` is false, so 21 untagged motifs were unreachable by
    any genre-tagged book, and 40 more were tagged `hook`/`connective` — genre-agnostic by design).
    The vectors are multilingual (bge-m3), so a `vi` row is a legitimate candidate for an `en`
    book; the 0.30 cosine floor is the quality gate, not the tag columns."""
    pool = stack
    u1 = uuid.uuid4()
    u2 = uuid.uuid4()
    # candidates that SHOULD match (active, en, genre overlap, visible to u1):
    await _insert_motif(pool, owner=None, code="sys.hit", genres=("xianxia",))          # system
    await _insert_motif(pool, owner=u2, code="pub.hit", visibility="public", genres=("xianxia",))
    await _insert_motif(pool, owner=u1, code="own.hit", visibility="private", genres=("xianxia",))
    # rows that must be EXCLUDED by the pre-filter (their vectors must never be loaded):
    await _insert_motif(pool, owner=u1, code="draft.miss", status="draft", genres=("xianxia",))
    await _insert_motif(pool, owner=u1, code="vi.miss", language="vi", genres=("xianxia",))
    await _insert_motif(pool, owner=u1, code="genre.miss", genres=("scifi",))           # disjoint
    await _insert_motif(pool, owner=u2, code="foreign.miss", visibility="private", genres=("xianxia",))

    _patch_query_embed(monkeypatch)
    retr = MotifRetriever(pool)
    out = await retr.retrieve(
        u1, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50, limit=50,
    )
    codes = {c.motif.code for c in out}
    # STATUS + VISIBILITY still exclude, and that is the part that matters for safety.
    assert "draft.miss" not in codes
    assert "foreign.miss" not in codes
    # The in-genre, in-language, visible rows are all there.
    assert {"sys.hit", "pub.hit", "own.hit"} <= codes
    # …and the cross-language / cross-genre rows are now CANDIDATES rather than invisible. This is
    # the whole fix: they rank lower, they do not vanish.
    assert "vi.miss" in codes, "a vi motif must be reachable — the vectors are multilingual"
    assert "genre.miss" in codes, "an out-of-genre motif must be reachable — genre is a rank, not a gate"


async def test_tier_predicate_matches_get_visible(stack, monkeypatch):
    """B-2: every retrieved candidate is ALSO fetchable via MotifRepo.get_visible (one
    predicate, two call sites). A foreign-private row is neither retrieved nor visible."""
    pool = stack
    u1 = uuid.uuid4()
    u2 = uuid.uuid4()
    sys_id = await _insert_motif(pool, owner=None, code="sys.x")
    pub_id = await _insert_motif(pool, owner=u2, code="pub.x", visibility="public")
    own_id = await _insert_motif(pool, owner=u1, code="own.x", visibility="private")
    foreign_id = await _insert_motif(pool, owner=u2, code="foreign.x", visibility="private")

    _patch_query_embed(monkeypatch)
    retr = MotifRetriever(pool)
    repo = MotifRepo(pool)
    out = await retr.retrieve(
        u1, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50, limit=50,
    )
    retrieved_ids = {c.motif.id for c in out}
    # every retrieved id is get_visible to the same caller:
    for mid in retrieved_ids:
        assert await repo.get_visible(u1, mid) is not None
    # the visible set IS the retrieved set (same predicate):
    assert retrieved_ids == {sys_id, pub_id, own_id}
    # the foreign-private row is neither retrieved nor get_visible (IDOR-safe):
    assert foreign_id not in retrieved_ids
    assert await repo.get_visible(u1, foreign_id) is None


async def test_no_embedding_projected(stack, monkeypatch):
    """The returned Motif never carries the embedding vector (server-side-only rule)."""
    pool = stack
    u1 = uuid.uuid4()
    await _insert_motif(pool, owner=u1, code="own.x", visibility="private")
    _patch_query_embed(monkeypatch)
    out = await MotifRetriever(pool).retrieve(
        u1, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50,
    )
    assert out
    assert "embedding" not in out[0].motif.model_dump()


async def test_genreless_call_still_retrieves(stack, monkeypatch):
    """MD-2: a genre-less book ([]) still retrieves.

    Amended by D-MOTIF-HARD-FILTERS-HIDE-HALF-THE-LIBRARY: the tier bound still applies, but a
    wrong-language row is no longer EXCLUDED — it is merely ranked below same-language ones. The
    vectors are bge-m3 (multilingual), so a Vietnamese motif is a real candidate for an English
    book, and the cosine floor decides."""
    pool = stack
    u1 = uuid.uuid4()
    await _insert_motif(pool, owner=u1, code="en.hit", language="en", genres=("scifi",))
    await _insert_motif(pool, owner=u1, code="vi.miss", language="vi", genres=("scifi",))
    _patch_query_embed(monkeypatch)
    out = await MotifRetriever(pool).retrieve(
        u1, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=[], language="en", beat_role="hook", tension=50, limit=50,
    )
    codes = {c.motif.code for c in out}
    assert "en.hit" in codes        # retrieved despite no genre constraint
    assert "vi.miss" in codes       # …and so is the vi row: language RANKS, it no longer gates


async def test_null_embedding_row_skipped_and_queued(stack, monkeypatch):
    """RECONCILE D4 on real rows: a seed with embedding=NULL is a candidate by the SQL
    pre-filter but SKIPPED in the cosine pass + queued for back-fill (not 0.0-ranked)."""
    pool = stack
    u1 = uuid.uuid4()
    await _insert_motif(pool, owner=u1, code="ready", embedding=_VEC)
    await _insert_motif(pool, owner=u1, code="seed", embedding=None)   # NULL vector (seed)
    _patch_query_embed(monkeypatch)
    retr = MotifRetriever(pool)
    out = await retr.retrieve(
        u1, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50, limit=50,
    )
    codes = {c.motif.code for c in out}
    assert "ready" in codes
    assert "seed" not in codes
    queued = retr.drain_backfill_queue()
    assert any(q["code"] == "seed" for q in queued)


# ── D-MOTIF-HARD-FILTERS-HIDE-HALF-THE-LIBRARY ───────────────────────────────────────────────────
# Genre and language were WHERE clauses, so they could only SUBTRACT. On live data they subtracted
# 52% of the library: `'{}' && '{fantasy}'` is false, so 21 untagged motifs were unreachable by any
# genre-tagged book, and 40 more carry structural tags (`hook`, `connective`, `emotion_arc` — rows
# like "Cliff Question", genre-agnostic by design) that no author would ever tag a book with.
# Measured per genre: fantasy 0 · scifi 0 · romance 0 · mystery 0 · thriller 0 · literary 0.

async def test_an_UNTAGGED_motif_is_reachable_at_all(stack, monkeypatch):
    """The sharpest case, and the one that was impossible: an empty `genre_tags` array can never
    overlap anything, so these rows could not be retrieved by ANY genre-tagged book. Ever."""
    pool = stack
    u1 = uuid.uuid4()
    await _insert_motif(pool, owner=None, code="untagged.one", genres=())

    _patch_query_embed(monkeypatch)
    out = await MotifRetriever(pool).retrieve(
        u1, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["fantasy"], language="en", beat_role="hook", tension=50, limit=50,
    )
    assert "untagged.one" in {c.motif.code for c in out}


async def test_a_book_in_an_UNREPRESENTED_genre_still_gets_candidates(stack, monkeypatch):
    """A fantasy book used to match zero motifs and plan every scene with no motif layer — the
    library is xianxia/court-heavy, and nothing carries `fantasy`. The structural motifs it should
    have been able to use were sitting right there, tagged `hook`."""
    pool = stack
    u1 = uuid.uuid4()
    await _insert_motif(pool, owner=None, code="structural.hook", genres=("hook", "connective"))
    await _insert_motif(pool, owner=None, code="xianxia.one", genres=("xianxia",))

    _patch_query_embed(monkeypatch)
    out = await MotifRetriever(pool).retrieve(
        u1, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["fantasy"], language="en", beat_role="hook", tension=50, limit=50,
    )
    assert "structural.hook" in {c.motif.code for c in out}


async def test_in_genre_and_in_language_still_win_the_CEILING(stack, monkeypatch):
    """The bound is what the ceiling is FOR, so relaxing the filter must not cost relevance: an
    in-genre, in-language row has to outrank an out-of-genre or cross-language one when the
    candidate set is truncated. Proven by squeezing the ceiling to 1."""
    from app.config import settings

    pool = stack
    u1 = uuid.uuid4()
    await _insert_motif(pool, owner=None, code="off.genre", genres=("scifi",))
    await _insert_motif(pool, owner=None, code="cross.lang", language="vi", genres=("xianxia",))
    await _insert_motif(pool, owner=None, code="on.target", genres=("xianxia",))

    monkeypatch.setattr(settings, "motif_candidate_ceiling", 1, raising=False)
    _patch_query_embed(monkeypatch)
    out = await MotifRetriever(pool).retrieve(
        u1, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50, limit=50,
    )
    assert {c.motif.code for c in out} == {"on.target"}


async def test_a_DRAFT_and_a_FOREIGN_PRIVATE_row_are_still_excluded(stack, monkeypatch):
    """The bounds that were never about relevance stay hard. Relaxing genre/language must not have
    quietly widened the VISIBILITY predicate — that would be a tenancy defect, not a tuning change."""
    pool = stack
    u1, u2 = uuid.uuid4(), uuid.uuid4()
    await _insert_motif(pool, owner=u1, code="draft.x", status="draft")
    await _insert_motif(pool, owner=u2, code="foreign.x", visibility="private")
    await _insert_motif(pool, owner=None, code="ok.x")

    _patch_query_embed(monkeypatch)
    codes = {c.motif.code for c in await MotifRetriever(pool).retrieve(
        u1, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["fantasy"], language="en", beat_role="hook", tension=50, limit=50,
    )}
    assert "ok.x" in codes
    assert "draft.x" not in codes and "foreign.x" not in codes
