"""usage-billing client (W4 — net-new for composition-service).

composition-service had NO billing client before W4 (the cowrite ENGINE spends
LLM tokens with zero pre-spend check — ``_execute_generate``). The Tier-W motif
ops (mine / arc-import / arc-conformance) are LLM-spend, so R1.3 mandates *"a real
usage-billing pre-check in the mine/import confirm effect — it is net-new."*

The client is modeled on chat-service's ``BillingClient`` shape (internal-token-
gated ``httpx`` client -> usage-billing-service) but adds a ``precheck`` method
that exists nowhere else. precheck reserves spend against usage-billing's real
guardrail subsystem (``POST /internal/billing/guardrail/reserve``): the endpoint
returns 200 when the estimated USD fits the caller's daily/monthly cap (and, for a
platform model, the platform balance) and 402 ``INSUFFICIENT_BUDGET`` when it does
not. A successful reserve places a hold the reconcile/sweep paths later settle —
i.e. the precheck is a real spend gate, not an advisory read.

MD-8 — FAIL-CLOSED: a billing-service outage (timeout / 5xx / connect error)
DENIES the new spend (``precheck`` -> ``False``) with the caller surfacing a clear
``billing_unavailable`` reason. Gating spend is the whole purpose of the precheck;
permitting unbounded spend on a billing outage is exactly the failure mode it
exists to prevent. (Contrast: a post-hoc ``log_usage`` record is best-effort
fail-OPEN — losing a usage RECORD is recoverable; permitting unbounded SPEND is
not.)
"""

from __future__ import annotations

import logging

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

__all__ = ["BillingClient", "get_billing_client"]


class BillingClient:
    def __init__(self) -> None:
        self._base = settings.usage_billing_service_url
        # usage-billing's /internal API enforces X-Internal-Token
        # (services/usage-billing-service/internal/api/server.go requireInternalToken).
        # Mirrors chat-service/knowledge-service: without it the call is 401.
        self._token = settings.internal_service_token

    async def precheck(
        self,
        *,
        owner_user_id: str,
        job_id: str,
        estimate_usd: float,
        model_source: str = "user_model",
    ) -> bool:
        """Reserve ``estimate_usd`` against the caller's spend guardrail BEFORE
        enqueuing an LLM-spend job. Returns ``True`` when the spend is within budget
        (a hold is placed, keyed idempotently by ``job_id``), ``False`` when the
        caller is over budget (402) OR on ANY billing-service error (MD-8 fail-CLOSED).

        ``job_id`` makes the reserve idempotent: a retried precheck for the same job
        returns the existing hold rather than double-reserving.
        """
        payload = {
            "owner_user_id": owner_user_id,
            "job_id": job_id,
            "estimated_usd": max(0.0, float(estimate_usd)),
            "model_source": model_source,
        }
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self._base}/internal/billing/guardrail/reserve",
                    json=payload,
                    headers={"X-Internal-Token": self._token},
                )
        except Exception as exc:  # noqa: BLE001 — any transport error fails CLOSED (MD-8)
            logger.warning("billing precheck transport error (fail-closed deny): %s", exc)
            return False
        if resp.status_code == 200:
            return True
        if resp.status_code == 402:
            # Over the daily/monthly cap or the platform balance — a clean deny.
            logger.info("billing precheck denied (402) for user %s: %s",
                        owner_user_id, resp.text[:200])
            return False
        # Any other status (4xx config error, 5xx outage) is a fail-CLOSED deny —
        # we never let spend through on an ambiguous billing response.
        logger.warning("billing precheck unexpected status %d (fail-closed deny): %s",
                       resp.status_code, resp.text[:200])
        return False


_client: BillingClient | None = None


def get_billing_client() -> BillingClient:
    global _client
    if _client is None:
        _client = BillingClient()
    return _client
