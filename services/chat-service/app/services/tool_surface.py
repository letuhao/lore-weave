"""Session-scoped tool surface assembly — whitelist-with-escape (story 04).

When ``enabled_tools`` is non-empty (curated mode), the turn advertises
ALWAYS_ON_CORE ∪ pins ∪ session ``activated_tools``; ``find_tools`` unions
matches into the per-turn active set AND persists to ``activated_tools``.
Empty pins preserve legacy hot-set + auto-discovery behaviour.
"""
from __future__ import annotations

import json
from dataclasses import dataclass

from app.services.token_budget import estimate_tokens
from app.services.tool_discovery import hot_tool_names, surface_hot_domains, tool_name

ACTIVATED_TOOLS_CAP = 64

# ── Token-budgeted tool surface (2026-07-06 context-explosion fix) ────────────
# The book-scoped hot-seed used to advertise ENTIRE domains (glossary+story ≈ 64
# tools / ~24K tokens) on EVERY LLM call, re-sent on each tool-loop iteration →
# 137K-token turns for an 8K-token conversation (see
# docs/eval/context-budget/context-explosion-investigation-2026-07-06.md). We now
# bound the always-advertised sets by a TOKEN budget; `find_tools` pulls the long
# tail on demand. Industry-standard "tool-RAG / lazy tool loading" (RAG-MCP,
# Anthropic Tool Search): a small hot core + discovery beats shipping whole domains.
HOT_SEED_TOKEN_BUDGET = 4000        # ~8-12 tools stay hot; rest lazy via find_tools
ACTIVATED_TOOLS_TOKEN_BUDGET = 6000  # cap the find_tools-accumulated set by tokens

# Read/query verbs → the tools safe to keep hot (writes/proposes are discovered on
# demand and usually confirmation-gated anyway).
_READ_VERBS = (
    "search", "list", "get", "read", "find", "lookup",
    "show", "view", "fetch", "describe", "query",
)


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
    ordered = sorted(
        defs.items(),
        key=lambda kv: (0 if _is_read_tool(kv[0]) else 1, _tool_tokens(kv[1]), kv[0]),
    )
    used = 0
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


def resolve_session_tool_pins(
    session_row,
    *,
    enabled_tools_override: list[str] | None = None,
    enabled_skills_override: list[str] | None = None,
) -> SessionToolPins:
    session_enabled = list(session_row.get("enabled_tools") or []) if session_row else []
    session_skills = list(session_row.get("enabled_skills") or []) if session_row else []
    session_activated = list(session_row.get("activated_tools") or []) if session_row else []
    effective_enabled = (
        enabled_tools_override if enabled_tools_override is not None else session_enabled
    )
    effective_skills = (
        enabled_skills_override if enabled_skills_override is not None else session_skills
    )
    return SessionToolPins(
        effective_enabled=effective_enabled,
        effective_skills=effective_skills,
        curated_mode=is_curated(effective_enabled),
        activation_state={"activated_tools": list(session_activated), "dirty": False},
    )


def discovery_seed_for_surface(
    catalog: list[dict],
    *,
    pins: SessionToolPins,
    editor: bool,
    book_scoped: bool,
    studio: bool = False,
) -> set[str]:
    """Discovery active-set seed: hot set (auto) or pins ∪ activated (curated)."""
    hot_domains = surface_hot_domains(editor=editor, book_scoped=book_scoped, studio=studio)
    # FIX (context-explosion): token-budget the hot-seed instead of seeding the
    # WHOLE domain(s). Cuts the always-advertised base ~24K → ~4K.
    raw_hot_seed = budget_names_by_tokens(
        catalog, hot_tool_names(catalog, hot_domains),
        token_budget=HOT_SEED_TOKEN_BUDGET,
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
        )
    return assemble_initial_active_names(
        curated=pins.curated_mode,
        enabled_tools=eff_pins,
        activated_tools=pins.activation_state["activated_tools"],
        hot_seed_names=raw_hot_seed,
    )


def is_curated(enabled_tools: list[str] | None) -> bool:
    return bool(enabled_tools)


def effective_enabled_tools(
    enabled_tools: list[str],
    *,
    glossary_skill: bool,
    catalog: list[dict],
    hot_domains: set[str],
) -> list[str]:
    """When glossary skill is active in curated mode, auto-union glossary hot tools."""
    if not glossary_skill or not enabled_tools:
        return list(enabled_tools)
    # FIX (context-explosion): budget the auto-unioned hot set too, so curated
    # sessions with the glossary skill don't re-inflate the whole domain.
    hot = budget_names_by_tokens(
        catalog, hot_tool_names(catalog, hot_domains),
        token_budget=HOT_SEED_TOKEN_BUDGET,
    )
    return list(dict.fromkeys([*enabled_tools, *sorted(hot)]))


def assemble_initial_active_names(
    *,
    curated: bool,
    enabled_tools: list[str],
    activated_tools: list[str],
    hot_seed_names: set[str],
) -> set[str]:
    if not curated:
        return set(hot_seed_names)
    return set(enabled_tools) | set(activated_tools)


def merge_activated_tools(
    current: list[str],
    matched: set[str],
    *,
    catalog: list[dict] | None = None,
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
        # keep newest-first until the token budget, then restore original order
        kept: list[str] = []
        used = 0
        for nm in reversed(merged):
            t = tok.get(nm, 0)
            if used + t > ACTIVATED_TOOLS_TOKEN_BUDGET and kept:
                break
            kept.append(nm)
            used += t
        keep_set = set(kept)
        return [nm for nm in merged if nm in keep_set]
    if len(merged) > ACTIVATED_TOOLS_CAP:
        merged = merged[-ACTIVATED_TOOLS_CAP:]
    return merged
