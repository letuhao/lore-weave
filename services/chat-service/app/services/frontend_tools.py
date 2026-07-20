"""ARCH-1 C6 — frontend (client-executed) tool definitions.

A *frontend tool* is advertised to the LLM by chat-service like any other tool,
but it is NOT executed server-side. When the model calls one, the tool-loop
SUSPENDS the run, streams the tool call to the browser, and waits for the
frontend to execute it and POST the result back (the resume endpoint). For the
editor write-back tool the "execution" is the human reviewing the proposed edit
and clicking Apply/Dismiss — human-in-the-loop tool calling.

The "execute on the client" marker lives ONLY here (FRONTEND_TOOL_NAMES); the
schema sent over the wire to the provider is a standard OpenAI function def, so
the LLM sees nothing non-standard. The tool-loop checks the name against this set
to decide suspend-vs-execute.

Only meaningful in agui stream mode + the editor `<Chat>` panel (the request must
carry editor_context); other clients never have these tools advertised.
"""
from __future__ import annotations

import re as _re
from copy import deepcopy

from jsonschema import Draft202012Validator

# Tool names that the FRONTEND executes (suspend the run, don't call a backend).
#   propose_edit                  — editor prose write-back (chapter editor only)
#   glossary_propose_entity_edit  — edit an existing glossary entity (any book-scoped
#                                   surface); the browser renders a diff card, the user
#                                   Applies (version-checked PATCH, H5) or Dismisses.
#   glossary_confirm_action       — generic class-C confirm of any proposed
#                                   high-impact glossary action (schema create,
#                                   book_delete, adopt/sync/system later); the
#                                   browser renders a confirm card keyed on the
#                                   action `descriptor`, the user Confirms (POST to
#                                   the token-gated /v1/glossary/actions/confirm) or
#                                   Cancels. Supersedes the schema-only confirm card.
# MCP-fanout S-CONSUMER — the GENERIC frontend tools (C-NAV / C-CONFIRM /
# C-PROPOSE), shared across every domain (book/composition/translation/settings)
# so the FE renders ONE confirm card + ONE diff card + the nav tools, not a
# per-domain variant:
#   ui_navigate/ui_open_book/ui_open_chapter/ui_show_panel/ui_watch_job
#                                — navigation (C-NAV); resolve-immediately (no Apply)
#   confirm_action               — generic Tier-W/S confirm (C-CONFIRM); the
#                                  `domain` selects the committing endpoint, optional
#                                  `items[]` renders ONE batch card (H2)
#   propose_record_edit          — generic record diff card (C-PROPOSE) for
#                                  book/composition record edits
FRONTEND_TOOL_NAMES: frozenset[str] = frozenset(
    {
        "glossary_propose_entity_edit",
        "glossary_confirm_action",
        "confirm_action",
        "propose_record_edit",
        # NOTE (Phase 2, P2.2, 2026-07-20): propose_edit is NO LONGER a frontend tool —
        # it is an ai-gateway consumer-local tool (propose-edit-tool.ts) that returns a
        # GATED proposal directive. chat-service stops intercepting it here (→ routes to
        # ai-gateway), detects io.loreweave/propose-edit in the tool result, and SUSPENDS
        # with the same shape the old frontend-tool suspend used, so ProposeEditCard is
        # unchanged. The PROPOSE_EDIT_TOOL def below stays for the editor-surface
        # advertisement (frontend_tool_defs) until Phase 4 sources it from the catalog.
        # NOTE (Phase 3, P3.2, 2026-07-20): the KIND-A ui_* tools are NO LONGER frontend
        # tools — they are ai-gateway CONSUMER-LOCAL directive tools (ui-tools.ts). Removing
        # them here stops chat-service intercepting/suspending on them: a ui_* call now routes
        # to ai-gateway, which validates (enum/required) and returns an io.loreweave/ui-directive
        # RESULT the FE acts on (useUiToolExecutor's directive path). They stay ADVERTISED —
        # the 5 nav tools via the federated catalog (ALWAYS_ON_CORE_NAMES → catalog_index wins),
        # the 2 studio tools via frontend_tool_defs (which keeps the F7c nav-intent gate). The
        # defs below are retained only as an ai-gateway-down advertisement fallback + the P0
        # validation-seam map; retire fully in P4 (D-P3-RETIRE-UI-FRONTEND-DEFS).
        #   removed: ui_navigate, ui_open_book, ui_open_chapter, ui_show_panel, ui_watch_job,
        #            ui_open_studio_panel, ui_focus_manuscript_unit
    }
)

# OpenAI function-calling schema for the editor write-back tool. Wire-standard;
# the description tells the model the edit is reviewed by the user, not applied
# automatically.
PROPOSE_EDIT_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "propose_edit",
        "description": (
            "Propose an edit to the chapter the user is currently writing. The "
            "edit is shown to the user with an Apply button and is NOT applied "
            "automatically — the user reviews it first. Use this to suggest "
            "inserting new prose at the cursor, or rewriting the user's current "
            "selection. After the user decides, you receive whether they applied "
            "or dismissed it."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": ["insert_at_cursor", "replace_selection"],
                    "description": (
                        "insert_at_cursor = insert `text` at the user's cursor. "
                        "replace_selection = replace the user's currently selected "
                        "text with `text`."
                    ),
                },
                "text": {
                    "type": "string",
                    "description": "The prose to insert, or the replacement for the selection.",
                },
                "rationale": {
                    "type": "string",
                    "description": "Optional one-line explanation shown to the user.",
                },
            },
            "required": ["operation", "text"],
            "additionalProperties": False,
        },
    },
}


