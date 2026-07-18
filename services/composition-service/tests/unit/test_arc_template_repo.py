"""W10 — ArcTemplateRepo unit tests (no DB) via a recording fake pool.

These prove the repo's SQL-BUILDING behavior without a Postgres: the read predicate
(system|public|owner) is present on every read, the conditional-param binding does NOT
bind an unused $1 (the R-NODE-P1 scope=system 500 lesson), patch is owner-scoped +
version-guarded, archive is owner-scoped, the catalog projection is the allow-list (no
embedding / raw source_ref leak), and rows map back through the model (JSONB decoded,
embedding never projected). The full SQL-against-Postgres guards live in the integration
suite (gated on TEST_COMPOSITION_DB_URL).

House style: the recording fake pool mirrors tests/unit/test_motif_retrieve.py's
_FakePool/_FakeConn.
"""

from __future__ import annotations

import json
import uuid

import asyncpg
import pytest

from app.db.models import (
    ArcPlacement,
    ArcRosterEntry,
    ArcTemplate,
    ArcTemplateCreateArgs,
    ArcTemplatePatchArgs,
    ArcThread,
)
from app.db.repositories import VersionMismatchError
from app.db.repositories.arc_template_repo import (
    _SELECT_COLS,
    _VISIBLE_PREDICATE,
    ArcTemplateRepo,
)

USER = uuid.uuid4()
OTHER = uuid.uuid4()


def _arc_row(**kw) -> dict:
    """A row shaped like the arc_template SELECT (JSONB as json strings, asyncpg-style)."""
    return {
        "id": kw.get("id", uuid.uuid4()),
        "owner_user_id": kw.get("owner_user_id", USER),
        "code": kw.get("code", "arc.three-year-pact"),
        "language": "en",
        "visibility": kw.get("visibility", "private"),
        "name": kw.get("name", "Three-Year Pact"),
        "summary": kw.get("summary", ""),
        "genre_tags": kw.get("genre_tags", ["xianxia"]),
        "chapter_span": kw.get("chapter_span", 30),
        "threads": kw.get("threads", '[{"key": "combat", "label": "Combat"}]'),
        "layout": kw.get("layout", "[]"),
        "pacing": kw.get("pacing", "[]"),
        "arc_roster": kw.get("arc_roster", "[]"),
        "source": kw.get("source", "authored"),
        "imported_derived": kw.get("imported_derived", False),
        "source_ref": kw.get("source_ref", None),
        "source_version": kw.get("source_version", None),
        "embedding_model": "",
        "embedding_dim": None,
        "status": kw.get("status", "active"),
        "version": kw.get("version", 1),
        "created_at": None,
        "updated_at": None,
    }


class _FakeConn:
    """Records every (sql, args) and returns canned rows. fetchrow returns rows[0] (or
    the queued sequence), fetch returns the list, fetchval returns the scalar."""

    def __init__(self, *, rows=None, rowseq=None, scalar=0):
        self._rows = rows or []
        self._rowseq = list(rowseq) if rowseq is not None else None
        self._scalar = scalar
        self.calls: list[tuple[str, tuple]] = []

    async def fetchrow(self, sql, *args):
        self.calls.append((sql, args))
        if self._rowseq is not None:
            return self._rowseq.pop(0) if self._rowseq else None
        return self._rows[0] if self._rows else None

    async def fetch(self, sql, *args):
        self.calls.append((sql, args))
        return self._rows

    async def fetchval(self, sql, *args):
        self.calls.append((sql, args))
        return self._scalar

    async def execute(self, sql, *args):
        self.calls.append((sql, args))
        return "UPDATE 1"


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, conn):
        self.conn = conn

    def acquire(self):
        return _FakeAcquire(self.conn)


def _repo(conn):
    return ArcTemplateRepo(_FakePool(conn))


# ── create ───────────────────────────────────────────────────────────────────────
async def test_create_stamps_owner_and_maps_row():
    conn = _FakeConn(rows=[_arc_row(owner_user_id=USER)])
    repo = _repo(conn)
    args = ArcTemplateCreateArgs(
        code="arc.x", name="X",
        threads=[ArcThread(key="combat", label="Combat")],
        layout=[ArcPlacement(motif_code="m.a", thread="combat", span_start=1, span_end=3)],
        arc_roster=[ArcRosterEntry(key="protagonist", actant="subject")],
    )
    arc = await repo.create(USER, args)
    sql, params = conn.calls[0]
    assert "INSERT INTO arc_template" in sql
    # owner_user_id is the FIRST bound param (server-stamped = caller, never an arg).
    assert params[0] == USER
    assert isinstance(arc, ArcTemplate)
    # JSONB decoded back to a list on read.
    assert arc.threads == [{"key": "combat", "label": "Combat"}]


