"""`is_mirrorable` — the CONSUMER's half of the mirror predicate.

glossary-service decides which entities exist (`mirrorTruthPredicate`, its emit-side
`deleted_at IS NULL`). This decides which of those the KG is supposed to end up holding,
and it is a genuinely different question that only this service can answer: the
`glossary.entity_updated` handler skips an event whose name or kind is empty, because a
freshly-created draft emits BEFORE its name attribute is filled and there is nothing to
MERGE a meaningful node from. The follow-up PATCH re-emits with the fields populated.

Why it lives here rather than inline in the handler
---------------------------------------------------
The detector has to apply exactly this rule. If it applied its own copy, then the day the
handler's skip changed the detector would start reporting rows as LOST that the handler is
deliberately declining to mirror — an alarm that can never be cleared, on a metric whose
entire contract is that it trends to zero. `reconcile-by-truth` has cost this repo a bug of
that shape before, by asking a narrower question than the producer asked itself.

One function, two callers, and a test that proves both call it.
"""

from __future__ import annotations

__all__ = ["is_mirrorable"]


def is_mirrorable(name: str | None, kind: str | None) -> bool:
    """Would the `glossary.entity_updated` handler write a node for this payload?

    False is NOT an error and NOT a divergence — it is "not yet nameable". A detector
    that could not tell that apart from "lost in delivery" would alarm on rows that are
    behaving exactly as designed.
    """
    return bool((name or "").strip()) and bool((kind or "").strip())
