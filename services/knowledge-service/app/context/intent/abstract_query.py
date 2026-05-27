"""P3 D5 — cheap heuristic to detect abstract vs specific queries.

When a user asks an abstract question ("what are the themes?", "summarize
chapter 5", "overview of the arc"), Mode-3 retrieval should query the
per-level summary indexes (chapter/part/book) instead of (only) the
scene-passage index.

Heuristic (no LLM call; runs on every Mode-3 query):
  - Strong abstract keywords (theme, overview, summary, arc, plot,
    synopsis, gist) → abstract.
  - Long query (> 20 tokens) AND no glossary-entity proper-noun match
    → abstract.
  - Otherwise → specific (preserves existing behavior).

When glossary-service is unavailable + entities not provided, the
heuristic degrades to "specific" (D-P3-INTENT-CLASSIFIER-GLOSSARY-METRIC
tracks the silent degradation).
"""

from __future__ import annotations

import re
from typing import Iterable

__all__ = ["is_abstract_query", "ABSTRACT_KEYWORDS"]

# Strong abstract-intent keywords (case-insensitive whole-word match).
# Word boundary `\b` keeps "summary" matching "summary" but not "subsume".
_ABSTRACT_PATTERN = re.compile(
    r"\b(theme|themes|overview|summary|summarize|summarise|"
    r"arc|plot|synopsis|gist|main idea|central idea|recap)\b",
    re.IGNORECASE,
)

# Public for tests/inspection.
ABSTRACT_KEYWORDS = frozenset({
    "theme", "themes", "overview", "summary", "summarize", "summarise",
    "arc", "plot", "synopsis", "gist", "main idea", "central idea", "recap",
})

# Token-count threshold for the "long query + no entity" branch.
_LONG_QUERY_TOKENS = 20


def is_abstract_query(
    message: str, glossary_entities: Iterable[str] | None = None,
) -> bool:
    """Classify a Mode-3 user query as abstract or specific.

    Returns True when the query should trigger summary-index retrieval
    in addition to (or instead of) the scene-passage index.

    glossary_entities: iterable of canonical entity NAMES known for this
    project/book. When None or empty: treat as no-entity-match (defaults
    to "no proper-noun anchor" for the long-query branch). Glossary-service
    outage → caller passes None → heuristic degrades safely.
    """
    if not message or not message.strip():
        return False

    msg = message.strip()

    # Branch 1: explicit abstract keywords win immediately.
    if _ABSTRACT_PATTERN.search(msg):
        return True

    # Branch 2: long query + NO glossary-entity proper-noun match.
    tokens = msg.split()
    if len(tokens) <= _LONG_QUERY_TOKENS:
        return False

    if not glossary_entities:
        # No entity list available — long query alone enough to abstract.
        return True

    # Lowercase the message once for case-insensitive substring check.
    msg_lower = msg.lower()
    for entity in glossary_entities:
        if not entity:
            continue
        # Substring match (whole-word would miss multi-word entity names);
        # the heuristic is cheap, not precise.
        if entity.lower() in msg_lower:
            return False  # specific entity match — back to specific path

    # Long query + no entity hit → abstract.
    return True
