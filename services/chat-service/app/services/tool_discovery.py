"""MCP-fanout S-CONSUMER — tool discovery + tier metadata (C-FT, C-TOOL).

This is the *consumer-side* tool-scaling foundation. At ~200 federated tools,
shipping the full catalog to the LLM every turn is context bloat + degraded
tool selection (spec P0). Instead the agent first *searches* with the
``find_tools`` meta-tool, and only the matched tools' full schemas are
advertised on the next pass.

Everything here operates on the catalog chat already caches
(``KnowledgeClient.get_tool_definitions()``); ``find_tools`` is **consumer-local**
— NOT a federated domain tool — so it carries no user-data envelope and needs
no ownership guard (spec OD-1 / C-FT).

Key pieces
----------
* ``FIND_TOOLS_TOOL`` / ``FIND_TOOLS_NAME`` — the meta-tool schema (C-FT).
* ``ALWAYS_ON_CORE`` — the ≤8 tools advertised every universal ``/chat`` turn.
* ``search_catalog()`` — in-memory fuzzy search over name + description +
  ``_meta.synonyms`` (stdlib token-overlap + difflib; no embeddings in v1, no
  new dependency). Returns ``(matches, confident)`` so the loop can apply the
  H6 low-confidence/empty escalation.
* ``tool_tier()`` / ``tool_undo_hint()`` — read C-TOOL ``_meta`` for the
  consumer's tier-driven behaviour.
* ``strip_tool_meta()`` — drop ``_meta`` before a def goes over the wire to the
  provider (the LLM must see only a standard OpenAI function def).
* ``provider_availability()`` — H10 helper turning the gateway's catalog-meta
  into "is this tool's provider temporarily unavailable?".
"""
from __future__ import annotations

import re
from difflib import SequenceMatcher

# ── C-FT: the find_tools meta-tool ───────────────────────────────────────────

FIND_TOOLS_NAME = "find_tools"

# Default number of matches returned to the agent.
FIND_TOOLS_DEFAULT_LIMIT = 8

# ── Part A: tool group directory (near-zero-cost discovery pointer) ─────────
# Injected as PLAIN TEXT (not tool schemas) alongside ALWAYS_ON_CORE, so the model
# has a map of what domains exist without paying a hot-seeded domain's full
# schema tax (~15-20 one-line entries ≈ 300-500 tokens total, vs ~24K for a
# hot-seeded domain — see docs/eval/context-budget/context-explosion-
# investigation-2026-07-06.md). Keys are tool-name-prefixes (the same federation
# naming convention `_provider_prefix` reads); `group` on find_tools scopes the
# fuzzy search to one entry instead of the full ~150-tool flat catalog.
GROUP_DIRECTORY: dict[str, str] = {
    "glossary": "Lore entities (characters/locations/items/kinds) — CRUD + wiki + standards ontology.",
    # `book_get_chapter` is prefix `book_`, not `story_` — it lives in the "book" group below;
    # the group filter is prefix-based (see `_provider_prefix`), so this entry must only claim
    # tools this group's search can actually surface.
    "story": "Manuscript search (story_search).",
    "composition": "Outline/scene/canon planning — Story Grid rules, motif/arc library.",
    "knowledge": "Derived KG facts (Neo4j-backed), passage retrieval, memory_search.",
    "translation": "Job-based chapter/book translation pipeline.",
    "book": "Book/chapter CRUD, publishing, chapter body reads (incl. book_get_chapter).",
    "jobs": "Job status/cancel for any long-running operation.",
    "catalog": "Public catalog browsing (published books, discovery).",
    "registry": "Agent/tool registry administration.",
    "settings": "User/account settings and provider-model configuration.",
    # PlanForge tools federate under their own `plan_` prefix (composition-service's M4
    # federation contract), NOT `composition_` — a separate group so group="plan" actually
    # surfaces them (they used to be mis-claimed under "composition" above, which the
    # prefix-based filter could never honor).
    "plan": "Novel planning workflow — PlanForge propose/refine/validate/compile (plan_propose_spec, plan_self_check, plan_interpret_feedback, plan_apply_revision, plan_review_checkpoint, plan_handoff_autofix, plan_validate, plan_compile).",
}

