"""Which substrate can honour `as_of`, and who gets to say so (plan T26).

This rule used to live in `services/knowledge-gateway/src/kal/temporal.ts`. It is a DOMAIN
rule — "can the KG answer a story-time question, or would it hand back transaction-time rows
that leak spoilers?" — and it was being decided in TypeScript by a gateway that owns no
substrate. D0.1 invalidates that: the gateway forwards what the service reports.

── WHY THE GATEWAY DECIDING IT WAS A BUG, NOT JUST A LAYERING PREFERENCE ─────────────────
The gateway read `KG_TEMPORAL_ENABLED` from its OWN environment. Nothing tied that flag to
the graph it describes. A gateway deployed with the flag on, in front of a knowledge-service
whose KG had not been migrated, would advertise `ordinal_valid_time` and then forward
`as_of` to a substrate that silently answers in transaction time — a spoiler leak produced by
two services disagreeing about a boolean. The service that owns the substrate is the only
process that can answer this without coordination.

── DEGRADE-SAFE MEANS DROP THE FILTER, NOT THE GUARD ─────────────────────────────────────
When the KG cannot honour `as_of`, the request is answered WITHOUT the time filter rather
than with transaction-time rows presented as story-time ones, and the response says so via
`temporal_capability.kg`. Dropping the filter loses precision; honouring it dishonestly
loses the reader's plot. The caller can see which happened, which is the part that makes
the degrade safe rather than merely quiet.
"""

from __future__ import annotations

from typing import Literal, TypedDict

from app.config import settings

__all__ = ["TemporalCapability", "kg_as_of_or_drop", "temporal_capability"]


class TemporalCapability(TypedDict):
    glossary: Literal["ordinal_valid_time", "current_only"]
    kg: Literal["ordinal_valid_time", "from_order_only", "temporal_unsupported"]


def temporal_capability() -> TemporalCapability:
    """What each source can honour for `as_of` (§12.5.1 / A5).

    `glossary` is a constant because the bi-temporal fact substrate (foundation F1) is not
    optional — `entity_facts` has story-time intervals by construction. `kg` is
    configuration-dependent until foundation F3 lands everywhere.
    """
    return {
        "glossary": "ordinal_valid_time",
        "kg": "ordinal_valid_time" if settings.kg_temporal_enabled else "temporal_unsupported",
    }


def kg_as_of_or_drop(as_of: int | None) -> int | None:
    """The `as_of` a KG read should actually apply, or None to answer untimed.

    Deliberately NOT a raise. A caller asking for a story position it cannot have is the
    normal state of a KG mid-migration, not a client error — and a 4xx here would take out
    every timeline-aware read the moment a deployment lagged. The response's
    `temporal_capability.kg` is how the caller learns the request was answered untimed.
    """
    if as_of is None:
        return None
    return as_of if settings.kg_temporal_enabled else None
