"""W3 — motif retrieval + platform-embed unit tests (no DB, no network).

Covers the audit-guards-as-failing-tests (W3 §7):
  - B-1/A8/A9 : ONE platform model for ALL motif vectors (cross-model impossible).
  - data-R1   : the SQL pre-filter bounds the vector load (asserted with a fake pool
                that records the pre-filter SQL — predicate + ceiling present).
  - R4        : query-embed outage degrades to genre+tension (never [], never raise);
                write-embed outage fails closed (raises EmbeddingError).
  - D4        : a NULL-embedding row is SKIPPED + queued for back-fill, never 0.0-ranked
                as a real miss.

The DB-touching behavior (real pre-filter SQL, tier predicate == get_visible) lives in
tests/integration/db/test_motif_retrieve_db.py (gated on TEST_COMPOSITION_DB_URL).
"""

from __future__ import annotations

import uuid

import pytest

from app.clients.embedding_client import EmbeddingError, EmbeddingResult
from app.db.models import Motif
from app.db.repositories.motif_retrieve import (
    _build_query_text,
    _genre_overlap,
    _precond_overlap,
    _tension_band,
)
from app.engine import motif_embed
from app.engine.motif_embed import (
    _platform_embed_model,
    _platform_embed_owner,
    motif_summary_text,
    summary_hash,
)


# ── _cosine (the references precedent, copied local — MD-4) ─────────────────────
def test_cosine_zero_on_mismatch():
    from app.db.repositories.motif_retrieve import _cosine

    assert _cosine([1.0, 2.0, 3.0], [1.0, 2.0]) == 0.0   # length mismatch
    assert _cosine([], [1.0]) == 0.0                     # empty
    assert _cosine([0.0, 0.0], [0.0, 0.0]) == 0.0        # zero vector


def test_cosine_ranks_correctly():
    from app.db.repositories.motif_retrieve import _cosine

    q = [1.0, 0.0, 0.0]
    identical = _cosine(q, [1.0, 0.0, 0.0])
    orthogonal = _cosine(q, [0.0, 1.0, 0.0])
    opposite = _cosine(q, [-1.0, 0.0, 0.0])
    assert identical == pytest.approx(1.0)
    assert orthogonal == pytest.approx(0.0)
    assert opposite == pytest.approx(-1.0)
    assert identical > orthogonal > opposite


# ── pure scoring functions ──────────────────────────────────────────────────────
def test_genre_overlap():
    assert _genre_overlap(["a", "b"], ["b", "c"]) == pytest.approx(0.5)   # 1 of 2 query genres
    assert _genre_overlap(["x"], ["y", "z"]) == 0.0                       # disjoint
    assert _genre_overlap(["a", "b"], ["a", "b"]) == pytest.approx(1.0)   # full
    assert _genre_overlap(["a"], []) == 0.0                               # no query genres → 0


def test_tension_band_map():
    # motif tension_target 1..5 → midpoint 10/30/50/70/90 vs chapter 0..100.
    assert _tension_band(5, 90) > 0.95          # band-mid 90 vs 90 → ~1.0
    assert _tension_band(5, 85) > _tension_band(1, 85)  # high band fits a high chapter better
    assert _tension_band(1, 90) < 0.3           # band-mid 10 vs 90 → far
    assert _tension_band(None, 50) == pytest.approx(0.5)  # no target → neutral
    assert _tension_band(3, None) == pytest.approx(0.5)   # no chapter tension → neutral


def test_precond_overlap():
    assert _precond_overlap([{"text": "hero is wounded"}], None) == 0.0       # no prev effects
    assert _precond_overlap([{"text": "hero is wounded"}], []) == 0.0         # empty prev effects
    assert _precond_overlap([{"text": "the hero is wounded badly"}],
                            ["hero wounded"]) > 0.0                           # token overlap
    assert _precond_overlap([], ["anything"]) == 0.0                          # no preconditions


def test_build_query_text():
    assert _build_query_text("hook", ["betrayal", "loss"]) == "hook betrayal loss"
    assert _build_query_text("hook", None) == "hook"
    assert _build_query_text(None, ["loss"]) == "loss"
    assert _build_query_text(None, None) == ""
    assert _build_query_text("", ["", "x"]) == "x"      # drops empties


