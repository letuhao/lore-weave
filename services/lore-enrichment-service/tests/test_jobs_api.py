"""C14 jobs router — HTTP-layer coverage (the GAP: auth, Q3 scoping → 404, C8
illegal-transition → 409, redis enqueue best-effort, create-job exception→status
mapping).

These drive the REAL FastAPI handlers via TestClient + dependency overrides — the
service/repo/state-machine classes are covered directly by test_job_runner /
test_review_gate; this file covers ONLY what those miss: the handler wiring.

NO live stack: ``get_db`` is overridden with a fake pool whose connection returns
seeded rows (or None for a cross-scope miss), and the redis producer is patched to
a recording fake (like test_gaps_api._RecordingProducer). asyncio_mode=auto.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import jwt as pyjwt
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import jobs as jobs_api
from app.deps import get_db
from app.strategies.registry import InactiveStrategyError, UnknownStrategyError

OWNER = "019d5e3c-7cc5-7e6a-8b27-1344e148bf7c"
PROJECT = "019e7850-aa1c-7cd3-a25c-c2f9ad84fd39"
BOOK = "019e7850-a8d9-78dd-8b2a-f33ccc2396ad"


def _bearer(sub: str = OWNER) -> str:
    """A bearer whose unverified `sub` resolves to the acting principal (the
    handler decodes `sub` without signature verification at this stage)."""
    return pyjwt.encode({"sub": sub}, "irrelevant", algorithm="HS256")


# ── fake async DB seam ────────────────────────────────────────────────────────


class _FakeConn:
    """A connection seeded with ONE optional row. ``fetchrow`` returns the row for
    a 'hit' or None for a cross-scope 'miss' (no existence oracle). ``execute``
    records the persisted UPDATE so the transition assertion can read it back."""

    def __init__(self, row):
        self._row = row
        self.executed: list[tuple] = []

    async def fetchrow(self, *args, **kwargs):
        return self._row

    async def fetchval(self, *args, **kwargs):
        return 0

    async def fetch(self, *args, **kwargs):
        return []

    async def execute(self, query, *args):
        self.executed.append((query, args))
        return None


class _FakeAcquire:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    """Pool that always hands out the same seeded connection (so a test can read
    back what the handler executed)."""

    def __init__(self, row):
        self.conn = _FakeConn(row)

    def acquire(self):
        return _FakeAcquire(self.conn)


class _RecordingProducer:
    """Captures the enqueued resume trigger (mirrors test_gaps_api). ``xadd`` may
    be configured to raise to exercise the best-effort enqueue path."""

    def __init__(self, raise_on_xadd: Exception | None = None):
        self.calls: list[tuple] = []
        self.closed = False
        self._raise = raise_on_xadd

    async def xadd(self, stream, fields, maxlen=None):
        self.calls.append((stream, fields, maxlen))
        if self._raise is not None:
            raise self._raise
        return "1-0"

    async def aclose(self):
        self.closed = True


def _job_row(*, status: str, project_id: str = PROJECT):
    """A full enrichment_job row as asyncpg.Record-like mapping (every key the
    _job_row serializer reads). ``status`` drives the transition legality."""
    return {
        "job_id": UUID(JOB_ID),
        "project_id": UUID(project_id),
        "status": status,
        "technique": "retrieval",
        "entity_kind": "location",
        "book_id": UUID(BOOK),
        "proposals_total": 3,
        "estimated_cost_usd": 1.5,
        "actual_cost_usd": 0.75,
        "max_spend_usd": 10.0,
        "error_message": None,
        "created_at": datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc),
    }


JOB_ID = "019e7850-1234-7000-8000-0000000000aa"


def _app(pool) -> FastAPI:
    app = FastAPI()
    app.include_router(jobs_api.router)
    app.dependency_overrides[get_db] = lambda: pool
    return app


def _client(pool) -> TestClient:
    return TestClient(_app(pool))


# ── (1) _transition_job: pause / start / illegal / scoping ────────────────────


def test_pause_running_job_returns_paused():
    """pause a running row → 200 {status: 'paused'}; the UPDATE persists 'paused'."""
    pool = _FakePool(_job_row(status="running"))
    resp = _client(pool).post(
        f"/v1/lore-enrichment/jobs/{JOB_ID}/pause",
        params={"project_id": PROJECT},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == {"job_id": JOB_ID, "status": "paused"}
    # the C8 transition persisted the new status (not a silent no-op).
    assert pool.conn.executed, "transition must persist the new status"
    assert pool.conn.executed[0][1][-1] == "paused"


def test_pause_completed_job_is_409_illegal_transition():
    """An illegal C8 move (pause a terminal 'completed' job) → 409, no persist."""
    pool = _FakePool(_job_row(status="completed"))
    resp = _client(pool).post(
        f"/v1/lore-enrichment/jobs/{JOB_ID}/pause",
        params={"project_id": PROJECT},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 409, resp.text
    # the illegal transition raised BEFORE the UPDATE — nothing persisted.
    assert pool.conn.executed == []


def test_transition_cross_scope_miss_is_404():
    """Q3 invariant: a cross-user/cross-project lookup returns None from fetchrow
    → 404 (no existence oracle), NOT 409/200."""
    pool = _FakePool(None)  # fetchrow → None
    resp = _client(pool).post(
        f"/v1/lore-enrichment/jobs/{JOB_ID}/pause",
        params={"project_id": PROJECT},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 404, resp.text
    assert pool.conn.executed == []


def test_transition_anonymous_is_401():
    """No bearer → anonymous principal (user_id None) → 401 before any DB read."""
    pool = _FakePool(_job_row(status="running"))
    resp = _client(pool).post(
        f"/v1/lore-enrichment/jobs/{JOB_ID}/pause",
        params={"project_id": PROJECT},
    )
    assert resp.status_code == 401, resp.text


def test_start_pending_walks_to_running_and_persists():
    """start walks pending → estimating → running and persists the final
    'running' (the multi-hop C8 walk lands on running, not estimating)."""
    pool = _FakePool(_job_row(status="pending"))
    resp = _client(pool).post(
        f"/v1/lore-enrichment/jobs/{JOB_ID}/start",
        params={"project_id": PROJECT},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "running"
    assert pool.conn.executed[0][1][-1] == "running"


def test_cancel_running_job_returns_cancelled():
    """cancel a running row → 200 {status: 'cancelled'} (C8 legal terminal move)."""
    pool = _FakePool(_job_row(status="running"))
    resp = _client(pool).post(
        f"/v1/lore-enrichment/jobs/{JOB_ID}/cancel",
        params={"project_id": PROJECT},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


# ── (2) resume: 202 + enqueue exactly one trigger; enqueue failure ≠ 500 ──────


def test_resume_paused_job_is_202_and_enqueues_one_trigger(monkeypatch):
    """resume a paused job → 202; flips paused→running AND enqueues exactly one
    redis trigger carrying job_id/project_id/user_id."""
    prod = _RecordingProducer()
    monkeypatch.setattr(jobs_api, "make_redis_producer", lambda url: prod)
    pool = _FakePool(_job_row(status="paused"))
    resp = _client(pool).post(
        f"/v1/lore-enrichment/jobs/{JOB_ID}/resume",
        params={"project_id": PROJECT},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "running"
    assert body["resume"] == "enqueued"
    # exactly one trigger enqueued, with the resume-stream payload.
    assert len(prod.calls) == 1
    stream, fields, _maxlen = prod.calls[0]
    assert stream == jobs_api.LORE_ENRICHMENT_RESUME_STREAM
    assert fields == {"job_id": JOB_ID, "project_id": PROJECT, "user_id": OWNER}
    assert prod.closed is True  # producer is closed in the finally


def test_resume_enqueue_failure_still_202_status_not_unwound(monkeypatch):
    """A transient Redis hiccup on xadd must NOT 500 nor unwind the already-flipped
    status: still 202, status 'running', resume marked 'enqueue_failed'."""
    prod = _RecordingProducer(raise_on_xadd=RuntimeError("redis down"))
    monkeypatch.setattr(jobs_api, "make_redis_producer", lambda url: prod)
    pool = _FakePool(_job_row(status="paused"))
    resp = _client(pool).post(
        f"/v1/lore-enrichment/jobs/{JOB_ID}/resume",
        params={"project_id": PROJECT},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    # the flipped status is NOT unwound — the job is left re-triggerable.
    assert body["status"] == "running"
    assert body["resume"] == "enqueue_failed"
    # the UPDATE to 'running' still persisted (the flip stands).
    assert pool.conn.executed and pool.conn.executed[0][1][-1] == "running"
    assert prod.closed is True


def test_resume_illegal_transition_is_409_before_enqueue(monkeypatch):
    """resume a NON-paused (running) job → 409 from C8 BEFORE any enqueue (the
    redis trigger must not fire on an illegal transition)."""
    prod = _RecordingProducer()
    monkeypatch.setattr(jobs_api, "make_redis_producer", lambda url: prod)
    pool = _FakePool(_job_row(status="running"))
    resp = _client(pool).post(
        f"/v1/lore-enrichment/jobs/{JOB_ID}/resume",
        params={"project_id": PROJECT},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 409, resp.text
    assert prod.calls == [], "no enqueue on an illegal transition"


# ── (3) GET /jobs/{id}: 404 cross-scope, 200 owned shape, 401 anonymous ───────


def test_get_job_cross_scope_miss_is_404():
    pool = _FakePool(None)  # scoped fetchrow → None
    resp = _client(pool).get(
        f"/v1/lore-enrichment/jobs/{JOB_ID}",
        params={"project_id": PROJECT},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 404, resp.text


def test_get_job_owned_returns_job_row_shape():
    pool = _FakePool(_job_row(status="running"))
    resp = _client(pool).get(
        f"/v1/lore-enrichment/jobs/{JOB_ID}",
        params={"project_id": PROJECT},
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["job_id"] == JOB_ID
    assert body["project_id"] == PROJECT
    assert body["status"] == "running"
    assert body["technique"] == "retrieval"
    assert body["entity_kind"] == "location"
    assert body["book_id"] == BOOK
    assert body["proposals_total"] == 3
    assert body["estimated_cost"] == 1.5
    assert body["actual_cost"] == 0.75
    assert body["max_spend"] == 10.0
    assert body["error_message"] is None
    assert body["created_at"] == "2026-06-01T12:00:00+00:00"


def test_get_job_anonymous_is_401():
    pool = _FakePool(_job_row(status="running"))
    resp = _client(pool).get(
        f"/v1/lore-enrichment/jobs/{JOB_ID}",
        params={"project_id": PROJECT},
    )
    assert resp.status_code == 401, resp.text


# ── (4) POST /jobs: create-job exception → status mapping ─────────────────────


class _FakeStore:
    """Captures create_job + mark_job_status so the auditable-refusal assertion
    can read what status the failed job was marked with."""

    def __init__(self, pool):
        self.marks: list[dict] = []

    async def create_job(self, **kw):
        return JOB_ID

    async def mark_job_status(self, *, job_id, status, error_message=None):
        self.marks.append(
            {"job_id": job_id, "status": status, "error_message": error_message}
        )
        return None


def _create_body(*, technique: str = "retrieval", fully_described: bool = False):
    target = {"canonical_name": "蓬萊", "entity_kind": "location", "mention_count": 3}
    if fully_described:
        # all five LOCATION dimensions present → _gap_from_target returns None.
        target["present_dimensions"] = [
            "history", "geography", "culture", "features", "inhabitants",
        ]
    return {
        "project_id": PROJECT,
        "embedding_model_ref": str(uuid4()),
        "generation_model_ref": str(uuid4()),
        "targets": [target],
        "technique": technique,
    }


def _install_create_fakes(monkeypatch, *, runner_factory):
    """Patch the names create_job pulls into the jobs module: a fake store +
    no-op save_job_request + a build_live_runner that runs ``runner_factory``."""
    store = _FakeStore(None)
    monkeypatch.setattr(jobs_api, "PgProposalStore", lambda pool: store)

    async def _fake_save(*, pool, job_id, request):
        return None

    monkeypatch.setattr(jobs_api, "save_job_request", _fake_save)
    monkeypatch.setattr(jobs_api, "build_live_runner", runner_factory)
    return store


def test_create_job_inactive_strategy_is_409_and_marks_failed(monkeypatch):
    """build_live_runner raising InactiveStrategyError (gate-locked technique) →
    409 AND the job is marked 'failed' (auditable refusal, not a silent drop)."""
    async def _raise_inactive(**kw):
        raise InactiveStrategyError("technique 'fabrication' gate-locked")

    store = _install_create_fakes(monkeypatch, runner_factory=_raise_inactive)
    pool = _FakePool(None)
    resp = _client(pool).post(
        "/v1/lore-enrichment/jobs",
        json=_create_body(technique="fabrication"),
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 409, resp.text
    # the refusal is auditable: the persisted job row was marked failed.
    assert store.marks and store.marks[0]["status"] == "failed"
    assert store.marks[0]["job_id"] == JOB_ID


def test_create_job_unknown_strategy_is_400_and_marks_failed(monkeypatch):
    """build_live_runner raising UnknownStrategyError → 400 + job marked 'failed'."""
    async def _raise_unknown(**kw):
        raise UnknownStrategyError("no registered strategy for 'recook'")

    store = _install_create_fakes(monkeypatch, runner_factory=_raise_unknown)
    pool = _FakePool(None)
    resp = _client(pool).post(
        "/v1/lore-enrichment/jobs",
        json=_create_body(technique="recook"),
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 400, resp.text
    assert store.marks and store.marks[0]["status"] == "failed"


def test_create_job_unknown_technique_string_is_400_before_factory(monkeypatch):
    """An unknown technique string (not in the Technique enum) → 400 raised BEFORE
    the store/factory are ever reached (no job row created)."""
    reached = {"factory": False}

    async def _never(**kw):
        reached["factory"] = True
        raise AssertionError("factory must not be reached for a bad technique")

    store = _install_create_fakes(monkeypatch, runner_factory=_never)
    pool = _FakePool(None)
    resp = _client(pool).post(
        "/v1/lore-enrichment/jobs",
        json=_create_body(technique="not-a-real-technique"),
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 400, resp.text
    assert reached["factory"] is False
    assert store.marks == []  # the bad-technique 400 precedes job creation


def test_create_job_all_targets_fully_described_is_400_no_gaps(monkeypatch):
    """When every target is already fully described (no missing dimension) → 400
    'no gaps to enrich', raised before the factory."""
    reached = {"factory": False}

    async def _never(**kw):
        reached["factory"] = True
        raise AssertionError("factory must not run when there are no gaps")

    _install_create_fakes(monkeypatch, runner_factory=_never)
    pool = _FakePool(None)
    resp = _client(pool).post(
        "/v1/lore-enrichment/jobs",
        json=_create_body(fully_described=True),
        headers={"Authorization": f"Bearer {_bearer()}"},
    )
    assert resp.status_code == 400, resp.text
    assert "no gaps" in resp.json()["detail"]
    assert reached["factory"] is False


def test_create_job_anonymous_is_401():
    """No bearer → 401 before any store/factory work."""
    pool = _FakePool(None)
    resp = _client(pool).post(
        "/v1/lore-enrichment/jobs",
        json=_create_body(),
    )
    assert resp.status_code == 401, resp.text


# ── de-bias C1 (#2, #3): targeted-enrich gap builder is multi-kind ──────────────


def test_gap_from_target_character_uses_character_dimensions():
    # A CHARACTER target gets CHARACTER dims (NOT the location enum) — KB3/#3.
    from app.api.jobs import GapTarget, _gap_from_target

    g = _gap_from_target(GapTarget(canonical_name="姜子牙", entity_kind="character",
                                   present_dimensions=[]))
    assert g is not None and g.entity_kind == "character"
    assert set(g.missing_dimensions) == {
        "appearance", "personality", "abilities", "relationships", "background",
    }


def test_gap_from_target_unmodeled_kind_is_generic_no_400():
    # An unmodeled kind (organization) → GENERIC dims, NEVER a 400/skip (the old
    # EntityKind(...) raised; the live run hit this).
    from app.api.jobs import GapTarget, _gap_from_target

    g = _gap_from_target(GapTarget(canonical_name="截教", entity_kind="organization",
                                   present_dimensions=[]))
    assert g is not None and g.entity_kind == "organization"
    assert set(g.missing_dimensions) == {"description", "details", "significance"}


def test_content_from_facts_localizes_header_by_language():
    # de-bias (LE-PROD-2 P2): zh book → "「name」补全：" + fullwidth colons (demo
    # unchanged); a non-zh book → English header + ASCII separators (no zh artifact).
    from types import SimpleNamespace

    from app.jobs.proposal_store import _content_from_facts

    facts = [SimpleNamespace(dimension="Appearance", content="A tall storm-mage.")]
    zh = _content_from_facts("X", facts, language="zh")
    en = _content_from_facts("Alaric", facts, language="en")
    assert "补全" in zh and "：" in zh
    assert "补全" not in en
    assert en.startswith("Alaric — enrichment:") and "Appearance: A tall storm-mage." in en


def test_build_proposal_fields_preserves_non_location_kind():
    # #2: the persist field-builder carries the proposal's REAL kind through (KB8
    # write-back then writes the correct glossary kind).
    from app.generation.provenance import SourceRef, make_enriched_fact
    from app.jobs.proposal_store import build_proposal_fields

    fact = make_enriched_fact(
        user_id="u", project_id="p", entity_kind="character", canonical_name="姜子牙",
        target_ref="姜子牙", dimension="外貌", content="姜子牙白须道袍。",
        technique="retrieval",
        source_refs=[SourceRef(corpus_id="c", chunk_id="c", chunk_index=0, score=0.5)],
        model_ref="m", confidence=0.3, qualified_origin=True,
    )
    fields = build_proposal_fields(
        user_id="u", project_id="p", entity_kind="character", canonical_name="姜子牙",
        target_ref="姜子牙", technique="retrieval", confidence=0.3, facts=[fact],
        verify=None, source_refs=[], gap_ref="姜子牙",
    )
    assert fields["entity_kind"] == "character"
    assert "外貌" in fields["provenance_json"]["dimensions"]


def test_facts_from_proposal_neutral_fallback_dimension():
    # de-bias C1 (#8): a dimension-less proposal falls back to the neutral stable id
    # "description", NOT the old zh-hardcoded "补充".
    from types import SimpleNamespace

    from app.services.writeback import WritebackService

    prop = SimpleNamespace(confidence=0.3, provenance_json={}, content="some lore")
    facts = WritebackService._facts_from_proposal(prop)
    assert len(facts) == 1
    assert facts[0]["dimension"] == "description"
    assert facts[0]["content"] == "some lore"
