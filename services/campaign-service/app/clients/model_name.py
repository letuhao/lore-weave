"""Best-effort model-NAME resolver (Unified Job Control Plane P4 — D-JOBS-P4-CAMPAIGN-MODEL-NAMES).

Resolves a BYOK ``(model_source, model_ref)`` → ``provider_model_name`` via provider-registry's
internal model-info endpoint, so a campaign's lifecycle event can carry the human per-stage model
NAMES (not the ref-UUIDs) for the unified Jobs GUI.

Best-effort: ``None`` on any failure. Resolve OUTSIDE the campaign-create DB transaction
(network I/O; H1) — the projection's COALESCE merge keeps the create-time names across the later
status events, which omit them. Mirrors composition/lore-enrichment resolvers.
"""
from __future__ import annotations

import logging

import httpx

from ..config import settings

log = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(5.0)


async def resolve_model_name(model_source: str | None, model_ref: str | None) -> str | None:
    """GET /internal/models/{model_source}/{model_ref}/info → provider_model_name.
    None on missing source/ref / non-200 / transport / decode failure."""
    if not model_source or not model_ref:
        return None
    base = settings.provider_registry_internal_url.rstrip("/")
    url = f"{base}/internal/models/{model_source}/{model_ref}/info"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.get(
                url, headers={"X-Internal-Token": settings.internal_service_token},
            )
        if resp.status_code != 200:
            log.debug("model-info %d for %s", resp.status_code, model_ref)
            return None
        name = (resp.json().get("provider_model_name") or "").strip()
        return name or None
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.debug("model-info resolve failed for %s: %s", model_ref, exc)
        return None