# ── get_visible: the read predicate ───────────────────────────────────────────────
async def test_get_visible_uses_read_predicate_and_binds_caller():
    arc_id = uuid.uuid4()
    conn = _FakeConn(rows=[_arc_row()])
    await _repo(conn).get_visible(USER, arc_id)
    sql, params = conn.calls[0]
    assert _VISIBLE_PREDICATE in sql
    assert params == (USER, arc_id)          # $1=caller, $2=arc_id


async def test_get_visible_foreign_private_returns_none():
    # the DB read predicate excludes a foreign private row → fetchrow returns None.
    conn = _FakeConn(rows=[])
    arc = await _repo(conn).get_visible(USER, uuid.uuid4())
    assert arc is None


# ── list_for_caller: the conditional-param binding (R-NODE-P1) ─────────────────────
async def test_list_scope_system_does_not_bind_unused_caller():
    # the R-NODE-P1 lesson: scope=system filters on owner_user_id IS NULL alone — the
    # caller_id must NOT be bound as $1 (asyncpg would raise IndeterminateDatatypeError).
    conn = _FakeConn(rows=[_arc_row(owner_user_id=None)])
    await _repo(conn).list_for_caller(USER, scope="system")
    sql, params = conn.calls[0]
    assert "owner_user_id IS NULL" in sql
    assert USER not in params               # caller NOT bound for a system scope
    assert _VISIBLE_PREDICATE not in sql


async def test_list_scope_public_does_not_bind_unused_caller():
    conn = _FakeConn(rows=[])
    await _repo(conn).list_for_caller(USER, scope="public")
    sql, params = conn.calls[0]
    assert "visibility = 'public'" in sql
    assert USER not in params


async def test_list_scope_all_binds_caller_in_predicate():
    conn = _FakeConn(rows=[])
    await _repo(conn).list_for_caller(USER, scope="all")
    sql, params = conn.calls[0]
    assert _VISIBLE_PREDICATE in sql
    assert params[0] == USER                # $1 = caller (used by the predicate)


async def test_list_scope_user_filters_owner_eq_caller():
    conn = _FakeConn(rows=[])
    await _repo(conn).list_for_caller(USER, scope="user")
    sql, params = conn.calls[0]
    assert "owner_user_id = $1" in sql
    assert params[0] == USER


async def test_list_appends_genre_status_language_q_filters():
    conn = _FakeConn(rows=[])
    await _repo(conn).list_for_caller(
        USER, scope="system", genre="xianxia", status="active",
        language="en", q="pact", limit=25,
    )
    sql, params = conn.calls[0]
    assert "= ANY(genre_tags)" in sql
    assert "ILIKE" in sql
    assert "xianxia" in params and "active" in params and "en" in params
    assert "%pact%" in params
    assert params[-1] == 25                  # LIMIT bound last


# ── patch: owner-scoped + version guard ────────────────────────────────────────────
async def test_patch_is_owner_scoped_and_version_guarded():
    conn = _FakeConn(rows=[_arc_row(version=2, name="New")])
    repo = _repo(conn)
    out = await repo.patch(
        USER, uuid.uuid4(), ArcTemplatePatchArgs(name="New"), expected_version=1,
    )
    sql, params = conn.calls[0]
    assert "UPDATE arc_template" in sql
    assert "owner_user_id = $1" in sql
    assert "version = version + 1" in sql
    assert "AND version = $" in sql          # optimistic lock present
    assert out is not None and out.version == 2


async def test_patch_summary_change_clears_embed_hash():
    conn = _FakeConn(rows=[_arc_row()])
    await _repo(conn).patch(
        USER, uuid.uuid4(), ArcTemplatePatchArgs(summary="new summary"),
        expected_version=1,
    )
    sql, _ = conn.calls[0]
    assert "embedded_summary_hash = NULL" in sql


async def test_patch_not_owned_returns_none():
    # no row updated AND no current row owned by caller → None (router → H13 404).
    conn = _FakeConn(rowseq=[None, None])     # update miss, then current-lookup miss
    out = await _repo(conn).patch(
        USER, uuid.uuid4(), ArcTemplatePatchArgs(name="x"), expected_version=1,
    )
    assert out is None


