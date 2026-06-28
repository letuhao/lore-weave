"""D-W8-MOTIF-BEAT-EXTRACTOR — motif-beat sequence derivation (Option A).

The composition-service motif miner (W8, narrative-pattern-library §12.4 / §R2.3)
needs **ordered beat-label sequences per book** as its PrefixSpan input: one list
per coherent narrative unit, each an ``event_order``-ordered list of
``{beat, thread, tension, role_mentions}`` steps.

**This is the deterministic Option A** — it RIDES the existing extracted
``:Event`` timeline (no new LLM call). knowledge-service already extracts
``:Event`` nodes keyed by ``event_order`` (the reading-order axis, dense at
chapter granularity via ``EVENT_ORDER_CHAPTER_STRIDE``). Each event maps cleanly
to a beat step:

  * **beat**          — the event's ``title`` (the narrative step label; the
                        miner abstracts these into ``(thread:beat)`` shapes).
  * **thread**        — the event's ``chapter_id`` (the coherent grouping the
                        event belongs to). Option A has no causal/thread edges
                        (spec R1.2 F-1: there are NO ``:CAUSES`` edges, only
                        scalar order), so chapter is the available thread proxy;
                        a real per-thread label is the LLM-extractor follow-up
                        (D-W8-MOTIF-BEAT-LLM-EXTRACTOR).
  * **tension**       — a 1..5 band derived from the event's salience signals
                        (the same ``importance`` projection the timeline rail
                        uses: participant breadth + confidence + re-mention
                        count). Matches the spec's ``tension_target(1..5)``.
  * **role_mentions** — the event's ``participants`` (resolved entity NAMES —
                        the concrete cast). The composition miner deliberately
                        strips these to mine reusable shapes; we keep them
                        concrete here per the frozen contract.

One **sequence per book/project**: events are grouped by their owning project
(book container) and ordered by ``event_order`` within it.

Tenancy: every query is scoped to ``user_id`` (the caller passes it; a
cross-user book/corpus returns ``[]``). Never crosses tenants.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.events import Event, list_events_in_order
from app.db.pool import get_knowledge_pool

logger = logging.getLogger(__name__)

# How many events one sequence (book) may contribute. A web-novel's full event
# set is book-scale (hundreds–low-thousands); cap so a pathological corpus can't
# materialise an unbounded sequence into the response. PrefixSpan over a few
# hundred beats per book is already plenty of mining signal.
_MAX_EVENTS_PER_SEQUENCE = 2000


def _tension_band(event: Event) -> int:
    """Map an event's salience to the 1..5 ``tension_target`` band the spec
    (§2.1 ``beats[].tension_target``) uses.

    Rides the SAME signals the ``Event.importance`` projection blends
    (participant breadth + confidence + re-mention count) so the band is
    consistent with the timeline rail's major/pivotal badges:

      * ``pivotal`` event → **5** (a clear hinge).
      * ``major``   event → **4** (notable, recurs).
      * else graded by raw salience: a multi-party or confident or
        re-mentioned event → **3**; a lightly-attested one → **2**; the
        long tail of one-off single-party events → **1** (floor).

    Never returns 0 — the band is always a real 1..5 dial.
    """
    importance = event.importance  # computed_field: 'pivotal' | 'major' | None
    if importance == "pivotal":
        return 5
    if importance == "major":
        return 4
    participant_count = len(event.participants)
    if participant_count >= 2 or event.confidence >= 0.5 or event.mention_count >= 2:
        return 3
    if event.confidence > 0.0 or event.mention_count >= 1:
        return 2
    return 1


def _event_to_beat_step(event: Event) -> dict:
    """Project one ``:Event`` into the frozen beat-step shape
    ``{beat, thread, tension, role_mentions}`` the composition client expects.

    ``thread`` prefers the classifier-assigned ``narrative_thread`` (D-W10-ARC-
    CONFORMANCE-THREAD-TAG — a real narrative thread like combat/romance), falling back
    to ``chapter_id`` (the Option-A proxy) then ``""`` when neither is set — a real string
    thread key, never null, so the miner can still partition by it (it groups every
    thread-less beat together). ``role_mentions`` is always a list (empty when none resolved).
    """
    return {
        "beat": event.title,
        "thread": event.narrative_thread or event.chapter_id or "",
        "tension": _tension_band(event),
        "role_mentions": list(event.participants),
    }


async def _list_user_book_projects(user_id: UUID, book_id: UUID | None, corpus: bool):
    """Resolve the (project_id, book_id) containers in scope for this call.

    * ``corpus=True``  → every NON-archived book-linked project the user owns.
    * ``book_id`` set  → just that book's project(s), but ONLY if the user owns
                         it (the WHERE clause filters by user_id, so a
                         cross-user book returns no rows → ``[]`` sequences).
    * neither          → ``[]`` (the composition client always sends one of the
                         two; defend against a malformed call).

    Returns a list of ``(project_id, book_id)`` rows. Book-less projects are
    excluded — a sequence is a *book* container per the contract.
    """
    pool = get_knowledge_pool()
    async with pool.acquire() as conn:
        if corpus:
            rows = await conn.fetch(
                "SELECT project_id, book_id FROM knowledge_projects "
                "WHERE user_id = $1 AND book_id IS NOT NULL AND NOT is_archived "
                "ORDER BY created_at ASC",
                user_id,
            )
        elif book_id is not None:
            rows = await conn.fetch(
                "SELECT project_id, book_id FROM knowledge_projects "
                "WHERE user_id = $1 AND book_id = $2 AND NOT is_archived "
                "ORDER BY created_at ASC",
                user_id, book_id,
            )
        else:
            return []
    return [(row["project_id"], row["book_id"]) for row in rows]


async def derive_motif_beat_sequences(
    *,
    user_id: UUID,
    book_id: UUID | None = None,
    corpus: bool = False,
    language: str | None = None,
) -> list[list[dict]]:
    """Option A — derive ordered motif-beat sequences from the extracted
    ``:Event`` timeline.

    Returns a LIST of sequences (one per in-scope book/project), each an
    ``event_order``-ORDERED list of ``{beat, thread, tension, role_mentions}``
    steps. An empty/absent corpus → ``[]`` (the composition miner degrades
    cleanly on ``[]``).

    ``language`` is accepted for contract compatibility but is **advisory** on
    the Option-A path: extracted ``:Event`` titles/participants are canonical
    SOURCE-language (the timeline localizer translates at read-time, not in
    storage), so there is no stored per-event language axis to filter on here.
    A real language-narrowed axis is the LLM-extractor follow-up
    (D-W8-MOTIF-BEAT-LLM-EXTRACTOR). We log when a language was requested so the
    no-op is visible, then proceed over the full timeline.

    Tenancy: scoped to ``user_id`` end to end (project lookup filters by it; a
    cross-user book yields no projects → ``[]``).
    """
    if language:
        logger.debug(
            "motif-beats: language=%r requested — advisory only on Option A "
            "(events are source-language; no stored language axis to filter)",
            language,
        )

    containers = await _list_user_book_projects(user_id, book_id, corpus)
    if not containers:
        return []

    sequences: list[list[dict]] = []
    async with neo4j_session() as session:
        for project_id, _container_book_id in containers:
            events = await list_events_in_order(
                session,
                user_id=str(user_id),
                project_id=str(project_id),
                limit=_MAX_EVENTS_PER_SEQUENCE,
            )
            # list_events_in_order already orders by event_order (nulls last)
            # then title — the dense reading-order axis the spec's PrefixSpan
            # input requires. Skip a project with no events (a cold-start book
            # contributes no sequence rather than an empty one).
            if not events:
                continue
            sequences.append([_event_to_beat_step(ev) for ev in events])

    return sequences
