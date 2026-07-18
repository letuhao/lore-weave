"""Intent->Skill Router (Part F / F2 of docs/specs/2026-07-07-skill-authoring-
and-mcp-exposure-standard.md, plan docs/plans/2026-07-07-intent-skill-router.md).

`resolve_skills_to_inject()` (skill_registry.py) selects skills from SURFACE
FLAGS only (editor/book_scoped/studio/admin/permission_mode) -- zero intent/
query-text input. This module adds the ADDITIVE, embedding-similarity layer on
top (Option C, spec Sec13.1 RESOLVED): embed the user's current turn text ONCE,
cosine-rank it against a small, process-cached set of skill-description
vectors, and return any skill scoring above `ROUTER_CONFIDENCE_THRESHOLD` that
the static/structural path did not already pick -- filtered to skills whose
`surfaces` already include the active surface (this module NEVER overrides
`surfaces`, which keeps encoding "does this skill even apply here").

Mirrors `tool_discovery.py`'s `_get_tool_vectors()` / `search_catalog_semantic()`
shape (the sibling embeddings-backed tool search B3 built) so the two
embeddings call sites in chat-service stay in lockstep, not two independently-
evolving copies:
  - `_get_skill_vectors()`  ~= `_get_tool_vectors()`
  - `route_additional_skills()` ~= the outer half of `search_catalog_semantic()`

Skill-vector cache lifetime is DELIBERATELY simpler than the tool-vector cache:
`SYSTEM_SKILLS` is a module-level constant (~11-15 entries), not a live,
per-user MCP catalog -- there is no TTL, only a signature check (the sorted
tuple of skill codes). In practice this means "compute once per process,
never again" today; the signature check exists only so a hypothetical future
where SYSTEM_SKILLS becomes dynamic doesn't silently serve stale vectors.

MANDATORY fallback discipline (same posture as `search_catalog_semantic`): ANY
embedding-client failure, timeout, or empty result degrades to an empty
addition list -- the caller (`skill_registry.resolve_skills_to_inject_async`)
then returns EXACTLY the static/structural result, unchanged. This module
never raises out of `route_additional_skills()`.
"""
from __future__ import annotations

import logging

from loreweave_vecmath import cosine_similarity

from app.services.skill_registry import SYSTEM_SKILLS, _skill_visible

__all__ = ["ROUTER_CONFIDENCE_THRESHOLD", "route_additional_skills"]

logger = logging.getLogger(__name__)

# One global confidence-threshold constant to start (spec Sec13.2 RESOLVED) --
# NOT yet empirically tuned; real tuning happens via Part E's eval harness
# (`run_skill_gate.py` against `scripts/eval/skill_scenarios/*.json`), tracked
# as F3. 0.35 sits inside the plan's recommended 0.3-0.5 cosine band, a hair
# above `tool_discovery.py`'s own CONFIDENCE_THRESHOLD (0.30) -- a router
# addition injects a whole skill BODY (much larger than one tool suggestion),
# so a slightly higher bar before paying that cost is a reasonable starting
# point, not a calibrated one. Revisit per-surface tuning only if measurement
# shows one surface needs a different bar (out of scope for this pass).
ROUTER_CONFIDENCE_THRESHOLD = 0.35

# Process-lifetime cache: skill code -> embedding vector. No TTL (see module
# docstring) -- invalidated only by a SYSTEM_SKILLS signature change.
_SKILL_VECTOR_CACHE: dict[str, list[float]] | None = None
_SKILL_VECTOR_CACHE_SIGNATURE: tuple[str, ...] | None = None


def _skill_embedding_text(code: str) -> str:
    """The haystack embedded per skill: label + description. Deliberately NOT
    a new authoring field (e.g. a `synonyms`-style hint) -- every current
    SkillDef.description is already a concrete, keyword-rich one-liner (see
    skill_registry.py's SYSTEM_SKILLS), which is sufficient signal at this
    coarse a granularity (~11-15 skills, not thousands of tools). Adding a
    second authoring field before evidence shows description text is
    insufficient would be over-engineering for a static, tiny set."""
    skill = SYSTEM_SKILLS[code]
    return f"{skill.label}: {skill.description}".strip(": ")