FIND_TOOLS_TOOL: dict = {
    "type": "function",
    "function": {
        "name": FIND_TOOLS_NAME,
        "description": (
            "Find tools that can perform an intent. Call this FIRST when the user "
            "asks for something you don't already have a tool advertised for "
            "(e.g. editing a book, starting a translation, changing settings). "
            "Returns matching tool names + descriptions; the matched tools become "
            "callable on your NEXT step. If it returns nothing useful, you may try "
            "once more with broader wording before telling the user you can't."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "intent": {
                    "type": "string",
                    "description": "What the user wants to do, in your own words.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Max tools to return (default 8).",
                    "default": FIND_TOOLS_DEFAULT_LIMIT,
                },
                "group": {
                    "type": "string",
                    "enum": sorted(GROUP_DIRECTORY),
                    "description": "Optional — scope the search to one tool domain from your tool-domain directory. Omit to search everything.",
                },
            },
            "required": ["intent"],
            "additionalProperties": False,
        },
    },
}


# ── C-FT: the always-on core (advertised on every discovery turn, ≤8) ─────────
# Domain reads/writes are discovered via find_tools; only the meta-tool + the
# truly GENERIC, surface-agnostic frontend tools are always present. The
# frontend-tool schemas live in frontend_tools.py (S-CONSUMER sole-owns that
# file); this names which are core.
#
# `propose_edit` is deliberately NOT core: it targets "the chapter the user is
# currently writing", so it only makes sense with editor_context and is
# advertised via `frontend_tool_defs(editor=True)` (discovery_extra_frontend) on
# the editor surface — never on a book-scoped or universal surface where there is
# no open chapter. (`propose_record_edit` is the generic, surface-agnostic record
# diff card and stays core.)
ALWAYS_ON_CORE_NAMES: tuple[str, ...] = (
    FIND_TOOLS_NAME,
    "ui_navigate",
    "ui_open_book",
    "ui_show_panel",
    "ui_watch_job",
    "propose_record_edit",
    "confirm_action",
)


# ── C-FT: per-surface HOT SET (the enterprise hot-set + lazy-tail pattern) ────
# Discovery is the STANDARD transport for every agui surface (the full catalog is
# never shipped — the agent find_tools-searches the long tail on demand). What
# differs per surface is the HOT SET: the domains whose tools are seeded into the
# discovery active-set on pass 1, so they're advertised immediately without a
# find_tools round-trip. This keeps a surface's own skill working (it names those
# tools directly) while everything OUTSIDE the surface's domains stays lazy — so
# the per-turn tool payload stays small no matter how many domains/MCP tools the
# platform federates (P0: scales to thousands of tools).
#
# The rule for choosing a surface's hot domains: HOT = the domain(s) the surface's
# injected SKILL names directly (so the skill works with no discovery hop); every
# other domain is lazy. Both the book-scoped (glossary page / reader) AND the
# chapter-editor surfaces inject the SAME glossary skill, which names only
# `glossary_*` tools — so both have hot domain {glossary}. The editor's extra
# capability (prose write-back) is the `propose_edit` FRONTEND tool, advertised via
# `frontend_tool_defs(editor=True)`, NOT a backend domain — so composition / book
# tools stay lazy there too (reachable via find_tools, which the glossary skill
# tells the agent to use for off-glossary asks). Universal (no book/editor) seeds
# nothing — pure discovery. Admin uses its own small catalog (no discovery).
#
# Domain membership is by the tool name's prefix (`glossary_book_patch` →
# `glossary`), matching the federated naming convention; a NEW domain service's
# tools are therefore lazy-by-default — they only enter a surface's hot set when
# that surface's domain list opts them in here.
# `story` = the `story_search` universal manuscript find (exact/lexical + semantic +
# block snippets). It is HOT on every book-bound surface, NOT find_tools-lazy, for the
# SAME reason composition_* is (below): a weak model asked "where is X at chapter N" /
# "the firm the character works for" reaches for memory_search (semantic, empty without
# ingested passages) and then PUNTS — "paste the manuscript" — instead of discovering the
# lexical search it's standing on. Measured 2026-07-05 on the Dracula eval: after
# story_search was un-dropped from federation the agent STILL never found it via
# find_tools (ranked 7th / missed), so it must be seeded. It needs no embeddings/KG (the
# exact leg is book-service full-text), so it is the grounding-of-last-resort for ANY
# book — including ones with no glossary/KG built.
_BOOK_SCOPED_HOT_DOMAINS: frozenset[str] = frozenset({"glossary", "story"})
# The Writing Studio compose panel IS the composition surface — its own tool family
# (outline/scene/canon reads + writes) must be hot, not find_tools-lazy. Live M-E
# gate evidence: with composition_* lazy, a local model spun for minutes in
# memory/glossary searches concluding "I don't see a list_scenes tool" and never
# discovered the family it was standing on. (`story` hot here too — same lesson.)
_STUDIO_HOT_DOMAINS: frozenset[str] = frozenset({"glossary", "composition", "story"})

