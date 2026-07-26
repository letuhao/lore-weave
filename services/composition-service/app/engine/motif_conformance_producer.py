"""D-MOTIF-CONFORMANCE-ENGINE-WIRING — wire the binary scene judge (W5,
``engine/motif_conformance.py``) into the per-scene generate producer.

After a scene is generated, IF ``motif_conformance_enabled`` AND the scene's
outline node has a BOUND motif (a ``motif_application`` written by W2's binder), run
the cost-bounded binary conformance judge over the realized prose and return a
critic-merge PATCH — the ``critic.motif_conformance`` dim the trace read
(``routers/conformance.py``) surfaces. The consumer persists it onto the job's
``critic`` column (the COALESCE-safe ``update_status(critic=…)``).

DESIGN (all reused, nothing re-invented):
  * ``should_judge_conformance`` — sampling gate (high-weight/high-tension beats are
    ALWAYS judged; the rest at ``motif_conformance_sample_random_pct``%).
  * ``derive_tension_band`` — the 0-100 band from the node tension / beat target.
  * ``judge_motif_conformance`` — the calibrated binary judge (degrades internally to
    an empty advisory verdict on any LLM/parse failure — NEVER raises).
  * ``build_conformance_dim`` / ``merge_conformance`` — fold provenance + the
    ``calibrated`` flag (from config; False until a human flips it — single-judge
    panel-safety, §5) and merge WITHOUT clobbering other critic dims.

ADVISORY + DEGRADE-SAFE (F1/CC4): gated OFF by default; the whole body is wrapped so a
resolution/DB/judge failure returns None (critic untouched) and NEVER fails a generate.
The judge model prefers the DISTINCT critic (anti-self-reinforcement) and falls back to
the drafter when there is none.
"""

from __future__ import annotations

import json
import logging
import random
from typing import Any
from uuid import UUID

from app.config import settings
from app.db.models import Motif, MotifApplication
from app.db.repositories.motif_repo import MotifRepo
from app.engine.motif_conformance import (
    _JudgeLLMClient,
    build_conformance_dim,
    derive_tension_band,
    judge_motif_conformance,
    merge_conformance,
    should_judge_conformance,
)
from app.packer.profile import BookProfile

logger = logging.getLogger(__name__)

__all__ = ["maybe_conformance_patch", "resolve_bound_application"]


async def resolve_bound_application(
    pool: Any, project_id: UUID, node_id: UUID,
) -> MotifApplication | None:
    """The most-recent ``motif_application`` for ``node_id`` (a re-bind supersedes),
    project scoped (access is gated on the book BEFORE this — 25 PM-8). READ-only —
    W2 is the sole writer. Mirrors the trace reader's ``apps_by_nodes`` query for
    one node. None when the scene has no bound motif (nothing planned to conform
    to)."""
    row = await pool.fetchrow(
        """
        SELECT DISTINCT ON (outline_node_id)
               id, created_by, project_id, book_id, motif_id, motif_version,
               outline_node_id, role_bindings, annotations, created_at
        FROM motif_application
        WHERE project_id = $1 AND outline_node_id = $2
        ORDER BY outline_node_id, created_at DESC
        """,
        project_id, node_id,
    )
    if row is None:
        return None
    data = dict(row)
    for f in ("role_bindings", "annotations"):
        if isinstance(data.get(f), str):
            data[f] = json.loads(data[f])
    return MotifApplication.model_validate(data)


def _beat(motif: Motif, beat_key: str | None) -> dict[str, Any] | None:
    """The motif beat whose key matches ``beat_key`` (the binder writes it into
    ``motif_application.annotations``). None → motif-level conformance (no specific beat)."""
    if not beat_key:
        return None
    for b in motif.beats or []:
        if isinstance(b, dict) and b.get("key") == beat_key:
            return b
    return None


async def maybe_conformance_patch(
    pool: Any,
    judge: _JudgeLLMClient,
    *,
    user_id: str,
    project_id: str,
    profile: BookProfile,
    final_text: str,
    outline_node_id: Any,
    beat_role: str | None,
    tension: int | None,
    model_source: str,
    model_ref: str,
    rng: Any = None,
) -> dict[str, Any] | None:
    """Run the sampled binary conformance judge for a generated scene → a critic dict
    carrying ``motif_conformance`` (to be persisted via ``update_status(critic=…)``),
    or None to leave the critic untouched.

    None when: conformance is disabled · no ``outline_node_id`` · the scene has no
    bound motif · the sampling gate declines · or anything fails (advisory, never
    raises). The ``calibrated`` flag is stamped from config (False ⇒ FE labels the dim
    'unverified self-report')."""
    if not settings.motif_conformance_enabled or not outline_node_id:
        return None
    try:
        node_uuid = UUID(str(outline_node_id))
        app = await resolve_bound_application(
            pool, UUID(project_id), node_uuid,
        )
        if app is None or app.motif_id is None:
            return None  # nothing planned to conform to

        if not should_judge_conformance(
            beat_role=beat_role, tension=tension, has_motif=True,
            rng=rng or random, sample_pct=settings.motif_conformance_sample_random_pct,
            high_threshold=settings.plan_high_tension_threshold,
        ):
            return None

        motif = await MotifRepo(pool).get_visible(UUID(user_id), app.motif_id)
        if motif is None:
            return None  # archived / not visible → skip (advisory)

        beat_key = (app.annotations or {}).get("beat_key")
        beat = _beat(motif, beat_key)
        beat_intent = (beat or {}).get("intent") or motif.summary or ""
        beat_tension_target = (beat or {}).get("tension_target")
        if beat_tension_target is None:
            beat_tension_target = motif.tension_target
        expected_roles = [
            str(r.get("label") or r.get("key") or "")
            for r in (motif.roles or []) if isinstance(r, dict)
        ]
        band = derive_tension_band(
            node_tension=tension, beat_tension_target=beat_tension_target,
            halfwidth=settings.motif_conformance_tension_halfwidth,
        )
        judge_out = await judge_motif_conformance(
            judge, user_id=user_id, model_source=model_source, model_ref=model_ref,
            beat_intent=beat_intent, beat_key=beat_key or "", motif_name=motif.name,
            tension_band=band, expected_roles=expected_roles, passage=final_text,
            profile=profile,
        )
        dim = build_conformance_dim(
            judge_out, motif_id=app.motif_id, beat_key=beat_key, band=band,
            calibrated=settings.motif_conformance_calibrated,
        )
        return merge_conformance(None, dim)
    except Exception:  # noqa: BLE001 — conformance is advisory; never fail a generate (F1).
        logger.warning("motif conformance producer failed (advisory)", exc_info=True)
        return None
