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
* ``ALWAYS_ON_CORE`` — the ≤10 tools advertised every universal ``/chat`` turn
  (the deterministic discovery pair ``tool_list``/``tool_load`` + ``find_tools`` + the
  generic frontend tools).
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

import json
import logging
import re
import time
from difflib import SequenceMatcher
from types import MappingProxyType

from loreweave_vecmath import cosine_similarity

from app.services.tool_liveness import tool_is_broken  # CD4 ship gate

logger = logging.getLogger(__name__)

# ── C-FT: the find_tools meta-tool ───────────────────────────────────────────

FIND_TOOLS_NAME = "find_tools"

# WS-1a (contracts.md C2) — the deterministic discovery pair that replaces mandatory
# find_tools semantic search. Advertised as core (see ALWAYS_ON_CORE_NAMES), listed FIRST.
TOOL_LIST_NAME = "tool_list"
TOOL_LOAD_NAME = "tool_load"

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
    # W10 worldbuilding — book-service's SECOND federated namespace (world_*, world_map_*).
    # A distinct group from "book" (prose): worlds are prose-less containers + reference
    # maps. `_domain_of` maps the `world_` prefix straight here (no _DOMAIN_ALIASES entry
    # needed — the prefix already equals the group name). Without this entry the tools
    # reach the raw catalog but are NOT enumerable by group and are excluded from "book".
    # Keep in lockstep with ai-gateway find-tools.ts GROUP_DIRECTORY.
    "world": "Worldbuilding containers + reference maps — world create/get/list/move, plus map/marker/region authoring (world_*, world_map_*).",
    # K23 (2026-07-23) — the CONSUMER-LOCAL tools (tool_list/tool_load, ui_*, propose_edit) had
    # no group, so `_domain_of` bucketed them under "tool"/"ui"/"propose" — names absent from
    # this directory and from CATEGORY_ENUM. They were SERVED but invisible to the discovery
    # pair: tool_list never listed them, tool_load said `not_found` (i.e. "no such tool").
    # Keep in lockstep with ai-gateway find-tools.ts GROUP_DIRECTORY.
    "meta": "The tools the assistant itself uses — tool discovery (tool_list, tool_load), browser navigation (ui_*), and the editor edit-proposal card (propose_edit).",
    "jobs": "Job status/cancel for any long-running operation.",
    "catalog": "Public catalog browsing (published books, discovery).",
    "registry": "Agent/tool registry administration.",
    "settings": "User/account settings and provider-model configuration.",
    # Track D CD5/C1: EXTERNAL retrieval (`web_search`, prefix `web_` → alias below).
    # Deliberately NOT folded into `knowledge`, which is the INTERNAL knowledge graph.
    "research": "External web research — search the open web for background facts (web_search). PAID.",
    # PlanForge tools federate under their own `plan_` prefix (composition-service's M4
    # federation contract), NOT `composition_` — a separate group so group="plan" actually
    # surfaces them (they used to be mis-claimed under "composition" above, which the
    # prefix-based filter could never honor).
    "plan": (
        "Novel planning workflow — PlanForge. THE SEQUENCE MATTERS: plan_propose_spec drafts a "
        "spec, but a proposal ALONE creates NOTHING the book can use. To actually lay out a story "
        "you MUST finish by calling plan_compile — that is the step that MATERIALISES the linked "
        "chapter/scene structure (the outline the manuscript hangs on). After a user asks you to "
        "plan or lay out their story: propose_spec → (refine with the user) → plan_compile. Do not "
        "stop at propose; a plan with no compiled structure is an unfinished plan. Also: "
        "plan_self_check, plan_interpret_feedback, plan_apply_revision, plan_review_checkpoint, "
        "plan_handoff_autofix, plan_validate."
    ),
}

# WS-1a (contracts.md C1) — the closed category enum for tool_list/tool_load: the
# GROUP_DIRECTORY domains + the "all" sentinel. Single-sourced here; the tool defs
# and the result builders both read it (no re-declaration).
CATEGORY_ENUM: list[str] = sorted(GROUP_DIRECTORY) + ["all"]

# Design item 1 (2026-07-07 discovery-hardening plan) reworded this description
# twice over, mirroring ai-gateway's find-tools.ts FIND_TOOLS_TOOL byte-for-byte
# in intent (not necessarily literal wording — the two engines are documented to
# rank/enumerate/cap IDENTICALLY, per the CAT-4 discipline already extended to
# this fix): (1) it now tells the caller about the enumeration affordance
# (`group` + no/empty `intent` lists everything in a domain — external audit #5,
# "no list-all-tools-in-a-domain affordance"); (2) it DROPS the old unconditional
# "if it returns nothing useful, you may try once more... before telling the user
# you can't" invitation — that unbounded retry bias is exactly what let one real
# session hit 40 find_tools iterations / 53.8s / a 0-length final answer (see the
# plan's Problem section). The retry-cap machinery below (FindToolsAttemptTracker)
# is what actually bounds it; the wording here just stops encouraging the failure
# mode in the first place.
FIND_TOOLS_TOOL: dict = {
    "type": "function",
    "function": {
        "name": FIND_TOOLS_NAME,
        "description": (
            "OPTIONAL (legacy) intent search for tools — PREFER `tool_list`/`tool_load`, "
            "which are deterministic and complete. Use `find_tools` only when you don't "
            "know which category fits and want to search by intent. Pass "
            "`group` (a tool domain) with `intent` omitted or empty to list EVERY "
            "tool in that domain, unranked — the fastest way to check whether a "
            "whole domain has what you need. With `intent` set, returns the "
            "best-matching tool names + descriptions; matched tools become "
            "callable next. If `group` is set and your query scores weak or empty "
            "against it, you automatically get the FULL domain list instead of a "
            "poor guess — no need to retry with different wording first. Without "
            "`group`, an empty/weak `intent` instead returns the tool-domain "
            "directory so you can pick one and search again scoped to it. If a "
            "second attempt on the same ask ALSO comes back empty or weak, stop "
            "searching and tell the user this isn't supported rather than "
            "guessing again."
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
                    "description": "Optional — scope the search to one tool domain from your tool-domain directory. Omit `intent` (or leave it blank) to list EVERY tool in this domain, unranked. Omit `group` entirely to search everything.",
                },
            },
            "required": ["intent"],
            "additionalProperties": False,
        },
        # C-TOOL — declared, not inferred. These are pure disclosure over the catalog:
        # they execute nothing and take no scope key. Without an explicit tier they
        # relied on tool_tier()'s silent "R" default — the exact hole the wire gates
        # exist to close, and the reason a federated catalog showed 3 untiered tools.
        "_meta": {"tier": "R", "scope": "none"},
    },
}


# WS-1a (contracts.md C2) — the deterministic discovery pair, advertised as core and FIRST
# (before find_tools). Mirror of ai-gateway's TOOL_LIST_TOOL / TOOL_LOAD_TOOL (find-tools.ts).
TOOL_LIST_TOOL: dict = {
    "type": "function",
    "function": {
        "name": TOOL_LIST_NAME,
        "description": (
            "List EVERY tool in a category (or \"all\"), complete and deterministic — the "
            "reliable way to see what you can do here. This is how you discover a tool that "
            "isn't already advertised: list the category, then call tool_load(name) to get a "
            "tool's exact arguments before using it. Returns {name, description, tier} per "
            "tool; deprecated tools are labeled with their replacement."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "category": {
                    "type": "string",
                    "enum": CATEGORY_ENUM,
                    "description": "A tool domain, or \"all\" for the whole catalog. Omit = all.",
                },
                "include_deprecated": {
                    # K22 (2026-07-23) — this said `default: True` / "Default true." while the
                    # HANDLER that actually runs (ai-gateway handleToolList) defaults it to
                    # FALSE, deliberately: "a browsing agent should see the CURRENT surface,
                    # not the shrunk-away legacy tools as noise (the book catalog was 16 active
                    # + 19 deprecated)" (spec 2026-07-22 review).
                    #
                    # So the model was told the opposite of what happens. It omits the arg
                    # expecting deprecated tools, gets only current ones, and concludes a tool
                    # it remembers by its OLD name no longer exists — on tool_list, which F17
                    # made the ONLY discovery surface, right after a unification renamed tools
                    # en masse. Advertised contract now matches executed behaviour.
                    "type": "boolean",
                    "description": (
                        "Include deprecated tools (shown labeled with their replacement). "
                        "Default false — omit to see only the CURRENT tools; set true only "
                        "when migrating off an old tool name."
                    ),
                    "default": False,
                },
            },
            "additionalProperties": False,
        },
        # C-TOOL — declared, not inferred. These are pure disclosure over the catalog:
        # they execute nothing and take no scope key. Without an explicit tier they
        # relied on tool_tier()'s silent "R" default — the exact hole the wire gates
        # exist to close, and the reason a federated catalog showed 3 untiered tools.
        "_meta": {"tier": "R", "scope": "none"},
    },
}

TOOL_LOAD_TOOL: dict = {
    "type": "function",
    "function": {
        "name": TOOL_LOAD_NAME,
        "description": (
            "Load the exact input schema(s) for one or more tools — by `name`, a list of `names`, "
            "or every tool in a `category` — so you can call them correctly. Loading makes them "
            "callable; it does NOT run anything. Use it after tool_list to pick tools by name."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "A single tool name."},
                "names": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Several tool names.",
                },
                "category": {
                    "type": "string",
                    "enum": CATEGORY_ENUM,
                    "description": "Load every tool in this category.",
                },
            },
            "additionalProperties": False,
        },
        # C-TOOL — declared, not inferred. These are pure disclosure over the catalog:
        # they execute nothing and take no scope key. Without an explicit tier they
        # relied on tool_tier()'s silent "R" default — the exact hole the wire gates
        # exist to close, and the reason a federated catalog showed 3 untiered tools.
        "_meta": {"tier": "R", "scope": "none"},
    },
}


# ── C-FT: the always-on core (advertised on every discovery turn, ≤10) ─────────
# WS-1a bumped the ceiling 8→10: the deterministic discovery pair tool_list/tool_load
# joined find_tools as core (the primary "what can I do here" path). Still small — the
# whole point of core is a tiny always-present set; domain tools stay lazy via discovery.
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
    # F17 (2026-07-20): the DETERMINISTIC discovery pair is the ONLY discovery surface now.
    # find_tools was retired FROM THE LLM's view — it is semantic top-K, so it structurally
    # CANNOT surface a tool the agent needs when that tool falls outside the K matches (dogfood
    # F14: the agent never reached book_list_chapters). tool_list (see every tool in a domain) +
    # tool_load (load the exact one) have no such blind spot. (The find_tools handler stays
    # dispatchable for any legacy caller, but is no longer advertised — never hot-seeded, never
    # discoverable — so the model is never steered into the top-K trap.)
    TOOL_LIST_NAME,
    TOOL_LOAD_NAME,
    # ui_navigate / ui_open_book / ui_show_panel / ui_watch_job REMOVED (2026-07-27).
    #
    # The agent GUI-control surface was deprecated in d389a3022 ("GUI control is user- and
    # logic-driven; agent-driven nav only cost tokens"). That commit removed their SCHEMAS
    # (`generic_frontend_tool_def` returns None for all four) and the ai-gateway handlers —
    # but left the names here, which was not harmless:
    #
    #   `TestSkillClaimsLint` EXEMPTS anything in ALWAYS_ON_CORE_NAMES from its reachability
    #   check, on the reasoning that an always-on tool can never be an unreachable claim. Once
    #   these stopped being always-on, that exemption became a hole — and four skills went on
    #   instructing the agent to call `ui_watch_job` / `ui_navigate`, tools that no longer
    #   reach the wire, with the lint waving them through.
    #
    # A deprecated tool must disappear from EVERY list that describes the live surface, not
    # just the one that emits schemas.
    # propose_record_edit REMOVED (auto-gate M5) — the generic record diff card is retired;
    # each domain edits via its own natural direct-write tool (audit-confirmed vestigial).
    #
    # confirm_action REMOVED 2026-09-03 (V7/DQ-V9). It is NOT retired — it moved to ai-gateway as
    # a consumer-local DIRECTIVE tool, so it now arrives through the federated catalogue like any
    # other tool and no longer needs naming here. It stayed in this list for weeks resolving via
    # `catalog_index.get(name) or generic_frontend_tool_def(name)`; because it was absent from the
    # catalogue the FALLBACK always fired, which is precisely how a chat-service-local schema
    # reached the model on every turn, on every surface.
    # Track D CD5 — `web_search` is fundamental: grounding an answer in the open web is a
    # base capability, not a glossary errand, so it must not cost a find_tools round-trip.
    # It is the ONLY backend (federated) tool in this set, so it resolves from the CATALOG
    # def, not `generic_frontend_tool_def` — which returns None for it, meaning a degraded
    # gateway simply omits it rather than advertising a fabricated schema.
    # It is PAID: advertising it is safe because chat's spend gate asks for consent at CALL
    # time, independently of tier and of permission mode.
    "web_search",
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
# SAME reason a book-bound skill's own domain is (below): a weak model asked "where is
# X at chapter N" / "the firm the character works for" reaches for memory_search
# (semantic, empty without ingested passages) and then PUNTS — "paste the manuscript" —
# instead of discovering the lexical search it's standing on. Measured 2026-07-05 on the
# Dracula eval: after story_search was un-dropped from federation the agent STILL never
# found it via find_tools (ranked 7th / missed), so it must be seeded. It needs no
# embeddings/KG (the exact leg is book-service full-text), so it is the
# grounding-of-last-resort for ANY book — including ones with no glossary/KG built. No
# skill declares "story" in its own `hot_domains` (it's not any one skill's tool family),
# so it is unioned in here explicitly rather than derived — the one deliberate
# surface-level exception to "hot = what an injected skill names."
_ALWAYS_HOT_ON_BOOK_BOUND_SURFACE: frozenset[str] = frozenset({"story"})


