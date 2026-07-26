"""D-KG-TL-PARTICIPANT-ANCHOR — per-project backfill of
``:Event.participant_entity_ids`` (KG-TL Option A).

Resolves each EXISTING event's ``participants`` (bare name strings) to glossary
``entity_id`` anchors and stores the aligned array on the node, so the timeline
localizer joins by stored id instead of re-resolving names at read time. Events
written before this feature (or grown a short array via an ON MATCH re-mention)
get a full aligned array here.

Idempotent: ``SET`` overwrites with a freshly-resolved aligned array, so a re-run
stamps the same values (modulo glossary changes since). Project-scoped. Triggered
by the internal route ``POST /internal/projects/{project_id}/backfill-participant-anchors``.

Mirrors ``backfill_orders.py`` (function + plain result holder; HTTP-triggered
per-project on demand).
"""

from __future__ import annotations

import logging

from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.entities import resolve_participant_anchors

logger = logging.getLogger(__name__)

__all__ = [
    "run_participant_anchor_backfill",
    "ParticipantAnchorBackfillResult",
]

# Only events that actually carry participants need an anchor array. Archived
# events are skipped (they never render on the timeline).
_LIST_PROJECT_EVENTS_CYPHER = """
MATCH (e:Event {user_id: $user_id, project_id: $project_id})
WHERE e.archived_at IS NULL AND size(coalesce(e.participants, [])) > 0
RETURN e.id AS id, e.participants AS participants
"""

# Overwrite the whole anchor array (aligned to the event's stored, already-deduped
# participants) — normalizes any legacy/short array to full length. Idempotent.
_SET_PARTICIPANT_ANCHORS_CYPHER = """
MATCH (e:Event {id: $id, user_id: $user_id})
SET e.participant_entity_ids = $participant_entity_ids,
    e.updated_at = datetime()
"""


class ParticipantAnchorBackfillResult:
    """Plain stats holder — direct attribute access from the route + tests."""

    def __init__(self) -> None:
        self.events_scanned = 0
        self.events_anchored = 0  # events that got ≥1 non-"" anchor
        self.anchors_resolved = 0  # total resolved (non-"") participant slots

    def __repr__(self) -> str:  # pragma: no cover (debug aid only)
        return (
            f"ParticipantAnchorBackfillResult("
            f"events_scanned={self.events_scanned}, "
            f"events_anchored={self.events_anchored}, "
            f"anchors_resolved={self.anchors_resolved})"
        )


async def run_participant_anchor_backfill(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
) -> ParticipantAnchorBackfillResult:
    """Resolve + stamp ``participant_entity_ids`` for one project's events.

    ``session`` is injected so unit tests can pass a fake. Resolution reuses the
    SAME :func:`resolve_participant_anchors` the write path uses, so a backfilled
    event and a freshly-extracted one carry identical anchors.
    """
    result = ParticipantAnchorBackfillResult()

    cypher_result = await session.run(
        _LIST_PROJECT_EVENTS_CYPHER, user_id=user_id, project_id=project_id,
    )
    events: list[tuple[str, list[str]]] = [
        (record["id"], list(record["participants"] or []))
        async for record in cypher_result
    ]

    for event_id_, participants in events:
        result.events_scanned += 1
        anchors = await resolve_participant_anchors(
            session, user_id=user_id, project_id=project_id, names=participants,
        )
        # Build the array ALIGNED to the event's stored participants ("" sentinel
        # where unanchored). Same length as participants → the read path trusts it.
        participant_entity_ids = [anchors.get(p, "") for p in participants]
        await session.run(
            _SET_PARTICIPANT_ANCHORS_CYPHER,
            id=event_id_,
            user_id=user_id,
            participant_entity_ids=participant_entity_ids,
        )
        resolved_count = sum(1 for x in participant_entity_ids if x)
        if resolved_count:
            result.events_anchored += 1
        result.anchors_resolved += resolved_count

    logger.info(
        "KG-TL participant-anchor backfill: project=%s scanned=%d anchored=%d "
        "anchors=%d",
        project_id, result.events_scanned, result.events_anchored,
        result.anchors_resolved,
    )
    return result