# OpenAI function-calling schema for the glossary edit-existing write-back tool
# (ARCH glossary-assistant P3). Like propose_edit it SUSPENDS the run and is
# executed in the browser, but its "execution" is the user reviewing a diff card
# and clicking Apply — which issues a version-checked PATCH to the glossary
# (If-Match: base_version → 412 on drift, H5). The outcome enum is what lets the
# agent report the REAL result (H6) instead of assuming success.
GLOSSARY_PROPOSE_EDIT_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "glossary_propose_entity_edit",
        "description": (
            "Propose ONE OR MORE edits to an EXISTING glossary entity (correct the name, "
            "an alias, the description, and/or any attribute) — all applied TOGETHER, "
            "atomically. The changes are shown to the user as a diff card with an Apply "
            "button and are NOT applied automatically — the user reviews them first. "
            "BEFORE calling this, call glossary_get_entity to read the current values and "
            "the entity's `updated_at` (pass it as `base_version`); for an attribute edit "
            "also read that attribute's `attr_value_id`. PRESERVE each value's format in "
            "`new_value` — if `old_value` is a JSON array (e.g. aliases like "
            "[\"King\",\"Art\"]) keep it a JSON array; if it is a number or a fixed option, "
            "keep that shape. After the user decides you receive an `outcome`: "
            "`applied_saved` (the edit was saved), `applied_conflict` (the entity changed "
            "since you read it — call glossary_get_entity again and propose afresh), "
            "`applied_error` (the save failed), or `dismissed` (the user declined). State "
            "that the change was made ONLY when the outcome is `applied_saved`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "book_id": {
                    "type": "string",
                    "description": "The book the entity belongs to (UUID).",
                },
                "entity_id": {
                    "type": "string",
                    "description": "The entity to edit (UUID).",
                },
                "base_version": {
                    "type": "string",
                    "description": (
                        "The entity's `updated_at` value from glossary_get_entity — used "
                        "to detect a concurrent change (optimistic concurrency). One token "
                        "covers ALL the changes (they apply in a single transaction)."
                    ),
                },
                "changes": {
                    "type": "array",
                    "description": (
                        "One or more field changes to apply together. A single-field edit "
                        "is just a one-element array."
                    ),
                    "items": {
                        "type": "object",
                        "properties": {
                            "target": {
                                "type": "string",
                                "enum": ["short_description", "attribute"],
                                "description": (
                                    "short_description = the entity's summary. attribute = "
                                    "one attribute value (name, aliases, or any attribute), "
                                    "identified by attr_value_id."
                                ),
                            },
                            "attr_value_id": {
                                "type": "string",
                                "description": (
                                    "Required when target=attribute: the attribute value to "
                                    "change (from glossary_get_entity)."
                                ),
                            },
                            "field_label": {
                                "type": "string",
                                "description": (
                                    "Human-readable label of the field (e.g. 'Name', "
                                    "'Aliases', 'Description'), shown on the diff card."
                                ),
                            },
                            "old_value": {"type": "string", "description": "The current value, for the diff."},
                            "new_value": {"type": "string", "description": "The proposed new value."},
                        },
                        "required": ["target", "field_label", "old_value", "new_value"],
                        "additionalProperties": False,
                    },
                },
                "rationale": {
                    "type": "string",
                    "description": "Optional one-line explanation shown to the user.",
                },
            },
            "required": ["book_id", "entity_id", "base_version", "changes"],
            "additionalProperties": False,
        },
    },
}


# OpenAI function-calling schema for the generalized class-C confirm frontend tool.
# The LLM proposes a high-impact action with a glossary_propose_*/glossary_book_*
# MCP tool (which MINTS a confirm_token + confirm card, no write), then calls THIS
# tool to surface the human confirm step. It suspends; the browser renders a confirm
# card keyed on `descriptor` (re-fetching a current-state preview via
# /v1/glossary/actions/preview); on Confirm the FE POSTs the token to
# /v1/glossary/actions/confirm (the only write path). H6: the resume reports the
# real outcome so the agent can't claim an action that didn't happen.
GLOSSARY_CONFIRM_ACTION_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "glossary_confirm_action",
        "description": (
            "Ask the user to CONFIRM a high-impact glossary action (a new kind/attribute, "
            "or DELETING a genre/kind/attribute) that you proposed with a glossary_propose_* "
            "or glossary_book_delete MCP tool. Pass the `confirm_token` and `descriptor` you "
            "received from that propose call. The action is shown with a Confirm button and is "
            "NOT applied automatically — high-impact and destructive changes ALWAYS require "
            "explicit human confirmation. After the user decides you receive an `outcome`: "
            "`action_done` (applied), `token_expired` (the confirmation lapsed — propose again), "
            "`action_error` (it failed), or `cancelled` (the user declined). State that the "
            "change happened ONLY when the outcome is `action_done`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "confirm_token": {
                    "type": "string",
                    "description": "The confirm_token returned by the propose call.",
                },
                "descriptor": {
                    "type": "string",
                    "description": (
                        "The action `descriptor` from the propose call (e.g. book_delete, "
                        "schema_create_kind) — keys which confirm card the browser renders."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": (
                        "Human-readable title of the action (the `title` from the propose "
                        "call), shown on the confirm card."
                    ),
                },
            },
            "required": ["confirm_token", "descriptor", "title"],
            "additionalProperties": False,
        },
    },
}


