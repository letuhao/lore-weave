"""A2A phase-2 — the `compose_prose` server-executed tool (in-turn model delegation).

When a session has a `composer_model_ref` configured, the orchestrator (the
session's tool-capable model) may call `compose_prose`. Unlike memory tools
(executed by knowledge-service) or the frontend `propose_edit` tool (executed in
the browser), this tool is fulfilled INSIDE chat-service by streaming a SECOND
model — the "composer" (a reasoning/writing model) — and returning its prose as
the tool result. The orchestrator then continues (typically wrapping the prose in
propose_edit).

This keeps each model on its strength: the orchestrator stays reliable at tool
calls, the composer just writes. See docs/specs/2026-06-02-a2a-model-routing-seam.md.
"""
from __future__ import annotations

COMPOSE_PROSE_NAME = "compose_prose"

# Default system prompt for the composer pass. The session's own system_prompt
# (the author's voice/lore instructions) is prepended by the caller when present.
COMPOSER_SYSTEM_PROMPT = (
    "You are a skilled prose writer. Produce only the requested narrative text — "
    "no preamble, no meta commentary, no markdown fences. Match the tone and "
    "language of the source text when one is given."
)

COMPOSE_PROSE_TOOL: dict = {
    "type": "function",
    "function": {
        "name": COMPOSE_PROSE_NAME,
        "description": (
            "Generate or rewrite narrative prose using the dedicated writing model. "
            "Call this for creative or long-form text (drafting, rewriting a "
            "paragraph more vividly, continuing a scene). Give clear instructions "
            "and pass the existing text in `source_text` when transforming. Returns "
            "the generated prose, which you can then present or apply with propose_edit."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "instructions": {
                    "type": "string",
                    "description": "What to write, or how to rewrite the source text.",
                },
                "source_text": {
                    "type": "string",
                    "description": "Existing text to transform (omit for fresh generation).",
                },
            },
            "required": ["instructions"],
        },
    },
}


def is_composer_tool(name: str) -> bool:
    return name == COMPOSE_PROSE_NAME


def compose_prose_defs() -> list[dict]:
    return [COMPOSE_PROSE_TOOL]


def build_composer_messages(args: dict, session_system_prompt: str | None) -> list[dict]:
    """Build the message list for the composer pass from the tool call args."""
    system = COMPOSER_SYSTEM_PROMPT
    if session_system_prompt:
        system = f"{session_system_prompt}\n\n{system}"
    instructions = (args.get("instructions") or "").strip()
    source_text = (args.get("source_text") or "").strip()
    user = instructions
    if source_text:
        user = f"{instructions}\n\n--- Source text ---\n{source_text}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user or "Continue the prose."},
    ]
