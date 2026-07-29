"""Motif text search — `q` as a RANK, not a filter (2026-07-29).

`q` was an ILIKE in the WHERE clause of every list method, and a WHERE clause can only
SUBTRACT: typing a phrase whose words were not literally present returned nothing, while the
PLANNER had been ranking the same library by cosine since the premise-seeding fix. The human
had a strictly weaker instrument than the model. These tests hold the fix and, just as
importantly, hold the two properties that make it safe to ship:

  · ADDITIVE — every row the old literal filter returned is still returned, still first.
  · DEGRADE-EQUAL — with no query vector the behaviour is byte-for-byte the old one.
"""

from __future__ import annotations

import uuid

from app.db.repositories import motif_repo as mr
from app.db.repositories.motif_repo import MotifRepo


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows
        self.fetched_sql: list[str] = []
        self.fetched_args: list[tuple] = []
        self.executed: list[tuple] = []

    async def fetch(self, sql, *args):
        self.fetched_sql.append(sql)
        self.fetched_args.append(args)
        return self._rows

    async def execute(self, sql, *args):
        self.executed.append((sql, args))
        return "UPDATE 1"


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, rows):
        self.conn = _FakeConn(rows)

    def acquire(self):
        return _FakeAcquire(self.conn)


def _row(code, name, summary, *, embedding, stale=False, owner=None):
    """A motif row shaped like `_SEARCH_COLS` (model columns + vector + hash)."""
    from app.engine.motif_embed import summary_hash
    text = f"{name}\n{summary}"          # == motif_summary_text with no beats
    return {
        "id": uuid.uuid4(), "owner_user_id": owner, "book_id": None, "book_shared": False,
        "code": code, "language": "en", "visibility": "unlisted", "kind": "situation",
        "category": None, "name": name, "summary": summary, "genre_tags": [],
        "roles": "[]", "beats": "[]", "preconditions": "[]", "effects": "[]",
        "info_asymmetry": None, "annotations": "{}", "tension_target": 3,
        "emotion_target": None, "examples": "[]", "abstraction_confidence": None,
        "source": "authored", "imported_derived": False, "source_ref": None,
        "source_version": 1, "embedding_model": "platform-embed-v1", "embedding_dim": 3,
        "judge_score": None, "mining_support": None, "status": "active", "version": 1,
        "created_at": None, "updated_at": None,
        "embedded_summary_hash": ("stale" if stale else summary_hash(text)),
        "embedding": embedding,
    }


def _patch_embed(monkeypatch, vector):
    async def _q(_text):
        return vector
    monkeypatch.setattr(mr, "embed_query", _q)
    monkeypatch.setattr(mr, "_platform_embed_model", lambda: ("platform_model", "platform-embed-v1"))


def _patch_embed_down(monkeypatch):
    from app.clients.embedding_client import EmbeddingError

    async def _q(_text):
        raise EmbeddingError("provider down", retryable=True)
    monkeypatch.setattr(mr, "embed_query", _q)


# ── THE bug: a phrase nobody wrote verbatim ──────────────────────────────────────────────────
async def test_a_phrase_with_no_literal_hit_still_finds_the_right_motif(monkeypatch):
    """`witness contradicts testimony` matched no name or summary substring, so the old
    ILIKE returned zero rows while the motif sat right there. Cosine finds it."""
    rows = [
        _row("mystery.witness_who_lies", "The Witness Whose Lie Is Not the Crime",
             "A statement contradicts one small checkable thing.", embedding=[1.0, 0.0, 0.0]),
        _row("cultivation.face_slap", "Face-Slap Reversal",
             "A preening heir is publicly broken.", embedding=[0.0, 1.0, 0.0]),
    ]
    _patch_embed(monkeypatch, [1.0, 0.0, 0.0])          # points at the witness motif
    out = await MotifRepo(_FakePool(rows)).list_for_caller(
        uuid.uuid4(), q="witness contradicts testimony", limit=10)
    assert [m.code for m in out] == ["mystery.witness_who_lies"], (
        "semantic ranking did not surface the motif the phrase describes")


async def test_a_literal_hit_always_outranks_a_merely_similar_one(monkeypatch):
    """Precision beats fuzziness: someone typing an exact name wants THAT row. This is also
    what makes the change purely additive — old results stay, and stay on top."""
    rows = [
        # semantically a perfect match for the query vector, but no literal hit
        _row("a.semantic", "Something Else Entirely", "unrelated words", embedding=[1.0, 0.0, 0.0]),
        # literal hit on the name, but semantically orthogonal
        _row("b.literal", "Face-Slap Reversal", "unrelated", embedding=[0.0, 1.0, 0.0]),
    ]
    _patch_embed(monkeypatch, [1.0, 0.0, 0.0])
    out = await MotifRepo(_FakePool(rows)).list_for_caller(uuid.uuid4(), q="face-slap", limit=10)
    assert [m.code for m in out] == ["b.literal", "a.semantic"], (
        "a literal match must rank above a semantic one")