def _skill_catalog_signature() -> tuple[str, ...]:
    return tuple(sorted(SYSTEM_SKILLS.keys()))


def reset_skill_vector_cache() -> None:
    """Test-only hook: force the next `route_additional_skills()` call to
    recompute the skill-vector cache (mirrors `td._TOOL_VECTOR_CACHE.clear()`'s
    role in test_tool_discovery.py)."""
    global _SKILL_VECTOR_CACHE, _SKILL_VECTOR_CACHE_SIGNATURE
    _SKILL_VECTOR_CACHE = None
    _SKILL_VECTOR_CACHE_SIGNATURE = None


async def _get_skill_vectors(
    *, user_id: str, model_source: str, model_ref: str,
) -> dict[str, list[float]] | None:
    """Best-effort per-skill embedding vectors, cached for the process
    lifetime (see module docstring). Returns None on ANY embedding-client
    failure -- the caller MUST fall back to "no additions"; this never
    raises."""
    global _SKILL_VECTOR_CACHE, _SKILL_VECTOR_CACHE_SIGNATURE
    sig = _skill_catalog_signature()
    if _SKILL_VECTOR_CACHE is not None and _SKILL_VECTOR_CACHE_SIGNATURE == sig:
        return _SKILL_VECTOR_CACHE
    codes = list(sig)
    if not codes:
        return {}
    texts = [_skill_embedding_text(c) for c in codes]
    try:
        from app.client.embedding_client import get_embedding_client  # noqa: PLC0415

        result = await get_embedding_client().embed(
            user_id=user_id, model_source=model_source, model_ref=model_ref, texts=texts,
        )
    except Exception:  # noqa: BLE001 -- mandatory fallback, never raise into the router
        logger.warning(
            "skill-vector embedding failed; router falling back to static-only skill selection",
            exc_info=True,
        )
        return None
    vectors = dict(zip(codes, result.embeddings))
    _SKILL_VECTOR_CACHE = vectors
    _SKILL_VECTOR_CACHE_SIGNATURE = sig
    return vectors


async def route_additional_skills(
    *,
    intent_text: str,
    active_surface: set[str],
    already_selected: list[str],
    user_id: str,
    model_source: str,
    model_ref: str,
) -> list[str]:
    """Additive-only: EXTRA skill codes (never already in `already_selected`)
    whose cosine similarity to `intent_text` clears `ROUTER_CONFIDENCE_THRESHOLD`,
    filtered to skills visible on `active_surface` (`SkillDef.surfaces` -- this
    NEVER widens what a skill's own `surfaces` declares eligible, it only
    narrows WITHIN it, per spec Sec13.2/Sec14).

    Returns `[]` (never raises) when: `intent_text` is blank, the skill-vector
    cache can't be built, the per-turn intent embed fails, or nothing clears
    the threshold. The caller (`skill_registry.resolve_skills_to_inject_async`)
    treats `[]` as "the router found nothing to add" -- indistinguishable from
    (and exactly as safe as) a genuine embedding-client outage."""
    if not intent_text or not intent_text.strip():
        return []

    vectors: dict[str, list[float]] | None = None
    intent_vector: list[float] | None = None
    try:
        vectors = await _get_skill_vectors(
            user_id=user_id, model_source=model_source, model_ref=model_ref,
        )
        if vectors:
            from app.client.embedding_client import get_embedding_client  # noqa: PLC0415

            intent_result = await get_embedding_client().embed(
                user_id=user_id, model_source=model_source, model_ref=model_ref,
                texts=[intent_text],
            )
            intent_vector = intent_result.embeddings[0] if intent_result.embeddings else None
    except Exception:  # noqa: BLE001 -- mandatory fallback, never raise into the router
        logger.warning(
            "intent embedding failed; router falling back to static-only skill selection",
            exc_info=True,
        )
        vectors = None
        intent_vector = None

    if not vectors or not intent_vector:
        return []

    already = set(already_selected)
    additions: list[str] = []
    for code, skill in SYSTEM_SKILLS.items():
        if code in already:
            continue
        if not _skill_visible(skill, active_surface):
            continue
        vec = vectors.get(code)
        if not vec:
            continue
        score = cosine_similarity(intent_vector, vec)
        if score >= ROUTER_CONFIDENCE_THRESHOLD:
            additions.append(code)
    return additions
