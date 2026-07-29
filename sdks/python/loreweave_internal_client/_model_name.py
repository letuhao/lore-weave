"""Shared best-effort model-NAME resolver.

The inventory (P3 SDK-first) found `resolve_model_name` copy-pasted ~byte-identically
across FIVE services (translation / knowledge / composition / campaign / video-gen) —
each `GET /internal/models/{source}/{ref}/info` → `provider_model_name`, each best-effort
(`None` on any failure), differing ONLY in which settings attr holds the target base URL.
This is the single implementation; each service keeps a thin shim wiring its base_url +
token (mirrors the `loreweave_grants` shim pattern).

Best-effort by design: returns `None` on missing source/ref, non-200, or transport/decode
error. A null model NAME is tolerated end-to-end (the Jobs GUI renders null-safe; the
projection COALESCE merge never wipes a previously-set value). Resolve OUTSIDE a job-create
DB transaction (network I/O — never hold a tx across it; H1).
"""
from __future__ import annotations

import logging
from typing import Any

import httpx

from ._transport import HEADER_INTERNAL_TOKEN, build_timeout

log = logging.getLogger(__name__)


async def resolve_model_name(
    base_url: str,
    model_source: str | None,
    model_ref: str | None,
    *,
    internal_token: str,
    timeout_s: float = 5.0,
) -> str | None:
    """GET {base_url}/internal/models/{source}/{ref}/info → provider_model_name.

    Returns `None` on missing source/ref, non-200, or transport/decode failure — never
    raises (best-effort; the caller tolerates a null name).
    """
    info = await resolve_model_info(
        base_url, model_source, model_ref, internal_token=internal_token, timeout_s=timeout_s)
    return (info or {}).get("provider_model_name")


async def resolve_model_info(
    base_url: str,
    model_source: str | None,
    model_ref: str | None,
    *,
    internal_token: str,
    timeout_s: float = 5.0,
) -> dict[str, Any] | None:
    """GET {base_url}/internal/models/{source}/{ref}/info →
    {provider_kind, provider_model_name, capability_flags}.

    The registry is AUTHORITATIVE about what a `model_ref` actually is. Callers that need the
    provider kind (not just the display name) must not take a client-supplied hint for it: the
    reasoning classifier keys off the kind to decide whether hidden thinking gets disabled, and
    a request that simply omitted the hint would silently classify as "not a local model" and
    send no suppression at all — the empty-draft failure, re-entered through the front door.

    Best-effort like its caller: `None` on missing source/ref, non-200, or transport/decode
    failure — never raises. A caller that gets `None` is UNVERIFIED, not "confirmed absent",
    and should say so rather than treat it as a negative answer.
    """
    if not model_source or not model_ref:
        return None
    url = f"{base_url.rstrip('/')}/internal/models/{model_source}/{model_ref}/info"
    try:
        async with httpx.AsyncClient(timeout=build_timeout(timeout_s)) as client:
            resp = await client.get(url, headers={HEADER_INTERNAL_TOKEN: internal_token})
        if resp.status_code != 200:
            log.debug("model-info %d for %s", resp.status_code, model_ref)
            return None
        body = resp.json()
        name = (body.get("provider_model_name") or "").strip()
        kind = (body.get("provider_kind") or "").strip()
        if not name and not kind:
            return None
        # capability_flags carries per-model behaviour overrides (notably `reasoning_control`,
        # which the reasoning classifier checks BEFORE its name heuristic). The route renders it
        # as an object, but an older registry predates the field — default to {} so a caller can
        # always treat it as a mapping, and re-check the type rather than trusting the peer.
        flags = body.get("capability_flags")
        return {
            "provider_model_name": name,
            "provider_kind": kind,
            "capability_flags": flags if isinstance(flags, dict) else {},
        }
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        log.debug("model-info resolve failed for %s: %s", model_ref, exc)
        return None