async def test_the_code_is_searchable_literally(monkeypatch):
    """An author who knows the code should be able to paste it."""
    rows = [_row("mystery.impossible_detail", "The Detail That Should Not Be There",
                 "one small physical thing", embedding=[0.0, 1.0, 0.0])]
    _patch_embed(monkeypatch, [1.0, 0.0, 0.0])          # orthogonal → semantic would drop it
    out = await MotifRepo(_FakePool(rows)).list_for_caller(
        uuid.uuid4(), q="mystery.impossible_detail", limit=10)
    assert [m.code for m in out] == ["mystery.impossible_detail"]


async def test_a_semantic_near_miss_below_the_floor_is_dropped(monkeypatch):
    """The floor is the planner's `motif_min_score` — one knob for one question. Without it a
    text search would return the whole library ranked by noise."""
    rows = [_row("far.away", "Nothing Like It", "nothing like it", embedding=[0.0, 1.0, 0.0])]
    _patch_embed(monkeypatch, [1.0, 0.0, 0.0])          # cosine 0.0, far below the floor
    out = await MotifRepo(_FakePool(rows)).list_for_caller(uuid.uuid4(), q="a phrase", limit=10)
    assert out == []


async def test_a_stale_vector_rides_on_its_literal_hit_and_is_never_invented(monkeypatch):
    """A row whose text changed after it was embedded cannot be judged semantically. It must
    still be findable by its own words, and must NOT be ranked on the stale vector."""
    rows = [
        _row("edited.literal", "Face-Slap Reversal", "edited since embedding",
             embedding=[1.0, 0.0, 0.0], stale=True),
        _row("edited.nomatch", "Unrelated Name", "also edited",
             embedding=[1.0, 0.0, 0.0], stale=True),
    ]
    _patch_embed(monkeypatch, [1.0, 0.0, 0.0])          # would score 1.0 on the STALE vectors
    out = await MotifRepo(_FakePool(rows)).list_for_caller(uuid.uuid4(), q="face-slap", limit=10)
    assert [m.code for m in out] == ["edited.literal"], (
        "a stale vector was trusted, or a literal hit was lost")


async def test_an_unembedded_row_is_still_findable_by_its_own_words(monkeypatch):
    """A just-created motif has no vector until the retrieve path back-fills it. The author
    must be able to find their own motif immediately."""
    rows = [_row("brand.new", "My New Trope", "just written", embedding=None)]
    _patch_embed(monkeypatch, [1.0, 0.0, 0.0])
    out = await MotifRepo(_FakePool(rows)).list_for_caller(uuid.uuid4(), q="my new trope", limit=10)
    assert [m.code for m in out] == ["brand.new"]


# ── degrade: no vector ⇒ exactly the old behaviour ───────────────────────────────────────────
async def test_no_query_vector_falls_back_to_the_literal_filter(monkeypatch):
    """Embed down / unconfigured must leave the shipped behaviour untouched — the ILIKE goes
    back into the WHERE clause and the DB does the filtering, as before."""
    _patch_embed_down(monkeypatch)
    pool = _FakePool([])
    await MotifRepo(pool).list_for_caller(uuid.uuid4(), q="witness", limit=10)
    sql = pool.conn.fetched_sql[-1].lower()
    assert "ilike" in sql, "degrade did not restore the literal WHERE filter"
    assert "%witness%" in [str(a) for a in pool.conn.fetched_args[-1]]


async def test_no_q_at_all_never_embeds_and_never_ranks(monkeypatch):
    """A plain browse must not pay for an embed round-trip."""
    called = {"n": 0}

    async def _q(_text):
        called["n"] += 1
        return [1.0, 0.0, 0.0]
    monkeypatch.setattr(mr, "embed_query", _q)
    pool = _FakePool([])
    await MotifRepo(pool).list_for_caller(uuid.uuid4(), limit=10)
    assert called["n"] == 0
    assert "ilike" not in pool.conn.fetched_sql[-1].lower()


async def test_a_slow_provider_degrades_instead_of_hanging_the_search_box(monkeypatch):
    """A search field is interactive: a user waiting on a provider is worse than a worse
    ranking, so the embed is wall-clock bounded (unlike the planning pipelines, which must
    not be). Deliberately distinct from the outage path above — a HANG is not an ERROR."""
    import asyncio

    async def _slow(_text):
        await asyncio.sleep(30)
    monkeypatch.setattr(mr, "embed_query", _slow)
    monkeypatch.setattr(mr, "_SEARCH_EMBED_BUDGET_S", 0.05)
    pool = _FakePool([])
    out = await asyncio.wait_for(
        MotifRepo(pool).list_for_caller(uuid.uuid4(), q="witness", limit=10), timeout=5)
    assert out == []
    assert "ilike" in pool.conn.fetched_sql[-1].lower(), "a slow embed did not degrade to literal"


