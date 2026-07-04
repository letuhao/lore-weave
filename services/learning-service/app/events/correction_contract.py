"""Canonical correction-event contract — the declared SoT for the dispatcher.

learning-service consumes 5 DOMAIN streams (glossary / knowledge / chat /
composition / translation — a firehose of many event types) and handles only the
CORRECTION / feedback subset. An unregistered type on those streams is CORRECTLY
skipped quietly (it is simply not a correction event — warning on it would spam).

The real silent-drop risk is a CORRECTION event that *should* be handled and isn't:
a producer renames one, or a new correction type ships without a handler. The
dispatcher would log it at DEBUG and skip — the learning signal is lost with no
visible failure. This frozenset is the DECLARED set of correction event types;
`build_dispatcher` fail-fasts if it does not register a handler for every one, and
the wiring test (`tests/test_correction_contract.py`) asserts the dispatcher
realizes EXACTLY this set — so a drop / rename / unwired-new-type fails at
startup + in CI instead of silently losing the correction (the Agent-Extensibility
"no-silent-no-op" rule, applied to the correction event bus).

Adding a correction event type is a two-line change that CANNOT half-land: add the
type here AND register its handler in `build_dispatcher` — omit either and both the
startup assert and the wiring test fail.
"""

from __future__ import annotations

CORRECTION_EVENT_TYPES: frozenset[str] = frozenset(
    {
        # glossary
        "glossary.entity_updated",
        "glossary.name_confirmed",
        # knowledge (entity/relation/event corrections share one handler)
        "knowledge.entity_corrected",
        "knowledge.relation_corrected",
        "knowledge.event_corrected",
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
