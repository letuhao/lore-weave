"""Observability + probe routes (RAID C18).

  * ``/metrics`` — Prometheus text exposition of the C18 registry. Internal-only
    (the scraper talks to the service directly); NO JWT. MUST NOT depend on the
    DB being up — a scrape must succeed even when Postgres is down so an operator
    can read jobs/proposals/latency during an incident (C18 adversary focus
    "metrics endpoint must not depend on DB being up").
  * ``/ready`` — readiness probe (DEFERRED-042). Acquires the pool and runs
    ``SELECT 1``: 200 when the DB is reachable, **503** when the pool is
    unavailable or the query fails. This is SEPARATE from ``/health`` (constant-ok
    liveness in main.py): an orchestrator gates traffic on ``/ready`` (DB dropped
    after startup → 503 → drained), but does NOT kill the pod on a brief DB blip
    (``/health`` stays 200 so liveness never trips → no crash-loop). C18 adversary
    focus "healthcheck wiring must not crash the service when DB is briefly down".
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from app.db.pool import get_pool
from app.metrics import registry

logger = logging.getLogger(__name__)

router = APIRouter(tags=["observability"])


@router.get("/metrics")
async def metrics() -> Response:
    """Prometheus text exposition. No DB access — works during a DB outage."""
    return Response(
        content=generate_latest(registry),
        media_type=CONTENT_TYPE_LATEST,
    )


@router.get("/ready")
async def ready() -> Response:
    """Readiness probe (042): SELECT 1 against the pool → 200 / 503.

    Returns 503 (not 200, not 500) when the pool is not initialised OR the
    round-trip fails, so an orchestrator drains traffic from a DB-disconnected
    replica without killing it (that is /health's job — liveness, constant ok).
    """
    try:
        pool = get_pool()
        result = await pool.fetchval("SELECT 1")
        if result != 1:
            raise RuntimeError(f"unexpected SELECT 1 result: {result!r}")
    except Exception as exc:  # noqa: BLE001 — any DB failure → not-ready (503)
        logger.warning("readiness probe failed: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "detail": "database unavailable"},
        )
    return JSONResponse(status_code=200, content={"status": "ready"})