# ── MCP-fanout C-NAV — the navigation ui_* tools moved to ai-gateway ─────────
# Phase 3 (P3.2): ui_navigate / ui_open_book / ui_open_chapter / ui_show_panel /
# ui_watch_job are ai-gateway CONSUMER-LOCAL directive tools now (ui-tools.ts).
# Their chat-service defs were retired in Phase 4 (D-P3-RETIRE-UI-FRONTEND-DEFS);
# the 5 nav tools resolve their schema from the federated catalog. The 2 STUDIO
# ui_* + propose_edit defs below remain until frontend_tool_defs sources them
# from the catalog too (the deferred nav-intent-gate-as-catalog-filter).


# ── Writing Studio surface (#09 Lane A) — dock navigation, resolve-immediately ──
# Advertised ONLY when the request carries studio_context (mirrors editor_context →
# propose_edit). The FE executes them against the StudioHost (open a dock panel / focus a
# chapter's editor) and POSTs the resolve — no human gate.

UI_OPEN_STUDIO_PANEL_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "ui_open_studio_panel",
        "description": (
            "Open a Writing Studio dock panel for the user (e.g. the AI compose chat, the "
            "manuscript editor). Use to bring a studio tool into view. Opens immediately — "
            "no confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "panel_id": {
                    "type": "string",
                    "enum": ["compose", "scene-compose", "chapter-assemble", "editor", "planner", "agent-mode", "usage", "notifications", "settings", "trash", "steering", "style-voice", "extensions", "proposals", "workflows", "workflow-proposals", "glossary", "glossary-ontology", "glossary-unknown", "glossary-ai-suggestions", "glossary-merge-candidates", "wiki", "knowledge", "kg-overview", "kg-entities", "kg-timeline", "kg-evidence", "kg-gap", "kg-proposals", "kg-schema", "kg-graph", "kg-insights", "kg-jobs", "kg-bio", "kg-privacy", "kg-triage", "search", "jobs-list", "books", "leaderboard-books", "leaderboard-authors", "leaderboard-translators", "leaderboard-trending", "chapter-browser", "scene-browser", "scene-inspector", "plan-hub", "decompose", "arc-inspector", "arc-templates", "structure-templates", "plan-passes", "whatif-canvas", "divergence", "reference-shelf", "canonview", "book-import", "context-inspector", "sharing", "book-settings", "translation", "enrichment-compose", "enrichment-proposals", "enrichment-gaps", "enrichment-sources", "enrichment-jobs", "enrichment-settings", "user-guide", "quality", "quality-promises", "quality-critic", "quality-coverage", "quality-canon", "quality-canon-rules", "quality-corrections", "quality-heal", "progress", "flywheel", "motif-library", "motif-graph", "quality-conformance", "world-map", "place-graph", "cast", "character-arc"],
                    "description": (
                        "The studio panel to open. 'compose' = the AI co-writer chat; "
                        "'scene-compose' = draft a scene with the AI — stream a ghost "
                        "draft or Diverge into several candidates, edit/accept one into "
                        "the editor, and your regenerate/reject/edit choices train the "
                        "model (the correction flywheel); "
                        "'chapter-assemble' = assemble a whole chapter from its scenes — "
                        "single-pass generate or stitch the done scene drafts, review the "
                        "editable preview, accept it into the editor (the second correction "
                        "producer); "
                        "'editor' = the manuscript editor; 'planner' = the PlanForge "
                        "novel-system planner; 'agent-mode' = mission control for an "
                        "autonomous multi-chapter authoring run — start/pause/resume a run "
                        "over an approved plan, review each drafted chapter's diff + critic "
                        "verdict, accept/reject/revert; 'usage' = spend/tokens/request log; "
                        "'notifications' = job completions & alerts; 'settings' = "
                        "account/providers/translation settings; 'trash' = restore "
                        "deleted books/chapters; 'steering' = author the book's steering "
                        "rules (persistent author guidance injected into book-scoped turns); "
                        "'extensions' = manage plugins, skills, MCP servers, commands & "
                        "hooks; 'proposals' = review skills the agent proposed (approve/reject); "
                        "'workflows' = manage saved multi-step workflow recipes (enable/disable, "
                        "delete your own); 'workflow-proposals' = review workflows the agent "
                        "proposed and approve (mints the workflow) or reject; "
                        "'glossary' = the book's entity list — search, filter, bulk status/delete; "
                        "'glossary-ontology' = the book's kinds/genres/attributes; "
                        "'glossary-unknown' = reassign unrecognized entities to a kind; "
                        "'glossary-ai-suggestions' = review AI-drafted entities; "
                        "'glossary-merge-candidates' = review likely-duplicate entities; "
                        "'wiki' = the book's generated wiki articles — browse, read, create, "
                        "regenerate; "
                        "'knowledge' = browse and open the user's knowledge-graph projects; "
                        "'kg-overview' = a KG project's summary and quick actions; "
                        "'kg-entities' = browse/search KG entities (a project or all projects); "
                        "'kg-timeline' = in-story events by chronological/narrative order; "
                        "'kg-evidence' = semantic search over chapter/chat passages; "
                        "'kg-gap' = high-mention entities missing from the glossary; "
                        "'kg-proposals' = pending glossary/wiki/enrichment suggestions for this book; "
                        "'kg-schema' = adopt/author/view/sync the book's KG schema; "
                        "'kg-graph' = explore the project's entity relationship graph; "
                        "'kg-insights' = extraction config quality & model performance across projects; "
                        "'kg-jobs' = monitor extraction jobs across all projects; "
                        "'kg-bio' = the user's cross-book author bio; "
                        "'kg-privacy' = export or delete the user's knowledge-graph data; "
                        "'kg-triage' = resolve extracted elements that didn't match the schema (map/add/dismiss); "
                        "'search' = search the book's prose (text) or lore drawers (semantic); a hit opens the editor there; "
                        "'jobs-list' = monitor the user's background jobs and tasks; "
                        "'books' = browse and read the user's other books (view-only, does not "
                        "leave the current book's studio); 'leaderboard-books' = top-ranked books; "
                        "'leaderboard-authors' = top-ranked authors; 'leaderboard-translators' = "
                        "top-ranked translators; 'leaderboard-trending' = currently trending books; "
                        "'chapter-browser' = sort/filter/search and bulk-act across this book's "
                        "chapters (title or full-text content search); "
                        "'scene-browser' = browse every scene in the book — the written prose and "
                        "its authored plan joined side by side (shows imported scenes even before a "
                        "plan exists); "
                        "'scene-inspector' = read/edit every field of ONE selected scene (intent, "
                        "craft, tension, grounding) — the detail pane over a selection; "
                        "'plan-hub' = the whole book's plan as a graph canvas — arc/sub-arc lanes "
                        "with their chapters and scenes, scene-link edges, and problem/staleness "
                        "decorations; pan/zoom, expand an arc to see its chapters; "
                        "'arc-inspector' = read/edit ONE arc or saga of the book's spec tree — "
                        "title/goal/status, the cascade-resolved plot tracks and cast roster, its "
                        "chapter span, open promises, and template provenance. This is the structure "
                        "that steers every generation; "
                        "'arc-templates' = the arc-template library — browse/create/adopt reusable "
                        "multi-chapter arc structures (parallel plot threads over a chapter span), "
                        "apply one onto this book, or save one of your arcs as a template; "
                        "'divergence' = manage the book's what-if derivatives (dị bản) — list "
                        "the canonical Work and every branched version, switch the whole studio "
                        "to one, archive one, read its spec, or spawn a new branch from a chapter; "
                        "'canonview' = what canon knows as of the chapter in focus — entities "
                        "present/established by now (glossary) and canon state + timeline "
                        "(knowledge), windowed to the active chapter; "
                        "'book-import' = import chapters from text/.docx/.epub files, or a whole "
                        "book from a PDF (with optional AI image captioning); "
                        "'context-inspector' = trace what context management did per turn "
                        "(budget gauge, allocation map, Planner→Compiler decisions); "
                        "'sharing' = this book's visibility (private/unlisted/public), unlisted "
                        "share-link, and collaborator invites/roles; "
                        "'book-settings' = this book's title/description/language/summary, cover "
                        "image, genre tags, and world grouping; "
                        "'translation' = the book's translation coverage matrix — filter by "
                        "language, bulk-translate or extract glossary entities, drill into "
                        "per-chapter version history; "
                        "'enrichment-compose' = create a new enriched lore draft (expand/paste/"
                        "upload/intent); "
                        "'enrichment-proposals' = review AI-proposed enriched lore (approve/"
                        "reject/promote); "
                        "'enrichment-gaps' = detect under-described entities and auto-enrich "
                        "them; "
                        "'enrichment-sources' = manage license-tagged source corpora for "
                        "retrieval/recook; "
                        "'enrichment-jobs' = monitor/resume background enrichment jobs; "
                        "'enrichment-settings' = author this book's enrichment de-bias profile; "
                        "'user-guide' = the catalog-driven help panel — every Studio tool, "
                        "grouped by area, with an Open button for each.; "
                        "'quality' = the Quality launcher — cards to open promises/critic/"
                        "coverage/canon-issues; "
                        "'quality-promises' = the open-promise debt ledger (setups not yet paid off); "
                        "'quality-critic' = per-chapter coherence/voice/pacing/canon critic scores; "
                        "'quality-coverage' = whole-book audit of which outline promises got paid off; "
                        "'quality-canon' = book-wide confirmed canon contradictions from generation "
                        "and knowledge extraction; "
                        "'motif-library' = the narrative-craft library (套路/爽点/打脸 tropes) — browse "
                        "by tier (yours/book/shared/system/public catalog/mined drafts), create, "
                        "adopt from the catalog, mine your corpus, inspect a motif's detail and its "
                        "relationship graph (composed_of/precedes/variant_of); "
                        "'motif-graph' = the book-wide motif relationship graph as a draggable "
                        "canvas (nodes = your + book-shared motifs, edges = composed_of/precedes/"
                        "variant_of) with your own saved node layout; "
                        "'quality-conformance' = the beat-by-beat trace of whether a chapter's PROSE "
                        "realized its planned motif beats (spec-vs-prose) — per-scene realized/not + "
                        "tension band, regenerate a missed scene, or re-run the check (BYOK); "
                        "'world-map' = create and edit a world's reference map(s) — upload a base "
                        "image, drop and drag location pins, draw and reshape regions, and bind them "
                        "to glossary/KG location entities; "
                        "'place-graph' = the book's places (locations) as a draggable node graph — add "
                        "a place, link two places (contains/borders/route_to), arrange them (saved "
                        "server-side), set a backdrop; location entities only; "
                        "'cast' = the book's cast codex — every character/place/organization/concept, "
                        "grouped and searchable, each with its spoiler-safe story-state; create/rename/"
                        "retire entities and edit aliases/kind; "
                        "'character-arc' = ONE character's events on a timeline (spoiler-cut at the "
                        "reading position), the active→gone band, and the 1-hop relations."
                    ),
                },
            },
            "required": ["panel_id"],
            "additionalProperties": False,
        },
    },
}

