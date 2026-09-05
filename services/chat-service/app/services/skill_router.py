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
tuple of skill codes, PLUS the embedding model since U-3: vectors from two
different models are not comparable, so sharing them silently corrupts every
similarity score the router ranks on). In practice this means "compute once per process,
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

# Top-K cap (2026-07-25, context-bloat fix) — the router returns at most this many
# additions, the HIGHEST-scoring ones, even when more clear the threshold. This is the
# real discriminator, not the absolute threshold: measured against the shipping bge-m3
# embedder, EVERY novel-authoring skill description scores 0.35-0.66 cosine to ANY
# authoring intent (they are all "assist with a novel" one-liners in one tight semantic
# cluster), so a bare `>= 0.35` gate passed ~all 10 studio-visible skills on EVERY turn
# and re-injected ~15.5k tokens of skill bodies — silently defeating `lazy_skill_bodies`
# (the L1 index + load_skill were supposed to keep the prompt at ~432 tok). An absolute
# threshold cannot separate a compressed distribution; a rank cap can. K=2 was chosen
# from the same measurement: the CORRECT skill for a turn is reliably rank 1-2 (knowledge
# for ontology, plan_forge for a plan), and the surface/mode base (e.g. co_write in write
# mode) already covers a 3rd, so base+2 spans the genuinely multi-skill turns (compile =
# plan_forge+composition+co_write) while bounding a mismatch to 2 bodies, not 10. The
# threshold stays as a FLOOR (kills the truly-unrelated tail); the cap bounds the head.
ROUTER_MAX_ADDITIONS = 2

# Process-lifetime cache: skill code -> embedding vector. No TTL (see module
# docstring) -- invalidated by a change to the SYSTEM_SKILLS signature OR to the
# embedding model, because vectors from two models are not comparable (U-3).
_SKILL_VECTOR_CACHE: dict[str, list[float]] | None = None
_SKILL_VECTOR_CACHE_SIGNATURE: tuple[str, ...] | None = None


#: DQ-T90 arm (b) — CONTRASTIVE skill texts, embedded INSTEAD of `description` when
#: `settings.skill_contrastive_desc` is on.
#:
#: WHY. Measured 2026-09-01: all 66 of 66 pairs of distinct skills are more similar to each other
#: than the 0.35 floor a skill must clear to be injected — median 0.5512, max 0.7715. The cap
#: boundary therefore falls inside embedding noise and no threshold can separate them. The
#: embedder is NOT at fault: it spreads 0.40 and puts admin/co_write at 0.3676. The texts collide.
#: `book` and `translation` (0.7715, the closest pair in the catalogue, and the pair that took
#: both cap slots on this row's founding prompt) both say "chapters" and "publish"; `co_write` and
#: `plan_forge` (0.7121) both say plan/propose/compile; `glossary` and `glossary_shaping` (0.6964)
#: both say kinds/attributes.
#:
#: HOW THEY ARE WRITTEN — the rule this repo already applies to entity kinds
#: (glossary-service/internal/domain/kinds.go): "say what the kind is AND what it is not, naming
#: the neighbour it is most often confused with. 'A body of people acting together; it survives
#: the loss of its building' discriminates; 'an organization' does not."
#:
#: KEPT SEPARATE from `description`, which is the L1 index line a READER sees. The two have
#: different jobs — the index says what a skill does, this says how it differs — and separating
#: them makes the arm a flag flip rather than a rewrite the control cannot be run without.
_CONTRASTIVE: dict[str, str] = {
    "book": "Chapter FILES and their lifecycle: create, reorder, rename, trash, restore a saved "
            "revision, publish a draft as canon, commission cover art or audio. This is "
            "librarianship, not authorship — it never writes prose, and it never renders another "
            "language.",
    "translation": "Rendering finished text into ANOTHER LANGUAGE: translate, review coverage, "
                   "apply a human's corrections, release a translated edition. Always works from "
                   "text that already exists; it never composes new material and never "
                   "reorganises the source.",
    "composition": "AUTHORING the story itself: shape the outline, write scene and chapter prose "
                   "with the cowrite engine, declare canon rules, work the motif library. The "
                   "craft of making the text, as distinct from filing it or restating it in "
                   "another tongue.",
    "co_write": "Writing WITH the author, turn by turn, and turning a story they describe aloud "
                "into real linked chapters and scenes. Interactive and mid-flight — the author is "
                "here now, talking; this is not the up-front design pass done before any text "
                "exists.",
    "plan_forge": "Deriving a novel's SYSTEM from a source document before the story is written: "
                  "magic rules, factions, power ladders, validated and compiled into a spec. A "
                  "cold-start design activity, not a drafting one, and it happens once rather "
                  "than continuously.",
    "glossary": "Individual world-bible ENTRIES: look up a character, place or item, read it, "
                "correct it, merge duplicates, retire it. Works on the records themselves, one at "
                "a time, never on the categories that describe them.",
    "glossary_shaping": "The SHAPE the world bible takes: which categories of thing exist, what "
                        "fields each carries, adopting a standard set, proposing many at once. "
                        "Structural and up-front — it defines the containers, never the contents.",
    "knowledge": "The GRAPH across the whole story: who relates to whom, what happened when, "
                 "recalling facts established chapters ago. Connections and memory spanning the "
                 "work, rather than any single record or the rules governing it.",
    "settings": "One user's own account and their private AI provider keys: profile, register a "
                "provider, favourite or activate a model, set a default. Personal configuration, "
                "affecting nobody else.",
    "admin": "PLATFORM-WIDE defaults that every book inherits, editable only by an operator. "
             "Changes what all users get, which is the opposite of adjusting a single account.",
    "jobs": "Watching WORK ALREADY RUNNING in the background: list it, inspect it, cancel or "
            "pause it. Concerned with the progress of tasks, never with performing the task.",
    "universal": "A fallback driver for requests no domain covers, including open-web research on "
                 "any subject. Use only when nothing more specific applies.",
}


