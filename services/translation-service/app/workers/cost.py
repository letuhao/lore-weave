"""Best-effort job-cost resolver (Unified Job Control Plane P4 — D-JOBS-P4-TRANSLATION-COST).

The translation gateway `usage` carries only tokens, never cost. To surface a job-level
cost in the unified Jobs GUI we price the job's ACTUAL summed tokens via provider-registry's
estimate oracle (POST /internal/billing/estimate — the same token-count→USD function the
campaign launch-estimate uses). Resolve OUTSIDE the finalize DB transaction (network I/O;
H1); the result rides the terminal job event + persists to translation_jobs.cost_usd.

Best-effort: returns None on any failure or an unpriced model (the GUI renders cost
null-safe). The figure is "actual tokens × list price" — a faithful cost for display, not
a re-derivation of the exact per-call billed amount.
"""
from __future__ import annotations

import logging

import httpx
from loreweave_internal_client import build_internal_client

from app.config import settings

log = logging.getLogger(__name__)

_TIMEOUT = 5.0  # seconds (build_internal_client takes a float, not httpx.Timeout)


async def resolve_job_cost_usd(
    *,
    owner_user_id: str,
    model_source: str | None,
    model_ref: str | None,
    input_tokens: int,
    output_tokens: int,
) -> float | None:
    """POST /internal/billing/estimate for one item → estimated_usd, or None on missing
    model / non-200 / transport / decode failure / unpriced model."""
    if not model_source or not model_ref:
        return None
    if input_tokens <= 0 and output_tokens <= 0:
        return None
    base = settings.provider_registry_internal_url.rstrip("/")
    url = f"{base}/internal/billing/estimate"
    body = {
        "owner_user_id": owner_user_id,
        "items": [{
            "label": "translation",
            "model_source": model_source,
            "model_ref": str(model_ref),
            "input_tokens": int(input_tokens),
            "output_tokens": int(output_tokens),
        }],
    }
    try:
        async with build_internal_client(settings.provider_registry_internal_url, internal_token=settings.internal_service_token, timeout_s=_TIMEOUT) as client:
            resp = await client.post(
                url, json=body,
            )
        if resp.status_code != 200:
            log.debug("billing/estimate %d for model %s", resp.status_code, model_ref)
            return None
        items = resp.json().get("items") or []
        if not items:
            return None
        usd = items[0].get("estimated_usd")
        return float(usd) if usd is not None else None
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        log.debug("billing/estimate resolve failed for %s: %s", model_ref, exc)
        return None
