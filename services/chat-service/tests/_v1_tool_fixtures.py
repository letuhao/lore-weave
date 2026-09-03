"""Frozen tool definitions kept ONLY as test fixtures — the production module is deleted.

🔴 THESE ARE NOT A SOURCE OF TRUTH AND MUST NEVER BECOME ONE. They are the schema dicts that
lived in `app/services/frontend_tools.py` until V7 (2026-09-03) removed it. Every one of them has
a LIVE owner elsewhere:

    propose_edit                      services/ai-gateway/src/mcp/propose-edit-tool.ts
    ui_open_studio_panel, ui_focus_*  services/ai-gateway/src/mcp/ui-tools.ts
    confirm_action, glossary_*        services/ai-gateway/src/mcp/confirm-tools.ts

and the CROSS-LANGUAGE SoT for all of them is `contracts/frontend-tools.contract.json`.

They survive here because a dozen chat-service tests use a tool def as a fixture — a plausible
`tools=[...]` argument to drive a turn — and rebuilding twelve hand-written dicts would be worse
than moving these once. A test that wants to assert a SHAPE must assert it against the contract or
against ai-gateway's own spec, never against this file: a snapshot asserting itself is the vacuity
this loop has now found in four places.

The production module was deleted because it had ZERO production references left — verified per
symbol, not assumed — once `frontend_tool_defs` stopped advertising anything. That also closes
`D-P3-RETIRE-UI-FRONTEND-DEFS`, which had tracked the `ui_*` and `propose_edit` residue since P3.2.
"""
from __future__ import annotations

import re
from copy import deepcopy

PROPOSE_EDIT_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "propose_edit",
        # K10 — MUST stay byte-identical to ai-gateway's copy
        # (src/mcp/propose-edit-tool.ts), which owns this tool since P2.2 and whose own
        # comment calls the prose "a MOVE, not a duplication — Phase 4 removes
        # chat-service's copy". The move never finished, and the leftover copy had already
        # drifted: this text said "the user's current selection" where ai-gateway says
        # "the current selection". Harmless in itself, but the DESCRIPTION is what decides
        # WHEN the model reaches for a tool, and it is the one field the contract SoT does
        # not pin (it slices args + required only). Pinned by
        # TestResidualAdvertisedDefsMatchContract::test_description_matches_ai_gateway.
        "description": (
            "Propose an edit to the chapter the user is currently writing. The "
            "edit is shown to the user with an Apply button and is NOT applied "
            "automatically — the user reviews it first. Use this to suggest "
            "inserting new prose at the cursor, or rewriting the current "
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

_UUID_PATTERN = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"

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
            "that the change was made ONLY when the outcome is `applied_saved`. "
            # Measured 2026-07-22 (S00b real-stack E2E): asked to "Add a character called X",
            # gemma called THIS tool 13× with entity_id="new_entity_id_placeholder" — an EDIT
            # tool has no target for a CREATE. Say so where the model is actually looking.
            "This tool ONLY EDITS an entity that ALREADY EXISTS. To CREATE a new entity that "
            "does not exist yet, call `tool_load(name='glossary_propose_entities')` and use "
            "that instead — do NOT call this with a made-up or placeholder entity_id."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "book_id": {
                    "type": "string",
                    "pattern": _UUID_PATTERN,
                    "description": "The book the entity belongs to (UUID).",
                },
                "entity_id": {
                    "type": "string",
                    "pattern": _UUID_PATTERN,
                    "description": (
                        "The entity to edit (UUID, from glossary_get_entity/glossary_search). "
                        "MUST be a real existing entity's id — never a placeholder."
                    ),
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
        # 🔴 **CP-5 · THIS TOOL WAS ON THE WIRE FOR WEEKS DECLARING NOTHING.** Every one of the 315
        # federated tools carries `tier` + `scope`; the four chat-service serves itself carried
        # neither, so `declared_lane` returned None for them while its own docstring said
        # *"measured on the live catalogue: 315/315 tools declare a tier"* — measured on the
        # population that excluded the only ones that did not. Undeclared, this tool could not be
        # derived, therefore not admitted, therefore could not carry a contract — which is why the
        # corpus's largest 0%-success tool (101 calls, 12 sessions) had no member to fix it.
        #
        # `tier: W` is read off this tool's OWN behaviour, not chosen: it suspends the turn and the
        # browser renders a diff card the user must Apply, which is the definition of W. `served_by`
        # is the load-bearing one — the NAME says `glossary_`, and `derive.resolve_service` is a
        # prefix table, so without this the manifest would record glossary-service as the owner of a
        # tool glossary-service does not serve. The name lying about the owner is a real defect; a
        # rename is a migration with live traffic (supersession), so the declaration carries the
        # truth today and the rename stays a separate decision.
        "_meta": {"tier": "W", "scope": "book", "served_by": "chat-service"},
    },
}

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
        #: CP-5 · declared, for the reason on `GLOSSARY_PROPOSE_EDIT_TOOL`. `W` is this tool's whole
        #: purpose — it exists to surface the human confirm step, and its own comment says
        #: *"high-impact and destructive changes ALWAYS require explicit human confirmation."*
        #: `scope: none` rather than `book`, and the parameters are the evidence: this tool takes a
        #: `confirm_token` and nothing else that identifies a book. The token carries the scope,
        #: which is what makes it a confirm step rather than a second chance to name a target.
        "_meta": {"tier": "W", "scope": "none", "served_by": "chat-service",
                  "_confirm_step": True},
    },
}

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
                    "enum": ["compose", "scene-compose", "chapter-assemble", "editor", "planner", "agent-mode", "usage", "notifications", "settings", "trash", "steering", "style-voice", "extensions", "proposals", "workflows", "workflow-proposals", "glossary", "glossary-ontology", "glossary-unknown", "glossary-ai-suggestions", "glossary-merge-candidates", "world-setup", "wiki", "knowledge", "kg-overview", "kg-entities", "kg-timeline", "kg-evidence", "kg-gap", "kg-proposals", "kg-schema", "kg-graph", "kg-insights", "kg-jobs", "kg-bio", "kg-privacy", "kg-triage", "search", "jobs-list", "books", "leaderboard-books", "leaderboard-authors", "leaderboard-translators", "leaderboard-trending", "chapter-browser", "scene-browser", "scene-inspector", "plan-hub", "decompose", "arc-inspector", "arc-templates", "structure-templates", "plan-passes", "whatif-canvas", "divergence", "reference-shelf", "canonview", "book-import", "context-inspector", "sharing", "book-settings", "translation", "enrichment-compose", "enrichment-proposals", "enrichment-gaps", "enrichment-sources", "enrichment-jobs", "enrichment-settings", "user-guide", "quality", "quality-promises", "quality-critic", "quality-coverage", "quality-canon", "quality-canon-rules", "quality-corrections", "quality-heal", "progress", "flywheel", "motif-library", "motif-graph", "quality-conformance", "world-map", "place-graph", "cast", "character-arc"],
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
                        "'world-setup' = build the cast/world + relationships from a description (the deterministic pipeline — plan, review, build, approve); "
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
        #: CP-5 · declared. `W` is stated by this section's own header — *"generic Tier-W/S
        #: confirm"* — so the tier is read out of the code rather than chosen. `scope: none`
        #: because it is the cross-domain tool: `domain` is a parameter, not a scope key.
        "_meta": {"tier": "W", "scope": "none", "served_by": "chat-service"},
    },
}


