"""Best-effort model-context-window resolver — thin shim over the shared SDK.

Mirrors `model_name.py`'s shape: the implementation lives in
`loreweave_internal_client.resolve_context_length`; this shim wires knowledge's
provider-registry base URL + internal token and keeps the same call signature.

Best-effort by design: `None` on missing ref, non-200, transport/decode error, or when
provider-registry itself reports the window as unresolved — never fabricate a number
(see provider-registry-service's `getModelContextWindow` docstring). Callers supply
their own conservative default for the genuinely-unknown case.
"""
from __future__ import annotations

from loreweave_internal_client import resolve_context_length as _resolve

from app.config import settings


async def resolve_context_length(model_source: str | None, model_ref: str | None) -> int | None:
    """GET /v1/model-registry/models/{ref}/context-window → context_window; None on failure."""
    return await _resolve(
        settings.provider_registry_internal_url,
        model_source,
        model_ref,
        internal_token=settings.internal_service_token,
    )