# RAID B2 follow-up — PLAN mode auto-injects the plan_forge skill (see
# skill_registry.resolve_skills_to_inject), which names `plan_*` tools directly on
# ANY surface that allows it (book/editor) — the same "HOT = the domain the
# injected skill names directly" rule this file documents above. It was missed
# when plan_forge shipped: `plan_*` federates under its OWN `plan` prefix (never
# `composition`), so it needs its own hot-domain entry, independent of which
# surface-driven set (book-scoped vs studio) is otherwise in play.
PLAN_HOT_DOMAINS: frozenset[str] = frozenset({"plan"})


def surface_hot_domains(
    *,
    editor: bool = False,
    book_scoped: bool = False,
    studio: bool = False,
    permission_mode: str = "write",
) -> set[str]:
    """The domain prefixes whose tools are HOT (advertised every turn) for a
    surface. Any book-scoped surface (the glossary page/reader OR the chapter
    editor — both inject the glossary skill) gets the glossary domain hot; the
    editor adds no extra backend domain (its prose write-back is a frontend tool).
    The STUDIO compose surface adds the composition domain (its own tool family).
    Universal (no flag) returns ∅ — pure discovery.

    ``permission_mode="plan"`` additionally hot-seeds the `plan` domain — the
    plan_forge skill is auto-injected in plan mode on any surface that allows it
    (book/editor), independent of the surface-driven sets above."""
    if studio:
        domains = set(_STUDIO_HOT_DOMAINS)
    elif book_scoped or editor:
        domains = set(_BOOK_SCOPED_HOT_DOMAINS)
    else:
        domains = set()
    if permission_mode == "plan":
        domains |= PLAN_HOT_DOMAINS
    return domains


def hot_tool_names(catalog: list[dict], domains: set[str]) -> set[str]:
    """The catalog tool names whose domain prefix is in ``domains`` — the set to
    seed into the discovery active-set so they're advertised on the first pass.
    Empty ``domains`` → empty set (universal surface: nothing pre-seeded).
    CAT-4: a `legacy`-tagged tool is NEVER hot-seeded, even when its domain is —
    the whole point of tagging it legacy is that it stops riding the wire by
    default; a domain hot-seed that ignored this would silently defeat CAT-4."""
    if not domains:
        return set()
    out: set[str] = set()
    for td in catalog:
        name = tool_name(td)
        if name and _domain_of(name) in domains and not is_legacy_tool(td):
            out.add(name)
    return out


def group_directory_text() -> str:
    """Render GROUP_DIRECTORY as the plain-text block injected into a surface's
    system prompt alongside ALWAYS_ON_CORE. Deterministic order (sorted by key)."""
    lines = [f"- {name}: {desc}" for name, desc in sorted(GROUP_DIRECTORY.items())]
    return "Tool domains (use find_tools with group=<name> to search one):\n" + "\n".join(lines)


# ── C-TOOL: tier + meta readers ──────────────────────────────────────────────


def _fn(tool_def: dict) -> dict:
    """The OpenAI `function` object of a tool def (or {} if malformed)."""
    fn = tool_def.get("function")
    return fn if isinstance(fn, dict) else {}


def tool_name(tool_def: dict) -> str:
    return _fn(tool_def).get("name", "") or ""


def tool_meta(tool_def: dict) -> dict:
    """The C-TOOL `_meta` block for a tool def, or {} when absent (legacy
    glossary/knowledge tools predate `_meta` — they're treated as untiered)."""
    meta = _fn(tool_def).get("_meta")
    return meta if isinstance(meta, dict) else {}


def tool_tier(tool_def: dict) -> str:
    """C-TOOL `_meta.tier` ∈ R|A|W|S. Defaults to "R" (read / inert) when a tool
    carries no tier — a missing tier must NEVER auto-commit a write."""
    tier = tool_meta(tool_def).get("tier")
    return tier if tier in ("R", "A", "W", "S") else "R"


