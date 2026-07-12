"""K21.1 — memory tool definitions.

Two parallel artefacts, kept in sync by `test_tool_definitions.py`:

  * `TOOL_DEFINITIONS` — the OpenAI function-calling schemas the
    chat-service passes to the LLM (Cycle B). Descriptions are written
    *for the model* — they are how it decides when to call each tool.
  * `ARG_MODELS` — per-tool Pydantic models the executor validates the
    LLM-supplied `tool_args` against before touching a repo.

**Envelope vs. tool args (design D3).** `user_id`, `project_id` and
`session_id` are NEVER tool parameters — they come from the MCP context
headers forwarded by ai-gateway (`X-User-Id`/`X-Project-Id`/`X-Session-Id`),
not from the LLM. The LLM only ever supplies the semantic arguments below.
`extra="forbid"` on every arg model means a hallucinated parameter is
surfaced as a tool error the model can see and correct, and can never
smuggle in a scope override.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.db.neo4j_repos.facts import FACT_TYPES
from app.tools.graph_schema_tools import (
    GRAPH_SCHEMA_ARG_MODELS,
    GRAPH_SCHEMA_TOOL_DEFINITIONS,
)
from app.tools.argbase import ProjectScopedArgs
from app.tools.build_tools import BUILD_TOOL_ARG_MODELS
from app.tools.project_tools import PROJECT_TOOL_ARG_MODELS
from app.tools.reader_tools import READER_TOOL_ARG_MODELS

__all__ = [
    "TOOL_NAMES",
    "TOOL_DEFINITIONS",
    "ARG_MODELS",
    "StorySearchArgs",
    "MemorySearchArgs",
    "MemoryRecallEntityArgs",
    "MemoryTimelineArgs",
    "MemoryRememberArgs",
    "MemoryForgetArgs",
]

# Truncated-ISO date: YYYY | YYYY-MM | YYYY-MM-DD. Mirrors the C18
# `event_date_iso` shape so a malformed date fails as a clear tool
# error here rather than deeper in the timeline repo.
_ISO_DATE_PATTERN = r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$"

# Result-size caps (design D7) — tool output is fed back into the LLM
# context, so each tool bounds how much it can return.
SEARCH_LIMIT_MAX = 20
SEARCH_LIMIT_DEFAULT = 10
TIMELINE_LIMIT_MAX = 50
TIMELINE_LIMIT_DEFAULT = 20

# L1/L2 reference-first contract (Context Budget Law §6b). `detail` is a
# versioned-default migration lever: it defaults to "full" (legacy/federated
# callers unchanged) and the chat-compiler passes "summary" for a compact,
# reference-only projection. Enum-locked so a weak local model can't guess a
# free-string value. Shared by the SET-returning memory tools (story_search /
# memory_search / memory_timeline); the executor applies `apply_response_contract`
# with the per-tool ref-field set. Drift-locked against the arg models by
# test_schema_properties_match_arg_model_fields + the MCP mirror test.
_DETAIL_PROP = {
    "type": "string",
    "enum": ["summary", "full"],
    "description": (
        "Response granularity. 'full' (default) = every field of each item. "
        "'summary' = a compact reference projection (ids/title/snippet/score "
        "only, heavy bodies dropped) — use it to scan many results cheaply, then "
        "re-read the ones you need at full detail (or via a get-by-id sibling). "
        "Result `meta` always reports total/returned/truncated."
    ),
}

# H-I: the optional, ownership-checked project_id parameter shared by the
# project-scoped memory tools (mirrors ProjectScopedArgs.project_id). Drift-locked
# against the model by test_schema_properties_match_arg_model_fields.
_PROJECT_ID_PROP = {
    "type": "string",
    "description": (
        "Optional knowledge project id to scope this call to. Omit to use the "
        "project linked to the current session. On the public API (no session "
        "project) set this to one of YOUR projects — you can only address projects "
        "you own."
    ),
}


# ── per-tool argument models ──────────────────────────────────────────


class MemorySearchArgs(ProjectScopedArgs):
    """`memory_search` — semantic passage search within the project."""

    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(
        default=SEARCH_LIMIT_DEFAULT, ge=1, le=SEARCH_LIMIT_MAX
    )
    source_type: Literal["chapter", "chat", "glossary"] | None = None
    # L1/L2 reference-first contract (§6b) — versioned default "full".
    detail: Literal["summary", "full"] = "full"


class StorySearchArgs(ProjectScopedArgs):
    """`story_search` — the UNIVERSAL manuscript search (#12 agent-search).

    One simple schema, three engines behind it (the market pattern — GitHub
    Blackbird / Cursor: index, never grep-at-query-time): exact (book-service
    FTS/trigram + Neo4j CJK fulltext), semantic (passage vectors), hybrid
    (both + RRF fusion + cross-encoder rerank). `exact` maps to the
    retriever's "lexical" mode. Granularity mirrors Claude-Code's grep
    funnel: chapter ≈ files_with_matches, block ≈ content."""

    query: str = Field(min_length=1, max_length=1000)
    mode: Literal["hybrid", "exact", "semantic"] = "hybrid"
    granularity: Literal["chapter", "block"] = "chapter"
    limit: int = Field(default=SEARCH_LIMIT_DEFAULT, ge=1, le=SEARCH_LIMIT_MAX)
    # L1/L2 reference-first contract (§6b) — versioned default "full".
    detail: Literal["summary", "full"] = "full"


class MemoryRecallEntityArgs(ProjectScopedArgs):
    """`memory_recall_entity` — entity detail + relations, by name."""

    entity_name: str = Field(min_length=1, max_length=200)


class MemoryTimelineArgs(ProjectScopedArgs):
    """`memory_timeline` — narrative events, optionally filtered."""

    from_date: str | None = Field(default=None, pattern=_ISO_DATE_PATTERN)
    to_date: str | None = Field(default=None, pattern=_ISO_DATE_PATTERN)
    entity_name: str | None = Field(default=None, min_length=1, max_length=200)
    limit: int = Field(
        default=TIMELINE_LIMIT_DEFAULT, ge=1, le=TIMELINE_LIMIT_MAX
    )
    # L1/L2 reference-first contract (§6b) — versioned default "full".
    detail: Literal["summary", "full"] = "full"

    @model_validator(mode="after")
    def _reject_reversed_range(self) -> "MemoryTimelineArgs":
        # /review-impl MED#1 — a reversed range would otherwise flow to
        # list_events_filtered and silently return empty, misleading the
        # LLM into "no events". Truncated ISO is lexicographically
        # ordered (C18 design), so a plain string compare is correct.
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date must not be after to_date")
        return self


class MemoryRememberArgs(ProjectScopedArgs):
    """`memory_remember` — store a new fact (guardrailed, design D5)."""

    fact_text: str = Field(min_length=1, max_length=2000)
    fact_type: Literal["decision", "preference", "milestone", "negation", "statement"]


class MemoryForgetArgs(BaseModel):
    """`memory_forget` — invalidate a fact by id."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(min_length=1, max_length=200)


ARG_MODELS: dict[str, type[BaseModel]] = {
    "memory_search": MemorySearchArgs,
    "story_search": StorySearchArgs,
    "memory_recall_entity": MemoryRecallEntityArgs,
    "memory_timeline": MemoryTimelineArgs,
    "memory_remember": MemoryRememberArgs,
    "memory_forget": MemoryForgetArgs,
    # Lane LF — KG ontology MCP tools (R + reversible W). Appended here so the
    # executor's validate→dispatch path and the MCP catalog cover them uniformly
    # with the memory tools. The class-C ontology tools (adopt/schema-edit/
    # sync-apply/schema-mutating-triage/handoff) are DEFERRED to KM6 (the
    # confirm-token machinery) and intentionally NOT registered (D-KG-LF-KM6).
    **GRAPH_SCHEMA_ARG_MODELS,
    # Knowledge-project lifecycle (kg_project_create) — book↔KG bootstrap.
    **PROJECT_TOOL_ARG_MODELS,
    # Cost-gated job triggers (kg_build_graph) — confirm-token mint.
    **BUILD_TOOL_ARG_MODELS,
    # W11-M2 reader "ask the lore" tools — spoiler-windowed reads.
    **READER_TOOL_ARG_MODELS,
}

TOOL_NAMES: tuple[str, ...] = tuple(ARG_MODELS)


# ── OpenAI function-calling schemas ───────────────────────────────────


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    """Assemble one OpenAI `type=function` tool entry."""
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
                "additionalProperties": False,
            },
        },
    }


