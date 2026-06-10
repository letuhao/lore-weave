"""A2-S1b-2 — one-time entity-status backfill over existing events.

Forward-only extraction (A2-S1b-1 prompt) gives status to every NEW publish.
Pre-existing books have events but no `:EntityStatus` records — this job
classifies each existing `:Event` summary into coarse `active`/`gone` status
effects and writes the records so the composition A2 canon guard works on
already-canonized books immediately.

Design (spec §A2-S1 + MED#2):
  - **Only events with non-null `event_order`.** Per CM4, legacy/chat events
    have `event_order=None` (timeline null-sinks) → they cannot be positioned
    on the reading axis a status needs. Such events are SKIPPED + counted (no
    silent unusable rows).
  - **Status evidence rides the event's own `ExtractionSource`**, not a
    separate backfill source. So when that chapter is later re-published or
    unpublished, the existing CM3b retract (`remove_evidence_for_natural_key`)
    supersedes the backfilled status too — a backfilled death does NOT survive
    an unpublish (which it would if evidenced by a standalone backfill source).
    An event with no resolvable source is skipped (can't be made retract-safe).
  - **Idempotent for a FIXED classification.** Deterministic `:EntityStatus`
    id + a stable backfill `job_id` → persisting the same `(entity, from_order,
    status)` merges the same node + same EVIDENCED_BY edge (no double-count).
    NOTE (/review-impl #2): the classifier is the LLM, so a *re-run* can emit a
    different set of status effects, and this job never retracts its own prior
    output — re-runs therefore ACCUMULATE (union) statuses. Run it ONCE per
    project as the bootstrap; real re-extraction (A2-S1b-1) is the authoritative
    updater thereafter.
  - **Project + user scoped** (K11.4 wrapper); coarse `active`/`gone` only.

The LLM classification is injected as `classify_fn` so the query → resolve →
persist core is unit-testable without a live model; `make_llm_classify_fn`
builds the real one for the endpoint.
"""

from __future__ import annotations

import json
import logging
from typing import Awaitable, Callable

from pydantic import BaseModel

from app.db.neo4j_helpers import CypherSession, run_read
from app.db.neo4j_repos.canonical import canonicalize_entity_name
from app.db.neo4j_repos.entity_status import STATUS_VALUES, merge_entity_status
from app.db.neo4j_repos.provenance import add_evidence

logger = logging.getLogger(__name__)

__all__ = [
    "EventToClassify",
    "StatusBackfillResult",
    "ClassifyFn",
    "run_status_backfill",
    "make_llm_classify_fn",
    "STATUS_BACKFILL_SYSTEM_PROMPT",
]

# Stable id so re-running the backfill is idempotent on the EVIDENCED_BY edge.
_BACKFILL_JOB_ID = "a2-s1b-2-status-backfill"
_BACKFILL_MODEL_TAG = "status-backfill"


class EventToClassify(BaseModel):
    """The minimal event projection handed to the classifier."""

    event_id: str
    summary: str
    participants: list[str]


# classify_fn(events) -> {event_id: [(entity_ref, status), ...]}
ClassifyFn = Callable[
    [list[EventToClassify]],
    Awaitable[dict[str, list[tuple[str, str]]]],
]


class StatusBackfillResult(BaseModel):
    events_scanned: int = 0            # events with non-null event_order considered
    events_skipped_no_order: int = 0   # MED#2 — null event_order, unpositionable
    statuses_written: int = 0          # :EntityStatus records merged
    skipped_unresolved_entity: int = 0 # entity_ref didn't match a project entity
    skipped_no_source: int = 0         # event had no ExtractionSource to ride
    skipped_bad_status: int = 0        # classifier returned a non active/gone value
    skipped_not_participant: int = 0   # entity_ref not one of the event's participants


_COUNT_NULL_ORDER_CYPHER = """
MATCH (e:Event)
WHERE e.user_id = $user_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
  AND e.event_order IS NULL
RETURN count(e) AS n
"""

# Events WITH a reading-axis position + their source. event_id is chapter-keyed
# (CM4) so an event normally has a SINGLE source; `collect(src.id)[0]` picks one
# arbitrarily for the rare cross-chapter-merged event (/review-impl #3 — accepted:
# the status rides one chapter's source; superseded by that chapter's re-extract).
_EVENTS_WITH_ORDER_CYPHER = """
MATCH (e:Event)
WHERE e.user_id = $user_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
  AND e.event_order IS NOT NULL
OPTIONAL MATCH (e)-[:EVIDENCED_BY]->(src:ExtractionSource)
WHERE src.user_id = $user_id
WITH e, collect(src.id)[0] AS source_id
RETURN e.id AS event_id, e.summary AS summary,
       e.participants AS participants, e.event_order AS event_order,
       source_id AS source_id
"""

