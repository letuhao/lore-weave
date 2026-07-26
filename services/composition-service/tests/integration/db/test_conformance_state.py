"""26 IX-8/IX-9/IX-14 — durable conformance snapshots + the staleness read contract.

Gated on TEST_COMPOSITION_DB_URL (a THROWAWAY DB — the fixture drops the touched
tables on setup AND teardown). Exercises the REAL schema (the new
`arc_conformance_state` table) end-to-end against a live Postgres:

  - persist_conformance_state round-trips a snapshot: report + input_manifest
    (chapters with published_revision_id + parse_version from canon-markers, plus the
    spec fingerprints), deep, generation_job_id — the manifest is assembled from the
    SAME reads the compute did.
  - compute_conformance_status computes never_run → fresh → dirty(prose_drift) BY
    EFFECT (a mocked canon_markers whose published_revision_id moves), plus the
    index.stale_chapter_count rollup.

asyncpg needs datetimes, not strings, bound to ::timestamptz — computed_at is a
server default (now()), never a client bind (the asyncpg-timestamptz lesson).
"""

from __future__ import annotations

import os
import uuid

import asyncpg
import pytest

from app.db.migrate import run_migrations
from app.db.repositories.conformance_state import ConformanceStateRepo
from app.db.repositories.structure import StructureRepo
from app.engine.arc_conformance_orchestrate import (compute_conformance_status,
                                                     persist_conformance_state)

_DSN = os.environ.get("TEST_COMPOSITION_DB_URL")

pytestmark = [
    pytest.mark.skipif(
        not _DSN, reason="set TEST_COMPOSITION_DB_URL to a throwaway DB to run",
    ),
    # Shared-Postgres tests serialize onto one xdist worker (CLAUDE.md).
    pytest.mark.xdist_group("pg"),
]

# structure_node FKs arc_template; arc_conformance_state FKs structure_node.
_TABLES = ["arc_conformance_state", "motif_application", "outline_node",
           "structure_node", "arc_template"]


async def _drop(p: asyncpg.Pool) -> None:
    async with p.acquire() as c:
        for t in _TABLES:
            await c.execute(f"DROP TABLE IF EXISTS {t} CASCADE")


@pytest.fixture
async def pool():
    p = await asyncpg.create_pool(_DSN, min_size=1, max_size=4)
    try:
        await _drop(p)
        await run_migrations(p)
        yield p
    finally:
        await _drop(p)
        await p.close()


async def _arc(c, *, book_id, created_by) -> uuid.UUID:
    return await c.fetchval(
        "INSERT INTO structure_node (book_id, created_by, kind, rank, title) "
        "VALUES ($1, $2, 'arc', 'aaa', 'Betrayal') RETURNING id",
        book_id, created_by,
    )


async def _chapter_node(c, *, project_id, book_id, created_by, arc_id, chapter_id) -> uuid.UUID:
    return await c.fetchval(
        "INSERT INTO outline_node (created_by, project_id, book_id, kind, rank, "
        "chapter_id, structure_node_id) VALUES ($1, $2, $3, 'chapter', 'aaa', $4, $5) "
        "RETURNING id",
        created_by, project_id, book_id, chapter_id, arc_id,
    )


class _FakeBook:
    """Stub book-service canon-markers batch — a mutable marker map so a test can move
    a chapter's published_revision_id (simulating a publish) between status reads."""

    def __init__(self, markers: dict[str, dict]) -> None:
        self.markers = markers
        self.calls: list[list[str]] = []

    async def canon_markers(self, book_id, chapter_ids):
        ids = [str(c) for c in chapter_ids]
        self.calls.append(ids)
        return {cid: self.markers[cid] for cid in ids if cid in self.markers}


def _report():
    # A coarse-shaped report — enough for the summary projection (thread_progress
    # 1/2=0.5, pacing_drift 14, succession_violations 1, unmaterialized 3).
    return {
        "scope": "arc", "coarse": True,
        "thread_progress": [{"thread": "revenge", "planned": 2, "covered": 1, "missing": []}],
        "pacing": {"comparable": True, "max_drift": 14},
        "succession": {"threads": [{"thread": "revenge", "violations": [{"from_motif_code": "a"}]}]},
        "unmaterialized": [{}, {}, {}],
    }


# ── C2: persist round-trips a snapshot ────────────────────────────────────────