# F7c (2026-07-19) — compact variant of ui_open_studio_panel. The full per-panel prose
# above is ~2.4k tokens on EVERY studio turn though a panel is opened rarely. This variant
# KEEPS the exact panel_id enum (Frontend-Tool Contract: the closed set is correctness — a
# free-string panel_id was the original silent-no-op bug; never trim the enum) and replaces
# the prose with a terse area-grouped guide (~0.7k). Most enum ids are self-describing
# (`kg-timeline`, `quality-critic`, `motif-graph`); the groups orient the model, and it can
# still pass any id. Gated by settings.compact_studio_panel_desc (default off) → A/B.
_COMPACT_PANEL_DESC = (
    "The studio panel to open (pass one panel_id from the enum). Panels by area — "
    "WRITE: compose (AI co-writer chat), scene-compose, chapter-assemble, editor, agent-mode "
    "(autonomous multi-chapter run). "
    "PLAN/STRUCTURE: planner (PlanForge), plan-hub, plan-passes, decompose, arc-inspector, "
    "arc-templates, structure-templates, scene-browser, scene-inspector, chapter-browser, "
    "whatif-canvas, divergence (what-if versions), reference-shelf, canonview. "
    "LORE (glossary): glossary, glossary-ontology, glossary-unknown, glossary-ai-suggestions, "
    "glossary-merge-candidates, wiki, cast, character-arc. "
    "KNOWLEDGE GRAPH: knowledge, kg-overview, kg-entities, kg-timeline, kg-evidence, kg-gap, "
    "kg-proposals, kg-schema, kg-graph, kg-insights, kg-jobs, kg-bio, kg-privacy, kg-triage. "
    "QUALITY: quality, quality-promises, quality-critic, quality-coverage, quality-canon, "
    "quality-canon-rules, quality-corrections, quality-heal, quality-conformance, progress, flywheel. "
    "MOTIFS: motif-library, motif-graph. "
    "WORLD: world-map, place-graph. "
    "LANGUAGES: translation (the multi-language translation coverage matrix — translate "
    "chapters into other languages, per-language version history). "
    "ENRICH LORE (expanding descriptions, NOT languages): enrichment-compose, "
    "enrichment-proposals, enrichment-gaps, enrichment-sources, enrichment-jobs, enrichment-settings. "
    "BOOK/ACCOUNT: books, book-import, book-settings, sharing, steering, context-inspector, "
    "extensions, proposals, workflows, workflow-proposals, settings, usage, notifications, "
    "jobs-list, trash, search, user-guide, quality-canon. "
    "DISCOVER: leaderboard-books, leaderboard-authors, leaderboard-translators, leaderboard-trending. "
    "If unsure which panel fits, open 'user-guide' (the catalog of every Studio tool)."
)