# V7 (2026-09-03) — `frontend_tools` is DELETED. These names are frozen test fixtures now; every
# one has a live owner in ai-gateway and a cross-language SoT in the contract. See
# tests/_v1_tool_fixtures.py.
FRONTEND_TOOL_NAMES: frozenset[str] = frozenset()


def frontend_tool_defs(**_kw) -> list:
    """Nothing is advertised from chat-service any more; kept so the call sites read honestly."""
    return []


def is_frontend_tool(_name: str) -> bool:
    """chat-service intercepts nothing — the whole point of V7."""
    return False


# The one predicate that SURVIVED the module, re-exported from its real home so a test importing
# it here gets the live function rather than a copy that can drift.
from app.services.browser_tools import is_browser_executed  # noqa: E402,F401


def generic_frontend_tool_def(_name: str):
    """Always None: chat-service serves no tool schema of its own any more.

    Kept honest rather than deleted, because the ADVERTISE path used to read
    `catalog_index.get(name) or generic_frontend_tool_def(name)` and the `or` is exactly how a
    local schema reached the model on every turn. A test asserting this returns None is asserting
    that the fallback cannot come back.
    """
    return None


def frontend_tool_def_by_name(_name: str):
    """Always None — see `generic_frontend_tool_def`."""
    return None


#: The maps the contract test unions to build ALL_FRONTEND_TOOLS. Frozen fixtures, like everything
#: else here — the live schemas are ai-gateway's and the SoT is the contract JSON.
_GENERIC_FRONTEND_TOOLS_BY_NAME: dict = {"confirm_action": CONFIRM_ACTION_TOOL}
_ALL_FRONTEND_TOOLS_BY_NAME: dict = {
    "propose_edit": PROPOSE_EDIT_TOOL,
    "glossary_propose_entity_edit": GLOSSARY_PROPOSE_EDIT_TOOL,
    "glossary_confirm_action": GLOSSARY_CONFIRM_ACTION_TOOL,
    "confirm_action": CONFIRM_ACTION_TOOL,
    "ui_open_studio_panel": UI_OPEN_STUDIO_PANEL_TOOL,
    "ui_focus_manuscript_unit": UI_FOCUS_MANUSCRIPT_UNIT_TOOL,
}