_RESOLVE_ENTITY_CYPHER = """
MATCH (e:Entity)
WHERE e.user_id = $user_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
  AND e.canonical_name = $canonical_name
RETURN e.id AS id
LIMIT 1
"""


async def _resolve_entity_id(
    session: CypherSession, *, user_id: str, project_id: str | None, name: str,
) -> str | None:
    cn = canonicalize_entity_name(name)
    if not cn:
        return None
    result = await run_read(
        session, _RESOLVE_ENTITY_CYPHER,
        user_id=user_id, project_id=project_id, canonical_name=cn,
    )
    record = await result.single()
    return record["id"] if record else None


async def run_status_backfill(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    classify_fn: ClassifyFn,
    batch_size: int = 25,
) -> StatusBackfillResult:
    """Classify existing positioned events into coarse status records.

    See module docstring. `classify_fn` maps a batch of events to
    `{event_id: [(entity_ref, status)]}`; the core gates/resolves/persists.
    """
    res = StatusBackfillResult()

    null_result = await run_read(
        session, _COUNT_NULL_ORDER_CYPHER, user_id=user_id, project_id=project_id,
    )
    null_record = await null_result.single()
    res.events_skipped_no_order = int(null_record["n"]) if null_record else 0
    if res.events_skipped_no_order:
        logger.info(
            "A2-S1b-2 backfill: %d events skipped (event_order IS NULL — "
            "unpositionable on the reading axis) project=%s",
            res.events_skipped_no_order, project_id,
        )

    rows_result = await run_read(
        session, _EVENTS_WITH_ORDER_CYPHER, user_id=user_id, project_id=project_id,
    )
    events: list[EventToClassify] = []
    meta: dict[str, dict] = {}
    async for rec in rows_result:
        ev_id = rec["event_id"]
        participants = list(rec["participants"] or [])
        events.append(EventToClassify(
            event_id=ev_id,
            summary=rec["summary"] or "",
            participants=participants,
        ))
        meta[ev_id] = {
            "event_order": rec["event_order"],
            "source_id": rec["source_id"],
            "participants": participants,
        }
    res.events_scanned = len(events)
    if not events:
        return res

    # Classify in batches (bounds the LLM context per call).
    classified: dict[str, list[tuple[str, str]]] = {}
    for i in range(0, len(events), batch_size):
        batch = events[i : i + batch_size]
        part = await classify_fn(batch)
        classified.update(part)

    for ev_id, effects in classified.items():
        m = meta.get(ev_id)
        if m is None:
            continue  # classifier hallucinated an id not in the batch
        from_order = m["event_order"]
        source_id = m["source_id"]
        if from_order is None:
            continue  # defensive (query already filtered)
        if not source_id:
            res.skipped_no_source += len(effects)
            continue
        participant_folds = {
            canonicalize_entity_name(p) for p in (m["participants"] or [])
        }
        participant_folds.discard("")
        for entity_ref, status in effects:
            if status not in STATUS_VALUES:
                res.skipped_bad_status += 1
                continue
            # /review-impl #1 — enforce the prompt's contract: a status_effect's
            # entity_ref MUST be one of THIS event's participants. The classifier
            # is told this, but a drifting model could name a different project
            # entity (or one merely mentioned in the summary) — and the
            # project-wide resolve below would then write a status for the WRONG
            # entity at this event's order. Reject non-participants up front.
            if canonicalize_entity_name(entity_ref) not in participant_folds:
                res.skipped_not_participant += 1
                continue
            entity_id = await _resolve_entity_id(
                session, user_id=user_id, project_id=project_id, name=entity_ref,
            )
            if entity_id is None:
                res.skipped_unresolved_entity += 1
                continue
            status_node = await merge_entity_status(
                session,
                user_id=user_id,
                project_id=project_id,
                entity_id=entity_id,
                status=status,
                from_order=int(from_order),
                source_type="book_content",
                provenance="human_authored",
            )
            # Ride the EVENT's own source so re-publish/unpublish retract
            # supersedes this backfilled status (canon-safe).
            await add_evidence(
                session,
                user_id=user_id,
                target_label="EntityStatus",
                target_id=status_node.id,
                source_id=source_id,
                extraction_model=_BACKFILL_MODEL_TAG,
                confidence=0.9,
                job_id=_BACKFILL_JOB_ID,
            )
            res.statuses_written += 1

    logger.info(
        "A2-S1b-2 backfill done project=%s scanned=%d written=%d "
        "skipped(no_order=%d unresolved=%d no_source=%d bad_status=%d)",
        project_id, res.events_scanned, res.statuses_written,
        res.events_skipped_no_order, res.skipped_unresolved_entity,
        res.skipped_no_source, res.skipped_bad_status,
    )
    return res