# F7c M4 — deterministic navigation-intent gate for ui_open_studio_panel. The panel
# navigator is a click/keypress the user can do manually, so it is advertised (paying its
# ~880 tok) ONLY when the turn actually asks to open/see a panel. Biased to PRECISION: a
# missed nav request just means the user clicks the panel; a FALSE POSITIVE (opening a panel
# on a plain writing turn) is the harmful error. So the trigger is a nav VERB *and* a
# PANEL-SPECIFIC noun — and the overloaded writing words (scene/arc/plan/chapter/character/
# beat) are deliberately NOT panel nouns, so "write a scene" / "plan the arc" never fire.
_NAV_VERBS: tuple[str, ...] = (
    "open", "show", "view", "display", "navigate", "go to", "goto", "bring up",
    "pull up", "switch to", "jump to", "take me to", "let me see", "let me open",
    "where is", "where can i", "i want to see", "manage", "let me manage",
    "import", "upload",  # the book-import panel's own opener verbs
)
_PANEL_NOUNS: frozenset[str] = frozenset({
    # panel-shape words (rare in prose-writing instructions)
    "panel", "tab", "dock", "matrix", "canvas", "inspector", "browser", "timeline",
    "graph", "leaderboard", "dashboard", "hub", "shelf", "codex",
    # panel-name words (a view, not a writing noun)
    "glossary", "wiki", "ontology", "settings", "notifications", "translation",
    "translations", "enrichment", "motif", "motifs", "quality", "critic", "coverage",
    "conformance", "divergence", "what-if", "whatif", "kg", "knowledge", "world",
    "map", "cast", "editor", "compose", "planner", "import", "proposals", "workflow",
    "workflows", "steering", "usage", "trash", "sharing", "flywheel", "promises",
    "leaderboards", "wireframe",
})


