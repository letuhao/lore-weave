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

# Anti-confabulation guardrail — always included. Two jobs: (1) THIS manuscript +
# memory is the only canon, NOT the model's parametric memory of any published work
# (a continue-writing user is often DIVERGING from the original, and the model's recall
# of the original is frequently wrong anyway); (2) on a missing specific detail, SEARCH
# before answering, and DECLINE rather than invent. Fixes D-AGENT-NEEDLE-CONFAB: gemma-4
# supplied a wrong firm name ("Holmgood, Voss & Co.") from its memory of Dracula instead
# of using story_search to find the real "Peter Hawkins" in the manuscript.
_ANTI_CONFAB = (
    "This memory and the user's manuscript are the ONLY source of truth — NOT your own "
    "training knowledge of any published work (the user's version may differ, and your "
    "recall of the original is often wrong). If a specific detail (a name, place, date, "
    "or quote) is NOT present above, do not supply it from general knowledge: search the "
    "manuscript with story_search (mode=exact for an exact name or phrase) first, and if "
    "it still isn't found, say plainly it isn't recorded yet rather than inventing one."
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
_WITH_SUMMARIES = (
    "Use <summaries> as high-level overviews of chapters, parts, and the "
    "whole book — answer abstract questions about themes, arcs, and plot "
    "from them. Higher-level summaries (book > part > chapter) cover broader "
    "scope; prefer the most specific level that still answers the question."
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
    has_summaries: bool = False,
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

    lines = [_BASE, _ANTI_CONFAB, _INTENT_HINTS[intent]]
    if has_facts:
        lines.append(_WITH_FACTS)
    if has_passages:
        lines.append(_WITH_PASSAGES)
    if has_summaries:
        lines.append(_WITH_SUMMARIES)
    if has_absences:
        lines.append(_WITH_ABSENCES)
    return " ".join(lines)