def surface_hot_domains(
    *,
    editor: bool = False,
    book_scoped: bool = False,
    studio: bool = False,
    permission_mode: str = "write",
) -> set[str]:
    """The domain prefixes whose tools are HOT (advertised every turn) for a
    surface — Part D of docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-
    standard.md (the generic derivation promised in that spec's Part A design
    text and mandated by its §8b.9 edge case).

    Previously three hand-authored constants (`_BOOK_SCOPED_HOT_DOMAINS`,
    `_STUDIO_HOT_DOMAINS`, `PLAN_HOT_DOMAINS`) had to independently track which
    domain(s) each surface's DEFAULT-injected skill(s) name directly — the exact
    shape that already caused one miss (plan_forge shipped, "plan" wasn't added to
    any of them). Now derived from a SINGLE source of truth: whichever skills
    `resolve_skills_to_inject` would inject BY DEFAULT (empty ``enabled_skills`` —
    the surface's legacy/auto behavior, never the curated pins) on this surface,
    unioned with each one's declared `SkillDef.hot_domains`, plus `story` (the one
    surface-level-not-skill-owned exception, see above).

    Deliberate, sign-off'd behavior change (2026-07-07): `knowledge_skill` already
    auto-injects on EVERY non-admin surface (including universal/chat) and always
    honestly declared `hot_domains={"knowledge"}` — but until this refactor that
    declaration was inert (no hand-authored constant ever included it). This
    function now honors it, so "knowledge" becomes hot EVERYWHERE knowledge_skill
    is injected, including the universal/chat surface, which previously hot-seeded
    nothing. This finally closes `D-SKILL-HOTDOMAIN-RUNTIME-WIRING` — see the
    token-budget regression test proving the shared `HOT_SEED_TOKEN_BUDGET` ceiling
    still holds with the extra domain in play (`tool_surface.py`'s existing
    `budget_names_by_tokens` gracefully truncates a wider candidate set to the same
    token cap, it does not widen the cap itself)."""
    from app.services.skill_registry import SYSTEM_SKILLS, resolve_skills_to_inject

    codes = resolve_skills_to_inject(
        enabled_skills=[],
        stream_format="agui",
        disable_tools=False,
        tool_calling_enabled=True,
        editor=editor,
        book_scoped=book_scoped,
        admin=False,
        permission_mode=permission_mode,
        studio=studio,
    )
    domains: set[str] = set()
    for code in codes:
        skill = SYSTEM_SKILLS.get(code)
        if skill:
            domains |= set(skill.hot_domains)
    if book_scoped or editor or studio:
        domains |= set(_ALWAYS_HOT_ON_BOOK_BOUND_SURFACE)
    return domains


# N5a (dogfood 2026-07-18 F3) — high-impact, book-WIDE tools that must NEVER ride the domain
# hot-seed. Keeping `glossary_adopt_standards` advertised let the co-writer proactively "set up
# the world" on a plain "write a chapter 1" turn and block the newcomer with a confirm they never
# asked for. A prompt guard-line AND removing it from ALWAYS_HOT_WRITES both FAILED live QC — the
# tool was still budget-hot (small schema fit the seed) and called directly (no find_tools). So it
# joins the never-hot-seed set: fully reachable via find_tools/tool_load when the writer EXPLICITLY
# asks to set up their world (the lean glossary skill instructs exactly that), just not advertised
# by default. Same "not on the wire by default" mechanism as CAT-4's legacy exclusion.
DISCOVER_ONLY_HIGH_IMPACT: frozenset[str] = frozenset({
    "glossary_adopt_standards",
})


# N5a-FULL (dogfood 2026-07-19) — the CAPABILITY floor for the "request-scoped autonomy"
# control model. These are the high-impact, book-WIDE ontology-BUILDING tools — "set up /
# reshape the whole world," not "add the character the writer just named." Keeping them in the
# per-turn catalog let the co-writer proactively rebuild a newcomer's ontology on a plain
# "write a chapter 1" turn: three prior fixes failed because hot-seed + find_tools exclusions
# don't cover `tool_load`, which loads ANY catalog name. So these are filtered out of the turn
# catalog ITSELF (the one object all three reach-paths read) UNLESS the turn is world-setup
# intent — signalled by `glossary_shaping` being injected (pinned OR the intent router matched
# the message to its "set up the book's world ontology" description). Guidance and capability
# then move as ONE signal. Single-entity / single-kind / read tools stay ALWAYS available
# (request-scoped: "add Kaila", "add a vampire kind" are the writer's direct asks).
INTENT_GATED_SETUP_TOOLS: frozenset[str] = frozenset({
    "glossary_adopt_standards",   # adopt genre/kind STANDARDS (the confirmed over-reach)
    "glossary_propose_kinds",     # batch-propose MANY kinds at once (build an ontology)
    "glossary_plan",              # planner: propose a WHOLE ontology behind one card
    "glossary_propose_batch",     # mixed batch ontology ops
    "glossary_book_sync_apply",   # bulk-reconcile adopted standards
})

# The intent skill whose injection means "this turn is world-setup" (pinned OR router-matched).
SETUP_INTENT_SKILL = "glossary_shaping"


def _final_live_successor(name: str, by_name: dict[str, dict]) -> str | None:
    """The first NON-legacy tool reached by following ``superseded_by`` from ``name``.

    A chain, not a single hop, because the catalogue has them: ``composition_get_prose`` ->
    ``book_get_chapter`` -> ``book_read``, where the middle tool is itself legacy and is being
    dropped on the same pass. A one-hop resolve would hand the vocabulary to a tool that is
    about to be deleted, which loses it just as completely as not moving it at all.

    Returns None when the chain dead-ends: no ``superseded_by``, a name absent from this
    catalogue, or a cycle. 31 legacy tools are in that position (measured 2026-08-28) and this
    deliberately invents nothing for them.
    """
    seen = {name}
    cur = tool_superseded_by(by_name.get(name) or {})
    while cur and cur in by_name and cur not in seen:
        if not is_legacy_tool(by_name[cur]):
            return cur
        seen.add(cur)
        cur = tool_superseded_by(by_name[cur])
    return None


def _inherit_superseded_vocabulary(
    kept: list[dict], by_name: dict[str, dict], dropped: list[str],
) -> list[dict]:
    """Move each dropped legacy tool's declared synonyms onto the live successor.

    See ``drop_superseded_tools``' docstring for why this is here rather than in
    ``answerable_tools``: R2's union runs over a catalogue this function has already stripped,
    so the union is inert exactly where it was written to fire.

    Non-mutating — a new dict is built for each affected tool. The catalogue is cached per-user
    in ``knowledge_client`` and shared across turns, so editing a def in place would leak one
    turn's inheritance into every later reader of the same cached object.
    """
    inherited: dict[str, list[str]] = {}
    for legacy in dropped:
        succ = _final_live_successor(legacy, by_name)
        if not succ:
            continue
        for syn in (tool_meta(by_name[legacy]).get("synonyms") or []):
            if isinstance(syn, str) and syn:
                inherited.setdefault(succ, []).append(syn)
    if not inherited:
        return kept
    out: list[dict] = []
    for td in kept:
        extra = inherited.get(tool_name(td))
        if not extra:
            out.append(td)
            continue
        fn = td.get("function") or {}
        meta = dict(tool_meta(td))
        have = list(meta.get("synonyms") or [])
        meta["synonyms"] = have + [s for s in extra if s not in have]
        out.append({**td, "function": {**fn, "_meta": meta}})
    return out


