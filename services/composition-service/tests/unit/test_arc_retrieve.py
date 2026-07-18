"""D-ARC-RETRIEVE — MotifRetriever.retrieve_arcs (composition_arc_suggest's source).

Mirrors test_motif_retrieve's harness but over arc_template, and adds coverage for the
arc-specific lazy inline embedding back-fill (NULL-vector arcs earn a vector on first
suggest, bounded + best-effort; an arc is NEVER dropped just for being unembedded).
"""

from __future__ import annotations

import uuid

import pytest

from app.clients.embedding_client import EmbeddingError

pytestmark = pytest.mark.asyncio


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


def _arc(code, *, embedding, genre_tags=("xianxia",), owner=None):
    """An arc_template row dict shaped like _ARC_RETRIEVE_COLS (incl. embedding)."""
    return {
        "id": uuid.uuid4(), "owner_user_id": owner, "code": code, "language": "en",
        "visibility": "public" if owner is None else "private", "name": code,
        "summary": "an arc", "genre_tags": list(genre_tags), "chapter_span": 12,
        "threads": "[]", "layout": "[]", "pacing": "[]", "arc_roster": "[]",
        "source": "authored", "imported_derived": False, "source_ref": None,
        "source_version": None, "embedding_model": "m" if embedding else "",
        "embedding_dim": 3 if embedding else None, "status": "active", "version": 1,
        "created_at": None, "updated_at": None,
        "embedded_summary_hash": "h" if embedding else None, "embedding": embedding,
    }


def _patch_query(monkeypatch, vector):
    async def _q(_text):
        return vector
    monkeypatch.setattr("app.db.repositories.motif_retrieve.embed_query", _q)


def _patch_backfill_embed(monkeypatch, vector, *, raises=False):
    class _Res:
        embeddings = [vector]

    async def _embed(_text):
        if raises:
            raise EmbeddingError("provider down", retryable=True)
        return _Res()
    monkeypatch.setattr("app.db.repositories.motif_retrieve.embed_motif_summary", _embed)
    monkeypatch.setattr("app.db.repositories.motif_retrieve._platform_embed_model",
                        lambda: ("platform_model", "platform-embed-v1"))


def _patch_user_query(monkeypatch, vector):
    """The U-space (caller's BYOK) query embedding — the counterpart to _patch_query's
    platform/P-space one. Records nothing; just returns the fixed vector."""
    async def _q(_text, *, user_id, model):
        return vector
    monkeypatch.setattr("app.db.repositories.motif_retrieve.embed_query_with", _q)


def _patch_private_embed(monkeypatch, vector, *, record=None, raises=False):
    """The private-arc write embed (owner's BYOK model). `record` captures the owner_id +
    user_model each call is billed to, so a test can assert the OWNER pays (tenancy fix)."""
    class _Res:
        embeddings = [vector]

    async def _embed(_text, *, owner_id, user_model):
        if record is not None:
            record.append({"owner_id": owner_id, "user_model": user_model})
        if raises:
            raise EmbeddingError("provider down", retryable=True)
        return _Res()
    monkeypatch.setattr("app.db.repositories.motif_retrieve.embed_private_summary", _embed)


def _retriever(rows):
    from app.db.repositories.motif_retrieve import MotifRetriever
    return MotifRetriever(_FakePool(rows))


async def test_retrieve_arcs_empty_prefilter_returns_empty(monkeypatch):
    _patch_query(monkeypatch, [1.0, 0.0, 0.0])
    out = await _retriever([]).retrieve_arcs(uuid.uuid4(), premise="x", genre="xianxia")
    assert out == []