def test_summary_text_and_hash_stable():
    m = Motif(
        id=uuid.uuid4(), code="c", name="Lucky Break", summary="a fortuitous encounter",
        beats=[{"label": "Discovery", "intent": "find the elixir"}],
    )
    t1 = motif_summary_text(m)
    t2 = motif_summary_text(m)
    assert t1 == t2                                  # deterministic
    assert "Lucky Break" in t1 and "fortuitous" in t1 and "Discovery" in t1
    assert summary_hash(t1) == summary_hash(t2)      # stable
    # adding a beat changes the text → changes the hash (beats are identity).
    m2 = Motif(
        id=m.id, code="c", name="Lucky Break", summary="a fortuitous encounter",
        beats=[{"label": "Discovery", "intent": "find the elixir"},
               {"label": "Twist", "intent": "rival appears"}],
    )
    assert summary_hash(motif_summary_text(m2)) != summary_hash(t1)


# ── B-1 : one platform model for ALL vectors + fail-closed config ───────────────
def test_platform_embed_model_parses_source_and_ref(monkeypatch):
    monkeypatch.setattr(motif_embed.settings, "motif_embed_model_source", "platform_model")
    monkeypatch.setattr(motif_embed.settings, "motif_embed_model_ref", "text-embed-3-small")
    assert _platform_embed_model() == ("platform_model", "text-embed-3-small")


def test_platform_embed_fails_closed_when_ref_unset(monkeypatch):
    monkeypatch.setattr(motif_embed.settings, "motif_embed_model_ref", "")
    with pytest.raises(motif_embed.EmbedConfigError):
        _platform_embed_model()


def test_platform_embed_fails_closed_when_owner_unset(monkeypatch):
    monkeypatch.setattr(motif_embed.settings, "motif_embed_model_ref", "m")
    monkeypatch.setattr(motif_embed.settings, "motif_embed_owner_id", "")
    with pytest.raises(motif_embed.EmbedConfigError):
        _platform_embed_owner()


class _RecordingClient:
    """Records every (user_id, model_source, model_ref) embed() is called with."""

    def __init__(self, vec=None):
        self.calls: list[tuple] = []
        self._vec = vec or [0.1, 0.2, 0.3]

    async def embed(self, *, user_id, model_source, model_ref, texts):
        self.calls.append((str(user_id), model_source, model_ref, tuple(texts)))
        return EmbeddingResult(
            embeddings=[self._vec for _ in texts], dimension=len(self._vec),
            model=model_ref, prompt_tokens=0,
        )


async def test_one_platform_model_for_all_vectors(monkeypatch):
    """Every embed call — motif summary AND query — uses config.motif_embed_model_*
    and the platform owner. Cross-model contamination is structurally impossible."""
    owner = uuid.uuid4()
    monkeypatch.setattr(motif_embed.settings, "motif_embed_model_source", "platform_model")
    monkeypatch.setattr(motif_embed.settings, "motif_embed_model_ref", "platform-embed-v1")
    monkeypatch.setattr(motif_embed.settings, "motif_embed_owner_id", str(owner))
    rec = _RecordingClient()
    monkeypatch.setattr(motif_embed, "get_embedding_client", lambda: rec)

    await motif_embed.embed_motif_summary("a motif summary")
    await motif_embed.embed_query("a chapter intent")

    assert len(rec.calls) == 2
    for user_id, src, ref, _texts in rec.calls:
        assert user_id == str(owner)
        assert (src, ref) == ("platform_model", "platform-embed-v1")  # ONE model, always


async def test_query_and_motif_share_model(monkeypatch):
    monkeypatch.setattr(motif_embed.settings, "motif_embed_model_ref", "shared-model")
    monkeypatch.setattr(motif_embed.settings, "motif_embed_owner_id", str(uuid.uuid4()))
    rec = _RecordingClient()
    monkeypatch.setattr(motif_embed, "get_embedding_client", lambda: rec)
    await motif_embed.embed_motif_summary("x")
    await motif_embed.embed_query("y")
    models = {(src, ref) for _u, src, ref, _t in rec.calls}
    assert len(models) == 1   # the query and the motif resolve to the identical model