def _is_panel_nav_intent(message: str | None) -> bool:
    """True when the turn reads as a request to OPEN/SEE a studio panel (nav verb +
    panel-specific noun). Deterministic; precision-biased (see the note above)."""
    m = (message or "").lower()
    if not m.strip():
        return False
    if not any(v in m for v in _NAV_VERBS):
        return False
    # word-ish token scan so "map" doesn't match "roadmap"; the [a-z\-]* class keeps
    # hyphenated panel nouns ("what-if") intact as a single token.
    tokens = set(_re.findall(r"[a-z][a-z\-]*", m))
    return bool(tokens & _PANEL_NOUNS)


def _studio_panel_tool(*, compact: bool) -> dict:
    """ui_open_studio_panel with the full (default) or compact panel_id description.
    Same schema + IDENTICAL enum either way — only the guidance prose differs."""
    if not compact:
        return UI_OPEN_STUDIO_PANEL_TOOL
    td = deepcopy(UI_OPEN_STUDIO_PANEL_TOOL)
    td["function"]["parameters"]["properties"]["panel_id"]["description"] = _COMPACT_PANEL_DESC
    return td


UI_FOCUS_MANUSCRIPT_UNIT_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "ui_focus_manuscript_unit",
        "description": (
            "Open and focus a specific chapter in the Writing Studio manuscript editor. Use "
            "when the user wants to write or see a particular chapter in the studio. Opens "
            "immediately — no confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "chapter_id": {"type": "string", "description": "The chapter to open in the editor (UUID)."},
                "scene_id": {"type": "string", "description": "Optional scene to focus within the chapter (UUID)."},
            },
            "required": ["chapter_id"],
            "additionalProperties": False,
        },
    },
}

_STUDIO_UI_TOOLS: list[dict] = [UI_OPEN_STUDIO_PANEL_TOOL, UI_FOCUS_MANUSCRIPT_UNIT_TOOL]


# ── MCP-fanout C-CONFIRM — generic Tier-W/S confirm (generalizes glossary) ────
# The `domain` selects which /v1/<domain>/actions/confirm endpoint commits; the
# optional `items[]` array renders ONE batch card with a single Apply (H2 — so
# "publish all my drafts" is one click, not N).
CONFIRM_ACTION_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "confirm_action",
        "description": (
            "Ask the user to CONFIRM a high-impact action (publish, delete, start a "
            "PRICED job, change a default) that you proposed with a domain MCP tool. "
            "Pass the `confirm_token`, `descriptor`, and `domain` you received from "
            "that propose call. High-impact and irreversible changes ALWAYS require "
            "explicit human confirmation — the action is NOT applied automatically. "
            "For a BULK action (e.g. publish several chapters) pass `items` so the "
            "user gets ONE card with a single Apply, not many cards. After the user "
            "decides you receive an `outcome`: `action_done` (applied), "
            "`token_expired` (the confirmation lapsed — propose again), `action_error` "
            "(it failed), or `cancelled` (the user declined). State that the change "
            "happened ONLY when the outcome is `action_done`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "confirm_token": {
                    "type": "string",
                    "description": "The confirm_token returned by the propose call.",
                },
                "descriptor": {
                    "type": "string",
                    "description": (
                        "The action descriptor from the propose call "
                        "(e.g. 'book.publish', 'translation.start_job')."
                    ),
                },
                "title": {
                    "type": "string",
                    "description": "Human-readable title of the action, shown on the card.",
                },
                "domain": {
                    "type": "string",
                    "enum": ["glossary", "book", "composition", "translation", "settings"],
                    "description": "Selects which service commits the action on Confirm.",
                },
                "items": {
                    "type": "array",
                    "description": (
                        "OPTIONAL — for a BATCH confirm: one entry per affected row "
                        "(e.g. the chapters to publish). The browser renders one card "
                        "listing all of them with a single Apply."
                    ),
                    "items": {"type": "object", "additionalProperties": True},
                },
            },
            "required": ["confirm_token", "descriptor", "title", "domain"],
            "additionalProperties": False,
        },
    },
}