async def test_retrieve_arcs_ranks_by_cosine(monkeypatch):
    _patch_query(monkeypatch, [1.0, 0.0, 0.0])
    rows = [
        _arc("near", embedding=[1.0, 0.0, 0.0]),   # cos 1.0
        _arc("mid", embedding=[1.0, 1.0, 0.0]),    # cos ~0.707
        _arc("far", embedding=[0.0, 1.0, 0.0]),    # cos 0.0
    ]
    out = await _retriever(rows).retrieve_arcs(uuid.uuid4(), premise="rise", genre="xianxia")
    assert [c.arc_template.code for c in out] == ["near", "mid", "far"]
    assert out[0].score == pytest.approx(1.0)
    assert out[0].match_reason["cosine"] == pytest.approx(1.0)


async def test_retrieve_arcs_result_has_no_embedding(monkeypatch):
    _patch_query(monkeypatch, [1.0, 0.0, 0.0])
    out = await _retriever([_arc("a", embedding=[1.0, 0.0, 0.0])]).retrieve_arcs(
        uuid.uuid4(), premise="p")
    # the ArcTemplate model has no embedding field at all → never leaks server-side vectors
    assert not hasattr(out[0].arc_template, "embedding")


async def test_retrieve_arcs_backfills_null_embedding_then_cosine(monkeypatch):
    """A NULL-vector arc is embedded INLINE (best-effort) and persisted, then cosine-ranked
    — not skipped (the arc-specific divergence from the motif retrieve)."""
    _patch_query(monkeypatch, [1.0, 0.0, 0.0])
    _patch_backfill_embed(monkeypatch, [1.0, 0.0, 0.0])
    pool_rows = [_arc("cold", embedding=None)]
    retr = _retriever(pool_rows)
    out = await retr.retrieve_arcs(uuid.uuid4(), premise="rise", genre="xianxia")
    assert [c.arc_template.code for c in out] == ["cold"]
    assert out[0].match_reason["cosine"] == pytest.approx(1.0)
    assert "degraded" not in out[0].match_reason          # it got a real vector
    # the back-fill persisted via an UPDATE arc_template … and is OWNER-SCOPED (never a
    # cross-tenant write — a read must not mutate another tenant's row).
    assert retr._pool.conn.executed and "UPDATE arc_template" in retr._pool.conn.executed[0][0]
    assert "owner_user_id IS NULL OR owner_user_id = $6" in retr._pool.conn.executed[0][0]


async def test_retrieve_arcs_does_not_backfill_a_foreign_public_arc(monkeypatch):
    """TENANCY: a NULL-vector arc owned by ANOTHER user is NEVER back-filled (a read must
    not trigger a cross-tenant write) — it ranks on genre this call; its owner back-fills it."""
    _patch_query(monkeypatch, [1.0, 0.0, 0.0])
    _patch_backfill_embed(monkeypatch, [1.0, 0.0, 0.0])
    foreign = _arc("foreign", embedding=None, genre_tags=["xianxia"])
    foreign["owner_user_id"] = uuid.uuid4()               # someone else's public arc, no vector
    retr = _retriever([foreign])
    out = await retr.retrieve_arcs(uuid.uuid4(), premise="rise", genre="xianxia")
    assert [c.arc_template.code for c in out] == ["foreign"]   # still surfaced…
    assert out[0].match_reason.get("degraded") is True        # …but genre-ranked, not embedded
    assert retr._pool.conn.executed == []                     # NO write to the foreign row


async def test_retrieve_arcs_backfill_failure_degrades_to_genre(monkeypatch):
    """Embed outage during back-fill → the arc still surfaces (genre rank), never dropped."""
    _patch_query(monkeypatch, [1.0, 0.0, 0.0])
    _patch_backfill_embed(monkeypatch, [1.0, 0.0, 0.0], raises=True)
    out = await _retriever([_arc("cold", embedding=None, genre_tags=["xianxia"])]).retrieve_arcs(
        uuid.uuid4(), premise="rise", genre="xianxia")
    assert [c.arc_template.code for c in out] == ["cold"]
    assert out[0].match_reason.get("degraded") is True
    assert out[0].match_reason["genre"] == pytest.approx(1.0)


