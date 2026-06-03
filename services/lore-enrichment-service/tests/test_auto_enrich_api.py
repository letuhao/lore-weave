"""auto-enrich HTTP handler — cost-cap + branch coverage (D1 follow-up).

Exercises the FastAPI handler (POST .../auto-enrich) via TestClient + dependency
overrides, NOT the store class directly. The basic happy path (detect → create
job → enqueue → 202) is already covered in ``test_gaps_api``; this file adds the
gaps that path does NOT cover:

  1. cost-cap round-trip — ``max_spend_usd`` set → ``create_job`` receives
     ``max_spend`` AND the persisted ``job_request`` carries the budget triad the
     worker reads back (``max_spend_usd`` + ``eval_reserve_fraction`` + ``top_k``).
  2. ZERO gaps detected → 202 with ``detected:0`` / ``enqueued:false`` and NO
     ``create_job`` / NO enqueue (the short-circuit branch).
  3. unknown technique → 400 BEFORE any glossary read / store write.
  4. enqueue FAILURE (producer.xadd raises) → still 202 with ``enqueued:false``
     but the job row + request DID persist (the run is re-triggerable).

NO live stack: the glossary coverage read is respx-mocked, the store +
save_job_request are monkeypatched fakes, and the redis producer is a recording
fake (matching ``test_gaps_api._RecordingProducer``). All assertions are against
real handler behaviour read from ``app/api/gaps.py``.
"""

from __future__ import annotations

from uuid import uuid4

import jwt as pyjwt
import pytest
import respx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import gaps as gaps_api
from app.config import settings
from app.deps import get_db

OWNER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"


# ── fakes (mirror test_gaps_api) ─────────────────────────────────────────────

class _RecordingProducer:
    """Captures the enqueued auto-enrich trigger (the happy enqueue path)."""

    def __init__(self):
        self.calls = []
        self.closed = False

    async def xadd(self, stream, fields, maxlen=None):
        self.calls.append((stream, fields))
        return "1-0"

    async def aclose(self):
        self.closed = True


class _ExplodingProducer:
    """xadd raises — the handler must swallow it (enqueued=False), still 202.

    The job row + request already persisted at this point, so the run is
    re-triggerable. aclose() must still run in the ``finally``."""

    def __init__(self):
        self.closed = False

    async def xadd(self, stream, fields, maxlen=None):
        raise RuntimeError("redis down")

    async def aclose(self):
        self.closed = True


def _app() -> FastAPI:
    app = FastAPI()
    app.include_router(gaps_api.router)
    # auto-enrich depends on get_db; a stub keeps wiring valid (the store +
    # save_job_request are monkeypatched per-test, so the pool is never used).
    app.dependency_overrides[get_db] = lambda: object()
    return app


def _bearer(sub: str = OWNER) -> str:
    return pyjwt.encode({"sub": sub}, "x", algorithm="HS256")


def _mock_coverage(book, entities):
    respx.get(
        f"{settings.glossary_service_url}/internal/books/{book}/enrichment-coverage"
    ).respond(200, json={"entities": entities})


def _under_described(name, mentions=10):
    """A location missing dimensions → yields a gap."""
    return {"entity_id": name, "canonical_name": name, "kind": "location",
            "mention_count": mentions, "dimensions": ["历史"]}


def _fully_described(name, mentions=10):
    """A location with EVERY dimension present → NOT a gap (engine skips it)."""
    return {"entity_id": name, "canonical_name": name, "kind": "location",
            "mention_count": mentions,
            "dimensions": ["历史", "地理", "文化", "features", "inhabitants"]}


def _patch_store(monkeypatch, *, jid, created, saved, producer):
    """Wire the four collaborators the handler reaches for. Returns nothing;
    mutates ``created``/``saved`` dicts so the caller asserts the round-trip."""

    class _FakeStore:
        def __init__(self, pool):
            ...

        async def create_job(self, **kw):
            created.update(kw)
            return str(jid)

    async def _fake_save(*, pool, job_id, request):
        saved["job_id"] = job_id
        saved["request"] = request

    monkeypatch.setattr(gaps_api, "PgProposalStore", _FakeStore)
    monkeypatch.setattr(gaps_api, "save_job_request", _fake_save)
    monkeypatch.setattr(gaps_api, "make_redis_producer", lambda url: producer)


# ── 1. cost-cap round-trip ───────────────────────────────────────────────────