async def test_embed_query_returns_bare_vector(monkeypatch):
    monkeypatch.setattr(motif_embed.settings, "motif_embed_model_ref", "m")
    monkeypatch.setattr(motif_embed.settings, "motif_embed_owner_id", str(uuid.uuid4()))
    monkeypatch.setattr(motif_embed, "get_embedding_client", lambda: _RecordingClient(vec=[1.0, 2.0]))
    assert await motif_embed.embed_query("q") == [1.0, 2.0]


async def test_write_embed_outage_fails_closed(monkeypatch):
    """A provider outage on the WRITE path (embed a summary) propagates EmbeddingError
    — W1 maps it to a 502; an active motif is never persisted with a stale/null vector."""
    monkeypatch.setattr(motif_embed.settings, "motif_embed_model_ref", "m")
    monkeypatch.setattr(motif_embed.settings, "motif_embed_owner_id", str(uuid.uuid4()))

    class _Down:
        async def embed(self, **_kw):
            raise EmbeddingError("provider down", retryable=True)

    monkeypatch.setattr(motif_embed, "get_embedding_client", lambda: _Down())
    with pytest.raises(EmbeddingError):
        await motif_embed.embed_motif_summary("x")


async def test_embed_motif_summary_empty_result_raises(monkeypatch):
    """A 200 with an empty embeddings list is a fail-closed (an active motif must
    never end up with a null vector silently)."""
    monkeypatch.setattr(motif_embed.settings, "motif_embed_model_ref", "m")
    monkeypatch.setattr(motif_embed.settings, "motif_embed_owner_id", str(uuid.uuid4()))

    class _Empty:
        async def embed(self, **_kw):
            return EmbeddingResult(embeddings=[], dimension=0, model="m")

    monkeypatch.setattr(motif_embed, "get_embedding_client", lambda: _Empty())
    with pytest.raises(EmbeddingError):
        await motif_embed.embed_query("x")


# ── retrieve() with a fake pool: pre-filter bound + degrade + NULL-skip ─────────
class _FakeConn:
    """Returns canned rows for fetch(); records the SQL it was asked to run so the
    test can assert the pre-filter predicate + the candidate ceiling are in the query."""

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


def _row(code, *, embedding, tension_target=3, genre_tags=("xianxia",),
         mining_support=0, judge_score=None, owner=None):
    """A motif row dict shaped like the retrieve SELECT (incl. embedding)."""
    return {
        "id": uuid.uuid4(), "owner_user_id": owner, "code": code, "language": "en",
        "visibility": "public" if owner is None else "private", "kind": "sequence",
        "category": None, "name": code, "summary": "s", "genre_tags": list(genre_tags),
        "roles": "[]", "beats": "[]", "preconditions": "[]", "effects": "[]",
        "info_asymmetry": None, "annotations": "{}", "tension_target": tension_target,
        "emotion_target": None, "examples": "[]", "abstraction_confidence": None,
        "source": "authored", "imported_derived": False, "source_ref": None,
        "source_version": None, "embedding_model": "m", "embedding_dim": 3,
        "judge_score": judge_score, "mining_support": mining_support,
        "status": "active", "version": 1, "created_at": None, "updated_at": None,
        "embedded_summary_hash": None if embedding is None else "h", "embedding": embedding,
    }


def _patch_query_embed(monkeypatch, vector):
    async def _fake_embed_query(_text):
        return vector
    monkeypatch.setattr("app.db.repositories.motif_retrieve.embed_query", _fake_embed_query)


def _patch_user_query(monkeypatch, vector):
    """The U-space (caller's BYOK) query embedding — the counterpart to _patch_query_embed's
    platform/P-space one."""
    async def _q(_text, *, user_id, model):
        return vector
    monkeypatch.setattr("app.db.repositories.motif_retrieve.embed_query_with", _q)