async def test_retrieve_arcs_query_outage_degrades_to_genre(monkeypatch):
    """No query vector (embed down) → genre order over the same set, no back-fill, degraded."""
    async def _boom(_t):
        raise EmbeddingError("down", retryable=True)
    monkeypatch.setattr("app.db.repositories.motif_retrieve.embed_query", _boom)
    rows = [_arc("match", embedding=[1.0, 0.0, 0.0], genre_tags=["xianxia"]),
            _arc("nomatch", embedding=[1.0, 0.0, 0.0], genre_tags=["other"])]
    retr = _retriever(rows)
    out = await retr.retrieve_arcs(uuid.uuid4(), premise="x", genre="xianxia")
    assert out[0].arc_template.code == "match"          # genre overlap wins
    assert all(c.match_reason.get("degraded") for c in out)
    assert retr._pool.conn.executed == []               # no back-fill without a query vec


async def test_retrieve_arcs_genre_filter_and_predicate_in_sql(monkeypatch):
    _patch_query(monkeypatch, [1.0, 0.0, 0.0])
    retr = _retriever([_arc("a", embedding=[1.0, 0.0, 0.0])])
    caller = uuid.uuid4()
    await retr.retrieve_arcs(caller, premise="p", genre="xianxia", limit=3)
    sql = retr._pool.conn.fetched_sql[0]
    assert "FROM arc_template" in sql
    assert "owner_user_id IS NULL OR visibility = 'public' OR owner_user_id = $1" in sql
    assert "genre_tags &&" in sql and "LIMIT $2" in sql
    assert retr._pool.conn.fetched_args[0][0] == caller   # $1 = caller


async def test_retrieve_arcs_backfill_is_capped(monkeypatch):
    """More NULL arcs than the per-call cap → at most _ARC_BACKFILL_CAP inline embeds."""
    from app.db.repositories import motif_retrieve as mr
    _patch_query(monkeypatch, [1.0, 0.0, 0.0])
    _patch_backfill_embed(monkeypatch, [1.0, 0.0, 0.0])
    rows = [_arc(f"a{i}", embedding=None) for i in range(mr._ARC_BACKFILL_CAP + 5)]
    retr = _retriever(rows)
    await retr.retrieve_arcs(uuid.uuid4(), premise="p", limit=50)
    assert len(retr._pool.conn.executed) == mr._ARC_BACKFILL_CAP


# ── 2026-07-17 tenancy re-design — two embedding SPACES (shared→platform, private→owner) ──


async def test_private_arc_embeds_with_owner_model_and_bills_owner(monkeypatch):
    """The tenancy fix: a caller's STRICTLY-PRIVATE arc is embedded with the caller's OWN
    BYOK model (billed to the caller), NOT the platform model, and persisted scoped to the
    owner's own private row. It lands in section='mine' and cosines against the U-query."""
    caller = uuid.uuid4()
    _patch_query(monkeypatch, [0.0, 1.0, 0.0])          # P-space query (a shared arc would use it)
    _patch_user_query(monkeypatch, [1.0, 0.0, 0.0])     # U-space query (the private arc uses THIS)
    calls: list[dict] = []
    _patch_private_embed(monkeypatch, [1.0, 0.0, 0.0], record=calls)
    row = _arc("secret", embedding=None, owner=caller)  # owner set → visibility 'private'
    retr = _retriever([row])
    out = await retr.retrieve_arcs(
        caller, premise="rise", genre="xianxia", user_model=("user_model", "user-embed-42"))
    assert [c.arc_template.code for c in out] == ["secret"]
    assert out[0].match_reason["section"] == "mine"
    assert out[0].match_reason["cosine"] == pytest.approx(1.0)          # ranked vs the U-query
    assert "degraded" not in out[0].match_reason
    # billed to the OWNER (caller) with the caller's model — never the platform credential
    assert calls == [{"owner_id": caller, "user_model": ("user_model", "user-embed-42")}]
    # persisted scoped to the owner's OWN private row (a read can't rewrite a since-published arc)
    assert "owner_user_id = $6 AND visibility = 'private'" in retr._pool.conn.executed[0][0]


