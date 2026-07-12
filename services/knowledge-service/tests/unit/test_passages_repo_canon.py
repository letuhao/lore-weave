"""D-RAWSEARCH-CANON-WIRING — infra-free unit guards for the :Passage repo
canon wiring.

The retriever/ingester suites prove the kwargs are *passed*; the integration
suite proves the cypher *filters* (live Neo4j, skipped without TEST_NEO4J_URI).
These tests sit in between: mock the neo4j helpers so a regression in the repo
layer (a dropped `canon=$canon`, a deleted canon WHERE clause) is caught with no
live database — the gap a kwarg-level mock one layer up can't see.
"""
from __future__ import annotations

import hashlib
from unittest.mock import MagicMock

import pytest

from app.db.neo4j_repos.passages import (
    delete_passages_for_source,
    find_passages_by_vector,
    get_chapter_index_for_source,
    get_source_ingest_state,
    passage_canonical_id,
    upsert_passage,
)

DIM = 1024


class _SingleRead:
    """Mimics a run_read result whose single() returns one record (or None)."""

    def __init__(self, record):
        self._record = record

    async def single(self):
        return self._record


class _Result:
    """Mimics the run_write result: a single() returning the upserted node."""

    def __init__(self, node: dict):
        self._node = node

    async def single(self):
        return {"p": self._node}


class _EmptyRead:
    """Async-iterable that yields no rows (we only assert the call wiring)."""

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


@pytest.mark.asyncio
async def test_upsert_passage_wires_canon_into_write(monkeypatch):
    captured: dict = {}

    async def fake_write(session, cypher, **kwargs):
        captured["cypher"] = cypher
        captured["kwargs"] = kwargs
        # Echo a node back so _node_to_passage round-trips the flag.
        return _Result({
            "id": kwargs["id"], "user_id": kwargs["user_id"],
            "source_type": "chapter", "source_id": "s", "chunk_index": 0,
            "text": "t", "canon": kwargs["canon"],
        })

    monkeypatch.setattr("app.db.neo4j_repos.passages.run_write", fake_write)

    p = await upsert_passage(
        MagicMock(), user_id="u", project_id="p", source_type="chapter",
        source_id="s", chunk_index=0, text="t",
        embedding=[0.1] * DIM, embedding_dim=DIM, canon=False,
    )
    # canon reaches the write …
    assert captured["kwargs"]["canon"] is False
    # … the cypher actually sets it (both ON CREATE and ON MATCH) …
    assert captured["cypher"].count("p.canon = $canon") == 2
    # … and it round-trips onto the projection.
    assert p.canon is False


@pytest.mark.asyncio
async def test_upsert_passage_defaults_canon_true(monkeypatch):
    captured: dict = {}

    async def fake_write(session, cypher, **kwargs):
        captured["kwargs"] = kwargs
        return _Result({
            "id": kwargs["id"], "user_id": kwargs["user_id"],
            "source_type": "chapter", "source_id": "s", "chunk_index": 0,
            "text": "t", "canon": kwargs["canon"],
        })

    monkeypatch.setattr("app.db.neo4j_repos.passages.run_write", fake_write)
    await upsert_passage(
        MagicMock(), user_id="u", project_id="p", source_type="chapter",
        source_id="s", chunk_index=0, text="t",
        embedding=[0.1] * DIM, embedding_dim=DIM,
    )
    assert captured["kwargs"]["canon"] is True  # published-by-default


@pytest.mark.asyncio
@pytest.mark.parametrize("include_drafts", [True, False])
async def test_find_wires_include_drafts_and_canon_clause(monkeypatch, include_drafts):
    captured: dict = {}

    async def fake_read(session, cypher, **kwargs):
        captured["cypher"] = cypher
        captured["kwargs"] = kwargs
        return _EmptyRead()

    monkeypatch.setattr("app.db.neo4j_repos.passages.run_read", fake_read)

    await find_passages_by_vector(
        MagicMock(), user_id="u", project_id="p",
        query_vector=[0.1] * DIM, dim=DIM, include_drafts=include_drafts,
    )
    # the flag is forwarded to the read …
    assert captured["kwargs"]["include_drafts"] is include_drafts
    # … and the canon gate is present in the cypher (legacy null = canon).
    assert "$include_drafts" in captured["cypher"]
    assert "coalesce(node.canon, true) = true" in captured["cypher"]


# -- M1b get_chapter_index_for_source ------------------------------


@pytest.mark.asyncio
async def test_get_chapter_index_resolves_and_scopes(monkeypatch):
    """Resolver returns the int index and scopes by user+project+chapter,
    filtering to source_type='chapter'."""
    captured: dict = {}

    async def fake_read(session, cypher, **kwargs):
        captured["cypher"] = cypher
        captured["kwargs"] = kwargs
        return _SingleRead({"chapter_index": 42})

    monkeypatch.setattr("app.db.neo4j_repos.passages.run_read", fake_read)

    idx = await get_chapter_index_for_source(
        MagicMock(), user_id="u", project_id="p", chapter_id="ch-1",
    )
    assert idx == 42
    assert captured["kwargs"] == {"user_id": "u", "project_id": "p", "chapter_id": "ch-1"}
    # tenancy + type scoping present in the cypher.
    assert "p.user_id = $user_id" in captured["cypher"]
    assert "p.project_id = $project_id" in captured["cypher"]
    assert "p.source_type = 'chapter'" in captured["cypher"]
    assert "p.source_id = $chapter_id" in captured["cypher"]


