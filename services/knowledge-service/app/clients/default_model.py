"""User-global default-model resolver (KN model-roles — tier 3 fallback).

Resolves a user's per-capability DEFAULT model (BYOK, set from Settings) via
provider-registry's internal route, so an extraction role with no project- or
role-scoped model can fall back to "the model this user picked for everything".

Best-effort by design: returns ``None`` on any failure (no default set → 404,
non-200, transport/decode error). None means "no user-global default" — the
caller's precedence chain then drops to the env floor / off. NEVER a platform
env model (provider-gateway + no-hardcoded-model invariants — the default is a
per-user BYOK `user_default_models` row).
"""
from __future__ import annotations

import logging

import httpx
from loreweave_internal_client import build_internal_client

from app.config import settings
from app.logging_config import trace_id_var

log = logging.getLogger(__name__)


async def resolve_user_default_model(
    user_id: str, capability: str = "chat",
) -> str | None:
    """GET /internal/default-models/{capability}?user_id= → user_model_id.

    Returns the BYOK ``user_model_id`` (always ``model_source='user_model'``),
    or None when the user has set no default for this capability (404) / on any
    transport or decode failure. The extraction LLM roles resolve against the
    ``chat`` capability (extraction runs a chat model)."""
    if not user_id:
        return None
    base = settings.provider_registry_internal_url.rstrip("/")
    url = f"{base}/internal/default-models/{capability}"
    try:
        # W5 (ephemeral wave): shared factory bakes X-Internal-Token + JSON + trace.
        async with build_internal_client(
            base, internal_token=settings.internal_service_token,
            timeout_s=5.0, trace_id_provider=trace_id_var.get,
        ) as client:
            resp = await client.get(url, params={"user_id": user_id})
        if resp.status_code == 404:  # DEFAULT_MODEL_NOT_SET — expected, not an error
            return None
        if resp.status_code != 200:
            log.debug("default-model %d for user=%s cap=%s", resp.status_code, user_id, capability)
            return None
        ref = (resp.json().get("user_model_id") or "").strip()
        return ref or None
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.debug("default-model resolve failed for user=%s: %s", user_id, exc)
        return None