def drop_superseded_tools(
    catalog: list[dict],
    pinned: "set[str] | frozenset[str] | None" = None,
) -> tuple[list[dict], list[str]]:
    """Drop EVERY legacy tool from a TURN CATALOG, transferring its synonyms to the successor.

    (Summary line corrected 2026-09-03. It read "…when its replacement is on the same wire",
    which is the pre-2026-08-25 NARROW rule — see the superseded block below. The first line is
    what every IDE hover, `help()` and doc extractor shows, so it was the one sentence about this
    function most readers ever saw, and it stated the opposite of the loop beneath it. The file
    already names that exact cost two paragraphs down.)

    🔴 THE THIRD REACH-PATH. CAT-4's own comment states the invariant — "A legacy tool must
    never be discoverable: excluded from search_catalog() and from every domain hot-seed" —
    and both of those do exclude it. The turn catalog that is actually ADVERTISED to the model
    did not, so a superseded tool sat on the wire beside the tool that replaced it.

    MEASURED 2026-08-14, batch 17: 5 of the 54 distinct tools advertised across the batch were
    legacy, and every one was the direct predecessor of a tool under test —

        composition_canon_rule_delete      -> composition_canon_rule_edit
        composition_authoring_run_pause    -> composition_authoring_run_review
        composition_archive_derivative     -> composition_derivative_edit
        composition_divergence_spec_update -> composition_derivative_edit
        book_list_chapters                 -> book_list

    That is not coincidence: the answerability matcher pulls the sibling in because it shares
    the user's vocabulary with its replacement. And the predecessor WINS, because it is the
    more specific name for the exact ask — the model called the legacy tool on 3 of 5
    scenarios, so the unified tool under test scored 0/5 while nothing was actually wrong.

    🔴 SUPERSEDED 2026-08-25 — THE PARAGRAPH BELOW DESCRIBES THE OLD RULE. It is kept
    because the reasoning still explains what the narrow rule was FOR, but it is no longer
    what this function does: the loop below drops EVERY legacy tool, replacement or not.
    A docstring that states the opposite of the code beneath it is worse than none — this
    one was read, believed, and quoted into a defect report before the code was checked.

    THE RULE WAS DELIBERATELY NARROWER THAN "DROP EVERY LEGACY TOOL". Of the 117 legacy
    tools, 31 name NO ``superseded_by`` — including ``book_create``, ``book_chapter_publish``
    and ``book_chapter_delete``. Dropping those would delete reach the platform still needs
    with nothing to redirect to. So a tool is dropped ONLY when its named replacement is
    present in the same catalog, which makes the swap capability-preserving by construction:
    whatever the caller wanted, the tool that does it is right there. All 86 such tools were
    verified to have their replacement in the live catalog (0 dangling ``superseded_by``).

    ``pinned`` — the session's ``pinned_legacy_tools`` (CAT-4 Part D). A user who deliberately
    pinned a legacy tool keeps it; that column, its closed-set validator and its picker feed
    existed with no consumer on the turn path, because nothing was filtering these out for it
    to re-admit.

    🔴 DROPPING A DECLARATION MUST NOT DROP ITS VOCABULARY — D-THE-MODEL-ASKS-INSTEAD-OF-
    RAISING-THE-CARD-IT-HAS, owner 2026-08-28 (DQ-T57: "promote the replacement onto the wire").

    ``answerable_tools`` carries a rule it calls R2: *whatever phrasing reaches A must also be
    able to reach the tool that REPLACED A*, because 59 of 62 superseded pairs orphan at least
    one phrasing — the deprecated tool declares the words a user actually says and its successor
    declares the unified ones. R2 implements that as a UNION over the catalog it is handed: if A
    matched, add A's ``superseded_by``.

    The 2026-08-25 widening above silently disabled it. R2's union needs A to be IN the catalog
    it reads, and per-pass answerability reads ``discovery_catalog`` — i.e. THIS function's
    output, with every legacy tool already removed. So the union had nothing left to union from,
    at exactly the pairs it was written for.

    MEASURED 2026-08-28 against the live 316-tool catalogue, prompt "Undo delete rule — I
    archived a canon rule by mistake, please restore it.":

        answerable over the FULL catalog       -> {composition_canon_rule_restore,
                                                   composition_canon_rule_edit}   (R2 fired)
        answerable over this function's OUTPUT -> {}                              (R2 inert)

    and live at K=5 the model found the archived rule, then asked the author to restore it in
    PROSE rather than raising the Tier-A confirm card — it had no card to raise. The successor
    ``composition_canon_rule_edit`` does declare "restore canon rule", but the author wrote
    "please restore it"; the phrasing that actually matched, "undo delete rule", belonged to the
    tool this function had just deleted.

    So the fix is here, in the function that DESTROYS the information: when a legacy tool is
    dropped, its declared synonyms transfer to the live successor that replaced it (following a
    chain of ``superseded_by`` hops to the first non-legacy tool). One chokepoint, and it repairs
    every reader of the narrowed catalog at once — R1 answerability, ``find_tools`` recall, the
    declaration arm, the reads-only mood check — rather than R1 alone.

    Free on the wire: ``_meta`` is consumer-only and ``strip_tool_meta`` removes it before the
    provider request, so an inherited synonym costs zero tokens.

    🔴 THE ALTERNATIVE WAS BUILT FIRST, MEASURED, AND REVERTED. The first attempt PROMOTED the
    replacement's definition into this function's output. It passed 20 unit tests and did nothing
    live: the promotion lands in ``discovery_catalog``, which is only a CANDIDATE pool — domain
    selection runs afterwards and withheld ``composition_canon_rule_edit`` at
    ``domain_not_selected`` on the very run under test. It also could not fire for this instance
    at all, because the replacement was already present in the pool (``replacement in kept_names``
    -> skip), which is why the server's own withheld record still showed the un-promoted reason.
    A mechanism that fires and cannot reach the wire is worse than none.

    MEASURED cost/recall of what shipped, over 1,917 distinct real user messages from the live
    corpus: mean 0.069 extra tools forced per turn (median 0, max 3), 115 turns of 1,917 (6.0%)
    gain at least one, across 7 distinct successors — dominated by the two pairs R2's own comment
    names, ``book_get``->``book_read`` and ``book_scene_list``->``book_list``. The rejected
    unconditional-promotion variant was ~27 extra tools per turn.

    DOES NOT COVER: 31 legacy tools name no resolvable successor (``book_create``,
    ``book_chapter_publish``, ``composition_publish`` — whose chain ends at a legacy tool with no
    ``superseded_by``); their vocabulary is genuinely lost when they are dropped, and nothing here
    invents a destination for it. Nor does inheritance put the successor on the wire by itself —
    it makes the successor ANSWERABLE, and R1's forcing at the advertise chokepoint is what
    carries it there; a successor absent from the turn catalog entirely (intent-gated) still
    cannot be reached.

    Returns ``(kept, dropped_names)`` so the caller can record the withholding rather than
    narrow the surface silently. A promoted replacement is counted in ``kept``, not
    ``dropped`` — it was never withheld.
    """
    pinned = set(pinned or ())
    _by_name = {tool_name(td): td for td in catalog}
    kept: list[dict] = []
    dropped: list[str] = []
    for td in catalog:
        name = tool_name(td)
        # 2026-08-25 — WIDENED TO EVERY LEGACY TOOL, on the owner's standing decision that a
        # legacy tool is a DEAD tool. The old rule dropped one only when its named
        # replacement happened to be on the same wire, which left 31 legacy tools with no
        # `superseded_by` advertised forever and 86 more advertised whenever their
        # replacement missed the turn. Traffic to a dead tool is rot, not a requirement:
        # find_tools is what that looks like when it is left to run.
        #   ...and replacement and replacement in present   <- the old, narrower condition
        if (
            name
            and name not in pinned
            and is_legacy_tool(td)
        ):
            dropped.append(name)
            continue
        kept.append(td)
    # The vocabulary the drop would otherwise delete, moved to whoever inherited the capability.
    # AFTER the drop loop, so a successor that is ITSELF being dropped is never a destination.
    kept = _inherit_superseded_vocabulary(kept, _by_name, dropped)
    if dropped:
        # Registered, not silently narrowed — the same reason filter_intent_gated_setup_tools
        # registers its own drops: "the runtime chose not to offer this and here is why" must
        # stay distinguishable from "this tool does not exist". Recorded HERE rather than at the
        # call site so a future caller cannot forget it.
        from app.services.instrument import record_surface_withheld
        for _n in dropped:
            _succ = _final_live_successor(_n, _by_name)
            if _succ:
                reason = (
                    f"superseded by {_succ}, which now also answers to this tool's declared "
                    "phrasing"
                )
            else:
                reason = (
                    f"superseded by {tool_superseded_by(_by_name[_n])}"
                    if tool_superseded_by(_by_name[_n])
                    else "marked visibility=legacy with no replacement named"
                ) + " — legacy tools are not advertised; pin it via pinned_legacy_tools to keep it"
            record_surface_withheld(_n, stage="superseded", reason=reason)
    return kept, dropped


def _declaration_named_setup_tools(
    catalog: list[dict], request_text: str | None, gated: "set[str] | frozenset[str]",
) -> set[str]:
    """The gated tools whose OWN declared synonyms answer this request.

    🔴 THE MATCH IS RUN AGAINST THE GATED TOOLS ALONE, NOT THE WHOLE CATALOGUE, and that is
    not an optimisation. ``answerable_tools`` ranks its matches and caps the result at
    ``ANSWERABLE_MAX``; run over 300-odd tools, a gated tool that genuinely answers the
    request could be crowded out of the cap by unrelated ones and the arm would open only
    sometimes. Handing it a catalogue of just the gated tools asks the question this gate
    actually has — *does the request use THIS tool's declared vocabulary* — and makes the
    answer independent of what else happens to be in the catalogue.

    Imported inside the function: ``tool_surface`` imports from this module, so a top-level
    import would be a cycle. The platform's own matcher is used rather than reimplemented —
    a second copy of the normalisation would drift from the first, and the first is already
    the thing the answerability contract is written against.
    """
    if not request_text or not gated:
        return set()
    gated_defs = [td for td in catalog if tool_name(td) in gated]
    if not gated_defs:
        return set()
    from app.services.tool_surface import answerable_tools

    return {n for n in answerable_tools(request_text, gated_defs) if n in gated}


def filter_intent_gated_setup_tools(
    catalog: list[dict],
    injected_skill_codes: list[str] | set[str],
    rail_step_tools: "set[str] | frozenset[str] | None" = None,
    request_text: str | None = None,
) -> list[dict]:
    """Drop the high-impact world-setup tools from a turn catalog UNLESS the turn is
    world-setup intent (`glossary_shaping` injected). Applied at catalog assembly so the
    tool is simultaneously un-seeded, un-findable (find_tools), AND un-loadable (tool_load)
    — closing the tool_load leak that per-search-function filters missed. Returns the catalog
    unchanged on a setup turn; returns a filtered copy otherwise. N5a-FULL.

    ``rail_step_tools`` — the step tools of a workflow rail PINNED for this turn. They are
    exempt, and the exemption is load-bearing rather than a loosening:

    A pinned rail is an authored, ordered recipe rendered into the prompt BY TOOL NAME. When
    this filter removed a tool the rail names, the two halves of the same intent signal came
    apart — the guidance said "call ``glossary_adopt_standards``" while the capability floor
    had made that name unseedable, unfindable AND unloadable. The model then did the only
    thing left: it reasoned correctly, reached for the right tool, could not have it, and
    retried forever (measured on the Mị Đế dogfood — 40,597 characters of one repeated
    paragraph before the author hit Stop). The comment above this gate already states the
    principle it needs — *"guidance and capability move as ONE signal"* — a pinned rail IS
    that signal, so honour it here too rather than only via ``glossary_shaping``.

    Scope stays tight: only the steps of a rail actually pinned this turn are exempt, so an
    unrelated "write chapter 1" turn still cannot reach these tools — which is the over-reach
    N5a-FULL exists to stop.

    ``request_text`` — DQ-T31's DECLARATION ARM (owner decision, 2026-08-27). A gated tool
    whose OWN declared synonyms answer this request is exempt, and only that tool.

    🔴 THE GATE OPENED ON VOCABULARY AND NOT ON WHAT WAS ASKED FOR, AND R1 COULD NOT REACH IN.
    ``_is_world_setup_intent`` is a substring match over a hand-written marker list, so the
    gate stayed SHUT on requests that named a gated tool outright — measured on
    ``glossary_book_sync_apply`` with the prompt *"Take the upstream changes — apply the
    standard updates to this book"*, which is two of its declared synonyms VERBATIM and
    against the live catalogue makes it the ONLY answerable tool, with no competitor. It
    surfaced 0/2 and was called 0/2.

    R1 answerability promises such a tool the wire "whatever the budget, the domain selection
    or the rail decided", and for a gated tool it cannot deliver — not through any fault of
    R1's. The one-off build is handed the UNFILTERED catalog and R1 does force the tool in
    there; the PER-PASS build is handed the catalog AFTER this filter and REPLACES that list
    on the first pass. So the rescue lands in a list that is immediately discarded, and every
    pass the model actually sees is built from a catalogue the tool was removed from. The only
    place that can be fixed is here, before the removal.

    THIS IS THE SAME SHAPE AS ``rail_step_tools`` AND IS SCOPED THE SAME WAY. A rail naming a
    tool is a signal that this turn is about it; a request using the tool's own declared words
    is the same signal from the other direction, and *"guidance and capability move as ONE
    signal"* applies to both. So the exemption is per-TOOL, never per-turn: matching
    ``glossary_book_sync_apply`` does not un-gate the other four, which is what widening the
    marker list would have done.

    AND IT DELIBERATELY DOES NOT WIDEN THE MARKERS. The other half of this gate's defect is a
    false POSITIVE — ``codex`` is a marker, so *"draft the prose for 'Chapter I — The Ember
    Codex'"* opens the gate on a pure prose turn (the gate fires on 11 of 186 corpus prompts,
    and at least one is that). A longer marker list fixes the shut side by enlarging the open
    side. A declaration match cannot: a tool's synonyms are its author's statement about what
    it is for, reviewable in the declaration, and matching them is evidence about THIS tool
    rather than a guess about the turn."""
    if SETUP_INTENT_SKILL in injected_skill_codes:
        return catalog
    _exempt = INTENT_GATED_SETUP_TOOLS - set(rail_step_tools or ())
    _exempt -= _declaration_named_setup_tools(catalog, request_text, _exempt)
    # P1 · THE SEVENTH FRAME, and the last one upstream. This drops tools at CATALOG ASSEMBLY —
    # before domain selection, before the hot seed, before the advertise loop, i.e. before every
    # stage instrumented so far. A verifier's accounting landed on exactly this set twice: the four
    # in neither bucket are `INTENT_GATED_SETUP_TOOLS` minus `glossary_adopt_standards`, which a
    # rail exempted. `catalog_miss` could never see them, because they ARE in the catalog index —
    # they are removed from the catalog handed to it.
    #
    # A narrowing this early is the easiest to mistake for "not a candidate". It is a candidate: the
    # gate exists precisely because these tools would otherwise be offered, and one injected skill
    # makes them appear. Registering it is what separates "the runtime chose not to offer this and
    # here is why" from "this tool does not exist", which is the distinction P1 is entirely about.
    _dropped = sorted(n for n in (tool_name(td) for td in catalog) if n in _exempt)
    if _dropped:
        from app.services.instrument import record_surface_withheld
        for _n in _dropped:
            record_surface_withheld(
                _n, stage="intent_gate",
                reason="world-setup tool withheld unless the turn has world-setup intent "
                       "(inject the glossary_shaping skill, or name it in a rail step)",
            )
    return [td for td in catalog if tool_name(td) not in _exempt]