def _skill_embedding_text(code: str) -> str:
    """The haystack embedded per skill: label + description. Deliberately NOT
    a new authoring field (e.g. a `synonyms`-style hint) -- every current
    SkillDef.description is already a concrete, keyword-rich one-liner (see
    skill_registry.py's SYSTEM_SKILLS), which is sufficient signal at this
    coarse a granularity (~11-15 skills, not thousands of tools). Adding a
    second authoring field before evidence shows description text is
    insufficient would be over-engineering for a static, tiny set."""
    skill = SYSTEM_SKILLS[code]
    # DQ-T90 arm (b). The docstring above says a second authoring field would be
    # "over-engineering ... before evidence shows description text is insufficient". That
    # evidence now exists and is the reason this branch is here: 66 of 66 skill pairs sit closer
    # to each other than the floor a skill must clear. Still OFF by default — the arm has to beat
    # the control's measured 70.0% before it becomes the shipped path.
    from app.config import settings  # noqa: PLC0415 — local, like the router's own imports

    if settings.skill_contrastive_desc and _CONTRASTIVE.get(code):
        return f"{skill.label}: {_CONTRASTIVE[code]}".strip(": ")
    return f"{skill.label}: {skill.description}".strip(": ")


def _skill_catalog_signature() -> tuple[str, ...]:
    """The skill CODES, and nothing else.

    🔴 It is used BOTH as the cache signature and as the code list (`codes = list(...)` below),
    so anything appended here is later looked up as a skill name. The module already records one
    instance of that ("`_skill_embedding_text` would look up a skill named after an embedding
    model"); a second was added and reverted on 2026-09-01 when arm (b)'s flag was appended here
    and ten router tests failed with `KeyError: 'contrastive=False'`. Extra cache dimensions
    belong at the call site, where the embedding model already is.
    """
    return tuple(sorted(SYSTEM_SKILLS.keys()))


def reset_skill_vector_cache() -> None:
    """Test-only hook: force the next `route_additional_skills()` call to
    recompute the skill-vector cache (mirrors `td._TOOL_VECTOR_CACHE.clear()`'s
    role in test_tool_discovery.py)."""
    global _SKILL_VECTOR_CACHE, _SKILL_VECTOR_CACHE_SIGNATURE
    _SKILL_VECTOR_CACHE = None
    _SKILL_VECTOR_CACHE_SIGNATURE = None


