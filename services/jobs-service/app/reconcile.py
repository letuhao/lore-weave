"""Reconcile sweep (Unified Job Control Plane — H1 backstop).

The projection is a MIRROR of each service's job rows (the SSOT). The transactional
outbox emit (P1) is the PRIMARY path — an event is written in the same tx as the
status change and relayed exactly-once. This periodic sweep is the BACKSTOP: it
re-reads each owning service's job rows (`GET /internal/{svc}/jobs?since=`) and
upserts them to heal any residual drift (outbox lag, a projection-service outage,
a dropped event). Outbox = primary; reconcile = safety net.

Design:
  - One source per owning service: `(base_url, "/internal/{svc}/jobs")`. The GET is
    internal-token S2S and returns ALL owners' rows (the projection mirrors every
    owner; user-scoping happens at the READ API, not here) in `JobEvent.to_payload()`
    shape, so each row flows through the SAME idempotent+monotonic `upsert_job_event`
    the live stream uses (a snapshot's `occurred_at` = the row's `updated_at`, so it
    competes fairly with stream events — a stale snapshot can't regress a fresher row).
  - Per-source watermark = the sweep's START time (advanced only on success). Any row
    updated during/after a fetch has `updated_at >= sweep_start` → caught next sweep;
    re-reading the overlap is harmless (idempotent). First sweep looks back
    `reconcile_lookback_s` (also covers a restart that wiped the in-memory watermark).
  - Per-source failure is logged + skipped — one unreachable service (or one whose
    `?since=` endpoint hasn't shipped yet → 404) never stalls the loop or the others.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from loreweave_jobs import JobEvent

from .config import settings
from .projection import store

log = logging.getLogger(__name__)

# service (as stored in job_projection.service) → (internal base url, GET path).
# GROWS one source per reconcile increment; a source not listed simply isn't swept
# (its outbox emit still feeds the projection). Increment A ships composition as the
# proof source; B adds knowledge / video_gen / lore_enrichment / translation.
_RECONCILE: dict[str, tuple[str, str]] = {
    "composition": (settings.composition_service_internal_url, "/internal/composition/jobs"),
}

_TIMEOUT = httpx.Timeout(15.0)


class ReconcileSweeper:
    """Periodically re-reads each source's job rows and upserts the projection."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool
        self._stop = asyncio.Event()
        # Per-source watermark; first sweep looks back reconcile_lookback_s.
        start = datetime.now(timezone.utc) - timedelta(seconds=settings.reconcile_lookback_s)
        self._watermark: dict[str, datetime] = {svc: start for svc in _RECONCILE}

    async def run(self) -> None:
        if not settings.reconcile_enabled or settings.reconcile_interval_s <= 0:
            log.info("reconcile sweep disabled (reconcile_enabled=%s)", settings.reconcile_enabled)
            return
        log.info("reconcile sweep started (interval=%.0fs, sources=%s)",
                 settings.reconcile_interval_s, list(_RECONCILE))
        # Wait first so the live consumer has a chance to drain the backlog before the
        # backstop runs — the sweep is for residual drift, not cold-start.
        while not self._stop.is_set():
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=settings.reconcile_interval_s)
            except asyncio.TimeoutError:
                pass
            if self._stop.is_set():
                break
            await self.sweep_once()

    async def sweep_once(self) -> dict[str, int]:
        """Sweep every source once. Returns {service: rows_applied} (for tests/obs)."""
        applied: dict[str, int] = {}
        for service in _RECONCILE:
            try:
                applied[service] = await self._sweep_source(service)
            except Exception as exc:  # noqa: BLE001 — one bad source never stalls the rest
                log.warning("reconcile sweep of %s failed: %s", service, exc)
                applied[service] = 0
        return applied

    async def _sweep_source(self, service: str) -> int:
        base, path = _RECONCILE[service]
        since = self._watermark[service]
        sweep_start = datetime.now(timezone.utc)
        rows = await self._fetch(base, path, since)
        n = 0
        for row in rows:
            try:
                event = JobEvent.from_payload(row)
            except (KeyError, ValueError) as exc:
                log.warning("reconcile %s: unparseable row skipped: %s", service, exc)
                continue
            if await store.upsert_job_event(self._pool, event):
                n += 1
        # Advance the watermark only on a clean fetch (sweep_start, not max-row-ts, so a
        # row updated mid-fetch isn't skipped next time; the overlap re-read is idempotent).
        self._watermark[service] = sweep_start
        if n:
            log.info("reconcile %s: %d/%d rows applied", service, n, len(rows))
        return n

    async def _fetch(self, base: str, path: str, since: datetime) -> list[dict[str, Any]]:
        url = f"{base}{path}"
        headers = {"X-Internal-Token": settings.internal_service_token}
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(url, params={"since": since.isoformat()}, headers=headers)
        resp.raise_for_status()
        body = resp.json()
        return body.get("jobs", []) if isinstance(body, dict) else []

    async def stop(self) -> None:
        self._stop.set()
