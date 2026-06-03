"""Prometheus metrics tests (RAID C18).

Two acceptance facets from the C18 brief:
  1. ``/metrics`` is scrapeable — returns Prometheus text exposition with the
     expected counter NAMES present (parseable by a Prometheus client).
  2. Metric HONESTY — the counters MOVE when the LIVE C14 emitter emits lifecycle
     events; they are NOT hardcoded/stubbed (a fixed-number endpoint would be a
     false-green). We drive the real :class:`JobEventEmitter` (the runner's
     chokepoint) and assert the registry value increased.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from app import metrics
from app.jobs.events import JobEventEmitter, JobEventType


def _sample(name: str, labels: dict | None = None) -> float:
    """Read the current value of a counter sample from the C18 registry."""
    return metrics.registry.get_sample_value(name, labels or {}) or 0.0


def _client(monkeypatch) -> TestClient:
    # Reuse the /health test stubbing so the app's lifespan does not dial a real
    # DB just to scrape /metrics (the endpoint itself must not touch the DB).
    import app.db.pool as pool_mod
    import app.main as main_mod

    async def _fake_create_pool(dsn):
        return object()

    async def _fake_close_pool():
        return None

    async def _fake_run_migrations(pool):
        return None

    monkeypatch.setattr(main_mod, "create_pool", _fake_create_pool)
    monkeypatch.setattr(main_mod, "close_pool", _fake_close_pool)
    monkeypatch.setattr(main_mod, "run_migrations", _fake_run_migrations)
    monkeypatch.setattr(pool_mod, "create_pool", _fake_create_pool)
    monkeypatch.setattr(pool_mod, "close_pool", _fake_close_pool)
    return TestClient(main_mod.app)


def test_metrics_endpoint_scrapeable_with_expected_counters(monkeypatch):
    """/metrics returns parseable Prometheus text with the named counters."""
    with _client(monkeypatch) as client:
        resp = client.get("/metrics")

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")

    body = resp.text
    families = {f.name for f in text_string_to_metric_families(body)}
    # prometheus strips the _total suffix from the family name.
    expected = {
        "lore_enrichment_jobs_started",
        "lore_enrichment_jobs_completed",
        "lore_enrichment_jobs_failed",
        "lore_enrichment_jobs_paused",
        "lore_enrichment_proposals_created",
        "lore_enrichment_stage_duration_seconds",
        "lore_enrichment_cost_cap_pauses",
        "lore_enrichment_llm_calls",
        "lore_enrichment_embed_calls",
    }
    missing = expected - families
    assert not missing, f"/metrics missing expected counter families: {missing}"


def test_metrics_endpoint_does_not_require_db(monkeypatch):
    """A /metrics scrape must succeed even when the DB pool is unavailable.

    The endpoint never calls get_pool, so we don't even stub it — the app's
    lifespan still needs a stubbed pool to START, which _client provides, but
    the /metrics handler path itself touches no DB.
    """
    with _client(monkeypatch) as client:
        resp = client.get("/metrics")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_counters_move_from_live_emitter():
    """The counters increment from the REAL emit() path — not hardcoded."""
    em = JobEventEmitter(
        None, job_id="job-metrics", project_id="proj-m", user_id="user-m"
    )

    before_started = _sample("lore_enrichment_jobs_started_total")
    before_completed = _sample("lore_enrichment_jobs_completed_total")
    before_prop = _sample(
        "lore_enrichment_proposals_created_total",
        {"source_type": "enriched:retrieval"},
    )
    before_pause = _sample("lore_enrichment_cost_cap_pauses_total")
    before_stage = metrics.registry.get_sample_value(
        "lore_enrichment_stage_duration_seconds_count",
        {"technique": "retrieval"},
    ) or 0.0

    await em.emit(JobEventType.STARTED, data={"gap_count": 1})
    await em.emit(
        JobEventType.STAGE_COMPLETED,
        gap_ref="g1",
        data={"elapsed_seconds": 1.5, "technique": "retrieval"},
    )
    await em.emit(
        JobEventType.PROPOSAL_CREATED,
        gap_ref="g1",
        data={"technique": "retrieval", "proposal_id": "p1"},
    )
    await em.emit(
        JobEventType.PAUSED,
        gap_ref="g2",
        data={"reason": "cost_cap"},
    )
    await em.emit(JobEventType.COMPLETED, data={"proposals_total": 1})

    assert _sample("lore_enrichment_jobs_started_total") == before_started + 1
    assert _sample("lore_enrichment_jobs_completed_total") == before_completed + 1
    assert (
        _sample(
            "lore_enrichment_proposals_created_total",
            {"source_type": "enriched:retrieval"},
        )
        == before_prop + 1
    )
    assert _sample("lore_enrichment_cost_cap_pauses_total") == before_pause + 1
    after_stage = metrics.registry.get_sample_value(
        "lore_enrichment_stage_duration_seconds_count",
        {"technique": "retrieval"},
    )
    assert after_stage == before_stage + 1


@pytest.mark.asyncio
async def test_deduped_event_does_not_double_count():
    """A re-emit of the same logical event (resume) must not double-count."""
    em = JobEventEmitter(
        None, job_id="job-dedupe", project_id="p", user_id="u"
    )
    before = _sample("lore_enrichment_jobs_started_total")
    await em.emit(JobEventType.STARTED, data={})
    await em.emit(JobEventType.STARTED, data={})  # duplicate — dedupe-skipped
    assert _sample("lore_enrichment_jobs_started_total") == before + 1


@pytest.mark.asyncio
async def test_unknown_technique_falls_back_to_bare_enriched():
    """A future/unknown technique never crashes recording — bare 'enriched'."""
    em = JobEventEmitter(None, job_id="job-unk", project_id="p", user_id="u")
    before = _sample(
        "lore_enrichment_proposals_created_total", {"source_type": "enriched"}
    )
    await em.emit(
        JobEventType.PROPOSAL_CREATED,
        gap_ref="g",
        data={"technique": "some_future_technique"},
    )
    assert (
        _sample(
            "lore_enrichment_proposals_created_total", {"source_type": "enriched"}
        )
        == before + 1
    )