async def _get_skill_vectors(
    *, user_id: str,
) -> dict[str, list[float]] | None:
    """Best-effort per-skill embedding vectors, cached for the process
    lifetime (see module docstring). Returns None on ANY embedding-client
    failure -- the caller MUST fall back to "no additions"; this never
    raises."""
    global _SKILL_VECTOR_CACHE, _SKILL_VECTOR_CACHE_SIGNATURE
    # 🔴 U-3 — THE EMBEDDING MODEL IS PART OF THE KEY, and it was not.
    #
    # The signature was the skill codes alone, while the vectors below are computed BY a specific
    # embedding model. So whichever model ran first after boot supplied the vectors for every later
    # turn, whatever model that turn asked for — and vectors from two different models are not
    # comparable, so the similarity scores the router ranks on were silently wrong.
    #
    # This is the SAME defect its twin already fixed: `tool_discovery._TOOL_VECTOR_CACHE` keys on
    # `(catalog_signature, model_source, model_ref)` under the note "so two distinct embedding
    # models never share a cached vector set". One of the pair was patched and the other was not,
    # which is this repository's most repeated shape — a correction applied where someone was
    # looking, and nowhere else.
    #
    # The consequence is a determinism defect as much as a correctness one: the surface then depends
    # on WHICH TURN RAN FIRST AFTER BOOT, which no record captures and no replay can reproduce.
    #
    # 🔴 AND THE TWIN CARRIED **TWO** FIXES; ONLY THE KEY WAS PORTED. `tool_discovery` HIGH-2 also
    # removed `model_source`/`model_ref` from its signature, because those were the turn-scoped
    # CHAT-completion model values — *"most chat models can't embed, so that either failed upstream
    # or risked an improvised vector from a model never meant to embed"* — and replaced them with
    # `_resolve_embedding_model(user_id)`. So the key here was honest about a model that should not
    # have been embedding at all: the same erratum-not-applied-everywhere shape as U-3 itself, one
    # level up, found by a verifier reading the twin rather than this file.
    from app.services.tool_discovery import _resolve_embedding_model  # noqa: PLC0415

    model = await _resolve_embedding_model(user_id)
    if model is None:
        return None
    model_source, model_ref = model
    # The contrastive flag is a cache DIMENSION, not a skill: arm (b) changes the TEXT the
    # vectors are built from without changing any skill CODE, so a key without it would
    # serve vectors of the old wording under the new flag. It goes here, beside the model,
    # and never into `_skill_catalog_signature` — see that function's docstring.
    from app.config import settings  # noqa: PLC0415

    sig = _skill_catalog_signature() + (
        model_source, model_ref, f"contrastive={bool(settings.skill_contrastive_desc)}")
    if _SKILL_VECTOR_CACHE is not None and _SKILL_VECTOR_CACHE_SIGNATURE == sig:
        return _SKILL_VECTOR_CACHE
    # NOT `list(sig)` — the signature now carries the model too, and feeding that to
    # `_skill_embedding_text` would look up a skill named after an embedding model.
    codes = list(_skill_catalog_signature())
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
        vectors = await _get_skill_vectors(user_id=user_id)
        if vectors:
            from app.client.embedding_client import get_embedding_client  # noqa: PLC0415

            # The SAME model that produced the cached skill vectors — a cosine score between two
            # models' vectors is not a similarity, it is a coincidence.
            from app.services.tool_discovery import _resolve_embedding_model  # noqa: PLC0415

            model = await _resolve_embedding_model(user_id)
            if model is None:
                return []
            intent_result = await get_embedding_client().embed(
                user_id=user_id, model_source=model[0], model_ref=model[1],
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
    scored: list[tuple[str, float]] = []
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
            scored.append((code, score))
    # Rank by score (highest first) and keep only the top-K — the absolute threshold
    # above is a FLOOR that removes the unrelated tail; this cap removes the flood when
    # the whole (tightly clustered) set clears that floor. `sorted` is stable, so ties
    # break on SYSTEM_SKILLS insertion order — deterministic, not arbitrary.
    scored.sort(key=lambda cs: cs[1], reverse=True)
    # DQ-T90 arm (a) — the cap is the shipped ROUTER_MAX_ADDITIONS unless overridden. The sweep
    # priced 2->3 at +6.1 points of hit rate for 270 more injected skills, 250 of them never
    # used, on a smooth curve with no knee; it is a stopgap, not an answer, and it is measurable
    # here rather than argued.
    from app.config import settings  # noqa: PLC0415

    cap = settings.router_max_additions or ROUTER_MAX_ADDITIONS
    return [code for code, _ in scored[:cap]]
