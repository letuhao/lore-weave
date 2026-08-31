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

from loreweave_internal_client import build_internal_client
from loreweave_jobs import JobEvent

from .config import settings
from .projection import store

log = logging.getLogger(__name__)

# service (as stored in job_projection.service) → (internal base url, GET path). The GET
# returns ALL owners' rows updated since the watermark, in JobEvent.to_payload() shape.
# A source not listed simply isn't swept (its outbox emit still feeds the projection).
_RECONCILE: dict[str, tuple[str, str]] = {
    "knowledge": (settings.knowledge_service_internal_url, "/internal/knowledge/jobs"),
    "composition": (settings.composition_service_internal_url, "/internal/composition/jobs"),
    "video_gen": (settings.video_gen_service_internal_url, "/internal/video_gen/jobs"),
    "lore_enrichment": (settings.lore_enrichment_service_internal_url, "/internal/lore_enrichment/jobs"),
    "translation": (settings.translation_service_internal_url, "/internal/translation/jobs"),
    "book": (settings.book_service_internal_url, "/internal/book/jobs"),
}

# Page size for one source fetch. Shared contract: the sweeper passes it as `?limit=`
# and each source caps at it, so a FULL page (len == _PAGE_LIMIT) signals "more rows
# may exist beyond this page" → the watermark must NOT jump to now (that would skip the
# overflow); it advances only to the last row's timestamp so the next sweep continues.
_PAGE_LIMIT = 1000


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
            # The ABSENCE pass rides the same tick and runs AFTER the delta sweep, never
            # before: a row the sweep is about to heal must not be asked about and marked
            # gone in the same pass. Opt-in — it is the only loop here that writes a terminal
            # status no owning service emitted.
            if settings.absence_check_enabled:
                await self.verify_absent_once()

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
        # Watermark advance — cap-aware so a paginated overflow is NEVER skipped:
        #   - FULL page (len >= _PAGE_LIMIT): more rows may exist beyond it → advance only
        #     to the last row's timestamp (rows are updated_at ASC, so [-1] is the max), and
        #     the next sweep continues from there (>= re-reads the boundary, idempotent).
        #   - PARTIAL page: caught up → jump to sweep_start (bounds the next query window,
        #     and a row updated mid-fetch lands >= sweep_start, caught next sweep).
        if len(rows) >= _PAGE_LIMIT and rows:
            self._watermark[service] = max(since, store._ts(rows[-1].get("occurred_at")))
        else:
            self._watermark[service] = sweep_start
        if n:
            log.info("reconcile %s: %d/%d rows applied", service, n, len(rows))
        return n

    async def verify_absent_once(self) -> dict[str, Any]:
        """Ask each owner about the rows this projection still calls LIVE, and mark what is gone.

        🔴 THE HALF THE BACKSTOP NEVER HAD (owner ruling 2026-08-31, DQ-T65: "a non-terminal
        row whose owner no longer has it is DEAD, and is marked so"). `_sweep_source` reads
        `?since=` — a DELTA — so it can only ever add: a row that stopped changing, or whose
        owning row was deleted, never appears in another window. Measured 2026-08-31:

            28 rows at running/pending/paused, up to 74 days old, `cancel` advertised on all
            22 of 22 composition rows had NO owning row at all
            446 of 910 composition projection rows have no owner (mostly harness teardown)

        DEGRADE-SAFE, AND IT SAYS SO. A source that does not understand `?ids=` answers 422 or
        404; that service is reported UNVERIFIED and nothing is marked. Silence would be the
        worse failure here — an absence pass that quietly verifies nothing looks exactly like
        one where everything is present.

        WHAT `dead` IS CALLED, and it is the one part that is a compromise: `failed` with
        `detail_status='owner_no_longer_has_row'` and an explicit error. A distinct terminal
        status would be truer — the job may well have COMPLETED before its row was removed —
        but `JobStatus` is a closed enum read in 40 files and at least six places carry their
        own hard-coded terminal tuple, so adding a member is a cross-cutting change that
        deserves its own decision rather than riding in on this one. Filed, with that count.
        """
        out: dict[str, Any] = {}
        for service in _RECONCILE:
            try:
                out[service] = await self._verify_source(service)
            except Exception as exc:  # noqa: BLE001 — one bad source never stalls the rest
                log.warning("absence check of %s failed: %s", service, exc)
                out[service] = {"unverified": True, "reason": str(exc)[:200]}
        return out

    async def _verify_source(self, service: str) -> dict[str, Any]:
        base, path = _RECONCILE[service]
        ids = await store.list_non_terminal_ids(
            self._pool, service, older_than_s=int(settings.absence_check_min_age_s))
        ids = ids[: int(settings.absence_check_batch)]
        if not ids:
            return {"asked": 0, "gone": 0}
        try:
            rows = await self._fetch(base, path, ids=ids)
        except Exception as exc:  # noqa: BLE001
            # UNVERIFIED IS A RESULT, NOT A SILENCE. A source without the `?ids=` mode answers
            # 422/404; reporting 0-gone here would be indistinguishable from "everything is
            # present" and is exactly the degrade this loop has been burned by.
            log.warning("absence check %s: source cannot answer ?ids= (%s) — %d rows UNVERIFIED",
                        service, str(exc)[:120], len(ids))
            return {"asked": len(ids), "unverified": True, "reason": str(exc)[:200]}
        present = {str(r.get("job_id")) for r in rows if isinstance(r, dict)}
        gone = [i for i in ids if i not in present]
        marked = 0
        for job_id in gone:
            if await store.mark_owner_lost(self._pool, service, job_id):
                marked += 1
        if marked:
            log.info("absence check %s: %d of %d asked are gone from their owner — marked",
                     service, marked, len(ids))
        return {"asked": len(ids), "gone": len(gone), "marked": marked}

    async def _fetch(self, base: str, path: str, since: datetime | None = None,
                     *, ids: list[str] | None = None) -> list[dict[str, Any]]:
        url = f"{base}{path}"
        # Exactly one mode, mirroring the contract the sources enforce: "gone" and "not
        # changed since" are different answers and must not share a response.
        params: dict[str, Any] = ({"ids": ids} if ids is not None
                                  else {"since": since.isoformat(), "limit": _PAGE_LIMIT})
        # W5 (ephemeral wave): shared factory bakes X-Internal-Token + JSON.
        async with build_internal_client(
            base, internal_token=settings.internal_service_token, timeout_s=15.0,
        ) as client:
            resp = await client.get(url, params=params)
        resp.raise_for_status()
        body = resp.json()
        return body.get("jobs", []) if isinstance(body, dict) else []

    async def stop(self) -> None:
        self._stop.set()
