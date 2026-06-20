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
FRONTEND_TOOL_NAMES: frozenset[str] = frozenset(
    {"propose_edit", "glossary_propose_entity_edit", "glossary_confirm_action"}
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


def frontend_tool_defs(*, editor: bool = False, book_scoped: bool = False) -> list[dict]:
    """Frontend tool schemas to advertise, by surface.

    ``editor`` — the chapter editor panel (book_id + chapter_id): adds the prose
    write-back ``propose_edit``.
    ``book_scoped`` — any book-scoped chat (editor OR a glossary-page/reader chat
    carrying a book context): adds ``glossary_propose_entity_edit``.

    The two are independent: a glossary-page chat is book_scoped but not editor.
    """
    defs: list[dict] = []
    if editor:
        defs.append(PROPOSE_EDIT_TOOL)
    if book_scoped:
        defs.append(GLOSSARY_PROPOSE_EDIT_TOOL)
        defs.append(GLOSSARY_CONFIRM_ACTION_TOOL)
    return defs


def is_frontend_tool(name: str) -> bool:
    return name in FRONTEND_TOOL_NAMES
