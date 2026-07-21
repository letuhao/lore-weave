"""Session-scoped tool surface assembly — whitelist-with-escape (story 04).

When ``enabled_tools`` is non-empty (curated mode), the turn advertises
ALWAYS_ON_CORE ∪ pins ∪ session ``activated_tools``; ``find_tools`` unions
matches into the per-turn active set AND persists to ``activated_tools``.
Empty pins preserve legacy hot-set + auto-discovery behaviour.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field

from app.services.token_budget import estimate_tokens, scale_by_window
from app.services.tool_discovery import (
    _domain_of,
    hot_tool_names,
    surface_hot_domains,
    tool_name,
)

logger = logging.getLogger(__name__)

ACTIVATED_TOOLS_CAP = 64

# ── Token-budgeted tool surface (2026-07-06 context-explosion fix) ────────────
# The book-scoped hot-seed used to advertise ENTIRE domains (glossary+story ≈ 64
# tools / ~24K tokens) on EVERY LLM call, re-sent on each tool-loop iteration →
# 137K-token turns for an 8K-token conversation (see
# docs/eval/context-budget/context-explosion-investigation-2026-07-06.md). We now
# bound the always-advertised sets by a TOKEN budget; `find_tools` pulls the long
# tail on demand. Industry-standard "tool-RAG / lazy tool loading" (RAG-MCP,
# Anthropic Tool Search): a small hot core + discovery beats shipping whole domains.
# Both budgets are tuned around a mid-size (~200K) window — `scale_by_window` grows
# them for a caller that resolves the session model's real (larger) context_length,
# instead of every model, including a 1M-context one, being capped at the same flat
# number (the exact bug class the Context Budget Law's `budget.py` fix addressed).
HOT_SEED_TOKEN_BUDGET = 4000        # ~8-12 tools stay hot; rest lazy via find_tools
ACTIVATED_TOOLS_TOKEN_BUDGET = 6000  # cap the find_tools-accumulated set by tokens

# Read/query verbs → the tools safe to keep hot (writes/proposes are discovered on
# demand and usually confirmation-gated anyway).
# WS-1b: `recall`/`timeline` are semantically READS (memory_recall_entity, memory_timeline)
# but contain no other read-verb substring, so they were misclassed as writes and starved.
_READ_VERBS = (
    "search", "list", "get", "read", "find", "lookup",
    "show", "view", "fetch", "describe", "query", "recall", "timeline",
)

# WS-1b — the hot-path write-tool allowlist (OQ7 / contracts.md C2, §4.4). The read-first
# token trim structurally starves WRITE tools (reads exhaust the budget first), so a mid-tier
# model could DISCOVER a write via tool_list but never had its schema hot to CALL it — the
# measured S02 blocker (gemma saw glossary_propose_entities in tool_list, couldn't call it).
# These few, small CANON-write tools — the ones the co-writer scenarios most need — are kept
# hot unconditionally when their domain is already a candidate (i.e. the surface's hot domain).
# Deliberately tight (not "all writes") so it never re-introduces the whole-domain context
# explosion the token budget fixed; the long tail still lazy-loads via tool_load/find_tools.
ALWAYS_HOT_WRITES: frozenset[str] = frozenset({
    # glossary — populate + edit EXISTING entities (S01/S02/S03). These are the safe,
    # low-surprise co-writer writes (add a character, set an attribute).
    "glossary_propose_entities",
    "glossary_entity_set_attributes",
    # NOTE (N5a, dogfood 2026-07-18 F3): `glossary_adopt_standards` is DELIBERATELY NOT hot.
    # Keeping it hot made the co-writer proactively "set up the world" on a plain "write a
    # chapter 1" turn and block the newcomer with a high-impact confirm they never asked for
    # (a prompt guard-line alone did NOT hold — a live Gemma QC proved it). It is high-impact,
    # book-wide, and confirmation-gated, so it belongs on the discover-on-demand path: the agent
    # reaches it via find_tools/tool_load ONLY when the writer explicitly asks to set up their
    # world (the lean glossary skill instructs exactly that). Do not re-add it here.
    # knowledge — continuity + KG build (S04, flagship)
    "memory_remember",
    "kg_propose_edge",
    "kg_propose_fact",
    # book — draft capture (compose) + the book's own DETAILS (title/description/
    # blurb/summary/genre). book_update_details is a SAFE, low-surprise co-writer
    # write (a diff card the human applies) and the ONLY home for editing a book's
    # description — but it's a Tier-W tool with a large 5-field schema, so the
    # read-first budget ordering STARVED it out of the hot set (dogfood 2026-07-21:
    # it was never advertised, so every model mis-routed "update the description" to
    # book_chapter_create/save_draft — the tool it could actually see). Allowlist it
    # so it's always reachable, exactly like save_draft. (This gap predates the
    # book_update_meta→book_update_details rename — the old name was starved too.)
    "book_chapter_save_draft",
    "book_update_details",
})


def _tool_tokens(td: dict) -> int:
    return estimate_tokens(json.dumps(td, ensure_ascii=False))


def _is_read_tool(name: str) -> bool:
    n = name.lower()
    return any(v in n for v in _READ_VERBS)


def budget_names_by_tokens(
    catalog: list[dict],
    names: set[str] | list[str],
    *,
    token_budget: int,
) -> set[str]:
    """Trim a candidate tool-name set to a TOKEN budget.

    Priority: read/query tools first (the safe always-hot set), then ascending
    schema size so the budget fits the most tools; deterministic (tie-break by
    name). `find_tools` backstops anything dropped. Names with no measurable
    schema in `catalog` (core/frontend tools, counted elsewhere) pass through
    free. At least one budgeted tool is always kept (a single oversized schema
    can't zero the seed).
    """
    want = set(names)
    defs = {tool_name(td): td for td in catalog if tool_name(td) in want}
    kept: set[str] = {n for n in want if n not in defs}  # non-catalog → passthrough
    used = 0
    # WS-1b: keep the allowlisted canon-write tools hot UNCONDITIONALLY (they were starved by
    # the read-first ordering below). Only those already candidates for this surface, and their
    # (small) token cost is charged against the budget so the remaining reads still fit.
    for nm in ALWAYS_HOT_WRITES:
        td = defs.get(nm)
        if td is not None:
            kept.add(nm)
            used += _tool_tokens(td)
    ordered = sorted(
        ((n, td) for n, td in defs.items() if n not in kept),
        key=lambda kv: (0 if _is_read_tool(kv[0]) else 1, _tool_tokens(kv[1]), kv[0]),
    )
    for nm, td in ordered:
        t = _tool_tokens(td)
        if used + t > token_budget and used > 0:
            break
        kept.add(nm)
        used += t
    return kept


@dataclass
class SessionToolPins:
    """Resolved session pin state for a chat turn (fresh or resume)."""

    effective_enabled: list[str]
    effective_skills: list[str]
    curated_mode: bool
    activation_state: dict
    # CAT-4 Part D — legacy tools the user manually pinned for THIS session
    # (`pinned_legacy_tools`, source: user_pinned). Always unioned into the
    # advertised set regardless of curated/auto mode — a manual pin is a
    # deliberate per-session override, not part of the discovery heuristic.
    pinned_legacy: list[str] = field(default_factory=list)


def budget_rail_tools(
    catalog: list[dict],
    ordered_names: list[str],
    *,
    token_budget: int,
) -> tuple[set[str], list[str]]:
    """Budget a WORKFLOW RAIL's step tools, keeping them in DECLARED STEP ORDER.

    Returns ``(kept, dropped)``.

    Why not ``budget_names_by_tokens``: that one orders read-tools-first, then by
    ascending schema size — correct for a surface hot-seed (advertise as many safe
    tools as fit), but WRONG for a rail. A rail is an ordered recipe whose *write*
    tools are the ones that persist anything; the read-first ordering would drop
    exactly those under budget pressure, leaving the agent a rail naming tools it
    cannot see — a silent no-op of the worst kind (it looks like it should work).
    Step order is the author's priority order, so honor it: early steps survive, and
    whatever gets dropped is REPORTED so the caller can log it rather than pretend.
    """
    defs = {tool_name(td): td for td in catalog}
    kept: set[str] = set()
    dropped: list[str] = []
    used = 0
    for nm in ordered_names:
        td = defs.get(nm)
        if td is None:
            kept.add(nm)  # non-catalog (core/frontend) tools are counted elsewhere
            continue
        t = _tool_tokens(td)
        if used + t > token_budget and used > 0:
            dropped.append(nm)
            continue
        kept.add(nm)
        used += t
    return kept, dropped


def resolve_session_tool_pins(
    session_row,
    *,
    enabled_tools_override: list[str] | None = None,
    enabled_skills_override: list[str] | None = None,
) -> SessionToolPins:
    session_enabled = list(session_row.get("enabled_tools") or []) if session_row else []
    session_skills = list(session_row.get("enabled_skills") or []) if session_row else []
    session_activated = list(session_row.get("activated_tools") or []) if session_row else []
    session_pinned_legacy = list(session_row.get("pinned_legacy_tools") or []) if session_row else []
    effective_enabled = (
        enabled_tools_override if enabled_tools_override is not None else session_enabled
    )
    effective_skills = (
        enabled_skills_override if enabled_skills_override is not None else session_skills
    )
    return SessionToolPins(
        effective_enabled=effective_enabled,
        effective_skills=effective_skills,
        curated_mode=is_curated(effective_enabled, effective_skills),
        activation_state={"activated_tools": list(session_activated), "dirty": False},
        pinned_legacy=session_pinned_legacy,
    )


def discovery_seed_for_surface(
    catalog: list[dict],
    *,
    pins: SessionToolPins,
    editor: bool,
    book_scoped: bool,
    studio: bool = False,
    context_length: int | None = None,
    permission_mode: str = "write",
    workflow_step_tools: set[str] | None = None,
    binding_categories: list[str] | None = None,
    pinned_step_tools: list[str] | None = None,
) -> set[str]:
    """Discovery active-set seed: hot set (auto) or pins ∪ activated (curated).

    ``binding_categories`` (WS-3/C6 ``seed_tool_categories``) are unioned into the
    surface's hot domains — ADDITIVE, and they ride the SAME single
    ``HOT_SEED_TOKEN_BUDGET`` ceiling as the surface's own domains (never a second,
    independently-budgeted call: that is the additive-per-domain pattern that caused the
    2026-07-06 context explosion).
    """
    hot_domains = surface_hot_domains(
        editor=editor, book_scoped=book_scoped, studio=studio, permission_mode=permission_mode,
    )
    if binding_categories:
        # An unknown category contributes no tools. The registry rejects one at the write
        # (contract C1 closed set), so if one arrives here the two sides have DRIFTED —
        # say so rather than silently seeding nothing.
        known = {_domain_of(tool_name(td)) for td in catalog}
        for _cat in binding_categories:
            if _cat not in known:
                logger.warning(
                    "mode binding seeds tool category %r, which matches no tool in the "
                    "catalog — it seeds nothing", _cat,
                )
        hot_domains = set(hot_domains) | set(binding_categories)
    # FIX (context-explosion): token-budget the hot-seed instead of seeding the
    # WHOLE domain(s). Cuts the always-advertised base ~24K → ~4K (scaled up for a
    # session model with a larger real context_length via scale_by_window).
    raw_hot_seed = budget_names_by_tokens(
        catalog, hot_tool_names(catalog, hot_domains),
        token_budget=scale_by_window(HOT_SEED_TOKEN_BUDGET, context_length),
    )
    eff_pins = pins.effective_enabled
    if pins.curated_mode:
        # In curated mode the hot set only enters via this union; the studio surface's
        # hot domains (glossary+composition) ride the same seam (M-E live-caught).
        glossary_in_skills = (
            "glossary" in pins.effective_skills
            or (not pins.effective_skills and (book_scoped or studio))
        )
        eff_pins = effective_enabled_tools(
            pins.effective_enabled,
            glossary_skill=glossary_in_skills,
            catalog=catalog,
            hot_domains=hot_domains,
            context_length=context_length,
        )
        # Plan mode force-injects the plan_forge skill regardless of curated pins
        # (skill_registry.resolve_skills_to_inject appends it unconditionally) — so
        # its plan_* tools must ride along too, independent of whether the curated
        # set happens to also pin "glossary" (the gate above is glossary-specific
        # and would otherwise leave plan_* stranded in a curated plan-mode session
        # that pinned e.g. only ["plan_forge"]).
        #
        # review-impl HIGH fix: when `glossary_in_skills` is True, the union above
        # ALREADY covers plan_* — `hot_domains` (passed in) includes "plan" via
        # surface_hot_domains, so `effective_enabled_tools` budgets glossary+story+
        # (composition+)plan together under ONE HOT_SEED_TOKEN_BUDGET ceiling. Adding
        # a SECOND, independently-budgeted call here unconditionally would double-seed
        # plan_* under its own fresh ceiling on top of the shared one — up to ~2x the
        # intended per-turn hot-seed size, the exact additive-per-domain pattern that
        # caused the 2026-07-06 context-explosion incident this budget system exists
        # to prevent. Only reach for a separate, independently-budgeted call in the
        # narrow case the shared union SKIPPED entirely (a curated session whose
        # pinned skills are non-empty and exclude "glossary" — the gap this fix
        # targets), where `eff_pins` otherwise carries no hot-seed contribution at all.
        covered_domains: set[str] = set(hot_domains) if glossary_in_skills else set()
        if permission_mode == "plan" and not glossary_in_skills:
            # Part D (2026-07-07): derive from the plan_forge SkillDef's own
            # declared hot_domains instead of a separate hand-authored
            # PLAN_HOT_DOMAINS constant — one source of truth (also used by
            # surface_hot_domains above), removing the two-constants-must-agree
            # drift risk the standalone constant carried.
            from app.services.skill_registry import SYSTEM_SKILLS
            plan_domains = set(SYSTEM_SKILLS["plan_forge"].hot_domains)
            plan_hot = budget_names_by_tokens(
                catalog, hot_tool_names(catalog, plan_domains),
                token_budget=scale_by_window(HOT_SEED_TOKEN_BUDGET, context_length),
            )
            eff_pins = list(dict.fromkeys([*eff_pins, *sorted(plan_hot)]))
            covered_domains |= plan_domains

        # Generic curated-skill hot-domain union (docs/specs/2026-07-07-skill-
        # authoring-and-mcp-exposure-standard.md Part B) — any OTHER explicitly
        # pinned skill (composition, translation, future skills) whose declared
        # `hot_domains` isn't already covered above needs its tools seeded, so a
        # curated session that pins e.g. "translation" doesn't strand its tools behind
        # find_tools the way plan_forge originally did.
        #
        # review-impl fix: this MUST be ONE shared budgeted call across every
        # not-yet-covered domain from every pinned skill — not one separate call PER
        # skill. A per-skill call would let each newly-pinned skill claim its own full
        # HOT_SEED_TOKEN_BUDGET, so pinning 2 skills could seed ~2x the intended
        # per-turn hot-set size (3 skills ~3x, ...) — the exact "separate ceiling per
        # domain-source" pattern the review-impl HIGH fix above already banned for the
        # plan/glossary case; the fix here is the SAME discipline, generalized: collect
        # every uncovered domain from every pinned skill FIRST, then budget them
        # together under one ceiling (mirrors how the auto-mode path already shares one
        # `budget_names_by_tokens` call across a whole surface's hot_domains SET).
        # review-impl fix (2026-07-08): a pinned skill only hot-seeds its tools
        # if it's actually VISIBLE on this surface — mirrors the same
        # `_skill_visible()` filter `resolve_skills_to_inject()` already applies
        # when deciding which skill PROMPTS to inject. Without this, a stale
        # pin from a different surface (e.g. "book" pinned while now on the
        # plain chat surface, where `book_skill.surfaces` doesn't include
        # "chat") hot-seeded the tools with no matching prompt telling the
        # model how/why to use them — decoupled tool exposure the skill
        # contract was specifically built to prevent (spec Part A/B).
        from app.services.skill_registry import SYSTEM_SKILLS, _skill_visible, _surface_key
        active_surface = _surface_key(editor=editor, book_scoped=book_scoped, admin=False, studio=studio)
        extra_domains: set[str] = set()
        for _code in pins.effective_skills:
            _skill = SYSTEM_SKILLS.get(_code)
            if _skill and _skill.hot_domains and _skill_visible(_skill, active_surface):
                extra_domains |= set(_skill.hot_domains) - covered_domains
        if extra_domains:
            extra_hot = budget_names_by_tokens(
                catalog, hot_tool_names(catalog, extra_domains),
                token_budget=scale_by_window(HOT_SEED_TOKEN_BUDGET, context_length),
            )
            eff_pins = list(dict.fromkeys([*eff_pins, *sorted(extra_hot)]))
    names = assemble_initial_active_names(
        curated=pins.curated_mode,
        enabled_tools=eff_pins,
        activated_tools=pins.activation_state["activated_tools"],
        hot_seed_names=raw_hot_seed,
        workflow_step_tools=workflow_step_tools,
    )
    # WS-3 (C6) — a PINNED workflow's step tools ride EVERY turn, in both curated and
    # auto mode. The rail is rendered into the prompt naming these tools by name; if they
    # weren't advertised the agent would read a recipe it cannot execute (a silent
    # no-op — the worst failure shape, since it looks like it should work). They are
    # budgeted in DECLARED STEP ORDER (`budget_rail_tools`), so the early steps always
    # survive and anything trimmed is reported rather than silently vanishing.
    if pinned_step_tools:
        kept, dropped = budget_rail_tools(
            catalog, list(pinned_step_tools),
            token_budget=scale_by_window(HOT_SEED_TOKEN_BUDGET, context_length),
        )
        names = names | kept
        if dropped:
            logger.warning(
                "pinned rail step tools dropped by the token budget: %s — the rail names "
                "tools the agent cannot see", ", ".join(dropped),
            )
    # CAT-4 Part D — a manually-pinned legacy tool rides every turn of THIS
    # session regardless of curated/auto mode; it bypasses find_tools entirely
    # (the whole point of the escape hatch is that the tool is otherwise
    # unreachable through discovery).
    return names | set(pins.pinned_legacy)


def is_curated(enabled_tools: list[str] | None, enabled_skills: list[str] | None = None) -> bool:
    """A session is curated when the user made ANY explicit tool-surface choice
    this session — pinning a raw tool name OR pinning a skill (a skill is
    exactly a curated tool-selection strategy, not a different concept).

    2026-07-07 (Part E live-eval finding, root cause of the eval's dominant
    failure signature — see `D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE`): this used to
    check `enabled_tools` ONLY. The real frontend's skill-pin UI
    (`useContextRack.ts` → `patchSession({enabled_skills: next})`) pins a skill
    WITHOUT ever setting `enabled_tools` — so a skill-only pin (translation,
    book, settings, jobs — all curated-pin-only, spec Part B) silently never
    entered curated mode: the skill's PROMPT was injected (naming its tools
    directly, "call X now") but `discovery_seed_for_surface`'s entire curated
    hot-domain union — the mechanism Part B built specifically to seed a
    pinned skill's tools — never ran, because it's gated behind
    `if pins.curated_mode:`. The model was left to `find_tools` its way to
    tools the skill confidently told it existed, live-observed producing
    exactly the "falsely claims a real, skill-documented tool doesn't exist"
    failure class this whole spec exists to prevent. This bug ALSO explains why
    Part B's own regression tests never caught it: every one of them (see
    `TestCuratedSkillHotDomainUnion`) co-pinned a dummy `enabled_tools` entry
    alongside the skill under test, accidentally exercising curated_mode
    through the OTHER param and masking the skill-only path entirely."""
    return bool(enabled_tools) or bool(enabled_skills)


def effective_enabled_tools(
    enabled_tools: list[str],
    *,
    glossary_skill: bool,
    catalog: list[dict],
    hot_domains: set[str],
    context_length: int | None = None,
) -> list[str]:
    """When glossary skill is active in curated mode, auto-union glossary hot tools.

    2026-07-07: the `or not enabled_tools` short-circuit used to be a harmless
    no-op (curated_mode, the only way this function gets called, implied
    `enabled_tools` was already non-empty) — now that `is_curated()` also
    triggers on a skill-only pin (empty `enabled_tools`, see its docstring),
    this condition would wrongly skip glossary's own hot-seed for exactly that
    case. Union against an empty starting list is a correct no-op either way,
    so the `enabled_tools`-emptiness check adds nothing but the bug — removed."""
    if not glossary_skill:
        return list(enabled_tools)
    # FIX (context-explosion): budget the auto-unioned hot set too, so curated
    # sessions with the glossary skill don't re-inflate the whole domain.
    hot = budget_names_by_tokens(
        catalog, hot_tool_names(catalog, hot_domains),
        token_budget=scale_by_window(HOT_SEED_TOKEN_BUDGET, context_length),
    )
    return list(dict.fromkeys([*enabled_tools, *sorted(hot)]))


def assemble_initial_active_names(
    *,
    curated: bool,
    enabled_tools: list[str],
    activated_tools: list[str],
    hot_seed_names: set[str],
    workflow_step_tools: set[str] | None = None,
) -> set[str]:
    # Auto (non-curated) mode is per-turn discovery — the hot-seed re-seeds each turn
    # and ad-hoc find_tools matches do NOT persist. The ONE exception: a WORKFLOW is an
    # explicit multi-step rail whose step tools workflow_load persists to
    # `activated_tools` (stream_service, ungated for exactly this reason) so they survive
    # to later turns of the same rail (the S03 failure: the agent listed the pile in T0,
    # but status_change/merge were gone by T1).
    #
    # review-impl: re-advertise ONLY the activated tools that belong to a CURRENTLY-VISIBLE
    # workflow's steps — NEVER the whole persisted set. A session that was curated earlier
    # (and accumulated find_tools/tool_load matches into activated_tools) then flipped to
    # auto must NOT leak those ad-hoc accumulations into the auto surface. `workflow_step_
    # tools` is the union of the turn's visible workflows' step tools; intersecting keeps
    # in-flight rail tools and drops everything else. Default None → the original strict
    # auto behavior (hot-seed only), so a caller that doesn't supply the filter can't leak.
    if not curated:
        wf = workflow_step_tools or set()
        return set(hot_seed_names) | (set(activated_tools) & wf)
    return set(enabled_tools) | set(activated_tools)


def merge_activated_tools(
    current: list[str],
    matched: set[str],
    *,
    catalog: list[dict] | None = None,
    context_length: int | None = None,
) -> list[str]:
    """Union find_tools matches into the persisted activated set.

    FIX (context-explosion): when `catalog` is supplied, cap by a TOKEN budget
    (most-recently-activated wins) instead of a raw COUNT of 64 — a count cap let
    64 verbose schemas re-inflate the surface. Without a catalog (legacy callers /
    tests) fall back to the count cap so behaviour is unchanged.
    """
    merged = list(dict.fromkeys([*current, *sorted(matched)]))
    if catalog is not None:
        tok = {tool_name(td): _tool_tokens(td) for td in catalog}
        budget = scale_by_window(ACTIVATED_TOOLS_TOKEN_BUDGET, context_length)
        # keep newest-first until the token budget, then restore original order
        kept: list[str] = []
        used = 0
        for nm in reversed(merged):
            t = tok.get(nm, 0)
            if used + t > budget and kept:
                break
            kept.append(nm)
            used += t
        keep_set = set(kept)
        return [nm for nm in merged if nm in keep_set]
    if len(merged) > ACTIVATED_TOOLS_CAP:
        merged = merged[-ACTIVATED_TOOLS_CAP:]
    return merged
