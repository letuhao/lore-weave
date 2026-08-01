"""Session-scoped tool surface assembly — whitelist-with-escape (story 04).

When ``enabled_tools`` is non-empty (curated mode), the turn advertises
ALWAYS_ON_CORE ∪ pins ∪ session ``activated_tools``; ``find_tools`` unions
matches into the per-turn active set AND persists to ``activated_tools``.
Empty pins preserve legacy hot-set + auto-discovery behaviour.
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from functools import lru_cache

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
# F12 (measured 2026-07-21, warm-cache A/B on gpt-4o-mini): env-tunable hot-seed budget.
# LOWERED 4000→2000 as the default. Isolated A/B (skills left on their designed lazy path —
# lazy_skill_bodies stays ON; NOT the blunt LW_LAZY_ALL_SKILLS test knob): 2000 cut the
# assembled prefix ~17-24% per turn on a warm 4-turn book session with NO extra discovery
# passes and NO quality loss (all adds persisted), and the smaller prefix still cache-hits
# (warm passes ~0.1 $/Mtok = fully cached). 2000 keeps ~4-6 common tools hot (robust for
# non-glossary tasks that budget=0 would push into pure discovery); the long tail stays lazy
# via find_tools. Set LW_HOT_SEED_TOKEN_BUDGET=0 for the original pure-index design, or 4000
# to restore the prior default.
HOT_SEED_TOKEN_BUDGET = int(os.environ.get("LW_HOT_SEED_TOKEN_BUDGET", "2000"))  # ~4-6 tools hot; rest lazy
# D-RAIL-OWN-BUDGET (2026-07-26, Mị Đế dogfood): a PINNED rail's step tools get their own,
# larger ceiling — separate from the discovery hot-seed. The 2000-token seed budget is
# surface economy against DISCOVERY sprawl (a weak model does worse with more tools); a
# pinned rail is the opposite of sprawl — a curated, bounded recipe whose TEXT names every
# step tool, so dropping one re-creates the "recipe names a tool the agent cannot see"
# silent no-op (measured live all day: glossary_propose_entities was the perpetual drop).
# 6000 tok fits a ~9-step rail with two large schemas; the budget remains a safety valve
# for a pathological rail, not a routine constraint.
RAIL_STEP_TOKEN_BUDGET = int(os.environ.get("LW_RAIL_STEP_TOKEN_BUDGET", "6000"))
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
    # ML-2 FALSE POSITIVE (documented, NOT an active pragma — language-bias-gate
    # exempts via its BASELINE fingerprint set, not inline markers, so writing one
    # here would be a claim that silences nothing). `name` is an MCP TOOL NAME,
    # ASCII by contract
    # (closed-set snake_case per the Frontend-Tool Contract), never user prose. On
    # ASCII, .lower() and the NFKC+casefold spine are identical, and routing tool
    # dispatch through an entity-name normalizer would imply it can carry prose.
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
    rail_done_step_tools: set[str] | None = None,
    rail_repeat_done_step_tools: set[str] | None = None,
    rail_next_step_tools: set[str] | None = None,
    sticky_domains: set[str] | None = None,
    injected_skill_codes: list[str] | None = None,
) -> set[str]:
    """Discovery active-set seed: hot set (auto) or pins ∪ activated (curated).

    ``binding_categories`` (WS-3/C6 ``seed_tool_categories``) are unioned into the
    surface's hot domains — ADDITIVE, and they ride the SAME single
    ``HOT_SEED_TOKEN_BUDGET`` ceiling as the surface's own domains (never a second,
    independently-budgeted call: that is the additive-per-domain pattern that caused the
    2026-07-06 context explosion).

    ``sticky_domains`` (D-DOMAIN-HOTSET-NOT-STICKY) are the domains the RECENT
    conversation has actively called into (``engaged_domains_from_tool_calls``). They
    union in the SAME additive way and ride the SAME single budget — so re-seeding the
    book domain the writer used two turns ago costs nothing extra beyond the shared
    ceiling, and the budget still truncates if the union grows. Without this, auto mode
    forgets the working domain across turns and the model can't act on a low-signal
    follow-up (or hallucinates that it did).
    """
    hot_domains = surface_hot_domains(
        editor=editor, book_scoped=book_scoped, studio=studio, permission_mode=permission_mode,
    )
    if sticky_domains:
        hot_domains = set(hot_domains) | set(sticky_domains)
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
        # Budget-priority fix (2026-07-26): budget_rail_tools keeps tools in DECLARED STEP
        # ORDER, so a long rail spends its budget on the EARLY steps and drops the late ones.
        # After the early steps are DONE that is backwards — it advertises completed steps
        # (which the action-space gate suppresses downstream anyway) and starves the step the
        # agent needs NOW (the live bug: `plan_propose_spec` dropped while the done glossary
        # steps stayed, so the agent read a recipe naming a tool it could not see and wrote the
        # plan as prose instead of calling the tool). Drop the fully-DONE step tools from the
        # candidate set first, so the not-done steps win the budget. A tool still owed by a
        # not-done step is NOT in this set (rail_gate_suppressions keeps it), so this never
        # hides a tool the agent still needs.
        # D-RAIL-REPEAT-BUDGET (v2 of the done-exclusion): done steps are REORDERED to the
        # back of the budget queue, not hard-dropped. The rail TEXT names every step tool;
        # a done-but-repeatable step (save-cast — "add MORE characters") must still ride
        # when room remains, it just can never starve a never-done step. Priority:
        # never-done → repeat-done (the ones a user re-invokes) → one-shot-done (advertise-
        # suppressed by the gate anyway — budget spent on them is pure waste). A done tool
        # that loses the budget is reported like any other drop.
        _done = rail_done_step_tools or set()
        _repeat_done = (rail_repeat_done_step_tools or set()) & _done
        _rail_candidates = (
            [t for t in pinned_step_tools if t not in _done]
            + [t for t in pinned_step_tools if t in _repeat_done]
            + [t for t in pinned_step_tools if t in _done - _repeat_done]
        )
        # D-RAIL-NEXT-STEP-EXEMPT (2026-07-26, Mị Đế dogfood): the rail's NEXT step tools are
        # budget-EXEMPT. Dropping by declared order still starved the step the agent needs NOW
        # when earlier not-done steps ate the budget — live wedge: kg_propose_edge failed with
        # "call kg_project_entities_to_nodes first" while that exact tool was budget-dropped,
        # so the step-runner redrove a step whose tool the agent could not see, 8 times, and
        # the model reported success anyway. The step being DRIVEN must always be on the wire.
        _next_exempt = (rail_next_step_tools or set()) & set(_rail_candidates)
        kept, dropped = budget_rail_tools(
            catalog, [t for t in _rail_candidates if t not in _next_exempt],
            token_budget=scale_by_window(RAIL_STEP_TOKEN_BUDGET, context_length),
        )
        names = names | kept | _next_exempt
        if dropped:
            logger.warning(
                "pinned rail step tools dropped by the token budget: %s — the rail names "
                "tools the agent cannot see", ", ".join(dropped),
            )
    # D-SKILL-NAMED-TOOLS-RIDE (2026-07-26, Mị Đế dogfood — THE root cause of the
    # entity_edit/propose_entities confusion): a skill PROMPT injected this turn can
    # NAME tools directly ("Add new entities: `glossary_propose_entities`"), but the
    # budgeted hot seed can drop exactly those tools under domain pressure — proven
    # on the wire: the request's instructions named glossary_propose_entities while
    # the 21 advertised tools carried only glossary_propose_entity_edit, so the
    # model mapped the create intent onto the similarly-named edit tool, every turn.
    # The authoring-time lint (test_every_skills_named_tools_are_in_its_hot_domains)
    # guarantees named ⊆ hot_domains, but a runtime budget still breaks the
    # invariant. Rule: an INJECTED instruction must never name a tool that is not
    # on the wire — the named tools of every injected skill ride budget-exempt,
    # exactly like a pinned rail's next-step tools. Bounded: a skill names a
    # handful of tools, and only skills actually injected THIS turn contribute.
    if injected_skill_codes:
        names = names | skill_named_tools(injected_skill_codes, catalog)
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


# D-TOOL-LOAD-PERSISTS — how many of the most-recently-activated tools an AUTO-mode
# turn re-advertises. Small on purpose: enough to keep the tool the model just
# tool_load'ed alive across turns, small enough that a stale accumulation can't
# re-inflate the surface.
AUTO_ACTIVATED_TAIL = 6


@lru_cache(maxsize=64)
def _skill_prompt_named_tokens(skill_code: str) -> frozenset[str]:
    """Backtick-quoted snake_case tokens a skill's PROSE names (candidate tool names).

    Cached per skill code — prompts are static module constants. The catalog
    intersection happens per call in `skill_named_tools` (the catalog can change)."""
    from app.services.skill_registry import SYSTEM_SKILLS

    skill = SYSTEM_SKILLS.get(skill_code)
    if skill is None:
        return frozenset()
    try:
        prompt = skill.prompt_loader()
    except Exception:  # noqa: BLE001 — a skill that can't load contributes nothing
        return frozenset()
    return frozenset(re.findall(r"`([a-z][a-z0-9_]{3,})`", prompt))


def skill_named_tools(skill_codes: list[str], catalog: list[dict]) -> set[str]:
    """The REAL catalog tools directly named by these skills' prompts.

    D-SKILL-NAMED-TOOLS-RIDE: an injected instruction must never name a tool that
    is not on the wire — the caller unions this set budget-exempt."""
    catalog_names = {tool_name(td) for td in catalog}
    out: set[str] = set()
    for code in skill_codes:
        out |= _skill_prompt_named_tokens(code) & catalog_names
    return out


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
    #
    # D-TOOL-LOAD-PERSISTS amendment (2026-07-26, Mị Đế dogfood): PLUS the recency TAIL of
    # the persisted set. tool_load now persists in auto mode too (stream_service — the
    # measured failure: the model's freshly-loaded create tool evaporated every turn while
    # the frontend edit tool stayed visible, so the create intent kept landing on the wrong
    # tool). The tail is bounded (last AUTO_ACTIVATED_TAIL names, most-recent-last thanks to
    # the LRU refresh), so a curated-then-flipped session leaks at most a handful of its
    # most recently REQUESTED tools — not the whole accumulation the review note rejected.
    if not curated:
        wf = workflow_step_tools or set()
        return (
            set(hot_seed_names)
            | (set(activated_tools) & wf)
            | set(activated_tools[-AUTO_ACTIVATED_TAIL:])
        )
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

    D-ACTIVATED-LRU-REFRESH (2026-07-26, Mị Đế dogfood): a RE-activated name must
    move to the recency END. The old `dict.fromkeys([*current, *matched])` kept
    the FIRST occurrence, so re-loading an already-activated tool left it at its
    original (oldest) position — and the budget evicted it first. Live degradation
    loop: gemma tool_load'ed glossary_propose_entities, the next turn's newer rail
    activations pushed it over budget, it was evicted DESPITE being the most
    recently requested, the model fell back to the always-visible edit tool whose
    error said "tool_load it" — and the cycle repeated, forever, with the agent
    never able to create an entity.
    """
    merged = list(dict.fromkeys([*(nm for nm in current if nm not in matched), *sorted(matched)]))
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
