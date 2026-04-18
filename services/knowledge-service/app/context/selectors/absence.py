"""K18.5 — absence detection for Mode 3.

Identifies entities the user mentioned that the memory graph has no
meaningful information about. Emits a ``<no_memory_for>`` block in
the final memory XML so the LLM can ask the user for clarification
instead of inventing details (the "don't hallucinate unknowns" rule
from KSA §4.5).

Input contract:

  - ``mentioned_entities`` — the entity names the K18.2a intent
    classifier extracted from the user's message.
  - ``l2_result`` — the L2 selector output. An entity is "covered by
    L2" if any fact in ``background`` / ``current`` / ``recent`` /
    ``negative`` mentions its name (case-insensitive substring).
  - ``l3_hits`` — optional list of L3 passage texts. Will be used in
    Commit 2 once K18.3 lands; for Commit 1 callers pass ``None``.

An entity that appears in neither bucket is absent. The output is a
de-duplicated list (preserves first-mention order) so the XML block
reads in the same order the user wrote the entities.
"""

from __future__ import annotations

import logging
from typing import Iterable

from app.context.selectors.facts import L2FactResult

__all__ = ["detect_absences"]

logger = logging.getLogger(__name__)


def _covered_by(corpus: Iterable[str], entity: str) -> bool:
    """True if any text in `corpus` contains `entity` (case-insensitive).

    Substring match on the whole phrase keeps the check trivial —
    fact sentences and passage quotes both render the entity's
    display name as-is. Tokenized word-boundary matching is overkill
    here: the false-positive rate is dominated by partial substrings
    of other entity names ("Arthur" in "Arthuria"), which is a very
    minor issue for a hint-level UI block.
    """
    needle = entity.lower()
    if not needle:
        return False
    return any(needle in (t or "").lower() for t in corpus)


def detect_absences(
    mentioned_entities: Iterable[str],
    l2_result: L2FactResult,
    *,
    l3_hits: Iterable[str] | None = None,
) -> list[str]:
    """Return entities the memory graph has no coverage for.

    Empty input → empty output. Entity order is preserved from
    ``mentioned_entities`` (first-mention wins when the same name
    appears twice).
    """
    l2_corpus = (
        list(l2_result.current)
        + list(l2_result.recent)
        + list(l2_result.background)
        + list(l2_result.negative)
    )
    l3_corpus = list(l3_hits or [])

    absent: list[str] = []
    seen: set[str] = set()
    for raw in mentioned_entities:
        name = raw.strip()
        if not name:
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        if _covered_by(l2_corpus, name) or _covered_by(l3_corpus, name):
            continue
        absent.append(name)

    if absent:
        logger.debug(
            "K18.5: absence detection flagged %d entities: %s",
            len(absent), absent,
        )
    return absent
