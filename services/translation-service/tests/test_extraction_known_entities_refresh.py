"""Extraction worker — known-entities are re-resolved at every chapter boundary.

D-KNOWN-ENTITIES-PER-JOB (Phase 0 / T2 of the knowledge-architecture refactor).

A book-wide extraction job runs for hours. The known-entity list used to be fetched
ONCE before the loop and held for the job's lifetime, so an entity the author trashed
mid-run stayed in the extractor's "you already know these" prompt context for every
remaining chapter — got re-proposed, got written back, and the delete was undone one
chapter at a time.

Two holes had to close, and each has a test here plus its positive control:
  1. entities the SERVER knows (frequency >= min_frequency) — closed by re-fetching;
  2. entities THIS RUN created — invisible to the frequency-filtered read until a
     second chapter mentions them, so they are carried locally and pruned by a
     batched liveness probe on the same boundary.
"""
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.workers.extraction_worker import _run_extraction_job


class _AcquireCM:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *_):
        return False


def _pool(db):
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AcquireCM(db))
    return pool


def _db(job_id):
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=job_id)  # claim succeeds; status check → not cancelled
    db.fetch = AsyncMock(return_value=[])         # no resume checkpoint
    db.execute = AsyncMock()
    return db


def _known(name, entity_id):
    return {"entity_id": entity_id, "name": name, "kind_code": "character",
            "aliases": [], "frequency": 3}


def _names(call):
    return {e["name"] for e in call.kwargs["known_entities"]}


async def _run(chapters, *, known_side_effect, live_side_effect=None, proc_results=None):
    """Drive a 2-chapter job and return the per-chapter _process_extraction_chapter calls."""
    jid = uuid4()
    proc = AsyncMock(side_effect=proc_results or [{} for _ in chapters])
    with patch("app.workers.extraction_worker.fetch_known_entities",
               new=AsyncMock(side_effect=known_side_effect)), \
         patch("app.workers.extraction_worker.fetch_live_entity_ids",
               new=AsyncMock(side_effect=live_side_effect or (lambda *a, **k: set()))), \
         patch("app.workers.extraction_worker._process_extraction_chapter", new=proc), \
         patch("app.workers.extraction_worker.resolve_job_cost_usd", new=AsyncMock(return_value=None)), \
         patch("app.workers.extraction_worker.emit_job_event_safe", new=AsyncMock()):
        await _run_extraction_job(
            {"book_id": "b", "chapter_ids": list(chapters)},
            jid, "u", _pool(_db(jid)), AsyncMock(), AsyncMock(), MagicMock(),
        )
    return proc.await_args_list


@pytest.mark.asyncio
async def test_entity_deleted_mid_job_leaves_the_next_chapters_known_set():
    """The bug, exactly: chapter 1 sees both, chapter 2 must not see the trashed one."""
    a, b = str(uuid4()), str(uuid4())
    calls = await _run(
        [str(uuid4()), str(uuid4())],
        # The endpoint filters `deleted_at IS NULL`, so the author's mid-run delete
        # shows up as the entity simply not coming back on the next fetch.
        known_side_effect=[
            [_known("Nezha", a), _known("Ao Bing", b)],
            [_known("Nezha", a)],
        ],
    )

    assert len(calls) == 2, "both chapters must be processed"
    assert _names(calls[0]) == {"Nezha", "Ao Bing"}
    assert _names(calls[1]) == {"Nezha"}, (
        "an entity trashed mid-job must leave the known set at the next chapter "
        "boundary — otherwise the extractor keeps re-proposing it and the delete "
        "is undone one chapter at a time"
    )


@pytest.mark.asyncio
async def test_the_known_set_is_re_resolved_per_chapter_not_held():
    """The mechanism, not just the outcome: one fetch PER CHAPTER, not one per job."""
    a = str(uuid4())
    fetches = []

    async def _fetch(book_id, **kw):
        fetches.append(book_id)
        return [_known("Nezha", a)]

    with patch("app.workers.extraction_worker.fetch_known_entities", new=_fetch), \
         patch("app.workers.extraction_worker.fetch_live_entity_ids",
               new=AsyncMock(return_value=set())), \
         patch("app.workers.extraction_worker._process_extraction_chapter",
               new=AsyncMock(return_value={})), \
         patch("app.workers.extraction_worker.resolve_job_cost_usd", new=AsyncMock(return_value=None)), \
         patch("app.workers.extraction_worker.emit_job_event_safe", new=AsyncMock()):
        jid = uuid4()
        await _run_extraction_job(
            {"book_id": "b", "chapter_ids": [str(uuid4()), str(uuid4()), str(uuid4())]},
            jid, "u", _pool(_db(jid)), AsyncMock(), AsyncMock(), MagicMock(),
        )

    assert len(fetches) == 3, f"want one known-entities fetch per chapter, got {len(fetches)}"


@pytest.mark.asyncio
async def test_an_entity_this_run_created_is_dropped_once_it_stops_being_live():
    """The second hole: a newborn is below min_frequency, so only a liveness probe sees it."""
    created = str(uuid4())
    chapter_one_result = {
        "entities": [{"entity_id": created, "name": "Shi Ji", "kind_code": "character",
                      "status": "created"}],
    }

    # Deleted: the liveness probe returns it as absent (the by-ids endpoint drops
    # soft-deleted ids), so it must not reach chapter 2.
    calls = await _run(
        [str(uuid4()), str(uuid4())],
        known_side_effect=[[], []],
        live_side_effect=lambda *a, **k: set(),
        proc_results=[chapter_one_result, {}],
    )
    assert _names(calls[0]) == set(), "chapter 1 predates the creation"
    assert _names(calls[1]) == set(), (
        "an entity created by THIS run and then trashed must not survive in the "
        "carried-forward context — the frequency-filtered read cannot see it, so "
        "the liveness probe is the only thing that can drop it"
    )

    # Control: still live → it MUST be carried, or the fix has silently cost the
    # prompt continuity the local carry-forward exists to provide.
    calls = await _run(
        [str(uuid4()), str(uuid4())],
        known_side_effect=[[], []],
        live_side_effect=lambda *a, **k: {created},
        proc_results=[chapter_one_result, {}],
    )
    assert _names(calls[1]) == {"Shi Ji"}, (
        "a live entity created this run must still be carried into the next chapter"
    )


@pytest.mark.asyncio
async def test_a_malformed_known_entities_response_does_not_abort_the_job():
    """The refresh runs OUTSIDE the per-chapter try, so it must not be able to raise.

    `fetch_known_entities` returns `resp.json()` unvalidated. Before the normalisation
    guard, a glossary response that was not a list of objects raised out of the refresh,
    past the per-chapter `except`, and killed the whole job — a strictly worse failure
    than the fetch-once code it replaced, which could at most fail one chapter.
    """
    a = str(uuid4())
    calls = await _run(
        [str(uuid4()), str(uuid4()), str(uuid4())],
        known_side_effect=[
            {"error": "boom"},            # an object, not a list — `for e in raw` yields str
            ["not-an-object", _known("Nezha", a)],  # a list with a non-dict element
            [_known("Nezha", a)],         # recovered
        ],
    )

    assert len(calls) == 3, (
        "a malformed known-entities response must not abort the job — all three "
        "chapters still process"
    )
    assert _names(calls[0]) == set(), "the unusable response degrades to an empty known set"
    assert _names(calls[1]) == {"Nezha"}, "usable rows survive alongside a bad one"
    assert _names(calls[2]) == {"Nezha"}
