"""T4.1 Flywheel — on-read net-new delta for one extraction job.

Counts the :Entity / :Event / :RELATES_TO that the Pass-2 writer MINTED for a
given job (stamped ``created_job_id`` ON CREATE), so the composition Flywheel
panel can show "+N entities/relations/events" for the latest publish→extraction.

Pure read, no migration: nodes that predate T4.1 (or were written by a non-job
path) carry a NULL ``created_job_id`` and are simply not counted — correct,
since this job did not add them. ``created_job_id`` is set ONLY on create, so a
later match by another job never re-attributes the node.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from app.db.neo4j_helpers import CypherSession, run_read

# Cap the named-highlight sample per type (counts are always exact/full).
NEW_ITEMS_PER_TYPE = 6


@dataclass
class FlywheelItem:
    kind: str  # 'entity' | 'event' | 'relation'
    id: str
    name: str


@dataclass
class FlywheelDelta:
    entities_added: int = 0
    relations_added: int = 0
    events_added: int = 0
    new_items: list[FlywheelItem] = field(default_factory=list)


# `count(...)` stays EXACT over all matched rows; the `[0..N]` slice bounds the
# returned sample so a first full-book extraction (thousands net-new) doesn't ship
# every created node over the wire just to show ~6 highlights.
_ENTITIES_CYPHER = f"""
MATCH (e:Entity {{user_id: $user_id}})
WHERE e.created_job_id = $job_id
RETURN count(e) AS total,
       collect({{id: e.id, name: coalesce(e.name, e.canonical_name)}})[0..{NEW_ITEMS_PER_TYPE}] AS items
"""

_EVENTS_CYPHER = f"""
MATCH (e:Event {{user_id: $user_id}})
WHERE e.created_job_id = $job_id
RETURN count(e) AS total,
       collect({{id: e.id, name: coalesce(e.title, e.canonical_title)}})[0..{NEW_ITEMS_PER_TYPE}] AS items
"""

# Relations are scoped by created_job_id (a job belongs to one project/user, so
# the stamp alone attributes correctly); the user_id guard is defense-in-depth.
_RELATIONS_CYPHER = f"""
MATCH (subj:Entity)-[r:RELATES_TO]->(obj:Entity)
WHERE r.created_job_id = $job_id AND r.user_id = $user_id
RETURN count(r) AS total,
       collect({{
         id: r.id,
         name: coalesce(subj.name, subj.canonical_name) + ' → ' + r.predicate + ' → ' + coalesce(obj.name, obj.canonical_name)
       }})[0..{NEW_ITEMS_PER_TYPE}] AS items
"""


async def _count_and_sample(
    session: CypherSession, cypher: str, *, job_id: str, user_id: str, limit: int,
) -> tuple[int, list[dict]]:
    result = await run_read(session, cypher, job_id=job_id, user_id=user_id)
    record = await result.single()
    if record is None:
        return 0, []
    total = int(record["total"] or 0)
    items = [i for i in (record["items"] or []) if i and i.get("id")][:limit]
    return total, items


async def get_flywheel_delta(
    session: CypherSession,
    *,
    job_id: str,
    user_id: str,
    limit_per_type: int = NEW_ITEMS_PER_TYPE,
) -> FlywheelDelta:
    """Net-new entity/event/relation counts (exact) + a capped named sample for
    the given extraction job, read from the ``created_job_id`` stamp."""
    e_total, e_items = await _count_and_sample(
        session, _ENTITIES_CYPHER, job_id=job_id, user_id=user_id, limit=limit_per_type,
    )
    v_total, v_items = await _count_and_sample(
        session, _EVENTS_CYPHER, job_id=job_id, user_id=user_id, limit=limit_per_type,
    )
    r_total, r_items = await _count_and_sample(
        session, _RELATIONS_CYPHER, job_id=job_id, user_id=user_id, limit=limit_per_type,
    )
    new_items = (
        [FlywheelItem(kind="entity", id=i["id"], name=i["name"]) for i in e_items]
        + [FlywheelItem(kind="event", id=i["id"], name=i["name"]) for i in v_items]
        + [FlywheelItem(kind="relation", id=i["id"], name=i["name"]) for i in r_items]
    )
    return FlywheelDelta(
        entities_added=e_total,
        relations_added=r_total,
        events_added=v_total,
        new_items=new_items,
    )
