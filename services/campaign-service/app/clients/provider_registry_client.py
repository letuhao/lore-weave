"""Internal client for the provider-registry pricing oracle (S5a).

Calls POST /internal/billing/estimate — a pure token-count → USD function. The
oracle owns pricing; this service owns the workload heuristics (see app/estimate.py).
"""

from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class EstimateUnavailable(Exception):
    """The pricing oracle was unreachable or returned a non-2xx — the estimate
    cannot be priced. The route maps this to a 502 (an estimate is informational;
    fail-soft is acceptable, but never silently return a $0 estimate)."""


class ProviderRegistryEstimateClient:
    def __init__(self, base_url: str, internal_token: str, timeout_s: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_s),
            headers={"X-Internal-Token": internal_token},
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def estimate(self, *, owner_user_id: str, items: list[dict]) -> list[dict]:
        """POST the batch → returns the per-item results
        ([{label, status, estimated_usd}]). Raises EstimateUnavailable on
        network failure or a non-2xx response."""
        url = f"{self._base_url}/internal/billing/estimate"
        body = {"owner_user_id": owner_user_id, "items": items}
        try:
            resp = await self._http.post(url, json=body)
        except httpx.RequestError as exc:
            raise EstimateUnavailable(f"pricing oracle: {exc}") from exc
        if not resp.is_success:
            raise EstimateUnavailable(f"pricing oracle {resp.status_code}: {resp.text[:300]}")
        return resp.json().get("items", [])
