"""K18.6 — Chain-of-thought instructions for Mode 3 memory blocks.

Generates the `<instructions>` block telling the LLM how to read the
surrounding XML (facts, passages, absences) and respond. Per KSA §4.2
+ §4.5.

Three dials drive the text:

  - `has_facts` — if False, drop the "engage with the <facts>" line.
  - `has_passages` — same for passages (the L3 selector may return
    nothing when embeddings aren't available or the query is too
    narrow).
  - `has_absences` — if True, add the "ask the user to clarify" line.

Locale: Track 1 is English-only (matches chat-service's own English
Mode-1 instructions, per the "Won't-fix" row in Deferred Items). The
`locale` parameter is present so a future i18n pass can plug in
alternative strings without touching callers.
"""

from __future__ import annotations

from app.context.intent.classifier import Intent

__all__ = ["build_instructions_block"]


# Base line — always included.
_BASE = (
    "Use the structured XML memory below as authoritative context about "
    "this story/project. Trust named entities in <glossary> as canonical "
    "references."
)

# Conditional lines, added when their respective blocks are present.
_WITH_FACTS = (
    "Engage with the <facts> as established truth — do not contradict "
    "them. Pay special attention to <negative> facts: if a fact says "
    "X does NOT know Y, your response must respect that."
)
_WITH_PASSAGES = (
    "Use <passages> as raw quotes for flavor and detail, but weight "
    "<facts> higher when they conflict (facts are curated, passages are "
    "excerpts)."
)
_WITH_ABSENCES = (
    "For any entity listed in <no_memory_for>, you have no reliable "
    "information. Ask the user a clarifying question rather than "
    "inventing details."
)

# Intent-specific nudges — steer the LLM toward the retrieval shape
# the classifier selected.
_INTENT_HINTS: dict[Intent, str] = {
    Intent.SPECIFIC_ENTITY: (
        "The user is asking about a specific named entity — prioritize "
        "that entity's facts over general context."
    ),
    Intent.RELATIONAL: (
        "The user is asking about a relationship between entities — "
        "trace the 2-hop <facts> and explain how the entities connect."
    ),
    Intent.HISTORICAL: (
        "The user is asking about earlier events — prefer older facts "
        "and older passages over recent ones."
    ),
    Intent.RECENT_EVENT: (
        "The user is asking about the current moment — prefer the most "
        "recent facts and passages."
    ),
    Intent.GENERAL: (
        "Treat the context as general background and draw freely from "
        "whatever is most relevant."
    ),
}


def build_instructions_block(
    intent: Intent,
    *,
    has_facts: bool,
    has_passages: bool,
    has_absences: bool,
    locale: str = "en",
) -> str:
    """Return the plain-text body for a Mode 3 `<instructions>` block.

    The caller is responsible for XML-escaping and wrapping in
    `<instructions>...</instructions>` — this function only produces
    the inner text so it can be plugged into whatever block structure
    `modes/full.py` ends up using.
    """
    # locale hook for future i18n; today only "en" has strings.
    del locale

    lines = [_BASE, _INTENT_HINTS[intent]]
    if has_facts:
        lines.append(_WITH_FACTS)
    if has_passages:
        lines.append(_WITH_PASSAGES)
    if has_absences:
        lines.append(_WITH_ABSENCES)
    return " ".join(lines)