def _patch_private_embed(monkeypatch, vector, *, record=None, raises=False):
    """The private-motif write embed (owner's BYOK model). `record` captures the owner_id +
    user_model each call is billed to → a test asserts the OWNER pays (the tenancy fix)."""
    class _Res:
        embeddings = [vector]

    async def _embed(_text, *, owner_id, user_model):
        if record is not None:
            record.append({"owner_id": owner_id, "user_model": user_model})
        if raises:
            raise EmbeddingError("provider down", retryable=True)
        return _Res()
    monkeypatch.setattr("app.db.repositories.motif_retrieve.embed_private_summary", _embed)


def _patch_platform_backfill_embed(monkeypatch, vector):
    """The platform-space write embed for a shared/system motif's inline back-fill."""
    class _Res:
        embeddings = [vector]

    async def _embed(_text):
        return _Res()
    monkeypatch.setattr("app.db.repositories.motif_retrieve.embed_motif_summary", _embed)
    monkeypatch.setattr("app.db.repositories.motif_retrieve._platform_embed_model",
                        lambda: ("platform_model", "platform-embed-v1"))


async def test_retrieve_empty_prefilter_returns_empty(monkeypatch):
    from app.db.repositories.motif_retrieve import MotifRetriever

    _patch_query_embed(monkeypatch, [1.0, 0.0, 0.0])
    retr = MotifRetriever(_FakePool([]))
    out = await retr.retrieve(
        uuid.uuid4(), book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50,
    )
    assert out == []


async def test_retrieve_ranks_by_cosine(monkeypatch):
    from app.db.repositories.motif_retrieve import MotifRetriever

    q = [1.0, 0.0, 0.0]
    rows = [
        _row("near", embedding=[1.0, 0.0, 0.0]),       # cos 1.0
        _row("mid", embedding=[1.0, 1.0, 0.0]),        # cos ~0.707
        _row("far", embedding=[0.0, 1.0, 0.0]),        # cos 0.0 → below min_score, dropped
    ]
    _patch_query_embed(monkeypatch, q)
    retr = MotifRetriever(_FakePool(rows))
    out = await retr.retrieve(
        uuid.uuid4(), book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50,
    )
    codes = [c.motif.code for c in out]
    assert codes[0] == "near"
    assert "far" not in codes                          # cos 0.0 < motif_min_score → dropped
    assert out[0].score >= out[-1].score
    assert out[0].match_reason["cosine"] == pytest.approx(1.0)


async def test_retrieve_no_embedding_in_result(monkeypatch):
    from app.db.repositories.motif_retrieve import MotifRetriever

    _patch_query_embed(monkeypatch, [1.0, 0.0, 0.0])
    retr = MotifRetriever(_FakePool([_row("a", embedding=[1.0, 0.0, 0.0])]))
    out = await retr.retrieve(
        uuid.uuid4(), book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50,
    )
    assert out
    assert not hasattr(out[0].motif, "embedding")      # Motif model has no embedding field


async def test_retrieve_null_embedding_skipped_not_zero_ranked(monkeypatch):
    """RECONCILE D4: a NULL-embedding row is SKIPPED (queued for back-fill), NEVER
    0.0-ranked as a real miss alongside scored rows."""
    from app.db.repositories.motif_retrieve import MotifRetriever

    rows = [
        _row("scored", embedding=[1.0, 0.0, 0.0]),
        _row("null_vec", embedding=None),              # seed not yet embedded
    ]
    _patch_query_embed(monkeypatch, [1.0, 0.0, 0.0])
    retr = MotifRetriever(_FakePool(rows))
    out = await retr.retrieve(
        uuid.uuid4(), book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50,
    )
    codes = [c.motif.code for c in out]
    assert "scored" in codes
    assert "null_vec" not in codes                     # skipped, not 0.0-ranked
    # and it was queued for back-fill (not silently dropped forever).
    assert any(r["code"] == "null_vec" for r in retr.drain_backfill_queue())


async def test_retrieve_min_score_floor(monkeypatch):
    from app.db.repositories.motif_retrieve import MotifRetriever

    # everything orthogonal → cos 0.0 < min_score → all dropped (no force-bind).
    rows = [_row("a", embedding=[0.0, 1.0, 0.0]), _row("b", embedding=[0.0, 0.0, 1.0])]
    _patch_query_embed(monkeypatch, [1.0, 0.0, 0.0])
    retr = MotifRetriever(_FakePool(rows))
    out = await retr.retrieve(
        uuid.uuid4(), book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50,
    )
    assert out == []