def hot_tool_names(catalog: list[dict], domains: set[str]) -> set[str]:
    """The catalog tool names whose domain prefix is in ``domains`` — the set to
    seed into the discovery active-set so they're advertised on the first pass.
    Empty ``domains`` → empty set (universal surface: nothing pre-seeded).
    CAT-4: a `legacy`-tagged tool is NEVER hot-seeded, even when its domain is —
    the whole point of tagging it legacy is that it stops riding the wire by
    default; a domain hot-seed that ignored this would silently defeat CAT-4.
    N5a: `DISCOVER_ONLY_HIGH_IMPACT` tools are excluded for the same reason (kept
    off the default wire; reachable via find_tools when explicitly asked)."""
    if not domains:
        return set()
    out: set[str] = set()
    for td in catalog:
        name = tool_name(td)
        if (name and _domain_of(name) in domains and not is_legacy_tool(td)
                and name not in DISCOVER_ONLY_HIGH_IMPACT):
            out.add(name)
    return out


def group_directory_text() -> str:
    """Render GROUP_DIRECTORY as the plain-text block injected into a surface's
    system prompt alongside ALWAYS_ON_CORE. Deterministic order (sorted by key)."""
    lines = [f"- {name}: {desc}" for name, desc in sorted(GROUP_DIRECTORY.items())]
    return "Tool domains (call tool_list with category=<name> to see every tool in one):\n" + "\n".join(lines)


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


#: C-1 · **the lane, as DECLARED data.** `_meta.tier` is set by the provider at registration and
#: federated verbatim; this map is the only place a tier becomes a lane.
LANES: tuple[str, ...] = ("read", "action", "write", "system")
_LANE_BY_TIER = MappingProxyType({"R": "read", "A": "action", "W": "write", "S": "system"})


def declared_lane(tool_def: dict) -> str | None:
    """CP-4.d · C-1's *"lane is data at registration, never inferred from a name"* — the read half.

    🔴 **THIS DELIBERATELY DOES NOT REUSE `tool_tier`, AND THE REASON IS ITS DEFAULT.** That function
    answers *"may this auto-commit a write?"*, where an unknown tier returning `"R"` is the fail-SAFE
    answer. The ranking asks the opposite question — *"does this belong in the always-advertised hot
    set?"* — and there the same default is fail-OPEN: an untiered tool would be promoted into the
    safe read-first set on the strength of a value nobody declared. One constant cannot be the
    conservative answer to two questions that point in opposite directions.

    So this returns `None` for an undeclared tier rather than guessing, and the caller sorts an
    undeclared lane with the writes. **Measured on the live catalogue: 315/315 tools declare a tier**
    (R=102, W=60, A=153), so nothing legitimate is demoted today — the `None` arm exists so that a
    provider federating an untiered tool tomorrow is visible instead of silently privileged.
    """
    return _LANE_BY_TIER.get(tool_meta(tool_def).get("tier"))


def tool_async(tool_def: dict) -> bool:
    """C-TOOL `_meta.async` — True when a tool STARTS a background job (queued, not
    done on return). The durable async-honesty signal the workflow step-runner reads
    from the catalog (vs. the tool-name heuristic). Absent ⇒ False."""
    return bool(tool_meta(tool_def).get("async"))


def tool_paid(tool_def: dict) -> bool:
    """Track D CD1 `_meta.paid` — True when CALLING this tool spends real money.

    ORTHOGONAL to `tier`: spend governs money, tier governs mutation. A paid READ
    (e.g. `web_search`) stays tier "R" and remains callable in `ask` mode, but must
    clear the SPEND gate. Never coerce a paid tool to tier A/W just because it costs.
    Absent ⇒ False (a tool that doesn't declare a cost is assumed free)."""
    return bool(tool_meta(tool_def).get("paid"))


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


def tool_superseded_by(tool_def: dict) -> str | None:
    """C-TOOL `_meta.superseded_by` — the replacement a deprecated tool points at,
    so ``tool_list`` can name it instead of silently dropping the deprecated one."""
    sb = tool_meta(tool_def).get("superseded_by")
    return sb if isinstance(sb, str) and sb else None


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
# WS-0 (contracts.md C1): `lore_enrichment_auto_enrich` (prefix `lore`) is the one orphan tool with
# no GROUP_DIRECTORY home — fold it into `glossary` (lore-enrichment is entity-enrichment, glossary's
# derived layer) rather than mint a new category. Keep in lockstep with ai-gateway's DOMAIN_ALIASES.
# Track D: `web_search` (prefix `web`) → the `research` group (EXTERNAL retrieval, not the
# internal KG). Keep in lockstep with ai-gateway's DOMAIN_ALIASES.
_DOMAIN_ALIASES: dict[str, str] = {
    "kg": "knowledge",
    "memory": "knowledge",
    "lore": "glossary",
    "web": "research",
    # K23 — the consumer-local trio (see the "meta" entry in GROUP_DIRECTORY).
    "tool": "meta",
    "ui": "meta",
    "propose": "meta",
}


def _domain_of(name: str) -> str:
    """The canonical GROUP_DIRECTORY domain for a tool name — `_provider_prefix`
    resolved through `_DOMAIN_ALIASES` (a no-op for every prefix that already equals
    its own domain name)."""
    prefix = _provider_prefix(name)
    return _DOMAIN_ALIASES.get(prefix, prefix)


# Discovery/write-back tools that are ALWAYS core — calling one says nothing about
# which DOMAIN the conversation is working in, so they never make a domain sticky.
_STICKY_DOMAIN_IGNORE: frozenset[str] = frozenset({
    FIND_TOOLS_NAME, TOOL_LIST_NAME, TOOL_LOAD_NAME,
    "confirm_action", "web_search",
    "ui_navigate", "ui_open_book", "ui_show_panel", "ui_watch_job",
    "workflow_list", "workflow_load", "load_skill", "run_subagent",
})


def engaged_domains_from_tool_calls(tool_calls_rows) -> set[str]:
    """The set of tool DOMAINS the recent conversation has ACTIVELY called into.

    D-DOMAIN-HOTSET-NOT-STICKY (dogfood 2026-07-21): auto mode recomputes the hot
    seed from the CURRENT message ONLY and forgets tools the agent discovered on a
    prior turn (find_tools/tool_load accumulations are not re-advertised in auto —
    tool_surface line ~453). So on a low-signal follow-up ("Option 3, go with that")
    the model can no longer see the `book` domain it used two turns ago: it wanders,
    or — worse, observed live — HALLUCINATES success ("I've prepared the update…")
    with no tool call at all. Re-seeding the domains recently engaged keeps the
    conversation's working domain hot across turns.

    Purely derived from the persisted `chat_messages.tool_calls` record — no new
    column, no write path — and it DECAYS naturally: once the lookback window no
    longer contains a domain's call, it stops being seeded. Each row is the server's
    executed-call record: a jsonb list of ``{iteration, tool, args, ok, …}`` (see
    `app/db/tool_call_history.py`). A row may arrive already-parsed (list) or as a raw
    jsonb string (asyncpg with no codec) — both are tolerated. Engagement is by INTENT,
    so a call is counted whether or not it succeeded (``ok``): a book edit that 400'd
    still means the writer is working in the book domain and wants it hot next turn.
    """
    domains: set[str] = set()
    for raw in tool_calls_rows or []:
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except (TypeError, ValueError):
                continue
        if not isinstance(raw, list):
            continue
        for call in raw:
            if not isinstance(call, dict):
                continue
            name = call.get("tool")
            if not name or not isinstance(name, str) or name in _STICKY_DOMAIN_IGNORE:
                continue
            domains.add(_domain_of(name))
    return domains


# ── Design item 1 — true per-domain enumeration (external audit #1/#5) ───────
# `search_catalog("")` always scores 0 (empty intent_tokens), so a caller could
# never tell "this domain truly has nothing matching" from "my wording didn't
# overlap enough tokens." Mirrors ai-gateway's `enumerateGroup` (find-tools.ts)
# — keep the two in lockstep, same discipline as GROUP_DIRECTORY/_domain_of.


def enumerate_group(
    catalog: list[dict],
    group: str,
    *,
    exclude: set[str] | None = None,
) -> list[dict]:
    """Return EVERY non-legacy tool in ``group``, UNRANKED (catalog order — no
    score, no sort; a sort would itself be an implicit rank) and UNFILTERED by
    ``INCLUSION_FLOOR``/``CONFIDENCE_THRESHOLD`` — mirrors what GROUP_DIRECTORY
    already does one level up (domain-level enumeration). CAT-4 still applies:
    a legacy-tagged tool is excluded from enumeration exactly like it is from
    a ranked search."""
    exclude = exclude or set()
    out: list[dict] = []
    for tool_def in catalog:
        name = tool_name(tool_def)
        if not name or name in exclude or is_legacy_tool(tool_def):
            continue
        if _domain_of(name) != group:
            continue
        out.append({"name": name, "description": _fn(tool_def).get("description", "") or ""})
    return out


# ── Track A / WS-0 · visible-set + deprecated-LABELING (contracts.md C2) ─────
# The Python twin of ai-gateway's `visibleTools` (find-tools.ts) — keep in lockstep.
# Unlike `enumerate_group`/`search_catalog` (which DROP legacy tools — you don't want a
# deprecated tool ranked in fuzzy search), `visible_tools` LABELS them (`deprecated` +
# `superseded_by`) so `tool_list` can show + redirect rather than hide-but-keep-callable
# (the invisible-but-callable drift class). The policy-allowed ∩ of the C2 visible-set is
# applied at the public edge (mcp-public-gateway), the only layer holding the key scope.
#: The index line's ceiling. 140 chars, chosen from the catalogue rather than taste: the first
#: sentence of a tool description has a median of 107 characters, so most survive whole, while the
#: tail (max 462) is what the cap exists to stop.
SHORT_DESCRIPTION_CHARS = 140

_SENTENCE_END = re.compile(r"(?<=[.!?])\s")


def _short_description(description: str) -> str:
    """The index line for `tool_list` (contracts.md C2): the description's FIRST SENTENCE, capped.

    DERIVED, never a second authoring field. Every tool description is already written summary-
    first, and a hand-written `short_description` beside the real one is a second thing to drift —
    the same reasoning `_skill_embedding_text` uses for skills. If the convention ever stops
    holding, the cap still bounds the damage.

    Whitespace is collapsed first so a description wrapped across source lines does not produce an
    index line full of newlines.
    """
    text = " ".join((description or "").split())
    if not text:
        return ""
    m = _SENTENCE_END.search(text)
    if m:
        # `_SENTENCE_END` is a lookbehind on [.!?] matching the WHITESPACE that follows, so
        # `m.start()` is the space itself and the terminator sits at m.start()-1. Slicing to
        # m.start() keeps the full stop and drops the space; `+1` would keep a trailing blank.
        text = text[: m.start()]
    if len(text) > SHORT_DESCRIPTION_CHARS:
        # Cut on a word boundary where one is near, so the line does not end mid-token.
        cut = text[:SHORT_DESCRIPTION_CHARS]
        sp = cut.rfind(" ")
        text = (cut[:sp] if sp > SHORT_DESCRIPTION_CHARS - 20 else cut).rstrip() + "…"
    return text


