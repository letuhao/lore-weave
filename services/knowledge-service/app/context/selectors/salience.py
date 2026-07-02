"""Salience-weighted entity ranking (Track 4 P1 — R-T4-01).

Blends the P0 access-log signal (how often / how recently THIS user surfaced an
entity) into the glossary entity ranking, so entities the user keeps returning to
rank higher and survive budget-trim longer. Read-time Ebbinghaus decay — no cron,
always fresh.

`weight == 0` (the default) short-circuits to the identity: the returned list is
the input list unchanged (byte-identical to pre-P1). Only a positive weight — set
once the POC eval shows the learned signal beats static ranking — re-orders.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from app.config import settings
from app.db.repositories.entity_access import EntitySalience

__all__ = ["blend_entity_salience", "apply_salience"]


async def apply_salience(entity_access_repo, entities: list, user_id: UUID, project_id: UUID) -> list:
    """Builder entry point: guard on the weight flag, load the (user, project)
    salience, and re-rank. The weight guard is FIRST so the default (0.0) does no
    DB read and returns the input unchanged — pre-P1 behaviour, byte-identical.
    A salience load failure is swallowed by the repo (→ {}), so this no-ops."""
    weight = settings.salience_access_weight
    if weight <= 0 or entity_access_repo is None or not entities:
        return entities
    salience = await entity_access_repo.load_salience(user_id, project_id)
    if not salience:
        return entities
    return blend_entity_salience(
        entities, salience,
        weight=weight,
        half_life_days=settings.salience_half_life_days,
        now=datetime.now(timezone.utc),
    )


def blend_entity_salience(
    entities: list,
    salience: dict[str, EntitySalience],
    *,
    weight: float,
    half_life_days: float,
    now: datetime,
):
    """Return `entities` re-sorted by `rank_score + weight * normalized_salience`.

    - `weight <= 0` OR no entities OR no salience → the input list, unchanged.
    - salience per entity = `retrieval_count * 0.5 ** (age_days / half_life_days)`
      (recency-decayed frequency), max-normalized across the project's rows to [0,1].
    - stable desc sort: entities with equal blended rank keep their original order,
      and an entity with no access row gets a 0 boost (no learned signal yet).

    `rank_score` on each entity is left untouched (it's the displayed score); only
    the ORDER changes, which is what feeds budget-trim (trims from the tail).
    """
    if weight <= 0 or not entities or not salience:
        return entities

    half_life = half_life_days if half_life_days > 0 else 1.0
    decayed: dict[str, float] = {}
    for eid, s in salience.items():
        age_days = max(0.0, (now - s.last_retrieved_at).total_seconds() / 86_400.0)
        decayed[eid] = s.retrieval_count * (0.5 ** (age_days / half_life))

    max_d = max(decayed.values(), default=0.0)
    if max_d <= 0:
        return entities  # all rows decayed to ~0 → no usable signal

    def _blended(e) -> float:
        eid = getattr(e, "entity_id", None)
        norm = (decayed.get(eid, 0.0) / max_d) if eid else 0.0
        return getattr(e, "rank_score", 0.0) + weight * norm

    # PINS LEAD, ALWAYS. A user-pinned entity is "always in context" — it must never
    # be re-ranked below a high-salience non-pinned one, or the full-mode budget-trim
    # (which pops from the tail) could drop the pin. Sort key = (is_pinned, blended),
    # reverse → all pins first (blended-ordered among themselves), then the rest.
    # Python's sort is stable → equal keys preserve the incoming order.
    return sorted(
        entities,
        key=lambda e: (bool(getattr(e, "is_pinned", False)), _blended(e)),
        reverse=True,
    )
