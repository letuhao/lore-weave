"""Canonical correction-event contract — the declared SoT for the dispatcher.

learning-service consumes 5 DOMAIN streams (glossary / knowledge / chat /
composition / translation — a firehose of many event types) and handles only the
CORRECTION / feedback subset. An unregistered type on those streams is normally a
non-correction event we correctly skip quietly.

No-silent-drop has TWO halves, because this contract is CONSUMER-owned (producers
in other services do not import it):

  1. COMPILE/CI half (this file): the DECLARED set of correction types this
     consumer wires. `build_dispatcher` fail-fasts if it registers no handler for a
     declared type, and the wiring test asserts the dispatcher realizes EXACTLY this
     set. This catches CONSUMER-side drift — a `register(...)` deleted, or a row
     added here without a handler (or vice-versa). It CANNOT see a producer rename
     or a producer-side new correction type: those live in other services, and this
     hand-authored list would simply not know about them.

  2. RUNTIME half (`EventDispatcher.dispatch`): a skipped event whose type carries a
     correction MARKER (`corrected`/`feedback`/`reviewed`/`merged`/…) but has no
     handler is logged at WARN, not DEBUG. THIS is what surfaces a producer rename /
     new-correction-type / a currently-unhandled correction — at runtime, where the
     producer-side truth actually lives.

Adding a correction type is a two-line change that CANNOT half-land: add it here AND
register its handler — omit either and the startup assert + wiring test fail.

`glossary.entity_merged` (a user merging duplicate entities — glossary outbox.go) is
now HANDLED (D-LEARN-ENTITY-MERGED): a merge is a resolution-quality correction on
the extractor's entity boundaries, encoded structurally (target = surviving winner;
before = absorbed loser ref, after = winner ref; op="merge"/"split" ⇒ diff_class
"merge"). Producer gap still open: the entity_merged payload carries no actor_id, so
merge events DLQ (missing-owner guard) until glossary adds the merging user to the
payload — the learning-side handler is ready.
"""

from __future__ import annotations

CORRECTION_EVENT_TYPES: frozenset[str] = frozenset(
    {
        # glossary
        "glossary.entity_updated",
        "glossary.entity_merged",
        "glossary.name_confirmed",
        # knowledge (entity/relation/event/fact corrections share one handler)
        "knowledge.entity_corrected",
        "knowledge.relation_corrected",
        "knowledge.event_corrected",
        "knowledge.fact_corrected",  # S-05 (extraction-derived fact retractions)
        "knowledge.extraction_run_completed",
        "knowledge.config_adjusted",
        # chat
        "chat.message_feedback",
        # composition
        "composition.generation_corrected",
        # translation
        "translation.quality",
        "translation.reviewed",
        "translation.corrected",
        # wiki
        "wiki.corrected",
        "wiki.suggestion_reviewed",
    }
)

__all__ = ["CORRECTION_EVENT_TYPES"]