async def test_retrieve_deterministic_tiebreak(monkeypatch):
    """Equal cosine → tie-break by mining_support DESC, judge_score DESC, code ASC."""
    from decimal import Decimal

    from app.db.repositories.motif_retrieve import MotifRetriever

    rows = [
        _row("zzz", embedding=[1.0, 0.0, 0.0], mining_support=1, judge_score=Decimal("0.5")),
        _row("aaa", embedding=[1.0, 0.0, 0.0], mining_support=1, judge_score=Decimal("0.5")),
        _row("top", embedding=[1.0, 0.0, 0.0], mining_support=9, judge_score=Decimal("0.1")),
    ]
    _patch_query_embed(monkeypatch, [1.0, 0.0, 0.0])
    retr = MotifRetriever(_FakePool(rows))
    out = await retr.retrieve(
        uuid.uuid4(), book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50,
    )
    codes = [c.motif.code for c in out]
    assert codes == ["top", "aaa", "zzz"]              # mining_support wins, then code ASC


async def test_retrieve_query_embed_outage_degrades(monkeypatch):
    """R4: query-embed outage → degrade to genre+tension over the SAME pre-filtered
    set; never [], never raise; cosine=0.0 + degraded marker in match_reason."""
    from app.db.repositories.motif_retrieve import MotifRetriever

    async def _down(_text):
        raise EmbeddingError("provider down", retryable=True)

    monkeypatch.setattr("app.db.repositories.motif_retrieve.embed_query", _down)
    rows = [
        _row("hi_tension", embedding=[1.0, 0.0, 0.0], tension_target=5, genre_tags=["xianxia"]),
        _row("lo_tension", embedding=[1.0, 0.0, 0.0], tension_target=1, genre_tags=["other"]),
    ]
    retr = MotifRetriever(_FakePool(rows))
    out = await retr.retrieve(
        uuid.uuid4(), book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="climax", tension=90,
    )
    assert out                                         # NOT [] — a bound, valid set
    assert out[0].motif.code == "hi_tension"           # genre+tension ordering
    for c in out:
        assert c.match_reason["cosine"] == 0.0
        assert c.match_reason["degraded"] is True


async def test_retrieve_degrade_skips_null_embedding(monkeypatch):
    """Even in the degrade branch, a NULL-embedding row is queued for back-fill — but
    it may still rank (degrade doesn't need a vector). It must be queued, not lost."""
    from app.db.repositories.motif_retrieve import MotifRetriever

    async def _down(_text):
        raise EmbeddingError("down", retryable=True)

    monkeypatch.setattr("app.db.repositories.motif_retrieve.embed_query", _down)
    rows = [_row("null_vec", embedding=None, tension_target=5, genre_tags=["xianxia"])]
    retr = MotifRetriever(_FakePool(rows))
    await retr.retrieve(
        uuid.uuid4(), book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="climax", tension=90,
    )
    # degrade can still surface it on genre+tension (no vector needed), and it's queued.
    assert any(r["code"] == "null_vec" for r in retr.drain_backfill_queue())


async def test_retrieve_passes_ceiling_to_sql(monkeypatch):
    """data-R1: the pre-filter SQL carries the candidate ceiling (LIMIT) + the genre/
    language/tier predicate — the vector load is bounded, not O(table)."""
    from app.db.repositories.motif_retrieve import MotifRetriever

    _patch_query_embed(monkeypatch, [1.0, 0.0, 0.0])
    pool = _FakePool([_row("a", embedding=[1.0, 0.0, 0.0])])
    retr = MotifRetriever(pool)
    await retr.retrieve(
        uuid.uuid4(), book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50,
    )
    sql = pool.conn.fetched_sql[0].lower()
    assert "status = 'active'" in sql
    assert "language =" in sql
    assert "genre_tags &&" in sql                      # array-overlap pre-filter
    assert "limit" in sql                              # the candidate ceiling
    # the read predicate is present (system | public | owned).
    assert "owner_user_id is null" in sql
    assert "visibility = 'public'" in sql