async def test_paging_past_the_first_page_keeps_the_literal_path(monkeypatch):
    """Offset is meaningless against a ranked set — the ranked answer IS the top-N. Rather
    than silently returning page 1 forever, an offset request stays on the pageable path."""
    _patch_embed(monkeypatch, [1.0, 0.0, 0.0])
    pool = _FakePool([])
    await MotifRepo(pool).list_for_caller(uuid.uuid4(), q="witness", limit=10, offset=10)
    assert "ilike" in pool.conn.fetched_sql[-1].lower()


# ── the book surface gets the same treatment (the studio's other scope tab) ───────────────────
async def test_the_book_library_ranks_too(monkeypatch):
    rows = [
        _row("mystery.witness_who_lies", "The Witness Whose Lie Is Not the Crime",
             "A statement contradicts one small checkable thing.", embedding=[1.0, 0.0, 0.0]),
        _row("other.thing", "Other", "other", embedding=[0.0, 1.0, 0.0]),
    ]
    _patch_embed(monkeypatch, [1.0, 0.0, 0.0])
    out = await MotifRepo(_FakePool(rows)).list_in_book(
        uuid.uuid4(), uuid.uuid4(), q="a witness who lies about something else", limit=10)
    assert [m.code for m in out] == ["mystery.witness_who_lies"]


def test_the_search_projection_never_leaks_the_vector():
    """`_SEARCH_COLS` loads the vector; the Motif model must not carry it out of the repo."""
    assert "embedding" in mr._SEARCH_COLS
    m = mr._row_to_motif(_row("x.y", "N", "S", embedding=[1.0, 2.0, 3.0]))
    assert not hasattr(m, "embedding")
    assert "embedding" not in m.model_dump()


# ── the warm path: a deploy that edits packs must not leave search semantically dark ─────────
def _patch_warm(monkeypatch, vector, *, fail=False):
    from app.clients.embedding_client import EmbeddingError

    class _Res:
        embeddings = [vector]

    async def _embed(_text):
        if fail:
            raise EmbeddingError("warm provider down", retryable=True)
        return _Res()
    monkeypatch.setattr(mr, "embed_motif_summary", _embed)


async def test_a_stale_row_is_re_embedded_so_search_self_heals_after_a_deploy(monkeypatch):
    """The boot seeder updates pack content on a `source_version` bump, which by design leaves
    the stored vector stale. Without this, every motif whose wording was just improved would be
    invisible to semantic search until an unrelated planning run happened to re-embed it —
    observed live: after re-seeding, `witness contradicts testimony` stopped finding
    `mystery.witness_who_lies` even though that is the phrase it describes."""
    rows = [_row("edited.nomatch", "Unrelated Name", "rewritten since embedding",
                 embedding=[0.0, 1.0, 0.0], stale=True)]
    _patch_embed(monkeypatch, [1.0, 0.0, 0.0])
    _patch_warm(monkeypatch, [1.0, 0.0, 0.0])          # the NEW text embeds onto the query
    pool = _FakePool(rows)
    out = await MotifRepo(pool).list_for_caller(uuid.uuid4(), q="a phrase about it", limit=10)
    assert [m.code for m in out] == ["edited.nomatch"], "the stale row was not warmed"
    assert pool.conn.executed, "no vector was persisted — the next search pays again"
    assert "UPDATE motif SET embedding" in pool.conn.executed[0][0]


async def test_warm_never_writes_another_tenants_vector(monkeypatch):
    """TENANCY: a READ by one user must not rewrite a row owned by someone else. Only system
    rows (owner NULL) and the caller's own are warmable."""
    foreign = uuid.uuid4()
    rows = [_row("theirs.private", "Their Motif", "their words",
                 embedding=[0.0, 1.0, 0.0], stale=True, owner=foreign)]
    _patch_embed(monkeypatch, [1.0, 0.0, 0.0])
    _patch_warm(monkeypatch, [1.0, 0.0, 0.0])
    pool = _FakePool(rows)
    await MotifRepo(pool).list_for_caller(uuid.uuid4(), q="a phrase about it", limit=10)
    assert not pool.conn.executed, "a search warmed a FOREIGN user's motif vector"


async def test_a_failing_warm_leaves_the_row_on_its_literal_hit_only(monkeypatch):
    """Warm is best-effort. When it fails the row must not be ranked on its stale vector, and
    must not vanish if the user's words literally match it."""
    rows = [
        _row("edited.literal", "Face-Slap Reversal", "edited", embedding=[1.0, 0.0, 0.0], stale=True),
        _row("edited.nomatch", "Unrelated", "edited", embedding=[1.0, 0.0, 0.0], stale=True),
    ]
    _patch_embed(monkeypatch, [1.0, 0.0, 0.0])
    _patch_warm(monkeypatch, [1.0, 0.0, 0.0], fail=True)
    out = await MotifRepo(_FakePool(rows)).list_for_caller(uuid.uuid4(), q="face-slap", limit=10)
    assert [m.code for m in out] == ["edited.literal"]