def visible_tools(
    catalog: list[dict],
    group: str | None = None,
    *,
    include_deprecated: bool = True,
    exclude: set[str] | None = None,
) -> list[dict]:
    """The deterministic, complete visible set for ``tool_list`` (contracts.md C2):
    EVERY tool (optionally scoped to ``group``), unranked, in catalog order — legacy
    tools LABELED ``deprecated: True`` (+ ``superseded_by``) rather than dropped.
    ``include_deprecated=False`` filters them out entirely."""
    exclude = exclude or set()
    out: list[dict] = []
    for tool_def in catalog:
        name = tool_name(tool_def)
        if not name or name in exclude:
            continue
        # CD4 ship gate — never advertise a tool the liveness matrix proved cannot
        # execute. A broken tool is WORSE than an absent one: the model spends a turn
        # calling it, gets an error, and often reports success anyway (the false-persist
        # bug class). Only an explicit `executes: false` hides a tool — an unprobed or
        # unchecked tool stays visible, and a RED-SELECT tool (works; the model just
        # doesn't pick it) stays visible too, because hiding it would guarantee it is
        # never picked. See tool_liveness.py.
        if tool_is_broken(name):
            continue
        if group is not None and _domain_of(name) != group:
            continue
        deprecated = is_legacy_tool(tool_def)
        if deprecated and not include_deprecated:
            continue
        entry: dict = {
            "name": name,
            # ── contracts.md C2 · tool_list IS AN INDEX ──────────────────────────────────────
            # `short_description`, never the full prose. The listing is BROWSED and the load is
            # READ; a listing that costs what the load costs buys nothing, which is exactly what
            # this returned before. Measured 2026-09-01: 192 tools at a mean 303 chars each was
            # 81.2% of a 71,686-byte payload, and tool_list alone was 21.4% of every tool-result
            # byte on the platform — its single largest producer.
            #
            # The contract had LOST the owner's original design ("a tool_list is a indexing with
            # short description ... it is a index not a full tool's description"): it named the
            # field `description` in both tiers, so copying the full text here was correct against
            # the spec as written. C2 is corrected and this follows it.
            #
            # SAFE TO CHANGE HERE because `visible_tools` has exactly two callers, both inside
            # `tool_list_result` (the "all" branch and the category branch). `tool_load` does NOT
            # go through this function and keeps the full description, which is the tier that is
            # supposed to carry it.
            "short_description": _short_description(_fn(tool_def).get("description", "") or ""),
            "tier": tool_tier(tool_def),
            # ── DQ-T59 (owner 2026-08-28) · THE REFUSAL, PER ENTRY ───────────────────────────
            # "REFUSE a contract question answered from a description-only read — the model must
            # call tool_load for arguments."
            #
            # 🔴 THE WORDING VERSION WAS MEASURED AND IT FAILS. `_stamp_no_schemas` has put
            # exactly that sentence at the TOP of every tool_list payload since 2026-08-23, added
            # for this defect and never tested. The owner's build note asked for the test before
            # calling it done: "whether a refusal needs a mechanism rather than wording is a
            # measurement, and it is owed".
            #
            # Run 2026-08-30, batch c-toollistoffwire1, K=5 — a tool_list read followed by a
            # contract question about `composition_arc_edit`, a tool that is NOT on the wire, so
            # the description is genuinely all the model holds:
            #     4 of 5 stated its arguments as FACT from the prose, never calling tool_load
            #     1 of 5 declined and pointed at tool_load
            # The stamp was present verbatim in the payload every time.
            #
            # TWO EARLIER ARMS PROVED NOTHING AND ARE RECORDED SO THEY ARE NOT REPEATED:
            # c-toolload3 (5/5 never called tool_list at all) and c-toollistcontract1 (5/5 read
            # it, but asked about an ADVERTISED tool whose real schema was already in context —
            # the reply recited it with types tool_list never carried). A clean arm proves
            # nothing until it is shown to have reached the path.
            #
            # So the sentence moves from ONE line above 29KB of prose to EVERY entry, beside the
            # description it is about. Same claim, at the point of use.
            "arguments": f"NOT SHOWN — call tool_load({name!r}) to read them.",
        }
        if deprecated:
            entry["deprecated"] = True
            sb = tool_superseded_by(tool_def)
            if sb:
                entry["superseded_by"] = sb
        out.append(entry)
    return out


# ── Track A / WS-1a · tool_list + tool_load result builders (contracts.md C2) ─
# Python twin of ai-gateway's tool_list/tool_load (find-tools.ts) — the deterministic
# discovery pair that replaces mandatory find_tools semantic search. Keep in lockstep.
# (CATEGORY_ENUM + the tool defs live up near GROUP_DIRECTORY / FIND_TOOLS_TOOL.)


def tool_parameters(tool_def: dict) -> dict:
    """The tool's JSON-Schema arguments (the OpenAI `function.parameters`), or an
    empty object schema when absent — what ``tool_load`` returns so the model can
    call the tool correctly."""
    params = _fn(tool_def).get("parameters")
    return params if isinstance(params, dict) else {"type": "object", "properties": {}}


def _stamp_incomplete(payload: dict, unavailable: set[str] | None) -> dict:
    """Mark a discovery payload as an INCOMPLETE view of the catalog when >=1 provider
    failed to federate. Python twin of find-tools.ts `stampIncomplete` — keep in lockstep.

    Without this a ``tool_list`` during an outage reads as a complete, healthy answer.
    Measured 2026-07-23 with glossary down: ``tool_list("glossary")`` returned ``count: 1``
    with no hint anything was missing, and the live agent then told the user it had "loaded
    the glossary tools", advertised a capability set built from the single surviving tool,
    and finally blamed the USER ("I don't have any details about her") for what was a
    platform outage.

    The availability signal already existed (H10) but was wired ONLY into ``find_tools``,
    which F17 retired from the LLM's view — so it reached nothing the model could still
    call. This is the missing half of that wiring.
    """
    if not unavailable:
        return payload
    listed = ", ".join(sorted(unavailable))
    payload["unavailable_providers"] = sorted(unavailable)
    payload["incomplete"] = True
    payload["note"] = (
        f"This listing is INCOMPLETE — {listed} is temporarily unavailable, so its tools are "
        "missing from the catalog right now. If the capability you need is not listed, tell "
        "the user that service is temporarily down and to try again shortly — do NOT conclude "
        "the capability doesn't exist, and do NOT substitute an unrelated tool."
    )
    return payload


def _excluded_in_scope(catalog: list[dict], category: str | None, exclude: set[str]) -> list[str]:
    """The names `exclude` removed that the caller's scope would otherwise have listed.

    Scoped by the SAME `_domain_of` rule `visible_tools` uses, so this can never name a tool
    the request was not asking about. A tool absent from the catalog entirely is not "held
    back" — it is simply not there — so this reads the catalog rather than `exclude` itself.
    """
    if not exclude:
        return []
    held = []
    for tool_def in catalog:
        name = tool_name(tool_def)
        if not name or name not in exclude:
            continue
        if category is not None and _domain_of(name) != category:
            continue
        held.append(name)
    return sorted(set(held))


def _stamp_no_schemas(payload: dict) -> dict:
    """Say that a listing carries NAMES and DESCRIPTIONS, never arguments.

    🔴 A MODEL ANSWERED A CONTRACT QUESTION FROM THIS PAYLOAD AND GOT IT WRONG. Measured
    2026-08-23, batch c-toolload2: asked "What arguments does the composition_arc_apply tool
    require? Read its real schema", one run of five called `tool_list` instead of `tool_load` and
    replied "arc_template_id + book_id". The real input_schema is {project_id, arc_template_id,
    roster_bindings, replace, idempotency_key} — there is NO book_id — and the words it answered
    with came from a DIFFERENT tool's description: composition_arc_edit's reads "op=create mints a
    saga/arc (needs book_id; optional ... arc_template_id ...)". One tool's requirements were
    attributed to another, confidently, with no error.

    The payload was not wrong; it was SILENT about what it is. 29KB of 53 descriptions reads like
    an authoritative answer to "what does this tool need", and nothing in it says otherwise. This
    is the same move the file already makes for `always_available` and for an unknown `category`:
    when a listing withholds something a caller could mistake for absent, it says so IN the
    payload rather than leaving the caller to infer it.
    """
    payload["schemas"] = (
        "NOT INCLUDED — these entries carry each tool's NAME and DESCRIPTION only. For a tool's "
        "arguments (which are required, their types), call tool_load with that tool's name. A "
        "description may MENTION another tool's arguments in prose; that is not this tool's schema."
    )
    return payload


def _stamp_always_available(
    payload: dict, catalog: list[dict], category: str | None, exclude: set[str],
) -> dict:
    """Name what the always-on exclusion withheld, so no listing silently under-reports.

    The exclusion itself is right — re-listing a tool the model already holds is noise. What
    was wrong was doing it invisibly: `tool_list` describes itself as "complete and
    deterministic", and a caller cannot tell a withheld tool from an absent one.
    """
    held = _excluded_in_scope(catalog, category, exclude)
    if held:
        payload["always_available"] = held
    return payload


#: DQ-T3 — how the intent gate is opened, in the model's terms. ONE string, used by both halves
#: of the discovery pair, so the listing and the load can never describe the same gate differently.
_SETUP_GATE_HOW = (
    "These become available on a turn that is explicitly about setting up or restructuring the "
    "world/ontology, or when a workflow step names one. You cannot enable them yourself, and "
    "calling or loading them now will not work."
)
_SETUP_GATE_WHY = (
    "They exist on this platform but are NOT callable on this turn: they make sweeping, "
    "hard-to-undo changes to a book's ontology, so they are held back unless the turn is "
    "world-setup."
)
_SETUP_GATE_DO = (
    "Do NOT retry them and do NOT tell the user they do not exist. If one of them is what the "
    "user actually needs, say so in plain words and ask whether they want to start world setup."
)


def _withheld_setup_tools(catalog: list[dict], category: str | None = None) -> list[str]:
    """The intent-gated setup tools that are MISSING from this turn's catalog.

    Absence from the catalog is the whole signal: `filter_intent_gated_setup_tools` returns the
    catalog UNCHANGED on a setup turn, so on such a turn nothing is withheld and this is empty.
    Deriving it from the catalog rather than re-evaluating the gate keeps one source of truth —
    a second copy of the gate condition would drift from the first.
    """
    present = {tool_name(td) for td in catalog}
    return sorted(
        n for n in INTENT_GATED_SETUP_TOOLS
        if n not in present
        and (category in (None, "all") or _domain_of(n) == category)
    )


def _stamp_withheld_setup(payload: dict, catalog: list[dict], category: str | None) -> dict:
    """DQ-T3 (a) — name the intent-gated tools the listing did not show, with the gate.

    🔴 A LISTING THAT OMITS WITHOUT SAYING SO READS AS A COMPLETE, HEALTHY ANSWER — the same
    class as `always_available` above and as `provider_unavailable` in tool_load. Measured
    2026-08-13: five glossary tools are dropped at CATALOG ASSEMBLY unless the turn is
    world-setup, so they are un-seeded, un-findable AND un-loadable. That is deliberate
    (N5a-FULL, the confirmed over-reach) and it IS instrumented — but only into telemetry the
    model never sees. From the model's side they are indistinguishable from tools that do not
    exist, and it tells the user so.

    Owner's decision on DQ-T3: option (a), stamp them the way T7-D2 stamps always-on tools.

    THE OPPOSITE ERROR IS ALSO MEASURED, AND IT IS WORSE, WHICH IS WHY THE WORDING IS SHAPED THE
    WAY IT IS. Naming a tool the capability floor had made unreachable produced 40,597 characters
    of one repeated paragraph on the dogfood book before the author hit Stop (see
    `filter_intent_gated_setup_tools`). So this stamp must never read as "here is a tool, go get
    it". It says the tools are not callable, that the model cannot open the gate itself, and that
    the move is to ASK THE USER — a route out that is not a retry.
    """
    withheld = _withheld_setup_tools(catalog, category)
    if withheld:
        payload["withheld_pending_setup_intent"] = {
            "tools": withheld,
            "why": _SETUP_GATE_WHY,
            "how_to_open": _SETUP_GATE_HOW,
            "do": _SETUP_GATE_DO,
        }
    return payload