async def test_retrieve_genreless_omits_overlap_clause(monkeypatch):
    """MD-2: a genre-less book ([]) must still retrieve — the && clause is OMITTED
    (an empty array && is always false → would zero out retrieval)."""
    from app.db.repositories.motif_retrieve import MotifRetriever

    _patch_query_embed(monkeypatch, [1.0, 0.0, 0.0])
    pool = _FakePool([_row("a", embedding=[1.0, 0.0, 0.0])])
    retr = MotifRetriever(pool)
    await retr.retrieve(
        uuid.uuid4(), book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=[], language="en", beat_role="hook", tension=50,
    )
    sql = pool.conn.fetched_sql[0].lower()
    assert "genre_tags &&" not in sql                  # omitted for a genre-less call
    assert "status = 'active'" in sql                  # but still bounded by status/lang


async def test_retrieve_respects_limit(monkeypatch):
    from app.db.repositories.motif_retrieve import MotifRetriever

    rows = [_row(f"m{i}", embedding=[1.0, 0.0, 0.0]) for i in range(20)]
    _patch_query_embed(monkeypatch, [1.0, 0.0, 0.0])
    retr = MotifRetriever(_FakePool(rows))
    out = await retr.retrieve(
        uuid.uuid4(), book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50, limit=5,
    )
    assert len(out) == 5


# ── 2026-07-17 tenancy re-design — two embedding SPACES (shared→platform, private→owner) ──


async def test_private_motif_embeds_with_owner_model_and_bills_owner(monkeypatch):
    """The tenancy fix: a caller's STRICTLY-PRIVATE motif is embedded (inline back-fill —
    the persist path that previously never ran) with the caller's OWN BYOK model, billed to
    the caller, and lands in section='mine' ranked against the U-query. NOT the platform."""
    from app.db.repositories.motif_retrieve import MotifRetriever

    caller = uuid.uuid4()
    _patch_query_embed(monkeypatch, [0.0, 1.0, 0.0])     # P-space query
    _patch_user_query(monkeypatch, [1.0, 0.0, 0.0])      # U-space query (the private motif uses this)
    calls: list[dict] = []
    _patch_private_embed(monkeypatch, [1.0, 0.0, 0.0], record=calls)
    row = _row("secret", embedding=None, owner=caller, genre_tags=["xianxia"])  # private, no vector
    retr = MotifRetriever(_FakePool([row]))
    out = await retr.retrieve(
        caller, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50,
        user_model=("user_model", "user-embed-42"))
    assert [c.motif.code for c in out] == ["secret"]
    assert out[0].match_reason["section"] == "mine"
    assert out[0].match_reason["cosine"] == pytest.approx(1.0)     # ranked vs the U-query
    assert "degraded" not in out[0].match_reason
    assert calls == [{"owner_id": caller, "user_model": ("user_model", "user-embed-42")}]
    # persisted scoped to the owner's OWN private, non-shared row
    assert retr._pool.conn.executed
    assert "owner_user_id = $6 AND visibility = 'private' AND NOT book_shared" in \
        retr._pool.conn.executed[0][0]


async def test_private_motif_without_user_model_degrades_never_platform_embeds(monkeypatch):
    """No BYOK embed model → a private motif ranks NON-SEMANTICALLY (genre+tension, degraded)
    and is NEVER embedded by the platform (the whole point of the fix). No write, no embed."""
    from app.db.repositories.motif_retrieve import MotifRetriever

    caller = uuid.uuid4()
    _patch_query_embed(monkeypatch, [1.0, 0.0, 0.0])
    _patch_platform_backfill_embed(monkeypatch, [1.0, 0.0, 0.0])   # platform embed available…
    calls: list[dict] = []
    _patch_private_embed(monkeypatch, [1.0, 0.0, 0.0], record=calls)
    row = _row("secret", embedding=None, owner=caller, genre_tags=["xianxia"], tension_target=5)
    retr = MotifRetriever(_FakePool([row]))
    out = await retr.retrieve(
        caller, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="climax", tension=90, user_model=None)
    assert out[0].match_reason["section"] == "mine"
    assert out[0].match_reason.get("degraded") is True
    assert calls == []                          # …never called for a private motif
    assert retr._pool.conn.executed == []       # and NO platform write to private content