# ── MCP-fanout C-PROPOSE — generic record diff card ──────────────────────────
# Generalizes glossary_propose_entity_edit for book/composition record edits.
# Suspends; on Apply the FE issues the domain's version-checked PATCH
# (If-Match: base_version → 409/412 on drift, H8).
PROPOSE_RECORD_EDIT_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "propose_record_edit",
        "description": (
            "Propose one or more edits to the fields of an EXISTING record (a book's "
            "metadata, a chapter's title, etc.) — applied together. The changes are "
            "shown as a diff card with an Apply button and are NOT applied "
            "automatically. BEFORE calling this, read the record's current values and "
            "its version token (pass it as `base_version`). After the user decides you "
            "receive an `outcome`: `applied_saved` (saved), `applied_conflict` (the "
            "record changed since you read it — re-read and propose afresh), "
            "`applied_error` (the save failed), or `dismissed`. State the change was "
            "made ONLY when the outcome is `applied_saved`."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "enum": ["glossary", "book", "composition", "translation", "settings"],
                    "description": "Which service owns the record.",
                },
                "resource_ref": {
                    "type": "object",
                    "description": "Domain-specific ids, e.g. {book_id} or {book_id, chapter_id}.",
                    "additionalProperties": True,
                },
                "base_version": {
                    "type": "string",
                    "description": "The record's version token (optimistic concurrency, H8).",
                },
                "changes": {
                    "type": "array",
                    "description": "One or more field changes to apply together.",
                    "items": {
                        "type": "object",
                        "properties": {
                            "field_label": {
                                "type": "string",
                                "description": "Human-readable field name shown on the diff card.",
                            },
                            "old_value": {"type": "string", "description": "The current value."},
                            "new_value": {"type": "string", "description": "The proposed value."},
                            "target": {
                                "type": "string",
                                "description": "Machine field key the PATCH writes.",
                            },
                            "target_ref": {
                                "type": "string",
                                "description": "Optional sub-resource id for the field.",
                            },
                        },
                        "required": ["field_label", "old_value", "new_value", "target"],
                        "additionalProperties": False,
                    },
                },
                "rationale": {
                    "type": "string",
                    "description": "Optional one-line explanation shown to the user.",
                },
            },
            "required": ["domain", "resource_ref", "base_version", "changes"],
            "additionalProperties": False,
        },
    },
}


# Map core frontend-tool names → their schema, so the discovery layer can
# advertise the always-on core by name (C-FT).
#
# Phase 3 (P3.2): the ui_* tools are NO LONGER here — they are ai-gateway federated
# directive tools now, so the always-on nav ui_* (ui_navigate/open_book/show_panel/
# watch_job in ALWAYS_ON_CORE_NAMES) resolve their def from the federated CATALOG
# (exactly like `web_search`: `catalog_index.get(name) or generic_frontend_tool_def(name)`
# → the catalog def, else None ⇒ a degraded gateway simply omits it, never advertises a
# fabricated schema). The studio ui_* keep their advertisement via `frontend_tool_defs`
# (which references UI_OPEN_STUDIO_PANEL_TOOL / UI_FOCUS_MANUSCRIPT_UNIT_TOOL directly and
# preserves the F7c nav-intent gate). The UI_*_TOOL constants remain for that + as the
# ai-gateway-down reference; P4 sources the studio pair from the catalog too.
_GENERIC_FRONTEND_TOOLS_BY_NAME: dict[str, dict] = {
    "confirm_action": CONFIRM_ACTION_TOOL,
    "propose_record_edit": PROPOSE_RECORD_EDIT_TOOL,
    # propose_edit removed (Phase 2 P2.2) — now an ai-gateway consumer-local tool; the
    # PROPOSE_EDIT_TOOL const is still advertised via frontend_tool_defs (editor branch).
}


def generic_frontend_tool_def(name: str) -> dict | None:
    """The schema for a generic (cross-domain) frontend tool by name, or None."""
    return _GENERIC_FRONTEND_TOOLS_BY_NAME.get(name)


# The COMPLETE frontend-tool schema map (generic + the two book-scoped glossary
# tools) — every name in FRONTEND_TOOL_NAMES resolves here. Distinct from
# `generic_frontend_tool_def`, which is deliberately the cross-domain-advertisement
# subset (it must NOT surface the glossary tools on non-book surfaces). This map is
# for the Phase 0 VALIDATION seam: it resolves a tool's canonical inputSchema even
# when the tool is not in THIS turn's advertised set, so no frontend tool can slip
# past validation on an unusual (called-but-not-advertised) path.
_ALL_FRONTEND_TOOLS_BY_NAME: dict[str, dict] = {
    **_GENERIC_FRONTEND_TOOLS_BY_NAME,
    "glossary_propose_entity_edit": GLOSSARY_PROPOSE_EDIT_TOOL,
    "glossary_confirm_action": GLOSSARY_CONFIRM_ACTION_TOOL,
}


def frontend_tool_def_by_name(name: str) -> dict | None:
    """The canonical schema-bearing def for ANY frontend tool by name — the whole
    set, for the validation seam. None for a non-frontend name."""
    return _ALL_FRONTEND_TOOLS_BY_NAME.get(name)


