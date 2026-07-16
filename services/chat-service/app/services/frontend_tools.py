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
        "propose_edit",
        "glossary_propose_entity_edit",
        "glossary_confirm_action",
        # generic, cross-domain (MCP-fanout):
        "ui_navigate",
        "ui_open_book",
        "ui_open_chapter",
        "ui_show_panel",
        "ui_watch_job",
        "confirm_action",
        "propose_record_edit",
        # Writing Studio surface (#09 Lane A) — advertised only when the request carries
        # studio_context; the FE executes them against the StudioHost (resolve-immediately).
        "ui_open_studio_panel",
        "ui_focus_manuscript_unit",
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


# ── MCP-fanout C-NAV — navigation/render frontend tools ──────────────────────
# Frontend tools (suspend→browser) but RESOLVE-IMMEDIATELY: no human Apply gate.
# The FE executes the navigation and POSTs the resolve straight back. Advertised
# only on the agui /chat surface (F2 — legacy clients never see them, so never
# suspend / hang).

UI_NAVIGATE_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "ui_navigate",
        "description": (
            "Navigate the user's browser to a page (e.g. '/books', '/jobs', "
            "'/settings'). Use this to SHOW the user something rather than dumping "
            "data into chat. The browser navigates immediately — no confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "An allowlisted in-app route, e.g. '/books' or '/settings'.",
                },
            },
            "required": ["path"],
            "additionalProperties": False,
        },
    },
}

UI_OPEN_BOOK_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "ui_open_book",
        "description": (
            "Open a book's detail page, optionally on a specific tab. Use when the "
            "user wants to SEE a book or one of its surfaces (translation, glossary, "
            "wiki...). Opens immediately."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "The book to open (UUID)."},
                "tab": {
                    "type": "string",
                    "enum": [
                        "overview", "translation", "glossary",
                        "enrichment", "wiki", "settings",
                    ],
                    "description": "Optional tab to open the book on.",
                },
            },
            "required": ["book_id"],
            "additionalProperties": False,
        },
    },
}

UI_OPEN_CHAPTER_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "ui_open_chapter",
        "description": (
            "Open a chapter in the editor or reader. Use when the user wants to write "
            "or read a specific chapter. Opens immediately."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "book_id": {"type": "string", "description": "The book (UUID)."},
                "chapter_id": {"type": "string", "description": "The chapter (UUID)."},
                "mode": {
                    "type": "string",
                    "enum": ["edit", "read"],
                    "description": "edit = open the editor; read = open the reader.",
                },
            },
            "required": ["book_id", "chapter_id", "mode"],
            "additionalProperties": False,
        },
    },
}

UI_SHOW_PANEL_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "ui_show_panel",
        "description": (
            "Open a tab or panel on the current view (e.g. the glossary, translation, "
            "or wiki panel). Use to reveal a surface without leaving the page. Opens "
            "immediately."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "panel": {"type": "string", "description": "The panel/tab name to show."},
                "args": {
                    "type": "object",
                    "description": "Optional panel-specific arguments.",
                    "additionalProperties": True,
                },
            },
            "required": ["panel"],
            "additionalProperties": False,
        },
    },
}

UI_WATCH_JOB_TOOL: dict = {
    "type": "function",
    "function": {
        "name": "ui_watch_job",
        "description": (
            "Open the jobs monitor focused on a running job so the user sees live "
            "progress. ALWAYS call this after starting a long-running job (translation, "
            "media generation): the job runs for minutes — say you STARTED it and offer "
            "this live view; NEVER claim it finished. Opens immediately."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "The job to watch (UUID)."},
            },
            "required": ["job_id"],
            "additionalProperties": False,
        },
    },
}


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
                    "enum": ["compose", "scene-compose", "chapter-assemble", "editor", "planner", "agent-mode", "usage", "notifications", "settings", "trash", "steering", "extensions", "proposals", "glossary", "glossary-ontology", "glossary-unknown", "glossary-ai-suggestions", "glossary-merge-candidates", "wiki", "knowledge", "kg-overview", "kg-entities", "kg-timeline", "kg-evidence", "kg-gap", "kg-proposals", "kg-schema", "kg-graph", "kg-insights", "kg-jobs", "kg-bio", "kg-privacy", "jobs-list", "books", "leaderboard-books", "leaderboard-authors", "leaderboard-translators", "leaderboard-trending", "chapter-browser", "scene-browser", "scene-inspector", "plan-hub", "arc-inspector", "plan-passes", "whatif-canvas", "divergence", "book-import", "context-inspector", "sharing", "book-settings", "translation", "enrichment-compose", "enrichment-proposals", "enrichment-gaps", "enrichment-sources", "enrichment-jobs", "enrichment-settings", "user-guide", "quality", "quality-promises", "quality-critic", "quality-coverage", "quality-canon", "quality-canon-rules", "quality-corrections", "quality-heal", "motif-library", "world-map", "place-graph", "cast", "character-arc"],
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
                        "'divergence' = manage the book's what-if derivatives (dị bản) — list "
                        "the canonical Work and every branched version, switch the whole studio "
                        "to one, archive one, read its spec, or spawn a new branch from a chapter; "
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
                        "(e.g. 'book.publish', 'book.delete', 'translation.start_job')."
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
# advertise the always-on core by name (C-FT). ui_open_chapter is NOT core
# (discovered via find_tools) but is a valid frontend tool.
_GENERIC_FRONTEND_TOOLS_BY_NAME: dict[str, dict] = {
    "ui_navigate": UI_NAVIGATE_TOOL,
    "ui_open_book": UI_OPEN_BOOK_TOOL,
    "ui_open_chapter": UI_OPEN_CHAPTER_TOOL,
    "ui_show_panel": UI_SHOW_PANEL_TOOL,
    "ui_watch_job": UI_WATCH_JOB_TOOL,
    "confirm_action": CONFIRM_ACTION_TOOL,
    "propose_record_edit": PROPOSE_RECORD_EDIT_TOOL,
    "propose_edit": PROPOSE_EDIT_TOOL,
    "ui_open_studio_panel": UI_OPEN_STUDIO_PANEL_TOOL,
    "ui_focus_manuscript_unit": UI_FOCUS_MANUSCRIPT_UNIT_TOOL,
}


def generic_frontend_tool_def(name: str) -> dict | None:
    """The schema for a generic (cross-domain) frontend tool by name, or None."""
    return _GENERIC_FRONTEND_TOOLS_BY_NAME.get(name)


def frontend_tool_defs(*, editor: bool = False, book_scoped: bool = False, studio: bool = False) -> list[dict]:
    """Frontend tool schemas to advertise, by surface.

    ``editor`` — the chapter editor panel (book_id + chapter_id): adds the prose
    write-back ``propose_edit``.
    ``book_scoped`` — any book-scoped chat (editor OR a glossary-page/reader chat
    carrying a book context): adds ``glossary_propose_entity_edit``.
    ``studio`` — the Writing Studio compose panel (studio_context): adds the studio
    dock-navigation tools (open panel / focus manuscript unit — #09 Lane A).

    The flags are independent: a glossary-page chat is book_scoped but not editor.
    """
    defs: list[dict] = []
    if editor:
        defs.append(PROPOSE_EDIT_TOOL)
    if book_scoped:
        defs.append(GLOSSARY_PROPOSE_EDIT_TOOL)
        defs.append(GLOSSARY_CONFIRM_ACTION_TOOL)
    if studio:
        defs.extend(_STUDIO_UI_TOOLS)
    return defs


def is_frontend_tool(name: str) -> bool:
    return name in FRONTEND_TOOL_NAMES