def tool_list_result(
    catalog: list[dict],
    category: str | None = None,
    *,
    include_deprecated: bool = True,
    exclude: set[str] | None = None,
    unavailable_providers: set[str] | None = None,
) -> dict:
    """Build the ``tool_list`` payload (contracts.md C2). ``category`` omitted or
    "all" → the whole visible catalog grouped by category; a specific category → its
    flat ``tools`` list (+ a ``reason`` when empty). Deterministic, unranked."""
    exclude = exclude or set()
    if category is None or category == "all":
        tools = visible_tools(catalog, None, include_deprecated=include_deprecated, exclude=exclude)
        categories: dict[str, list] = {}
        for t in tools:
            categories.setdefault(_domain_of(t["name"]), []).append(t)
        payload_all: dict = {"categories": categories, "count": len(tools)}
        _stamp_always_available(payload_all, catalog, None, exclude)
        _stamp_no_schemas(payload_all)
        return _stamp_incomplete(payload_all, unavailable_providers)
    if category not in CATEGORY_ENUM:
        # T7-D3 — a category that is not a domain at all must say SO, not report itself empty.
        #
        # This function's contract is that `reason` lets a caller "tell 'no tools' from a bad
        # guess". It could not: both answered the identical string. MEASURED in recorded traffic
        # 2026-08-13 — the model sent `book}` (a mangled `book`) twice, plus `learning` and
        # `media`, and each time was told "no tools currently available in this category". The
        # `book` domain holds 16 current tools, so a single stray brace told the model the
        # platform has no book tools.
        #
        # `category` declares an enum, but a consumer-local tool is dispatched here WITHOUT the
        # gateway's JSON-schema validation, so an out-of-enum value arrives intact. The enum is
        # therefore checked at the only layer that sees the call.
        return _stamp_incomplete(
            {
                "category": category,
                "count": 0,
                "tools": [],
                "reason": (
                    f"unknown category {category!r} — that is not one of the tool domains, so "
                    "this is a mistyped or invented name rather than an empty domain. Call "
                    "tool_list again with one of: " + ", ".join(CATEGORY_ENUM) + "."
                ),
                "valid_categories": list(CATEGORY_ENUM),
            },
            unavailable_providers,
        )
    tools = visible_tools(catalog, category, include_deprecated=include_deprecated, exclude=exclude)
    payload: dict = {"category": category, "count": len(tools), "tools": tools}
    _stamp_no_schemas(payload)
    held = _excluded_in_scope(catalog, category, exclude)
    if not tools:
        # T7-D2 — `reason` is the field a caller uses to tell "no such tools" from "bad guess",
        # so it must never assert the first when the EXCLUSION is what emptied the category.
        #
        # MEASURED LIVE 2026-08-13 (session 019ff9da). `research` holds exactly one tool,
        # `web_search`, which is in ALWAYS_ON_CORE_NAMES and therefore excluded from listings as
        # redundant — it is already advertised on every turn. So tool_list("research") returned
        # count 0 and "no tools currently available in this category", while the group directory
        # injected into that same system prompt says `research: External web research — search
        # the open web for background facts (web_search). PAID.` and instructs the model to call
        # tool_list to see a domain's tools. Asked to list them, the model answered "there are
        # actually **no tools** currently listed under a specific research category."
        #
        # Same class as the `incomplete` stamp one function up, and for the same reason: a
        # listing that omits without saying so reads as a complete, healthy answer.
        payload["reason"] = (
            "no tools currently available in this category"
            if not held else
            "every tool in this category is ALREADY advertised and callable right now, so it is "
            "not repeated here: " + ", ".join(held) + ". This category is not empty."
        )
    _stamp_always_available(payload, catalog, category, exclude)
    _stamp_withheld_setup(payload, catalog, category)
    return _stamp_incomplete(payload, unavailable_providers)


def tool_load_result(
    catalog: list[dict],
    *,
    name: str | None = None,
    names: list[str] | None = None,
    category: str | None = None,
    unavailable_providers: set[str] | None = None,
    legacy_index: dict[str, str | None] | None = None,
) -> tuple[dict, list[str]]:
    """Build the ``tool_load`` payload + the names to activate (contracts.md C2).
    Pure disclosure — returns full ``input_schema``(s); executes nothing. Unknown
    requested names come back under ``not_found`` (never a silent drop) — EXCEPT while a
    provider is down, when non-existence is unknowable and they come back under
    ``provider_unavailable`` instead (see the block below)."""
    want: set[str] = set()
    if name:
        want.add(name)
    for n in names or []:
        if n:
            want.add(n)
    whole = category == "all"
    by_category = category if category and category != "all" else None
    loaded: list[dict] = []
    seen: set[str] = set()
    broken: set[str] = set()
    for tool_def in catalog:
        nm = tool_name(tool_def)
        if not nm or nm in seen or nm in broken:
            continue
        match = nm in want or whole or (by_category is not None and _domain_of(nm) == by_category)
        if not match:
            continue
        # CD4 — never ACTIVATE a proven-broken tool either. Report it with a reason
        # rather than silently omitting it: a resolver that drops a request without
        # saying so is how a model ends up hallucinating that the call succeeded.
        if tool_is_broken(nm):
            broken.add(nm)
            continue
        seen.add(nm)
        entry: dict = {
            "name": nm,
            "description": _fn(tool_def).get("description", "") or "",
            "tier": tool_tier(tool_def),
            "input_schema": tool_parameters(tool_def),
        }
        if is_legacy_tool(tool_def):
            entry["deprecated"] = True
            sb = tool_superseded_by(tool_def)
            if sb:
                entry["superseded_by"] = sb
        loaded.append(entry)
    payload: dict = {"tools": loaded}
    missing = sorted(n for n in want if n not in seen and n not in broken)

    # 🔴 A DEPRECATED TOOL IS NOT A NON-EXISTENT ONE, AND SAYING SO IS THE LIE THIS FUNCTION
    # ALREADY WARNS ABOUT ONE PARAGRAPH DOWN.
    #
    # Since the 2026-08-25 widening, `drop_superseded_tools` removes EVERY legacy tool from the
    # turn catalogue, so a legacy name reaches here as simply absent and fell into `not_found`.
    # Measured 2026-09-03 against the live catalogue: `tool_load("book_get")` answered
    # `{"not_found": ["book_get"]}` — for a tool that exists, is federated, and has
    # `superseded_by: book_read` sitting in its own meta. That is the same false premise that
    # cost the 2026-07-23 incident, arrived at from the other direction: there a live tool was
    # called non-existent because its provider was down; here because it was deprecated.
    #
    # A model told "no such tool" stops looking. Told "deprecated, use X" it calls X — which is
    # the entire point of dropping the predecessor. So the refusal NAMES THE SUCCESSOR.
    #
    # PINNED legacy tools never reach this branch: a pin keeps them IN the catalogue, so they
    # load normally and come back labelled `deprecated: True`. That is deliberate (DQ-V3) — an
    # explicit per-session user pin is not the model reaching a dead tool.
    if missing and legacy_index:
        retired = [n for n in missing if n in legacy_index]
        if retired:
            missing = [n for n in missing if n not in legacy_index]
            payload["deprecated"] = [
                {"name": n, "superseded_by": legacy_index[n]} if legacy_index[n]
                else {"name": n} for n in retired
            ]
            _named = [f"{n} -> {legacy_index[n]}" for n in retired if legacy_index[n]]
            _bare = [n for n in retired if not legacy_index[n]]
            _parts = []
            if _named:
                _parts.append("use the replacement instead: " + ", ".join(_named))
            if _bare:
                _parts.append("retired with no replacement: " + ", ".join(_bare))
            # A DISTINCT KEY, not `note`. The block below also writes `note` (for a provider
            # outage or a genuine not_found), so one request mixing a deprecated name with an
            # absent one would have silently lost whichever wrote first.
            payload["deprecated_note"] = (
                f"{', '.join(retired)} is deprecated and is no longer offered. "
                + ". ".join(_parts) + ". Do NOT report it as missing — it exists, it is retired."
            )

    if missing:
        # `not_found` ASSERTS that no such tool exists. During an outage that assertion is
        # unknowable: a down provider's tools are absent from the catalog entirely, so an
        # unresolvable name is indistinguishable from one that vanished with its provider.
        # Asserting it there is a LIE, and it cost a real incident — 2026-07-23, glossary
        # down, `tool_load("glossary_propose_entities")` answered `not_found`; the model
        # reasoned correctly from that false premise and gave up on a tool that exists.
        # Only assert non-existence when the catalog is COMPLETE.
        # Key is `provider_unavailable`, NOT `unavailable` — the latter already means a CD4
        # BROKEN tool below (exists but reliably fails). One name, one concept.
        if unavailable_providers:
            listed = ", ".join(sorted(unavailable_providers))
            payload["provider_unavailable"] = missing
            payload["unavailable_providers"] = sorted(unavailable_providers)
            payload["note"] = (
                f"Could not load {', '.join(missing)}. This does NOT mean the tool does not "
                f"exist — {listed} is temporarily unavailable, so its tools are missing from "
                "the catalog right now. Tell the user that service is temporarily down and to "
                "try again shortly."
            )
        else:
            # DQ-T3 — the SAME lie as the outage case above, from a different cause. An
            # intent-gated setup tool is absent from this turn's catalog by design, so an
            # unresolvable name here is not "no such tool" — it is "not on THIS turn". Asserting
            # non-existence is what makes the model tell the user the capability is missing.
            _gated = [n for n in missing if n in INTENT_GATED_SETUP_TOOLS]
            _really_missing = [n for n in missing if n not in INTENT_GATED_SETUP_TOOLS]
            if _gated:
                payload["withheld_pending_setup_intent"] = {
                    "tools": _gated,
                    "why": _SETUP_GATE_WHY,
                    "how_to_open": _SETUP_GATE_HOW,
                    "do": _SETUP_GATE_DO,
                }
            if _really_missing:
                payload["not_found"] = _really_missing
    if broken & want:
        payload["unavailable"] = sorted(broken & want)
        payload["unavailable_reason"] = (
            "this tool is known to fail when called — it is temporarily withdrawn. "
            "Do not retry it; use another tool or tell the user it is unavailable."
        )
    return payload, [t["name"] for t in loaded]


# ── Design item 1 — retry-cap (bounds the unbounded-retry bias) ─────────────
#
# Mirrors ai-gateway's `FindToolsAttemptTracker` (find-tools.ts). The closest
# stable per-exchange key available to `find_tools_result` is the caller's
# `session_id` — tracked here as an in-PROCESS, TTL-bounded map (the same shape
# as other bounded in-memory per-session state in this codebase). A caller with
# no session id is never tracked (fail-open — a caller we can't key can't be
# safely capped without risking cross-talk).
_RETRY_WINDOW_S = 10 * 60.0  # bounds one exchange's worth of guessing, not a whole day
_RETRY_REPEAT_AT = 2  # the 2nd attempt at the same (group, intent) this window is a "repeat"


class FindToolsAttemptTracker:
    """Per-session tracker of prior ``(group, normalized-intent)`` `find_tools`
    attempts. A repeated or near-duplicate call — SAME group + a token-set-equal
    intent (order/casing/punctuation-insensitive, the same ``_tokens()`` splitter
    ``search_catalog`` scores with, so "search the web" and "web search" collide)
    — reports ``True``, the signal ``find_tools_result`` uses to stop inviting
    further guessing and instead permit "tell the user this isn't supported"."""

    def __init__(self, ttl_s: float = _RETRY_WINDOW_S, *, now=time.monotonic) -> None:
        self._ttl_s = ttl_s
        self._now = now
        self._sessions: dict[str, dict[str, tuple[int, float]]] = {}

    @staticmethod
    def _key(group: str | None, intent: str) -> str:
        toks = " ".join(sorted(_tokens(intent)))
        return f"{group or ''} {toks}"

    def record(self, session_id: str | None, group: str | None, intent: str) -> bool:
        """Record this attempt for ``session_id`` and report whether it is a
        REPEAT. Blank/enumeration calls (no intent to guess with) are never
        tracked — there is no "wording" to repeat.

        review-impl fix (mirrors ai-gateway's `FindToolsAttemptTracker.record`,
        same root cause, same fix, patched independently in each engine): the
        previous version only pruned stale entries INSIDE the CURRENT
        session's own bucket and never deleted the top-level ``session_id``
        key once that bucket went empty — so every distinct session ever seen
        leaked a dict entry for the life of the process, unbounded by however
        many sessions the caller produces. A narrower fix that only swept the
        current caller's own bucket is observably inert: THIS call always
        re-populates its own bucket with the entry it's about to record before
        returning, so the top-level key for THIS session is back immediately —
        no net shrinkage. The actual fix sweeps EVERY tracked session on each
        call: drop each session's expired entries, then drop that session's
        top-level key if its bucket is now empty. O(sessions currently
        tracked) per call, but that count is itself bounded by "sessions active
        within the last TTL window" — the busier the tracker gets, the more
        aggressively each call prunes it, so it can never grow unbounded the
        way the un-swept version could. Negligible cost at this tracker's real
        cardinality (session ids scoped to one exchange, TTL = 10 minutes)."""
        if not session_id or not intent.strip():
            return False
        now = self._now()
        for sid in list(self._sessions.keys()):
            bucket = self._sessions[sid]
            for k in [k for k, (_, exp) in bucket.items() if exp <= now]:
                del bucket[k]
            if not bucket:
                del self._sessions[sid]
        bucket = self._sessions.setdefault(session_id, {})
        key = self._key(group, intent)
        existing = bucket.get(key)
        if existing is not None:
            count, _ = existing
            count += 1
            bucket[key] = (count, now + self._ttl_s)
            return count >= _RETRY_REPEAT_AT
        bucket[key] = (1, now + self._ttl_s)
        return False

    @property
    def session_count(self) -> int:
        """Test-only accessor (mirrors the TS twin's `sessionCount` getter) —
        lets tests assert the top-level map actually shrinks back down after
        entries expire, not just that lookups still behave correctly. Not used
        by production code."""
        return len(self._sessions)


