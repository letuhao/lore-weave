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