@pytest.mark.asyncio
async def test_get_chapter_index_none_when_no_passages(monkeypatch):
    """No ingested passages for the chapter (not extracted / stale id) → None,
    so the caller skips the boost rather than erroring."""
    async def fake_read(session, cypher, **kwargs):
        return _SingleRead(None)

    monkeypatch.setattr("app.db.neo4j_repos.passages.run_read", fake_read)
    idx = await get_chapter_index_for_source(
        MagicMock(), user_id="u", project_id="p", chapter_id="ch-x",
    )
    assert idx is None


@pytest.mark.asyncio
async def test_get_chapter_index_none_when_index_null(monkeypatch):
    """A passage row with a NULL chapter_index → None (never int(None))."""
    async def fake_read(session, cypher, **kwargs):
        return _SingleRead({"chapter_index": None})

    monkeypatch.setattr("app.db.neo4j_repos.passages.run_read", fake_read)
    idx = await get_chapter_index_for_source(
        MagicMock(), user_id="u", project_id="p", chapter_id="ch-1",
    )
    assert idx is None


# -- D-R20 (P-3) keep-both: canon-discriminated passage ids + scoped reap ----


def _legacy_passage_id(
    *, user_id, project_id, source_type, source_id, chunk_index, source_lang=""
) -> str:
    """Recompute the PRE-P-3 id (no canon segment) so the byte-identical contract
    for canon=True is pinned — a future format drift that adds a segment to the
    published bucket reds this."""
    lang_seg = f"{source_lang}:" if source_lang else ""
    key = (
        f"v1:{user_id}:{project_id or 'global'}:"
        f"{source_type}:{source_id}:{lang_seg}{chunk_index}"
    )
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def test_canonical_id_canon_true_is_byte_identical_to_legacy():
    """canon=True (published) must produce the exact pre-P-3 id — zero re-key
    churn for every already-ingested canon passage (mirrors the source_lang trick)."""
    for lang in ("", "zh"):
        canon_id = passage_canonical_id(
            user_id="u", project_id="p", source_type="chapter",
            source_id="ch", chunk_index=3, source_lang=lang, canon=True,
        )
        default_id = passage_canonical_id(
            user_id="u", project_id="p", source_type="chapter",
            source_id="ch", chunk_index=3, source_lang=lang,
        )
        legacy_id = _legacy_passage_id(
            user_id="u", project_id="p", source_type="chapter",
            source_id="ch", chunk_index=3, source_lang=lang,
        )
        assert canon_id == default_id == legacy_id  # default is canon=True


def test_canonical_id_draft_is_distinct_bucket():
    """canon=False (draft) forks a DISTINCT id from canon for the SAME chunk, so
    indexing a draft on a published chapter can't MERGE onto (clobber) the canon
    node — the two buckets coexist. Holds per language."""
    for lang in ("", "zh"):
        canon_id = passage_canonical_id(
            user_id="u", project_id="p", source_type="chapter",
            source_id="ch", chunk_index=0, source_lang=lang, canon=True,
        )
        draft_id = passage_canonical_id(
            user_id="u", project_id="p", source_type="chapter",
            source_id="ch", chunk_index=0, source_lang=lang, canon=False,
        )
        assert canon_id != draft_id


@pytest.mark.asyncio
@pytest.mark.parametrize("canon", [None, True, False])
async def test_delete_passages_for_source_scopes_canon(monkeypatch, canon):
    """The reap forwards `canon` to the write and the cypher gates on it
    (None = both buckets; a bool = only that bucket). A dropped canon clause
    would make a draft index wipe the published canon set — the keep-both bug."""
    captured: dict = {}

    async def fake_write(session, cypher, **kwargs):
        captured["cypher"] = cypher
        captured["kwargs"] = kwargs
        return _SingleRead({"deleted": 0})

    monkeypatch.setattr("app.db.neo4j_repos.passages.run_write", fake_write)

    await delete_passages_for_source(
        MagicMock(), user_id="u", source_type="chapter", source_id="ch",
        canon=canon,
    )
    assert captured["kwargs"]["canon"] is canon
    assert "($canon IS NULL OR coalesce(p.canon, true) = $canon)" in captured["cypher"]


@pytest.mark.asyncio
async def test_delete_passages_for_source_defaults_to_both_buckets(monkeypatch):
    """Back-compat: no `canon` arg → None → the clause is inert (both buckets),
    so chapter-delete / kg_excluded retract still drops everything."""
    captured: dict = {}

    async def fake_write(session, cypher, **kwargs):
        captured["kwargs"] = kwargs
        return _SingleRead({"deleted": 0})

    monkeypatch.setattr("app.db.neo4j_repos.passages.run_write", fake_write)
    await delete_passages_for_source(
        MagicMock(), user_id="u", source_type="chapter", source_id="ch",
    )
    assert captured["kwargs"]["canon"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize("canon", [None, True, False])
async def test_get_source_ingest_state_scopes_canon(monkeypatch, canon):
    """The skip-gate read forwards `canon` and gates the cypher on it, so the
    canon and draft buckets have INDEPENDENT content-hash gates (no cross-bucket
    false-miss/false-hit once keep-both lets both coexist)."""
    captured: dict = {}

    async def fake_read(session, cypher, **kwargs):
        captured["cypher"] = cypher
        captured["kwargs"] = kwargs
        return _SingleRead(None)  # cache miss

    monkeypatch.setattr("app.db.neo4j_repos.passages.run_read", fake_read)
    await get_source_ingest_state(
        MagicMock(), user_id="u", source_type="chapter", source_id="ch",
        canon=canon,
    )
    assert captured["kwargs"]["canon"] is canon
    assert "($canon IS NULL OR coalesce(p.canon, true) = $canon)" in captured["cypher"]
