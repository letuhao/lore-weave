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

__all__ = [
    "TOOL_NAMES",
    "TOOL_DEFINITIONS",
    "ARG_MODELS",
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


# ── per-tool argument models ──────────────────────────────────────────


class MemorySearchArgs(BaseModel):
    """`memory_search` — semantic passage search within the project."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=1000)
    limit: int = Field(
        default=SEARCH_LIMIT_DEFAULT, ge=1, le=SEARCH_LIMIT_MAX
    )
    source_type: Literal["chapter", "chat", "glossary"] | None = None


class MemoryRecallEntityArgs(BaseModel):
    """`memory_recall_entity` — entity detail + relations, by name."""

    model_config = ConfigDict(extra="forbid")

    entity_name: str = Field(min_length=1, max_length=200)


class MemoryTimelineArgs(BaseModel):
    """`memory_timeline` — narrative events, optionally filtered."""

    model_config = ConfigDict(extra="forbid")

    from_date: str | None = Field(default=None, pattern=_ISO_DATE_PATTERN)
    to_date: str | None = Field(default=None, pattern=_ISO_DATE_PATTERN)
    entity_name: str | None = Field(default=None, min_length=1, max_length=200)
    limit: int = Field(
        default=TIMELINE_LIMIT_DEFAULT, ge=1, le=TIMELINE_LIMIT_MAX
    )

    @model_validator(mode="after")
    def _reject_reversed_range(self) -> "MemoryTimelineArgs":
        # /review-impl MED#1 — a reversed range would otherwise flow to
        # list_events_filtered and silently return empty, misleading the
        # LLM into "no events". Truncated ISO is lexicographically
        # ordered (C18 design), so a plain string compare is correct.
        if self.from_date and self.to_date and self.from_date > self.to_date:
            raise ValueError("from_date must not be after to_date")
        return self


class MemoryRememberArgs(BaseModel):
    """`memory_remember` — store a new fact (guardrailed, design D5)."""

    model_config = ConfigDict(extra="forbid")

    fact_text: str = Field(min_length=1, max_length=2000)
    fact_type: Literal["decision", "preference", "milestone", "negation"]


class MemoryForgetArgs(BaseModel):
    """`memory_forget` — invalidate a fact by id."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(min_length=1, max_length=200)


ARG_MODELS: dict[str, type[BaseModel]] = {
    "memory_search": MemorySearchArgs,
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
        "memory_search",
        "Semantic search over the user's stored memory for the current "
        "project — chapter text, past chat turns, and glossary entries. "
        "Call this to find what is already known about a topic, "
        "character, place, or event before answering. Returns the most "
        "relevant text snippets.",
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
]