# CAT-4 (mcp-tool-io.md Part 4) — a superseded tool is tagged `_meta.visibility:
# "legacy"` rather than deleted, so any existing caller keeps working. A legacy
# tool must never be discoverable: excluded from search_catalog() and from every
# domain hot-seed. The ai-gateway TS twin (`find-tools.ts` `toolVisibility()`/
# `searchCatalog()`) must carry the identical exclusion — the two engines are
# documented to rank identically; this is the one place they must also FILTER
# identically, or a legacy tool leaks through whichever surface forgot the check.
_VISIBILITY_LEGACY = "legacy"


def tool_visibility(tool_def: dict) -> str:
    """C-TOOL `_meta.visibility` ∈ discoverable|legacy. Defaults to "discoverable"
    when absent — every pre-CAT-4 tool is unaffected without a code change."""
    vis = tool_meta(tool_def).get("visibility")
    return vis if vis == _VISIBILITY_LEGACY else "discoverable"


def is_legacy_tool(tool_def: dict) -> bool:
    return tool_visibility(tool_def) == _VISIBILITY_LEGACY


def unknown_pinned_legacy_names(catalog: list[dict], requested: list[str]) -> list[str]:
    """SET-6 closed-set validation for `pinned_legacy_tools`: any requested name
    that is NOT a legacy tool in the live catalog (unknown name, or a
    discoverable/non-legacy tool someone tried to pin this way). Empty = all
    requested names are valid; the router rejects the write when non-empty
    rather than silently dropping the bad names."""
    legacy_names = {t["name"] for t in legacy_tools_catalog(catalog)}
    return [n for n in requested if n not in legacy_names]


def legacy_tools_catalog(catalog: list[dict]) -> list[dict]:
    """CAT-4 Part D — the server-sourced, closed-set list of legacy tools a user
    may manually pin for a session (`pinned_legacy_tools`, SET-6). Never
    hand-authored: always derived from the LIVE catalog, so a future tag/untag
    of a tool is reflected here with no separate list to keep in sync."""
    return sorted(
        (
            {"name": tool_name(td), "description": _fn(td).get("description", "") or ""}
            for td in catalog
            if is_legacy_tool(td)
        ),
        key=lambda t: t["name"],
    )


def tool_undo_hint(result_meta: dict | None) -> dict | None:
    """C-ACTIVITY — the `_meta.undo_hint` a Tier-A tool RESULT carries
    (``{tool, args}``), or None. Read from the tool *result*, not the def."""
    if not isinstance(result_meta, dict):
        return None
    hint = result_meta.get("undo_hint")
    return hint if isinstance(hint, dict) else None


def strip_tool_meta(tool_def: dict) -> dict:
    """Return a copy of a tool def with the consumer-only `_meta` removed, so
    the provider sees a standard OpenAI function def (C-TOOL: identity/tier
    metadata is consumer-side only, never advertised to the LLM)."""
    fn = _fn(tool_def)
    if "_meta" not in fn:
        return tool_def
    clean_fn = {k: v for k, v in fn.items() if k != "_meta"}
    out = dict(tool_def)
    out["function"] = clean_fn
    return out


# ── C-FT: in-memory fuzzy search ─────────────────────────────────────────────

_TOKEN_RE = re.compile(r"[a-z0-9]+")

# Below this best-match score the result is "low confidence" → the loop may
# escalate once to the full curated group rather than denying (H6).
CONFIDENCE_THRESHOLD = 0.30
# A tool must score at least this to appear in results at all — keeps pure-noise
# difflib near-misses (a few shared characters) out of the match list, so a true
# "no such tool" reads as empty (H10) rather than a bogus suggestion.
INCLUSION_FLOOR = 0.20


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall((text or "").lower()))


