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
FRONTEND_TOOL_NAMES: frozenset[str] = frozenset({"propose_edit"})

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


def frontend_tool_defs() -> list[dict]:
    """The frontend tool schemas to advertise to the LLM (editor panel only)."""
    return [PROPOSE_EDIT_TOOL]


def is_frontend_tool(name: str) -> bool:
    return name in FRONTEND_TOOL_NAMES