TOOL_DEFINITIONS: list[dict] = [
    _tool(
        "story_search",
        "Search the book's manuscript for text or ideas — the universal "
        "find tool. Use it to LOCATE where something appears before reading "
        "or editing: an exact phrase/name (mode=exact), a concept described "
        "in your own words (mode=semantic), or both fused (mode=hybrid, "
        "default, best for most queries). granularity=chapter tells you "
        "WHICH chapters match; granularity=block drills into the matching "
        "passages with snippets. Follow up with book_get_chapter to read.",
        {
            "query": {
                "type": "string",
                "description": (
                    "The text or idea to find — an exact phrase, a character/"
                    "place name, or a natural-language description."
                ),
            },
            "mode": {
                "type": "string",
                "enum": ["hybrid", "exact", "semantic"],
                "description": (
                    "hybrid (default) = exact + semantic fused and reranked; "
                    "exact = literal text match only; semantic = meaning "
                    "match only."
                ),
            },
            "granularity": {
                "type": "string",
                "enum": ["chapter", "block"],
                "description": (
                    "chapter (default) = which chapters match; block = the "
                    "matching passages with snippets."
                ),
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": SEARCH_LIMIT_MAX,
                "description": (
                    f"Max hits to return (default {SEARCH_LIMIT_DEFAULT})."
                ),
            },
            "detail": _DETAIL_PROP,
            "project_id": _PROJECT_ID_PROP,
        },
        ["query"],
    ),
    _tool(
        "memory_search",
        "Search the project's stored knowledge for what is already known about a "
        "topic, character, place, or event before answering — the book's chapter "
        "text (lexical + semantic, so it finds an exact phrase even with nothing "
        "indexed yet), past chat turns, and glossary entries. Returns the most "
        "relevant snippets. (For locating/reading manuscript prose specifically, "
        "`story_search` is the primary find tool.)",
        {
            "query": {
                "type": "string",
                "description": "What to search for, in natural language.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": SEARCH_LIMIT_MAX,
                "description": (
                    f"Max snippets to return (default {SEARCH_LIMIT_DEFAULT})."
                ),
            },
            "source_type": {
                "type": "string",
                "enum": ["chapter", "chat", "glossary"],
                "description": (
                    "Optional — restrict to one source. Omit to search all."
                ),
            },
            "detail": _DETAIL_PROP,
            "project_id": _PROJECT_ID_PROP,
        },
        ["query"],
    ),
    _tool(
        "memory_recall_entity",
        "Look up a specific entity (character, place, organization, "
        "item, etc.) by name and return its stored details plus its "
        "relationships to other entities. Use this when the user asks "
        "about a named thing and you need what memory holds on it.",
        {
            "entity_name": {
                "type": "string",
                "description": "The entity's name as it appears in the story.",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["entity_name"],
    ),
    _tool(
        "memory_timeline",
        "Retrieve narrative events in order for the current project, "
        "optionally filtered by a date range or by an entity that took "
        "part. Use this to answer 'what happened' or 'when did' "
        "questions.",
        {
            "from_date": {
                "type": "string",
                "description": (
                    "Optional inclusive lower bound, ISO date "
                    "(YYYY, YYYY-MM, or YYYY-MM-DD)."
                ),
            },
            "to_date": {
                "type": "string",
                "description": "Optional inclusive upper bound, same ISO form.",
            },
            "entity_name": {
                "type": "string",
                "description": (
                    "Optional — only events this named entity took part in."
                ),
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": TIMELINE_LIMIT_MAX,
                "description": (
                    f"Max events to return (default {TIMELINE_LIMIT_DEFAULT})."
                ),
            },
            "detail": _DETAIL_PROP,
            "project_id": _PROJECT_ID_PROP,
        },
        [],
    ),
    _tool(
        "memory_remember",
        "Store a new fact into long-term memory. Use sparingly — only "
        "for durable, important information the user explicitly stated "
        "or confirmed. Stored facts are recorded at low confidence and "
        "tagged as assistant-created so the user can review them.",
        {
            "fact_text": {
                "type": "string",
                "description": "The fact to store, as a clear statement.",
            },
            "fact_type": {
                "type": "string",
                "enum": list(FACT_TYPES),
                "description": (
                    "decision = a choice made; preference = a standing "
                    "like/dislike or habit; milestone = a notable "
                    "achievement; negation = something explicitly NOT true."
                ),
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["fact_text", "fact_type"],
    ),
    _tool(
        "memory_forget",
        "Invalidate a previously stored fact by its id so it no longer "
        "appears in memory. Only use a fact_id you have seen in an "
        "earlier tool result.",
        {
            "fact_id": {
                "type": "string",
                "description": "The id of the fact to invalidate.",
            },
        },
        ["fact_id"],
    ),
    # Lane LF — KG ontology MCP tools (R + reversible W). Spread last so the
    # memory tools keep their indices; drift-locked against GRAPH_SCHEMA_ARG_MODELS
    # by test_tool_definitions / test_graph_schema_tools.
    *GRAPH_SCHEMA_TOOL_DEFINITIONS,
    # Knowledge-project lifecycle — the book↔KG bootstrap tool.
    _tool(
        "kg_project_create",
        "Create (or get) the knowledge PROJECT that anchors a book's knowledge "
        "graph + memory — the prerequisite for the KG schema, extraction, and "
        "wiki tools, which all operate on 'the current project'. A book-bound "
        "project (book_id set) can only be created by the book's owner; omit "
        "book_id for a personal project. Idempotent: a repeat call for the same "
        "book returns the existing project. Returns the project_id to use next.",
        {
            "name": {
                "type": "string",
                "minLength": 1,
                "maxLength": 200,
                "description": "A human-readable project name.",
            },
            "project_type": {
                "type": "string",
                "enum": ["book", "translation", "code", "general"],
                "description": "Project kind (default 'book' for a book's KG).",
            },
            "book_id": {
                "type": "string",
                "description": "Link to this book (book-owner only). Omit for a personal project.",
            },
            "description": {
                "type": "string",
                "maxLength": 2000,
                "description": "Optional project description.",
            },
            "genre": {
                "type": "string",
                "maxLength": 100,
                "description": "Optional genre hint (e.g. 'gothic horror').",
            },
        },
        ["name"],
    ),
    # Project discovery — the answer to "no project in scope" (W0 #4a).
    _tool(
        "kg_project_list",
        "List YOUR OWN knowledge projects (id, name, type, linked book). Use this "
        "to find the `project_id` to pass to a project-scoped kg_* tool when no "
        "project is in scope. Owner-scoped: only the caller's projects are returned.",
        {
            "include_archived": {
                "type": "boolean",
                "description": "Also include archived projects (default false).",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "description": "Max projects to return (default 20).",
            },
        },
        [],
    ),
    # Project setup — the step BETWEEN kg_project_create and kg_run_benchmark that
    # used to exist only as a REST route behind the Build-KG dialog, dead-ending
    # every agent-created project (F6, Track D liveness eval).
    _tool(
        "kg_project_set_embedding_model",
        "Configure the project's EMBEDDING MODEL — the one-time setup that "
        "kg_run_benchmark and kg_build_graph both require. Call this when a build "
        "reports the project has no embedding model configured, instead of sending "
        "the user to the UI. Pass a provider-registry user_model UUID for one of your "
        "own embedding models (find one with settings_list_models). The vector "
        "dimension is probed automatically. Free, reversible, owner-only. Then call "
        "kg_run_benchmark, then kg_build_graph.",
        {
            "embedding_model": {
                "type": "string",
                "minLength": 1,
                "description": (
                    "provider-registry user_model UUID of an embedding model you own."
                ),
            },
            "project_id": {
                "type": "string",
                "description": "Project to configure. Omit to use the project in scope.",
            },
        },
        ["embedding_model"],
    ),
    # Cost-gated job trigger — build the knowledge graph (propose→confirm).
    _tool(
        "kg_build_graph",
        "Build the current project's knowledge graph by starting an extraction job over "
        "the book's chapters. EXPENSIVE (LLM cost) so it does NOT run immediately — it "
        "returns a confirm_token + summary; a human confirms on the review surface, which "
        "shows the estimated cost, and the job starts then. Requires the project to have "
        "an embedding model configured — if it does not, call kg_project_set_embedding_model "
        "then kg_run_benchmark first, rather than sending the user to the UI. Pick "
        "the extraction llm_model from settings_list_models.",
        {
            "llm_model": {
                "type": "string",
                "maxLength": 200,
                "description": "The extraction LLM model ref (from settings_list_models).",
            },
            "scope": {
                "type": "string",
                "enum": ["all", "chapters", "chat", "glossary_sync"],
                "description": "What to extract (default 'all').",
            },
            "chapter_from": {
                "type": "integer",
                "minimum": 0,
                "description": "Optional inclusive lower chapter ordinal (with chapter_to).",
            },
            "chapter_to": {
                "type": "integer",
                "minimum": 0,
                "description": "Optional inclusive upper chapter ordinal (with chapter_from).",
            },
            "reasoning_effort": {
                "type": "string",
                "enum": ["none", "low", "medium", "high"],
                "description": "Reasoning effort for the extraction LLM (paid compute; clamped "
                               "to your grant — Edit caps at medium, Manage/owner at high).",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["llm_model"],
    ),
    # Cost-gated job trigger — generate wiki articles (propose→confirm).
    _tool(
        "kg_build_wiki",
        "Generate wiki articles for the current project's book entities. EXPENSIVE (LLM "
        "cost per entity) so it does NOT run immediately — it returns a confirm_token + "
        "summary; a human confirms on the review surface (which shows the entity count + "
        "estimated cost) and the job starts then. Omit entity_ids to generate for ALL the "
        "book's glossary entities (extract the glossary first); pick model_ref from "
        "settings_list_models.",
        {
            "model_ref": {
                "type": "string",
                "maxLength": 200,
                "description": "The wiki-generation LLM model ref (from settings_list_models).",
            },
            "model_source": {
                "type": "string",
                "maxLength": 40,
                "description": "Model source (default 'user_model' for BYOK).",
            },
            "entity_ids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional explicit entity ids; omit to generate for ALL book entities.",
            },
            "reasoning_effort": {
                "type": "string",
                "enum": ["none", "low", "medium", "high"],
                "description": "Reasoning effort for the wiki-gen LLM (paid compute; clamped "
                               "to your grant — Edit caps at medium, Manage/owner at high).",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["model_ref"],
    ),
    # Direct action — run the embedding benchmark that gates Build-KG (R4).
    _tool(
        "kg_run_benchmark",
        "Run the required embedding-quality benchmark for the current project's embedding "
        "model. Build-KG (kg_build_graph) is BLOCKED until this passes — call this when a "
        "build preview warns the benchmark is not passing, instead of sending the user to "
        "the UI. Cheap (embeddings only, no LLM cost) and runs immediately on a hidden "
        "sandbox (it never touches the real graph). Returns passed + gate_failures; a pass "
        "enables Build-KG for this embedding model.",
        {"project_id": _PROJECT_ID_PROP},
        [],
    ),
    # ── W11-M2 reader "ask the lore" tools (spoiler-windowed; cutoff server-enforced) ──
    _tool(
        "lore_ask",
        "Ask about a book's lore SPOILER-SAFELY on the reader's behalf. Returns a "
        "spoiler-windowed evidence bundle — canon entities the reader has met + "
        "manuscript passages — bounded to the reader's own furthest-read chapter (you "
        "cannot widen it). Compose the answer from this evidence on your own model; if "
        "window_available is false the reader's position couldn't be pinned so nothing "
        "is shown.",
        {
            "query": {
                "type": "string",
                "description": "What the reader is asking — a name, a relationship, or "
                "'what has happened so far', in natural language.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "description": "Max passages + canon entities each (default 25).",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["query"],
    ),
    _tool(
        "lore_browse_entities",
        "List the CANON cast (characters, places, factions) the reader has met so far "
        "— spoiler-windowed to their furthest-read chapter. A reader whose position "
        "can't be pinned gets an empty list, never the whole cast.",
        {
            "kind": {
                "type": "string",
                "description": "Optional — restrict to one entity kind (e.g. 'character', "
                "'location'). Omit for the whole windowed cast.",
            },
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "description": "Max entities (default/max 50).",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        [],
    ),
    _tool(
        "lore_entity",
        "One entity's spoiler-windowed status + known facts, bounded to the reader's "
        "furthest-read chapter (facts established later are hidden).",
        {
            "entity_id": {
                "type": "string",
                "minLength": 1,
                "maxLength": 200,
                "description": "The entity id returned by lore_browse_entities / lore_ask.",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        ["entity_id"],
    ),
    _tool(
        "lore_timeline",
        "The sequence of events up to the reader's position — spoiler-windowed so "
        "later events are hidden. Empty when the reader's position can't be pinned.",
        {
            "limit": {
                "type": "integer",
                "minimum": 1,
                "maximum": 50,
                "description": "Max events (default/max 50).",
            },
            "project_id": _PROJECT_ID_PROP,
        },
        [],
    ),
]
