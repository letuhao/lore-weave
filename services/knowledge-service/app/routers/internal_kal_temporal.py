"""The KAL's temporal-capability authority (plan T26).

One endpoint, so the gateway can FORWARD what the substrate's owner reports instead of
deciding it from its own environment. See `app/kal/temporal.py` for why the gateway holding
this rule was a correctness bug rather than a layering preference.

Cheap on purpose: no database access, no per-book variation. The gateway caches it briefly
and stamps it onto reads that are served by glossary — which is precisely why it has to be
fetchable rather than merely returned alongside KG responses.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.kal.temporal import TemporalCapability, temporal_capability
from app.middleware.internal_auth import require_internal_token

router = APIRouter(
    prefix="/internal/kal",
    tags=["Internal", "KAL"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("/temporal-capability")
async def get_temporal_capability() -> TemporalCapability:
    """What each substrate can honour for `as_of`. The gateway forwards this verbatim."""
    return temporal_capability()
