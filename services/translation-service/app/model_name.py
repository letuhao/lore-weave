"""Best-effort model-NAME resolver — thin shim over the shared SDK.

P3 SDK-first: this was a byte-identical copy across 5 services; the implementation now
lives in `loreweave_internal_client.resolve_model_name`. This shim wires translation's
provider-registry base URL + internal token and keeps the same signature so callers
(`from .model_name import resolve_model_name`) are unchanged.

Best-effort: `None` on missing source/ref, non-200, or transport/decode error. Resolve
OUTSIDE a job-create DB transaction (network I/O; H1).
"""
from __future__ import annotations

from loreweave_internal_client import resolve_model_name as _resolve

from .config import settings


async def resolve_model_name(model_source: str | None, model_ref: str | None) -> str | None:
    """GET /internal/models/{source}/{ref}/info → provider_model_name; None on any failure."""
    return await _resolve(
        settings.provider_registry_internal_url,
        model_source,
        model_ref,
        internal_token=settings.internal_service_token,
    )