@respx.mock
async def test_auto_enrich_cost_cap_round_trips_to_job_and_request(monkeypatch):
    """max_spend_usd → create_job(max_spend=...) AND the persisted job_request
    carries the worker's budget triad (max_spend_usd + eval_reserve_fraction +
    top_k). This is the budget the resume worker reads back, so the round-trip
    MUST be lossless."""
    book, project, jid = uuid4(), uuid4(), uuid4()
    _mock_coverage(book, [_under_described("玉虛宮", mentions=55)])

    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)

    resp = TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{project}/auto-enrich",
        json={
            "book_id": str(book),
            "embedding_model_ref": str(uuid4()),
            "generation_model_ref": str(uuid4()),
            "max_gaps": 5,
            "max_spend_usd": 4.25,
            "eval_reserve_fraction": 0.3,
            "top_k": 8,
        },
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["enqueued"] is True
    assert body["job_id"] == str(jid)

    # create_job receives the cost cap under the store's `max_spend` kwarg.
    assert created["max_spend"] == 4.25
    assert created["estimated_cost"] == 0.0
    assert created["user_id"] == OWNER
    assert created["project_id"] == str(project)
    assert created["book_id"] == str(book)
    assert created["technique"] == "retrieval"  # default
    assert created["entity_kind"] == "location"

    # The persisted request carries the worker-read budget triad, losslessly.
    req = saved["request"]
    assert saved["job_id"] == jid
    assert req["max_spend_usd"] == 4.25
    assert req["eval_reserve_fraction"] == 0.3
    assert req["top_k"] == 8
    # ...alongside the rest of the re-drive shape the worker rebuilds from.
    assert req["technique"] == "retrieval"
    assert req["book_id"] == str(book)
    assert req["user_id"] == OWNER
    assert req["entity_kind"] == "location"
    assert len(req["targets"]) == 1


@respx.mock
async def test_auto_enrich_default_max_spend_is_none(monkeypatch):
    """When max_spend_usd is omitted, the cap is None (uncapped) and the
    defaults for the budget triad flow through unchanged."""
    book, project, jid = uuid4(), uuid4(), uuid4()
    _mock_coverage(book, [_under_described("蓬萊")])

    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)

    resp = TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{project}/auto-enrich",
        json={
            "book_id": str(book),
            "embedding_model_ref": str(uuid4()),
            "generation_model_ref": str(uuid4()),
        },
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 202, resp.text
    assert created["max_spend"] is None
    # AutoEnrichBody defaults: eval_reserve_fraction=0.15, top_k=5.
    assert saved["request"]["max_spend_usd"] is None
    assert saved["request"]["eval_reserve_fraction"] == 0.15
    assert saved["request"]["top_k"] == 5


# ── 2. ZERO gaps detected → short-circuit (no job, no enqueue) ───────────────

@respx.mock
async def test_auto_enrich_zero_gaps_does_not_create_job_or_enqueue(monkeypatch):
    """A fully-described entity yields no gap → handler returns 202 with
    detected:0 / enqueued:false and NEVER touches the store or the producer."""
    book, project, jid = uuid4(), uuid4(), uuid4()
    # Every dimension present → the engine skips it → zero ranked gaps.
    _mock_coverage(book, [_fully_described("玉虛宮", mentions=55)])

    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)

    resp = TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{project}/auto-enrich",
        json={
            "book_id": str(book),
            "embedding_model_ref": str(uuid4()),
            "generation_model_ref": str(uuid4()),
        },
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["detected"] == 0
    assert body["enqueued"] is False
    assert body["entities_scanned"] == 1
    assert "job_id" not in body  # short-circuit return shape omits it
    # The short-circuit must NOT touch the write path or the worker stream.
    assert created == {}
    assert saved == {}
    assert prod.calls == []


# ── 3. unknown technique → 400 BEFORE any glossary/store call ────────────────

@respx.mock
async def test_auto_enrich_unknown_technique_400_before_any_side_effect(monkeypatch):
    """An invalid technique is rejected with 400 before the glossary read or any
    store write — so no coverage HTTP call, no create_job, no enqueue."""
    book, project, jid = uuid4(), uuid4(), uuid4()
    coverage_route = respx.get(
        f"{settings.glossary_service_url}/internal/books/{book}/enrichment-coverage"
    ).respond(200, json={"entities": [_under_described("玉虛宮")]})

    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)

    resp = TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{project}/auto-enrich",
        json={
            "book_id": str(book),
            "embedding_model_ref": str(uuid4()),
            "generation_model_ref": str(uuid4()),
            "technique": "not-a-technique",
        },
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 400, resp.text
    assert "not-a-technique" in resp.json()["detail"]
    # 400 is raised before glossary is read and before any store write.
    assert not coverage_route.called
    assert created == {}
    assert saved == {}
    assert prod.calls == []