# ── LLM classifier (the real classify_fn for the endpoint) ────────────

STATUS_BACKFILL_SYSTEM_PROMPT = """\
RESPOND DIRECTLY. Emit ONLY a JSON object — no prose, no markdown fences.

You classify narrative events for a fiction knowledge graph. For each event
below, decide whether the event makes any of its participants change status:
- "gone": the participant ceases to exist as an active presence — dies, is
  destroyed, permanently departs, or is irreversibly lost.
- "active": a previously-gone participant is restored to active presence.
Most events change NO status. Use ONLY "gone" or "active". `entity_ref` MUST
be one of that event's listed participants. Decide from the summary text in
whatever language it uses; do NOT infer beyond it.

Return strict JSON:
{"results": [{"event_id": "<id>", "status_effects": [{"entity_ref": "<participant>", "status": "gone"}]}]}
Include an entry ONLY for events that have at least one status effect.
"""


def make_llm_classify_fn(
    llm_client,
    *,
    user_id: str,
    model_source: str,
    model_ref: str,
) -> ClassifyFn:
    """Build a classify_fn backed by the LLM (chat op — reuses the OpenAI wire
    shape per `feedback_op_enum_reuse_via_chat_precedent`; this caller parses
    the JSON itself, so no new JobOperation enum)."""

    async def _classify(events: list[EventToClassify]) -> dict[str, list[tuple[str, str]]]:
        if not events:
            return {}
        payload = [
            {"event_id": e.event_id, "summary": e.summary, "participants": e.participants}
            for e in events
        ]
        user_msg = "EVENTS:\n" + json.dumps(payload, ensure_ascii=False)
        job = await llm_client.submit_and_wait(
            user_id=user_id,
            operation="chat",
            model_source=model_source,
            model_ref=model_ref,
            input={
                "messages": [
                    {"role": "system", "content": STATUS_BACKFILL_SYSTEM_PROMPT},
                    {"role": "user", "content": user_msg},
                ],
                "response_format": {"type": "text"},
                "temperature": 0.0,
                "max_tokens": 2048,
            },
        )
        out: dict[str, list[tuple[str, str]]] = {}
        if getattr(job, "status", None) != "completed" or job.result is None:
            logger.warning("A2-S1b-2 classify batch did not complete; skipping batch")
            return out
        content = _extract_content(job.result)
        parsed = _parse_classify_json(content)
        valid_ids = {e.event_id for e in events}
        for item in parsed:
            ev_id = item.get("event_id")
            if ev_id not in valid_ids:
                continue
            effects: list[tuple[str, str]] = []
            for eff in item.get("status_effects") or []:
                if not isinstance(eff, dict):
                    continue
                ref = eff.get("entity_ref")
                st = eff.get("status")
                if isinstance(ref, str) and ref.strip() and st in STATUS_VALUES:
                    effects.append((ref.strip(), st))
            if effects:
                out[ev_id] = effects
        return out

    return _classify


def _extract_content(result: dict) -> str:
    """Gateway returns the completion at result['messages'][0]['content']
    (per `feedback_gateway_response_messages_array_not_content_string`)."""
    msgs = result.get("messages")
    if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
        return msgs[0].get("content") or ""
    return result.get("content") or ""


def _parse_classify_json(content: str) -> list[dict]:
    """Tolerant parse: strip fences, take the outermost object, read results[]."""
    if not content:
        return []
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        nl = text.find("\n")
        if nl != -1:
            text = text[nl + 1 :]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return []
    try:
        obj = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return []
    results = obj.get("results") if isinstance(obj, dict) else None
    return [r for r in results if isinstance(r, dict)] if isinstance(results, list) else []
