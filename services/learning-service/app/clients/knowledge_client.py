"""Q4b-feed — knowledge-service internal client (run-sample fetch).

The eval-runner judges an online extraction by fetching its items+source from
knowledge-service (the run-attributable store worker-ai wrote for opted-in
runs), then feeding `run_online_judge`. A 404 means no sample exists (the run's
project didn't opt into save_raw_extraction, it wasn't a succeeded chapter, or
the 7-day TTL pruned it) — the eval-runner falls back to structural-only.

Internal auth: X-Internal-Token (service-to-service). NO gateway hop — this is
an internal-network call, same pattern as worker-ai → knowledge-service.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class KnowledgeClient:
    def __init__(self, *, base_url: str, internal_token: str, timeout: float = 10.0):
        self._base_url = base_url.rstrip("/")
        self._headers = {"X-Internal-Token": internal_token}
        self._timeout = timeout

    async def fetch_run_sample(self, run_id: str) -> dict[str, Any] | None:
        """GET the items+source sample for `run_id`.

        Returns ``{"items": {...}, "source_text": "...", ...}`` on 200, or None
        on 404 (no sample) / any transport error (best-effort — a fetch failure
        only drops a judging opportunity, never fails the consumer)."""
        url = f"{self._base_url}/internal/extraction/runs/{run_id}/sample"
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.get(url, headers=self._headers)
        except httpx.HTTPError:
            logger.warning(
                "Q4b-feed: run-sample fetch failed run=%s (non-fatal — "
                "structural-only this run)", run_id, exc_info=True,
            )
            return None
        if resp.status_code == 404:
            return None
        if resp.status_code != 200:
            logger.warning(
                "Q4b-feed: run-sample fetch run=%s returned %s (non-fatal)",
                run_id, resp.status_code,
            )
            return None
        return resp.json()


def build_knowledge_client(*, base_url: str, internal_token: str) -> KnowledgeClient:
    return KnowledgeClient(base_url=base_url, internal_token=internal_token)