# Process-wide singleton shared across all find_tools calls in this process —
# mirrors ai-gateway's module-level `findToolsAttempts`.
find_tools_attempts = FindToolsAttemptTracker()


# ── Design item 1 (embeddings sub-item, OQ4) — embeddings-backed search ─────
#
# `search_catalog()`'s token-overlap/difflib scorer stays the MANDATORY fallback
# (never removed): on any embedding-client failure/timeout, `search_catalog_semantic`
# degrades to identical behaviour to `search_catalog()` — a find_tools call must
# NEVER fail, block indefinitely, or rank worse than today because of this upgrade.
#
# Tool vectors are cached PER TOOL-CATALOG SIGNATURE (the sorted tuple of tool
# names) with the SAME TTL `knowledge_client.py`'s `_TOOL_CATALOG_TTL_S` uses for
# the catalog itself (60s) — so the vector cache invalidates on the same schedule
# as the catalog it was computed from, never a separate one. `test_tool_discovery.py`
# carries a drift-lock asserting the two constants stay equal.
#
# review-impl HIGH-1 fix: the cache key MUST also fold in which embedding model
# produced the vectors (`model_source`, `model_ref`), not just the catalog
# signature. Two callers within the same 60s TTL window using DIFFERENT
# embedding models (different users/sessions with different BYOK embedding
# configs) would otherwise share the FIRST caller's vectors — and
# `cosine_similarity` between two different embedding models' vector spaces is
# meaningless (can only inflate scores via the `max(token_score, cosine_score)`
# blend in `search_catalog_semantic`, never deflate them — a false-positive-only
# failure mode, silent cross-model cache poisoning).
TOOL_VECTOR_CACHE_TTL_S = 60.0

_TOOL_VECTOR_CACHE: dict[tuple[int, str, str], tuple[float, dict[str, list[float]]]] = {}


def _embedding_text(tool_def: dict) -> str:
    """The same name+description+synonyms haystack `_score()` token-overlaps
    over, embedded instead of tokenized."""
    name = tool_name(tool_def)
    desc = _fn(tool_def).get("description", "") or ""
    synonyms = tool_meta(tool_def).get("synonyms") or []
    syn_text = " ".join(s for s in synonyms if isinstance(s, str))
    return f"{name.replace('_', ' ')} {desc} {syn_text}".strip()


def _catalog_signature(catalog: list[dict]) -> int:
    """A cheap fingerprint of a catalog's tool-name SET (sorted, hashed) — used
    to key the tool-vector cache. Recomputing this is O(N) string work, no
    network call, so checking it before deciding to skip re-embedding is far
    cheaper than the embed round trip it guards."""
    names = tuple(sorted(n for n in (tool_name(td) for td in catalog) if n))
    return hash(names)


# ── review-impl HIGH-2 fix — resolve a REAL embedding-capable model ─────────
#
# The embeddings-blended search used to reuse the TURN's own chat
# `model_source`/`model_ref` (the completion model the user picked, e.g.
# gpt-4o or a local chat GGUF) for the embed call. Most chat models can't
# embed at all, so this either failed upstream (safely caught by the
# mandatory-fallback try/except below — but silently made the whole
# embeddings feature INERT for real usage, since it degraded to
# token-overlap on essentially every real call) or, worse, some backends may
# "helpfully" return an improvised vector for a model that was never meant to
# embed anything.
#
# Fix: resolve the user's own configured embedding-capable model — the
# Account-tier default for the `embedding` capability (provider-registry,
# same route `app/client/provider_client.py`'s `get_default_model()` already
# exposes for exactly this "which model for which capability" question, spec
# §3.4) — BEFORE ever attempting an embed call. `get_default_model()` is
# already best-effort (never raises; returns None on 404/unset/any upstream
# error), so a user with nothing configured resolves to None here — the
# caller then skips the embed round trip ENTIRELY (no doomed network call)
# and goes straight to the token-overlap fallback.
#
# Cached briefly per user (mirrors the tool-vector cache's TTL discipline) so
# a burst of find_tools calls within one turn/session doesn't re-hit
# provider-registry for the same answer on every single call.
_EMBEDDING_MODEL_CACHE_TTL_S = 60.0

_EMBEDDING_MODEL_CACHE: dict[str, tuple[float, tuple[str, str] | None]] = {}


async def _resolve_embedding_model(user_id: str) -> tuple[str, str] | None:
    """The caller's embedding-capable model as ``(model_source, model_ref)``, or ``None``
    when they have no ACTIVE embedding-capable model at all. Never raises.

    D-A-TOOL-REACHES-THE-WIRE-WITHOUT-ITS-DOMAINS-GUIDANCE. This used the strict
    `get_default_model("embedding", user_id)`, which 404s unless the user EXPLICITLY set an
    'embedding' default — measured 2026-08-28: zero accounts on this deployment ever had, while
    7 active embedding-capable models exist across the platform. `resolve_embedding_model`
    falls back to the user's best active embedding-capable model server-side (provider-
    registry's `internalResolveEmbeddingModel`, mirroring the existing planner-model
    fallback), so this now returns None only when the user genuinely has no such model."""
    now = time.monotonic()
    cached = _EMBEDDING_MODEL_CACHE.get(user_id)
    if cached is not None and now < cached[0]:
        return cached[1]
    from app.client.provider_client import get_provider_client  # noqa: PLC0415

    ref = await get_provider_client().resolve_embedding_model(user_id)
    _EMBEDDING_MODEL_CACHE[user_id] = (now + _EMBEDDING_MODEL_CACHE_TTL_S, ref)
    return ref


async def _get_tool_vectors(
    catalog: list[dict],
    *,
    user_id: str,
    model_source: str,
    model_ref: str,
) -> dict[str, list[float]] | None:
    """Best-effort per-tool embedding vectors for ``catalog``, cached until the
    catalog's own tool-name set changes or ``TOOL_VECTOR_CACHE_TTL_S`` elapses.

    Returns ``None`` on ANY embedding-client failure — the caller MUST fall
    back to the token-overlap scorer unconditionally; this never raises."""
    names = [tool_name(td) for td in catalog if tool_name(td)]
    if not names:
        return {}
    # HIGH-1: key by (catalog signature, model_source, model_ref) — NOT the
    # catalog signature alone — so two distinct embedding models never share a
    # cached vector set (see the constant's docstring above).
    cache_key = (_catalog_signature(catalog), model_source, model_ref)
    now = time.monotonic()
    cached = _TOOL_VECTOR_CACHE.get(cache_key)
    if cached is not None and now < cached[0]:
        return cached[1]
    texts = [_embedding_text(td) for td in catalog if tool_name(td)]
    try:
        from app.client.embedding_client import get_embedding_client  # noqa: PLC0415

        result = await get_embedding_client().embed(
            user_id=user_id, model_source=model_source, model_ref=model_ref, texts=texts,
        )
    except Exception:  # noqa: BLE001 — mandatory fallback, never raise into find_tools
        logger.warning("tool-vector embedding failed; falling back to token-overlap search", exc_info=True)
        return None
    vectors = dict(zip(names, result.embeddings))
    _TOOL_VECTOR_CACHE[cache_key] = (now + TOOL_VECTOR_CACHE_TTL_S, vectors)
    return vectors


async def search_catalog_semantic(
    catalog: list[dict],
    intent: str,
    limit: int = FIND_TOOLS_DEFAULT_LIMIT,
    *,
    exclude: set[str] | None = None,
    group: str | None = None,
    user_id: str,
) -> tuple[list[dict], bool]:
    """Embeddings-blended twin of ``search_catalog()`` (design item 1, OQ4).

    Ranks by ``max(token-overlap score, cosine similarity)`` — a BLEND, not a
    replacement. This is a deliberate choice, not a half-measure: the
    token-overlap floor/threshold stay the safety net (CAT-4 legacy exclusion
    happens before either score is computed; the "no bogus suggestion" H10
    discipline is preserved) even when embeddings succeed, while a genuinely
    semantic match with near-zero token overlap (e.g. "look up who the king's
    rival is" ~ glossary_search) can still surface via the embedding term. A
    full replacement would risk regressing the already-tested precision
    behaviour tied to token overlap (CAT-4, the "one shared word" fix) any time
    the embedding model itself is noisy/mediocre — blending means embeddings
    can only ADD recall, never subtract precision the token scorer already had.

    review-impl HIGH-2 fix: this used to take the TURN's own chat
    `model_source`/`model_ref` and reuse them for the embed call — removed.
    The embedding model is now resolved independently per `user_id` via
    `_resolve_embedding_model()` (the user's configured `embedding`-capability
    default from provider-registry), never the chat completion model. When
    the user has no embedding model configured, this is a FAST PRE-NETWORK
    SKIP straight to the token-overlap score — no doomed embed round trip.

    MANDATORY fallback: on ANY embedding-client failure/timeout (tool-vector
    embedding OR intent embedding), this returns EXACTLY what ``search_catalog()``
    would — same ranking, same tests — never raises, never blocks past the
    embedding client's own timeout.
    """
    exclude = exclude or set()
    intent_tokens = _tokens(intent)
    candidates: list[dict] = []
    for tool_def in catalog:
        name = tool_name(tool_def)
        if not name or name in exclude or is_legacy_tool(tool_def):
            continue
        if group is not None and _domain_of(name) != group:
            continue
        candidates.append(tool_def)

    tool_vectors: dict[str, list[float]] | None = None
    intent_vector: list[float] | None = None
    embedding_ref = await _resolve_embedding_model(user_id)
    if embedding_ref is not None:
        embed_source, embed_ref = embedding_ref
        try:
            tool_vectors = await _get_tool_vectors(
                catalog, user_id=user_id, model_source=embed_source, model_ref=embed_ref,
            )
            if tool_vectors is not None:
                from app.client.embedding_client import get_embedding_client  # noqa: PLC0415

                intent_result = await get_embedding_client().embed(
                    user_id=user_id, model_source=embed_source, model_ref=embed_ref, texts=[intent],
                )
                intent_vector = intent_result.embeddings[0] if intent_result.embeddings else None
        except Exception:  # noqa: BLE001 — mandatory fallback, never raise into find_tools
            logger.warning("intent embedding failed; falling back to token-overlap search", exc_info=True)
            tool_vectors = None
            intent_vector = None
    # else: no embedding-capable model configured for this user — skip the
    # embed round trip entirely (HIGH-2 fast pre-network skip) instead of
    # paying a network call that would only fail against a non-embedding model.

    scored: list[tuple[float, dict]] = []
    for tool_def in candidates:
        name = tool_name(tool_def)
        base = _score(intent_tokens, intent, tool_def)
        sim = 0.0
        if tool_vectors is not None and intent_vector is not None:
            vec = tool_vectors.get(name)
            if vec:
                sim = max(0.0, cosine_similarity(intent_vector, vec))
        s = max(base, sim)
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