# ── 4. enqueue FAILURE → 202 enqueued:false, job + request persisted ─────────

@respx.mock
async def test_auto_enrich_enqueue_failure_still_persists_and_returns_202(monkeypatch):
    """If producer.xadd raises, the handler swallows it: enqueued=false but the
    job row + request DID persist (re-triggerable). Still 202, and the producer
    is closed in the finally."""
    book, project, jid = uuid4(), uuid4(), uuid4()
    _mock_coverage(book, [_under_described("玉虛宮", mentions=55)])

    created, saved, prod = {}, {}, _ExplodingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)

    resp = TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{project}/auto-enrich",
        json={
            "book_id": str(book),
            "embedding_model_ref": str(uuid4()),
            "generation_model_ref": str(uuid4()),
            "max_spend_usd": 2.0,
        },
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["enqueued"] is False  # xadd raised → swallowed
    assert body["job_id"] == str(jid)
    assert body["detected"] == 1
    assert body["enqueued_gaps"] == 1
    # The persist happened BEFORE the failed enqueue → the run is re-triggerable.
    assert created["max_spend"] == 2.0
    assert saved["job_id"] == jid
    assert saved["request"]["max_spend_usd"] == 2.0
    # The producer was still closed in the finally despite the raise.
    assert prod.closed is True


# ── LE-064 — targeted enrich (per-row "enrich →") ────────────────────────────

@respx.mock
async def test_auto_enrich_with_targets_skips_detection_and_enqueues(monkeypatch):
    """When ``targets`` is provided, the handler enriches exactly those gaps (the
    per-row "enrich →"), bypassing the glossary coverage read + top-N ranking. The
    persisted job_request carries the provided targets; the worker re-drives them
    on the same async path. ``target_ref`` defaults to ``canonical_name``."""
    book, project, jid = uuid4(), uuid4(), uuid4()
    # A coverage route that MUST NOT be called — detection is skipped for targets.
    coverage_route = respx.get(
        f"{settings.glossary_service_url}/internal/books/{book}/enrichment-coverage"
    ).respond(200, json={"entities": [_under_described("should-not-be-read")]})

    created, saved, prod = {}, {}, _RecordingProducer()
    _patch_store(monkeypatch, jid=jid, created=created, saved=saved, producer=prod)

    resp = TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{project}/auto-enrich",
        json={
            "book_id": str(book),
            "embedding_model_ref": str(uuid4()),
            "generation_model_ref": str(uuid4()),
            "max_spend_usd": 1.5,
            "targets": [
                {"canonical_name": "玉虛宮", "entity_kind": "location",
                 "mention_count": 42, "present_dimensions": ["历史"]},
            ],
        },
        headers={"Authorization": f"Bearer {_bearer()}"},
    )

    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["enqueued"] is True
    assert body["job_id"] == str(jid)
    assert body["detected"] == 1
    assert body["enqueued_gaps"] == 1
    assert body["entities_scanned"] == 1
    # Detection was SKIPPED — the glossary coverage route was never called.
    assert not coverage_route.called
    # The persisted request carries exactly the provided target; target_ref
    # defaults to the canonical_name when omitted; the budget still round-trips.
    req = saved["request"]
    assert created["max_spend"] == 1.5
    assert req["max_spend_usd"] == 1.5
    targets = req["targets"]
    assert len(targets) == 1
    assert targets[0]["canonical_name"] == "玉虛宮"
    assert targets[0]["target_ref"] == "玉虛宮"
    assert targets[0]["present_dimensions"] == ["历史"]
    assert len(prod.calls) == 1  # one re-drive trigger enqueued


# ── auth: anonymous principal → 401 ──────────────────────────────────────────

def test_auto_enrich_requires_auth():
    """No bearer → anonymous principal (user_id=None) → 401 before any work."""
    resp = TestClient(_app()).post(
        f"/v1/lore-enrichment/projects/{uuid4()}/auto-enrich",
        json={"book_id": str(uuid4()), "embedding_model_ref": str(uuid4()),
              "generation_model_ref": str(uuid4())},
    )
    assert resp.status_code == 401