def frontend_tool_defs(
    *,
    editor: bool = False,
    book_scoped: bool = False,
    studio: bool = False,
    compact_studio_panel: bool = False,
    studio_panel_nav: bool = True,
) -> list[dict]:
    """Frontend tool schemas to advertise, by surface.

    ``editor`` — the chapter editor panel (book_id + chapter_id): adds the prose
    write-back ``propose_edit``.
    ``book_scoped`` — any book-scoped chat (editor OR a glossary-page/reader chat
    carrying a book context): adds ``glossary_propose_entity_edit``.
    ``studio`` — the Writing Studio compose panel (studio_context): adds the studio
    dock-navigation tools (open panel / focus manuscript unit — #09 Lane A).
    ``compact_studio_panel`` (F7c) — advertise ui_open_studio_panel with the compact
    area-grouped description instead of the full per-panel prose (same enum). Off ⇒
    byte-identical to pre-F7c.
    ``studio_panel_nav`` (F7c M4) — include the ui_open_studio_panel NAVIGATOR this turn.
    Pass False on a plain writing turn (no navigation intent) to omit its ~880 tok;
    ui_focus_manuscript_unit (open a chapter, part of the writing loop) is unaffected.
    Default True ⇒ pre-M4 behavior.

    The flags are independent: a glossary-page chat is book_scoped but not editor.
    """
    defs: list[dict] = []
    if editor:
        defs.append(PROPOSE_EDIT_TOOL)
    if book_scoped:
        defs.append(GLOSSARY_PROPOSE_EDIT_TOOL)
        defs.append(GLOSSARY_CONFIRM_ACTION_TOOL)
    if studio:
        if studio_panel_nav:
            defs.append(_studio_panel_tool(compact=compact_studio_panel))
        defs.append(UI_FOCUS_MANUSCRIPT_UNIT_TOOL)
    return defs


def is_frontend_tool(name: str) -> bool:
    return name in FRONTEND_TOOL_NAMES


# ── Phase 0 (frontend-tools → MCP migration) — the MCP-native validation seam ──
# A frontend tool advertised to the LLM carries a canonical JSON-Schema (its
# `function.parameters`, JSON Schema 2020-12) exactly like a backend MCP tool.
# Backend tools inherit arg VALIDATION for free (the domain-service SDK validates
# `arguments` against inputSchema before dispatch); frontend tools were a pre-MCP
# construct that SUSPENDED the run on the raw args with NO validation. That gap
# shipped the reported bug (session 019f771a): the model called `propose_edit`
# with `propose_record_edit`'s args — nothing rejected it, so the run suspended
# and rendered an Apply card that could never apply.
#
# This closes the gap at the source for ALL frontend tools in one place: validate
# the (already-unwrapped) args against the tool's OWN canonical schema before the
# suspend, and on a mismatch feed the model the SAME `required: missing
# properties` signal the domain validator emits — the shape it already knows how
# to repair. Uses the STANDARD Draft202012Validator against the canonical schema
# (NOT a hand-rolled per-tool check), so Phases 1-3 reuse the exact same schema.
#
# The marker substring MUST match stream_service._MISSING_REQUIRED_ARGS_MARKER so
# a frontend-tool miss feeds the same cross-tool blank/invalid-args streak breaker
# the backend feeds. Kept in sync deliberately (two consumers, one contract).
_MISSING_REQUIRED_MARKER = "required: missing properties"


def _canonical_input_schema(tool_def: dict | None) -> dict | None:
    """The tool's JSON-Schema for its arguments — `function.parameters` for an
    OpenAI-shaped def (how both the generic frontend defs and the normalized
    discovery-catalog entries are stored). None if absent."""
    schema = (((tool_def or {}).get("function") or {}).get("parameters"))
    return schema if isinstance(schema, dict) and schema else None


def validate_frontend_tool_args(
    name: str, args: object, tool_def: dict | None
) -> str | None:
    """Validate a frontend tool's (unwrapped) args against its canonical
    inputSchema. Return None when valid (or when there is nothing to validate
    against — FAIL-OPEN, so a schema-less tool is never blocked); otherwise a
    compact, model-repairable error string.

    The message prioritises the two shapes the incident exercised:
      * missing top-level required props  → ``required: missing properties: [...]``
        (contains the shared streak marker),
      * disallowed props (additionalProperties:false) → the validator's message,
    then falls back to the first schema error (type/enum/...). This is the exact
    root-cause fix: a `propose_edit`-with-`propose_record_edit`-args call is
    rejected here, before any suspend, for every frontend tool.
    """
    schema = _canonical_input_schema(tool_def)
    if schema is None or not isinstance(args, dict):
        return None  # fail-open: no schema, or a non-object payload we can't judge
    try:
        errors = list(Draft202012Validator(schema).iter_errors(args))
    except Exception:  # noqa: BLE001 — a malformed schema must never block a call
        return None
    if not errors:
        return None

    parts: list[str] = []
    top_required = [
        p for p in (schema.get("required") or []) if p not in args
    ]
    if top_required:
        parts.append(f"{_MISSING_REQUIRED_MARKER}: {top_required}")
    extra = next((e for e in errors if e.validator == "additionalProperties"), None)
    if extra is not None:
        parts.append(extra.message)
    if not parts:
        e0 = errors[0]
        loc = "/".join(str(p) for p in e0.absolute_path) or "(root)"
        parts.append(f"{loc}: {e0.message}" if loc != "(root)" else e0.message)
    return f'invalid arguments for "{name}": ' + "; ".join(parts)