def provider_availability(catalog_meta: dict) -> set[str]:
    """H10 — the set of provider prefixes the gateway reports as temporarily
    unavailable (partial catalog). Reads the catalog-level `_meta` from
    ``KnowledgeClient.get_catalog_meta()``.

    **The key is FROZEN (2026-07-23): ``unavailable_providers``**, a list of provider
    names, emitted by ai-gateway ``handlers.ts::availabilityMeta`` on the ``tools/list``
    ``_meta``. Pinned cross-language by ``test_provider_availability_key_is_frozen``;
    change it in one language and that test reds. (The ``providers`` map branch below is
    retained as inert back-compat for an older payload shape — it is NOT a second
    supported contract; do not emit it.)

    Returns an empty set when nothing is present, so this never invents an outage —
    the no-false-alarm property the whole outage-visibility change depends on.
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


def _enumeration_result(
    catalog: list[dict], group: str, exclude: set[str], *, fallback_reason: str | None = None,
) -> tuple[dict, list[str]]:
    """Shared ENUMERATION-mode payload assembly — used by both
    `find_tools_result()` and `find_tools_result_async()` so the two search
    backends never drift on enumeration wording/shape. Two callers:
    (1) `group` set + blank `intent` (the original design-item-1 case), and
    (2) external audit #1 (2026-07-08 re-verification pass) — `group` set +
    a NON-blank but low-signal/generic `intent` (e.g. "list everything you
    can do in this domain") that scores below `CONFIDENCE_THRESHOLD`.
    Real measurement from that audit: `book` returned 1/~15 tools (7% recall)
    for exactly this shape, because a generic phrase token-overlaps poorly
    against specific tool descriptions — the ORIGINAL blank-intent
    enumeration fix never fired since the caller's intent wasn't literally
    empty. ``fallback_reason``, when given (case 2), replaces the "domain
    genuinely has no tools" note with an explanation of why a full list is
    being returned instead of a weak top-K, so the caller understands this
    wasn't what they explicitly asked for."""
    matches = enumerate_group(catalog, group, exclude=exclude)
    payload: dict = {"tools": matches, "enumerated": True}
    if not matches:
        payload["note"] = (
            f"The \"{group}\" domain genuinely has no tools right now — this "
            "capability isn't supported; no need to keep searching."
        )
    elif fallback_reason:
        payload["note"] = fallback_reason
    return payload, [m["name"] for m in matches]


def _blank_intent_result() -> tuple[dict, list[str]]:
    """Shared "missing/blank intent, NO group" directory payload. External
    audit #5 (2026-07-08 re-verification): a caller with neither a `group`
    nor a real `intent` had no safe path forward — the old response was just
    a scold ("intent is required") with nothing to act on, and returning the
    full ~200-tool federated catalog unranked would defeat the entire reason
    `find_tools` exists (context/schema bloat). The safe middle ground is
    `GROUP_DIRECTORY` itself (domain names + one-line descriptions, the same
    ~300-500 token block already injected into system prompts via
    `group_directory_text()`) — cheap, and gives the caller a concrete next
    step: pick a domain, call again with that `group`."""
    return (
        {
            "tools": [],
            "domains": dict(GROUP_DIRECTORY),
            "note": (
                "`intent` was missing/empty and no `group` was given either — "
                "pick a domain from `domains` above and call find_tools again "
                "with that `group` (leave `intent` empty to list everything in "
                "it, unranked), or describe what you want to do in your own "
                "words as a non-empty `intent`."
            ),
        },
        [],
    )


def _scored_result_payload(
    matches: list[dict], confident: bool, *, catalog_meta: dict, is_repeat: bool,
) -> dict:
    """Shared note/payload assembly for a SCORED (non-enumeration) find_tools
    result — the H10 (provider-availability) / retry-cap note wording, used by
    both `find_tools_result()` (token-overlap) and `find_tools_result_async()`
    (embeddings-blended) so the two scorers' notes never drift apart."""
    unavailable = provider_availability(catalog_meta)
    payload: dict = {"tools": matches}
    if not matches:
        if unavailable:
            # H10: capability may exist but its provider is briefly down —
            # unaffected by repeat status, transient outages ARE worth retrying.
            payload["unavailable_providers"] = sorted(unavailable)
            payload["note"] = (
                "No matching tool is currently available. One or more services are "
                "temporarily unavailable — tell the user the capability exists but "
                "to try again shortly; do NOT say you can't do it."
            )
        elif is_repeat:
            payload["note"] = (
                "No tool matched, and this is a repeat of a search you already "
                "tried. Stop searching — tell the user this capability is not "
                "supported."
            )
        else:
            payload["note"] = (
                "No tool matched. You may try once more with different wording "
                "(or list a `group` instead), but if that also comes back empty, "
                "tell the user this isn't supported rather than continuing to retry."
            )
    elif not confident:
        payload["low_confidence"] = True
        if is_repeat:
            payload["note"] = (
                "These are still only weak matches on a repeated search. Pick the "
                "closest one if it genuinely fits, or tell the user this isn't "
                "well supported — don't search again."
            )
        else:
            payload["note"] = (
                "These are weak matches. If none fit, you may search once more with "
                "different wording."
            )
    return payload


def find_tools_result(
    catalog: list[dict],
    intent: str,
    limit: int,
    *,
    exclude: set[str],
    catalog_meta: dict,
    group: str | None = None,
    session_id: str | None = None,
) -> tuple[dict, list[str]]:
    """Build the ``find_tools`` tool RESULT payload + the list of matched names
    to union into the active set (C-FT loop semantics), scored via the
    token-overlap `search_catalog()`.

    The payload distinguishes (H10): a genuinely empty result from one where the
    only plausible providers are *temporarily unavailable* — so the agent says
    "try again", never a false "I can't".

    2026-07-07 (Part E eval finding, `D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE` root
    cause): a weak/quantized local model sometimes emits `find_tools()` with NO
    `intent` at all despite the schema marking it `required` — the schema-level
    requirement was never enforced server-side, so an empty intent silently
    degraded into a genuine zero-token search (`_score()` returns 0.0 for empty
    `intent_tokens`), landing on the SAME generic "No tool matched. Reconsider the
    wording..." note a real no-match gets. That note gives the model no signal
    that its OWN call was malformed, so it retried identically — live-observed
    30+ consecutive empty-`intent` calls in one turn, ending in an empty final
    reply. Mirrors the "model-directed validation error" pattern jobs-service's
    kit already uses for pydantic failures (`_validation_directive`): reject a
    missing/blank intent with a directive naming the exact fix, instead of
    silently degrading to an uninformative empty-match note.

    Design item 1 (2026-07-07 discovery-hardening plan) — `group` set + a
    blank/missing `intent` switches to ENUMERATION mode (mirrors ai-gateway's
    `findToolsResult`/`enumerateGroup`): the true fix for "a whole domain
    under-returns on generic queries" (external audit #1/#5), instead of the
    "intent required" directive below or a zero-token fuzzy search.

    2026-07-08 re-verification pass (external audit, same #1/#5) — the
    original fix above only covered a LITERALLY blank `intent`; a real
    exploratory agent instead phrases a broad ask as non-blank generic text
    ("list everything you can do in this domain"), which token-overlaps
    poorly and got silently filtered to near-nothing (measured: `book` →
    7% recall). Two further fixes close that gap: (1) `group` set + a
    NON-blank intent that scores below `CONFIDENCE_THRESHOLD` now ALSO falls
    back to full enumeration (see `_enumeration_result`'s `fallback_reason`);
    (2) no `group` + blank `intent` no longer returns a bare scold — see
    `_blank_intent_result()`, now returns the `GROUP_DIRECTORY` listing too,
    so the caller has a concrete next step instead of nothing to act on.

    `session_id` (optional, keyword-only, default None) feeds the module-level
    `find_tools_attempts` retry-cap tracker (`FindToolsAttemptTracker`) — a
    caller that omits it (or passes None) is simply never tracked (fail-open,
    same discipline as "no session id" on the ai-gateway TS mirror), so this
    stays fully backward-compatible for any existing caller that doesn't thread
    a session id through yet.

    Stays SYNCHRONOUS on purpose (no embeddings call) — see
    `find_tools_result_async()` for the embeddings-blended twin the live
    `_stream_with_tools()` call path actually uses; this sync version remains
    for any caller (and the bulk of this module's existing tests) that only
    needs the token-overlap scorer.
    """
    if bool(group) and not intent.strip():
        return _enumeration_result(catalog, group, exclude)

    if not intent.strip():
        return _blank_intent_result()

    is_repeat = find_tools_attempts.record(session_id, group, intent)
    matches, confident = search_catalog(catalog, intent, limit, exclude=exclude, group=group)
    if group is not None and not confident:
        # External audit #1 (2026-07-08 re-verification) — see _enumeration_result's
        # docstring: a low-signal/generic non-blank intent, scoped to a known
        # group, gets the SAME enumeration safety net as a literal blank intent
        # instead of a mostly-empty/weak top-K silently under-returning.
        return _enumeration_result(
            catalog, group, exclude,
            fallback_reason=(
                "Your query didn't score well against anything specific in the "
                f"\"{group}\" domain — showing the FULL domain list instead of a "
                "weak/empty guess. Pick whichever tool(s) actually fit."
            ),
        )
    payload = _scored_result_payload(matches, confident, catalog_meta=catalog_meta, is_repeat=is_repeat)
    matched_names = [m["name"] for m in matches]
    return payload, matched_names


async def find_tools_result_async(
    catalog: list[dict],
    intent: str,
    limit: int,
    *,
    exclude: set[str],
    catalog_meta: dict,
    group: str | None = None,
    session_id: str | None = None,
    user_id: str,
) -> tuple[dict, list[str]]:
    """Embeddings-blended twin of `find_tools_result()` — IDENTICAL enumeration /
    blank-intent / retry-cap / H10 semantics (delegated to the same
    `_enumeration_result` / `_blank_intent_result` / `_scored_result_payload`
    helpers, so the two never drift), but scores a non-enumeration search via
    `search_catalog_semantic()` (cosine-blended) instead of `search_catalog()`
    (token-overlap only).

    This is the variant the live `_stream_with_tools()` tool-loop call site
    awaits, so a real `find_tools` invocation actually exercises the
    embeddings path (design item 1 / OQ4) instead of leaving it built-but-
    unwired.

    review-impl HIGH-2 fix: `model_source`/`model_ref` were REMOVED from this
    signature — they used to be the SAME turn-scoped chat-completion model
    values threaded through `_stream_with_tools()`, reused here for the embed
    call. Most chat models can't embed, so that either failed upstream (caught
    by the mandatory fallback, but silently made the whole embeddings feature
    inert for real usage) or risked an improvised vector from a model never
    meant to embed anything. `search_catalog_semantic()` now resolves a real
    embedding-capable model independently per `user_id` (the account's
    `embedding`-capability default), so only `user_id` is needed here. The
    MANDATORY fallback contract is unchanged: on ANY embed-call failure, OR
    when the user has no embedding model configured at all, this degrades to
    the identical token-overlap ranking `find_tools_result()` would have
    produced — a find_tools call must never fail or rank worse because of this
    upgrade.
    """
    if bool(group) and not intent.strip():
        return _enumeration_result(catalog, group, exclude)

    if not intent.strip():
        return _blank_intent_result()

    is_repeat = find_tools_attempts.record(session_id, group, intent)
    matches, confident = await search_catalog_semantic(
        catalog, intent, limit, exclude=exclude, group=group, user_id=user_id,
    )
    if group is not None and not confident:
        # Mirrors find_tools_result()'s fallback — see _enumeration_result's
        # docstring (external audit #1). Kept in lockstep with the sync scorer.
        return _enumeration_result(
            catalog, group, exclude,
            fallback_reason=(
                "Your query didn't score well against anything specific in the "
                f"\"{group}\" domain — showing the FULL domain list instead of a "
                "weak/empty guess. Pick whichever tool(s) actually fit."
            ),
        )
    payload = _scored_result_payload(matches, confident, catalog_meta=catalog_meta, is_repeat=is_repeat)
    matched_names = [m["name"] for m in matches]
    return payload, matched_names