async def test_private_arc_without_user_model_degrades_never_platform_embeds(monkeypatch):
    """No BYOK embed model → a private arc falls back to NON-SEMANTIC (genre) ranking and is
    NEVER embedded by the platform (the whole point of the fix). No write, no private embed."""
    caller = uuid.uuid4()
    _patch_query(monkeypatch, [1.0, 0.0, 0.0])
    _patch_backfill_embed(monkeypatch, [1.0, 0.0, 0.0])   # platform embed available…
    calls: list[dict] = []
    _patch_private_embed(monkeypatch, [1.0, 0.0, 0.0], record=calls)
    row = _arc("secret", embedding=None, owner=caller, genre_tags=["xianxia"])
    retr = _retriever([row])
    out = await retr.retrieve_arcs(caller, premise="rise", genre="xianxia", user_model=None)
    assert out[0].match_reason["section"] == "mine"
    assert out[0].match_reason.get("degraded") is True
    assert out[0].match_reason["genre"] == pytest.approx(1.0)
    assert calls == []                          # …never called for a private arc
    assert retr._pool.conn.executed == []       # and NO platform write to private content


async def test_two_spaces_rank_against_their_own_query_no_cross_cosine(monkeypatch):
    """A private (U-space) and a shared (P-space) arc each cosine against their OWN query
    vector — never each other's. Both align to their space's query → both ~1.0, in separate
    sections, mine-first. Proves the platform query never touches the private vector."""
    caller = uuid.uuid4()
    _patch_query(monkeypatch, [1.0, 0.0, 0.0])          # P query
    _patch_user_query(monkeypatch, [0.0, 1.0, 0.0])     # U query (orthogonal to P)
    shared = _arc("lib", embedding=[1.0, 0.0, 0.0])                 # owner None → P-space, ~P query
    private = _arc("mine", embedding=[0.0, 1.0, 0.0], owner=caller)  # U-space, ~U query
    private["embedding_model"] = "user-embed-42"        # stored in the caller's model space → trusted
    retr = _retriever([shared, private])
    out = await retr.retrieve_arcs(
        caller, premise="x", genre="xianxia", user_model=("user_model", "user-embed-42"))
    by = {c.arc_template.code: c for c in out}
    assert by["mine"].match_reason["section"] == "mine"
    assert by["lib"].match_reason["section"] == "library"
    assert by["mine"].match_reason["cosine"] == pytest.approx(1.0)   # vs U query
    assert by["lib"].match_reason["cosine"] == pytest.approx(1.0)    # vs P query
    assert out[0].arc_template.code == "mine"           # mine-first
    assert retr._pool.conn.executed == []               # both vectors were fresh → no re-embed


async def test_legacy_private_arc_with_platform_vector_reembeds_with_owner_model(monkeypatch):
    """Lazy migration: a private arc still holding a LEGACY platform vector (embedding_model
    != the caller's model) is re-embedded with the owner's model on read — not trusted as-is
    (that would cosine a platform vector against the U-query)."""
    caller = uuid.uuid4()
    _patch_query(monkeypatch, [0.0, 1.0, 0.0])
    _patch_user_query(monkeypatch, [1.0, 0.0, 0.0])
    calls: list[dict] = []
    _patch_private_embed(monkeypatch, [1.0, 0.0, 0.0], record=calls)
    row = _arc("legacy", embedding=[0.0, 1.0, 0.0], owner=caller)  # has a vector…
    row["embedding_model"] = "platform-embed-v1"                    # …but in the PLATFORM space
    retr = _retriever([row])
    out = await retr.retrieve_arcs(
        caller, premise="x", genre="xianxia", user_model=("user_model", "user-embed-42"))
    assert calls and calls[0]["owner_id"] == caller     # re-embedded with the owner's model
    assert out[0].match_reason["cosine"] == pytest.approx(1.0)   # now vs U-query, fresh vector
    assert "visibility = 'private'" in retr._pool.conn.executed[0][0]