def _score(intent_tokens: set[str], intent_raw: str, tool_def: dict) -> float:
    """Heuristic relevance score in [0, 1] of a tool for an intent.

    Combines token overlap (Jaccard-ish, the dominant signal) over the tool's
    name + description + synonyms with a difflib ratio on the raw strings, so a
    near-miss spelling still scores. No embeddings (v1, C-FT)."""
    name = tool_name(tool_def)
    desc = _fn(tool_def).get("description", "") or ""
    synonyms = tool_meta(tool_def).get("synonyms") or []
    syn_text = " ".join(s for s in synonyms if isinstance(s, str))
    # The name often encodes the verb (book_create, translation_start_job);
    # split snake_case so its tokens participate.
    hay = f"{name.replace('_', ' ')} {desc} {syn_text}"
    hay_tokens = _tokens(hay)
    if not intent_tokens:
        return 0.0

    overlap = len(intent_tokens & hay_tokens)
    token_score = overlap / len(intent_tokens)
    # difflib catches typo/near-miss matches the token set misses (e.g.
    # "translit" ~ "translate"), compared PER token against the name + synonym
    # tokens (more discriminating than the whole raw string, which would let an
    # unrelated long word like "frobnicate" score on incidental shared chars).
    target_tokens = _tokens(f"{name} {syn_text}")
    best_ratio = 0.0
    for it in intent_tokens:
        for tt in target_tokens:
            r = SequenceMatcher(None, it, tt).ratio()
            if r > best_ratio:
                best_ratio = r
    # Only a STRONG fuzzy hit (≥0.8, i.e. a near-spelling) rescues a tool with NO
    # token overlap — a weak char-similarity must not invent a match (H10).
    #
    # review-impl live-verification fix (2026-07-06): this precondition (`overlap
    # == 0`) was documented above but never actually enforced — `best_ratio` was
    # computed unconditionally and any EXACT single-token overlap (ratio=1.0 for
    # identical strings) qualified as a "strong fuzzy hit," overriding token_score
    # to a perfect 1.0 even when only one incidental, generic shared word (e.g.
    # "book") connected an otherwise-unrelated tool to the intent. Invisible in
    # the small offline eval catalog (curated synonyms with no accidental overlap
    # with intent wording); live-verified at the real ~190-tool federated catalog
    # scale, where e.g. "add a new kind to the book" scored translation_start_job
    # a perfect 1.0 (via its unrelated synonym sharing only the word "book"),
    # outranking glossary_ontology_upsert's genuine 3-token overlap.
    fuzzy = best_ratio if (overlap == 0 and best_ratio >= 0.8) else 0.0
    return max(token_score, fuzzy)


def search_catalog(
    catalog: list[dict],
    intent: str,
    limit: int = FIND_TOOLS_DEFAULT_LIMIT,
    *,
    exclude: set[str] | None = None,
    group: str | None = None,
) -> tuple[list[dict], bool]:
    """C-FT — fuzzy-search the cached catalog for tools matching ``intent``.

    Returns ``(matches, confident)`` where:
      * ``matches`` — up to ``limit`` ``{"name", "description"}`` dicts (names +
        descriptions only — NOT full schemas; the schemas are advertised next
        pass once the names are unioned into the active set).
      * ``confident`` — False when the result is empty OR the best score is
        below ``CONFIDENCE_THRESHOLD`` (H6 low-confidence → the loop may
        escalate once to the full curated surface rather than denying).

    ``exclude`` — names already always-on (the core); they're skipped so a
    search never re-suggests a tool the agent already has.

    ``group`` (Part A) — when set, scope the search to tools whose domain
    prefix matches (see GROUP_DIRECTORY); improves precision over a fully-flat
    search across ~150 tools.

    CAT-4 — a `legacy`-tagged tool is EXCLUDED unconditionally, group filter or
    not. This is the mechanism the tool-catalog-simplification eval
    (docs/eval/tool-catalog-comprehension-2026-07-06.md) found is load-bearing:
    a legacy tool's short, punchy pre-CAT-4 description out-scores a new
    tool's more precise one on raw token overlap, so description/synonym
    tuning alone does not make a superseded tool lose the ranking race —
    only removing it from the search space does.
    """
    exclude = exclude or set()
    intent_tokens = _tokens(intent)
    scored: list[tuple[float, dict]] = []
    for tool_def in catalog:
        name = tool_name(tool_def)
        if not name or name in exclude or is_legacy_tool(tool_def):
            continue
        if group is not None and _domain_of(name) != group:
            continue
        s = _score(intent_tokens, intent, tool_def)
        if s >= INCLUSION_FLOOR:
            scored.append((s, tool_def))
    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[: max(1, limit)] if scored else []
    matches = [
        {"name": tool_name(td), "description": _fn(td).get("description", "") or ""}
        for _, td in top
    ]
    confident = bool(scored) and scored[0][0] >= CONFIDENCE_THRESHOLD
    return matches, confident