async def test_two_spaces_rank_against_their_own_query_no_cross_cosine(monkeypatch):
    """A private (U-space) and a shared (P-space) motif each cosine against their OWN query
    vector — never each other's. Both align to their space → ~1.0, separate sections, mine-first."""
    from app.db.repositories.motif_retrieve import MotifRetriever

    caller = uuid.uuid4()
    _patch_query_embed(monkeypatch, [1.0, 0.0, 0.0])     # P query
    _patch_user_query(monkeypatch, [0.0, 1.0, 0.0])      # U query (orthogonal to P)
    shared = _row("lib", embedding=[1.0, 0.0, 0.0])                 # owner None → P-space
    private = _row("mine", embedding=[0.0, 1.0, 0.0], owner=caller)  # U-space
    private["embedding_model"] = "user-embed-42"         # stored in the caller's model space → trusted
    retr = MotifRetriever(_FakePool([shared, private]))
    out = await retr.retrieve(
        caller, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50,
        user_model=("user_model", "user-embed-42"))
    by = {c.motif.code: c for c in out}
    assert by["mine"].match_reason["section"] == "mine"
    assert by["lib"].match_reason["section"] == "library"
    assert by["mine"].match_reason["cosine"] == pytest.approx(1.0)   # vs U query
    assert by["lib"].match_reason["cosine"] == pytest.approx(1.0)    # vs P query
    assert out[0].motif.code == "mine"                   # mine-first
    assert retr._pool.conn.executed == []                # both fresh → no re-embed


async def test_shared_row_with_stale_user_vector_not_cross_cosined(monkeypatch):
    """Cross-space guard: a PUBLIC (shared/P-space) motif still holding a stale USER-model
    vector — a since-PUBLISHED private motif whose owner hasn't re-embedded it yet — is NOT
    cosined against the platform query when the platform ref is known. It is skipped +
    queued, never wrong-space ranked. (On the pre-fix logic this row would score 1.0.)"""
    from app.db.repositories.motif_retrieve import MotifRetriever

    caller = uuid.uuid4()
    _patch_query_embed(monkeypatch, [1.0, 0.0, 0.0])          # platform (P) query
    monkeypatch.setattr("app.db.repositories.motif_retrieve._platform_embed_model",
                        lambda: ("platform_model", "platform-embed-v1"))
    row = _row("published", embedding=[1.0, 0.0, 0.0], genre_tags=["xianxia"])
    row["owner_user_id"] = uuid.uuid4()                       # another user's now-public motif
    row["visibility"] = "public"
    row["embedding_model"] = "someones-user-embed"            # a stale U-space vector, NOT platform
    retr = MotifRetriever(_FakePool([row]))
    out = await retr.retrieve(
        caller, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50, user_model=None)
    assert out == []                                          # skipped — never cross-space cosined
    assert any(r["code"] == "published" for r in retr.drain_backfill_queue())


async def test_book_shared_motif_is_library_space_not_private(monkeypatch):
    """A book_shared motif (visibility='private' but shared to a book's grantees) is a SHARED
    tier → P-space/section='library', embedded by the platform — NOT the owner's private space."""
    from app.db.repositories.motif_retrieve import MotifRetriever

    caller = uuid.uuid4()
    _patch_query_embed(monkeypatch, [1.0, 0.0, 0.0])
    calls: list[dict] = []
    _patch_private_embed(monkeypatch, [1.0, 0.0, 0.0], record=calls)
    row = _row("shared", embedding=[1.0, 0.0, 0.0], owner=caller)   # owner+private…
    row["book_shared"] = True                                       # …but book-shared → SHARED tier
    retr = MotifRetriever(_FakePool([row]))
    out = await retr.retrieve(
        caller, book_id=uuid.uuid4(), project_id=uuid.uuid4(),
        genre_tags=["xianxia"], language="en", beat_role="hook", tension=50,
        user_model=("user_model", "user-embed-42"))
    assert out[0].match_reason["section"] == "library"   # shared, not 'mine'
    assert calls == []                                   # never billed to the owner as private
