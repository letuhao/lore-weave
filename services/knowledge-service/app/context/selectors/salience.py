"""Salience-weighted entity ranking (Track 4 P1 access + P3a promotion).

Blends two LEARNED signals into the glossary entity ranking so what matters most
ranks higher and survives budget-trim longer:

- **P1 access** (R-T4-01): the P0 access-log — how often/recently THIS user
  surfaced the entity. Read-time Ebbinghaus decay, no cron.
- **P3a promotion** (R-T4-02, graph-native slice): per-entity signals already ON
  the KG — `evidence_count` + `mention_count` (log-damped) + edit recency
  (`updated_at` decay). The feedback-driven slice (thumbs → entity attribution)
  is P3b — needs a chat-events consumer + turn attribution, spec'd separately.

BOTH weights default 0.0 (byte-identical, zero extra I/O). Measure-before-flip:
the P1 explicit-query eval showed REGRESSION at w_access=0.3 (spec §8b), so the
flip gate for either weight is an ambiguous-query eval showing lift.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from app.config import settings
from app.db.repositories.entity_access import EntitySalience

__all__ = [
    "PromotionSignals",
    "apply_salience",
    "blend_entity_salience",
    "load_promotion_signals",
]


@dataclass(frozen=True)
class PromotionSignals:
    """Graph-native per-entity promotion inputs (P3a)."""
    evidence_count: int
    mention_count: int
    updated_at: datetime | None


def promotion_score(
    sig: PromotionSignals,
    *,
    max_log_evidence: float,
    max_log_mention: float,
    half_life_days: float,
    now: datetime,
) -> float:
    """[0,1] promotion score: 0.5·norm(log1p(evidence)) + 0.3·norm(log1p(mention))
    + 0.2·edit-recency-decay. Log-damping keeps a single mega-entity from
    saturating the scale; max-normalized within the candidate set."""
    ev = (math.log1p(sig.evidence_count) / max_log_evidence) if max_log_evidence > 0 else 0.0
    mn = (math.log1p(sig.mention_count) / max_log_mention) if max_log_mention > 0 else 0.0
    rec = 0.0
    if sig.updated_at is not None and half_life_days > 0:
        age_days = max(0.0, (now - sig.updated_at).total_seconds() / 86_400.0)
        rec = 0.5 ** (age_days / half_life_days)
    return 0.5 * ev + 0.3 * mn + 0.2 * rec


async def load_promotion_signals(
    session, project_id: UUID, entity_ids: list[str]
) -> dict[str, PromotionSignals]:
    """Batch-fetch P3a signals from Neo4j for glossary-anchored candidates.
    Keyed by glossary_entity_id (the id the context block surfaces). Returns {}
    on empty input; caller guards the weight flag so the default costs nothing."""
    if not entity_ids:
        return {}
    res = await session.run(
        """
        MATCH (e:Entity {project_id: $pid})
        WHERE e.glossary_entity_id IN $gids
        RETURN e.glossary_entity_id AS gid,
               coalesce(e.evidence_count, 0) AS ev,
               coalesce(e.mention_count, 0) AS mn,
               e.updated_at AS up
        """,
        pid=str(project_id), gids=entity_ids,
    )
    out: dict[str, PromotionSignals] = {}
    async for r in res:
        up = r["up"]
        # neo4j temporal → aware datetime; tolerate string/None from legacy writes.
        if up is not None and hasattr(up, "to_native"):
            up = up.to_native()
        if isinstance(up, str):
            try:
                up = datetime.fromisoformat(up)
            except ValueError:
                up = None
        if isinstance(up, datetime) and up.tzinfo is None:
            up = up.replace(tzinfo=timezone.utc)
        out[r["gid"]] = PromotionSignals(
            evidence_count=int(r["ev"]), mention_count=int(r["mn"]),
            updated_at=up if isinstance(up, datetime) else None,
        )
    return out


async def apply_salience(
    entity_access_repo,
    entities: list,
    user_id: UUID,
    project_id: UUID,
    *,
    neo4j_session=None,
) -> list:
    """Builder entry point: guard on the weight flags FIRST so the defaults
    (both 0.0) do no I/O and return the input unchanged — byte-identical.
    Every load failure degrades to a no-op (repo swallows; Neo4j errors are
    caught here) — salience must never break a context build."""
    w_access = settings.salience_access_weight
    w_promote = settings.salience_promote_weight
    w_feedback = settings.salience_feedback_weight
    if (w_access <= 0 and w_promote <= 0 and w_feedback <= 0) or not entities:
        return entities

    access: dict[str, EntitySalience] = {}
    if (w_access > 0 or w_feedback > 0) and entity_access_repo is not None:
        access = await entity_access_repo.load_salience(user_id, project_id)

    promotion: dict[str, PromotionSignals] = {}
    if w_promote > 0 and neo4j_session is not None:
        try:
            promotion = await load_promotion_signals(
                neo4j_session, project_id,
                [e.entity_id for e in entities if getattr(e, "entity_id", None)],
            )
        except Exception:
            promotion = {}  # degrade — promotion is advisory, never load-bearing

    if not access and not promotion:
        return entities
    return blend_entity_salience(
        entities, access,
        weight=w_access,
        half_life_days=settings.salience_half_life_days,
        now=datetime.now(timezone.utc),
        promotion=promotion,
        promote_weight=w_promote,
        promote_half_life_days=settings.salience_promote_half_life_days,
        feedback_weight=w_feedback,
    )


def blend_entity_salience(
    entities: list,
    salience: dict[str, EntitySalience],
    *,
    weight: float,
    half_life_days: float,
    now: datetime,
    promotion: dict[str, PromotionSignals] | None = None,
    promote_weight: float = 0.0,
    promote_half_life_days: float = 30.0,
    feedback_weight: float = 0.0,
):
    """Return `entities` re-sorted by `rank_score + weight·norm(access)
    + promote_weight·promotion + feedback_weight·tanh(feedback/3)` (terms in [0,1];
    the P3b feedback term is signed — a net-negative thumbs history DEMOTES).

    - all weights <= 0 (or nothing to blend) → the input list, unchanged.
    - access = `retrieval_count * 0.5 ** (age_days / half_life_days)` (P1,
      recency-decayed frequency), max-normalized across the project's rows.
    - promotion = graph-native signals (P3a) via `promotion_score`.
    - stable desc sort: equal blended ranks keep their original order; an entity
      with no signal rows gets a 0 boost.

    `rank_score` on each entity is left untouched (it's the displayed score); only
    the ORDER changes, which is what feeds budget-trim (trims from the tail).
    """
    have_access = weight > 0 and bool(salience)
    have_promo = promote_weight > 0 and bool(promotion)
    have_feedback = feedback_weight > 0 and any(
        s.feedback_score for s in salience.values()
    )
    if not entities or (not have_access and not have_promo and not have_feedback):
        return entities

    decayed: dict[str, float] = {}
    max_d = 0.0
    if have_access:
        half_life = half_life_days if half_life_days > 0 else 1.0
        for eid, s in salience.items():
            age_days = max(0.0, (now - s.last_retrieved_at).total_seconds() / 86_400.0)
            decayed[eid] = s.retrieval_count * (0.5 ** (age_days / half_life))
        max_d = max(decayed.values(), default=0.0)
        if max_d <= 0:
            have_access = False  # all rows decayed to ~0 → no usable access signal
    if not have_access and not have_promo and not have_feedback:
        return entities

    max_log_ev = max_log_mn = 0.0
    if have_promo:
        max_log_ev = max((math.log1p(p.evidence_count) for p in promotion.values()), default=0.0)
        max_log_mn = max((math.log1p(p.mention_count) for p in promotion.values()), default=0.0)

    def _blended(e) -> float:
        eid = getattr(e, "entity_id", None)
        score = getattr(e, "rank_score", 0.0)
        if eid and have_access:
            score += weight * (decayed.get(eid, 0.0) / max_d)
        if eid and have_promo and eid in promotion:
            score += promote_weight * promotion_score(
                promotion[eid],
                max_log_evidence=max_log_ev, max_log_mention=max_log_mn,
                half_life_days=promote_half_life_days, now=now,
            )
        if eid and have_feedback and eid in salience:
            # tanh(x/3) squashes the accumulated ±1 thumbs into (-1, 1): ~3 net
            # thumbs ≈ 0.76, saturating ~1 — one enthusiastic user can't pin an
            # entity forever, and net-negative history demotes symmetrically.
            score += feedback_weight * math.tanh(salience[eid].feedback_score / 3.0)
        return score

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