# ── H10: provider availability ───────────────────────────────────────────────


def _provider_prefix(name: str) -> str:
    """The provider prefix of a tool name (`book_create` → `book`). Frontend
    + meta tools (no prefix convention) return ""."""
    return name.split("_", 1)[0] if "_" in name else ""


# The "knowledge" GROUP_DIRECTORY entry covers TWO literal tool-name prefixes
# (`kg_*` — the Neo4j-backed graph, and `memory_*` — conversation/passage recall) under
# one conceptual domain, but domain/group matching elsewhere compares the LITERAL
# prefix against the domain name directly — so `_provider_prefix("kg_graph_query")` is
# `"kg"`, never `"knowledge"`, and `hot_tool_names(catalog, {"knowledge"})` /
# `find_tools(group="knowledge")` silently matched NOTHING before this alias existed
# (found 2026-07-07 while auditing GROUP_DIRECTORY for the skill-authoring lint — same
# root cause as the "story"/"composition" GROUP_DIRECTORY text mismatches fixed the
# same day, just at the matching-mechanism layer instead of the description-text layer).
_DOMAIN_ALIASES: dict[str, str] = {"kg": "knowledge", "memory": "knowledge"}


def _domain_of(name: str) -> str:
    """The canonical GROUP_DIRECTORY domain for a tool name — `_provider_prefix`
    resolved through `_DOMAIN_ALIASES` (a no-op for every prefix that already equals
    its own domain name)."""
    prefix = _provider_prefix(name)
    return _DOMAIN_ALIASES.get(prefix, prefix)


def provider_availability(catalog_meta: dict) -> set[str]:
    """H10 — the set of provider prefixes the gateway reports as temporarily
    unavailable (partial catalog). Reads the catalog-level `_meta` from
    ``KnowledgeClient.get_catalog_meta()``.

    S-GATEWAY (C-GW) owns the exact key; we accept the most likely shapes
    (``unavailable_providers`` list / ``providers`` availability map) and return
    an empty set when none is present — so this never invents an outage.
    TODO(S-GATEWAY): freeze the key at COMPOSE A.
    """
    if not isinstance(catalog_meta, dict):
        return set()
    unavailable = catalog_meta.get("unavailable_providers")
    if isinstance(unavailable, (list, tuple, set)):
        return {str(p) for p in unavailable}
    providers = catalog_meta.get("providers")
    if isinstance(providers, dict):
        # {"book": {"available": false}, ...} or {"book": "down"}
        out: set[str] = set()
        for prov, state in providers.items():
            if isinstance(state, dict) and state.get("available") is False:
                out.add(str(prov))
            elif isinstance(state, str) and state.lower() in ("down", "unavailable"):
                out.add(str(prov))
        return out
    return set()


def find_tools_result(
    catalog: list[dict],
    intent: str,
    limit: int,
    *,
    exclude: set[str],
    catalog_meta: dict,
    group: str | None = None,
) -> tuple[dict, list[str]]:
    """Build the ``find_tools`` tool RESULT payload + the list of matched names
    to union into the active set (C-FT loop semantics).

    The payload distinguishes (H10): a genuinely empty result from one where the
    only plausible providers are *temporarily unavailable* — so the agent says
    "try again", never a false "I can't"."""
    matches, confident = search_catalog(catalog, intent, limit, exclude=exclude, group=group)
    unavailable = provider_availability(catalog_meta)
    payload: dict = {"tools": matches}
    if not matches:
        if unavailable:
            # H10: capability may exist but its provider is briefly down.
            payload["unavailable_providers"] = sorted(unavailable)
            payload["note"] = (
                "No matching tool is currently available. One or more services are "
                "temporarily unavailable — tell the user the capability exists but "
                "to try again shortly; do NOT say you can't do it."
            )
        else:
            payload["note"] = (
                "No tool matched. Reconsider the wording and search once more before "
                "telling the user this isn't supported."
            )
    elif not confident:
        payload["low_confidence"] = True
        payload["note"] = (
            "These are weak matches. If none fit, you may search once more with "
            "different wording."
        )
    matched_names = [m["name"] for m in matches]
    return payload, matched_names