async def test_persist_conformance_state_round_trips(pool):
    book_id, created_by, project_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ch = uuid.uuid4()
    rev = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    async with pool.acquire() as c:
        arc_id = await _arc(c, book_id=book_id, created_by=created_by)
        await _chapter_node(c, project_id=project_id, book_id=book_id,
                            created_by=created_by, arc_id=arc_id, chapter_id=ch)

    arc = await StructureRepo(pool).get(arc_id)
    # WS-0.7: the fake must mirror the REAL canon-markers response, which now also
    # carries kg_indexed_revision_id + kg_exclude. A mock that encodes the OLD contract
    # would hide the very drift this change is about (mocked-client-hides-server-side
    # -defaults). On a normally-published chapter the two pointers are equal.
    book = _FakeBook({str(ch): {
        "published_revision_id": rev, "kg_indexed_revision_id": rev,
        "kg_exclude": False, "last_parsed_revision_id": rev,
        "parse_version": 3, "editorial_status": "published"}})

    manifest = await persist_conformance_state(
        pool=pool, book_client=book, book_id=book_id, arc=arc,
        report=_report(), deep=True, generation_job_id=job_id)

    # the manifest was assembled from the canon-markers read + the spec fingerprints.
    # WS-0.7: it now RECORDS kg_indexed_revision_id — the pin _dirty_reasons compares
    # against (the revision the scenes the report binds to were parsed from).
    # published_revision_id is kept for provenance/back-compat.
    assert manifest["v"] == 1
    assert manifest["chapters"] == [
        {"chapter_id": str(ch), "kg_indexed_revision_id": rev,
         "published_revision_id": rev, "parse_version": 3}]
    assert set(manifest["spec"]) == {
        "structure_node_version", "outline_fingerprint", "bindings_fingerprint"}
    assert manifest["spec"]["outline_fingerprint"].startswith("sha256:")

    snap = await ConformanceStateRepo(pool).get(book_id, arc_id)
    assert snap is not None
    assert snap.report == _report()             # full report body round-trips
    assert snap.input_manifest == manifest
    assert snap.deep is True
    assert snap.generation_job_id == uuid.UUID(job_id)
    assert snap.computed_at is not None

    # UPSERT-latest: a second persist replaces (still one row).
    await persist_conformance_state(
        pool=pool, book_client=book, book_id=book_id, arc=arc,
        report={"scope": "arc", "v2": True}, deep=False)
    snap2 = await ConformanceStateRepo(pool).get(book_id, arc_id)
    assert snap2.report == {"scope": "arc", "v2": True} and snap2.deep is False
    rows = await ConformanceStateRepo(pool).list_for_book(book_id)
    assert len(rows) == 1


# ── C3: status computes never_run → fresh → dirty by EFFECT ───────────────────

async def test_status_never_run_then_fresh_then_prose_drift(pool):
    book_id, created_by, project_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    ch = uuid.uuid4()
    r1, r2 = str(uuid.uuid4()), str(uuid.uuid4())
    async with pool.acquire() as c:
        arc_id = await _arc(c, book_id=book_id, created_by=created_by)
        await _chapter_node(c, project_id=project_id, book_id=book_id,
                            created_by=created_by, arc_id=arc_id, chapter_id=ch)
    arc = await StructureRepo(pool).get(arc_id)

    # editorial published, index fresh (last_parsed == published) so index_stale never
    # muddies the prose_drift assertion.
    book = _FakeBook({str(ch): {
        "published_revision_id": r1, "kg_indexed_revision_id": r1, "kg_exclude": False,
        "last_parsed_revision_id": r1,
        "parse_version": 1, "editorial_status": "published"}})

    # never_run — no snapshot yet.
    st = await compute_conformance_status(pool=pool, book_client=book, book_id=book_id)
    assert len(st["arcs"]) == 1
    a = st["arcs"][0]
    assert a["structure_node_id"] == str(arc_id) and a["kind"] == "arc"
    assert a["dirty"] is True and a["dirty_reasons"] == ["never_run"]
    assert a["computed_at"] is None and a["summary"] is None
    assert st["index"]["stale_chapter_count"] == 0

    # snapshot it at r1 → fresh.
    await persist_conformance_state(
        pool=pool, book_client=book, book_id=book_id, arc=arc,
        report=_report(), deep=True)
    st = await compute_conformance_status(pool=pool, book_client=book, book_id=book_id)
    a = st["arcs"][0]
    assert a["dirty"] is False and a["dirty_reasons"] == []
    assert a["computed_at"] is not None and a["deep"] is True
    assert a["summary"] == {"thread_progress": 0.5, "pacing_drift": 14,
                            "succession_violations": 1, "unmaterialized": 3}
    assert st["index"]["stale_chapter_count"] == 0

    # publish a new revision for the member chapter → prose_drift by predicate.
    # The index is FRESH here (last_parsed == published), so this is the NORMAL publish
    # path (IX-2 re-parses in-Tx): prose_drift is the only signal, index_stale is empty.
    book.markers[str(ch)] = {
        "published_revision_id": r2, "kg_indexed_revision_id": r2, "kg_exclude": False,
        "last_parsed_revision_id": r2,
        "parse_version": 2, "editorial_status": "published"}
    st = await compute_conformance_status(pool=pool, book_client=book, book_id=book_id)
    a = st["arcs"][0]
    assert a["dirty"] is True and a["dirty_reasons"] == ["prose_drift"]
    # COMP-STALE-1: the prose-drifted chapter MUST be in stale_chapters, or the
    # scene-inspector chip (arc.dirty AND chapter IN stale_chapters) renders false-fresh
    # on the dominant publish path. But the book-level rollup counts index-stale only, so
    # a fresh-index prose-drift does NOT bump stale_chapter_count (distinct concepts).
    assert a["stale_chapters"] == [str(ch)]
    assert st["index"]["stale_chapter_count"] == 0

    # a lagging index (last_parsed behind published) → index_stale + the rollup.
    book.markers[str(ch)] = {
        "published_revision_id": r2, "kg_indexed_revision_id": r2, "kg_exclude": False,
        "last_parsed_revision_id": r1,
        "parse_version": 2, "editorial_status": "published"}
    st = await compute_conformance_status(pool=pool, book_client=book, book_id=book_id)
    a = st["arcs"][0]
    assert "prose_drift" in a["dirty_reasons"] and "index_stale" in a["dirty_reasons"]
    assert a["stale_chapters"] == [str(ch)]
    assert st["index"]["stale_chapter_count"] == 1