async def test_patch_stale_version_raises_mismatch():
    # update miss BUT the row exists for the caller → stale version → raise w/ current.
    conn = _FakeConn(rowseq=[None, _arc_row(version=5)])
    with pytest.raises(VersionMismatchError) as ei:
        await _repo(conn).patch(
            USER, uuid.uuid4(), ArcTemplatePatchArgs(name="x"), expected_version=1,
        )
    assert ei.value.current.version == 5


# ── archive: owner-scoped soft delete ──────────────────────────────────────────────
async def test_archive_is_owner_scoped_soft_delete():
    conn = _FakeConn()
    await _repo(conn).archive(USER, uuid.uuid4())
    sql, params = conn.calls[0]
    assert "status = 'archived'" in sql
    assert "owner_user_id = $1" in sql
    assert params[0] == USER


# ── clone (= adopt) ────────────────────────────────────────────────────────────────
async def test_clone_copies_source_and_stamps_lineage():
    src_id = uuid.uuid4()
    src = _arc_row(owner_user_id=OTHER, visibility="public", version=4, source="authored")
    # the clone read also pulls the embedding cols (excluded from the model projection).
    src["embedding"] = None
    src["embedded_summary_hash"] = None
    new = _arc_row(owner_user_id=USER, source_ref=f"lineage:{src_id}")
    # clone reads the source (with embedding cols), then inserts the new row.
    conn = _FakeConn(rowseq=[src, new])
    out = await _repo(conn).clone(USER, src_id, target_owner=USER)
    read_sql, read_params = conn.calls[0]
    ins_sql, ins_params = conn.calls[1]
    assert _VISIBLE_PREDICATE in read_sql     # may only clone what you can see
    assert "embedding" in read_sql            # source vector copied
    assert "INSERT INTO arc_template" in ins_sql
    assert ins_params[0] == USER              # new owner = target
    assert f"lineage:{src_id}" in ins_params  # lineage source_ref stamped
    assert isinstance(out, ArcTemplate)


async def test_clone_invisible_source_raises_lookup():
    conn = _FakeConn(rowseq=[None])           # source not visible → read returns None
    with pytest.raises(LookupError):
        await _repo(conn).clone(USER, uuid.uuid4(), target_owner=USER)


# ── catalog allow-list (B-3 analogue: no embedding / no raw source_ref leak) ───────
async def test_catalog_projection_is_allow_list_no_leak():
    # The effective RESULT key of each projected column (25 M5.2: the track skeleton is now the
    # `tracks` column aliased back to the `threads` result key — the API name is unchanged).
    keys = {c.split(" AS ")[-1].strip() for c in ArcTemplateRepo._CATALOG_COLS}
    assert "embedding" not in keys
    assert "source_ref" not in keys          # raw lineage id never leaves on the catalog
    assert "layout" not in keys              # heavy placement detail is a get_visible away
    assert "arc_roster" not in keys and "roster" not in keys
    # the at-a-glance fields ARE present (threads = the aliased tracks column).
    for c in ("id", "code", "name", "summary", "genre_tags", "chapter_span", "threads"):
        assert c in keys


async def test_list_public_filters_public_active_and_returns_total():
    row = {
        "id": uuid.uuid4(), "code": "arc.x", "language": "en", "name": "X",
        "summary": "", "genre_tags": ["xianxia"], "chapter_span": 30,
        "threads": '[{"key": "combat"}]', "source": "authored", "version": 1,
        "updated_at": None,
    }
    conn = _FakeConn(rows=[row], scalar=7)
    items, total = await _repo(conn).list_public(genre="xianxia", q="x", language="en")
    # the LIST query (calls[0]) carries the public+active filter + allow-list cols.
    list_sql, _ = conn.calls[0]
    assert "visibility = 'public'" in list_sql and "status = 'active'" in list_sql
    assert "embedding" not in list_sql
    assert total == 7
    assert items[0]["threads"] == [{"key": "combat"}]   # JSONB decoded


async def test_count_shared_by_owner_counts_shareable_active():
    conn = _FakeConn(scalar=3)
    n = await _repo(conn).count_shared_by_owner(USER)
    sql, params = conn.calls[0]
    assert "visibility IN ('public','unlisted')" in sql
    assert "status <> 'archived'" in sql
    assert params[0] == USER
    assert n == 3
