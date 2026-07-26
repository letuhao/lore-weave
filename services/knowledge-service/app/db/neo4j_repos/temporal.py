"""F3 — story valid-time (chapter-ordinal) bi-temporal primitives.

Incremental Temporal Knowledge Architecture, milestone F3 (KG side).
Spec: ``docs/specs/2026-06-29-incremental-temporal-knowledge-architecture.md``
§12.3 (bi-temporal correctness). This module is the **single home** of the
locked interval convention + the ordinal-aware chain-maintenance routine that
BOTH ``:Fact`` and ``:RELATES_TO`` reuse, so neither substrate re-derives it.

## The two time axes (§3.2)

Every fact/relation carries TWO independent temporal axes:

| Axis | Fields | Meaning |
|---|---|---|
| **Story (valid) time** | ``valid_from_ordinal`` / ``valid_to_ordinal`` | the chapter range over which it held true *in the story* — UNIFIED with the existing ``from_order``/``event_order`` reading axis (§8B: "unify with from_order") |
| **Transaction (system) time** | ``valid_from`` / ``valid_until`` (wall-clock ``datetime()``) | when we ingested it / when a re-extraction superseded it — today's existing columns, kept as-is |

Story-time uses CHAPTER ORDINALS (ints), NOT wall-clock — that is the
load-bearing F3 change. ``valid_from_ordinal`` is the ordinal at which the
fact/edge was first established; ``valid_to_ordinal`` is the ordinal at which a
later, superseding fact opened (or NULL while still current).

## Interval convention — LOCKED half-open ``[from, to)`` (§12.3.1, D1)

An open fact stores ``valid_to_ordinal = NULL`` meaning **+∞**. The canonical
as-of-N predicate, everywhere (it matches ``contracts/api/knowledge-service/
views.yaml`` and the §5 predicate):

    valid_from_ordinal <= N AND (valid_to_ordinal IS NULL OR N < valid_to_ordinal)

A supersede sets ``old.valid_to_ordinal = new.valid_from_ordinal`` (contiguous:
no gap, no overlap). For an index-served range query we also stamp a stored
``valid_to_ordinal_eff = coalesce(valid_to_ordinal, _ORDINAL_OPEN_CEILING)`` —
the **null-sink** ceiling, NOT ``spoiler_window.py``'s fail-closed ``-1``
(which is the OPPOSITE sentinel). We reuse the exact KG null-sink
``events._NULL_ORDER_SENTINEL`` (= INT64_MAX = ``9223372036854775807``) so the
two scales never diverge.

## The close is an ordinal-aware interval-split (§12.3.2, A2) — NOT single_active

The existing ``relations._CLOSE_PRIOR_SINGLE_ACTIVE_CYPHER`` closes *any* open
instance by wall-clock ``datetime()`` — ZERO ordinal awareness, so a
back-filled / out-of-order fact inverts a still-correct later interval (gap A2).
``maintain_chain`` here is the correct primitive: for a ``(scope-key)`` chain it
sorts the *surviving* instances by ``valid_from_ordinal`` and sets each
``valid_to_ordinal = next survivor's valid_from_ordinal`` (the last stays open).
It is the **single writer** of ``valid_to_ordinal`` and is invoked at three
entry points — the open-fact close (§12.3.2), the retract re-stitch (§12.3.3
step B.3.5), and (future) the merge reconcile (§12.4.1) — so they are one
routine, not three algorithms. Correct for backfill, parallel/ATOM merge, and
re-import; ``single_active`` stays only for monotonic L7/user edits.
"""

from __future__ import annotations

# Reuse the EXACT KG null-sink sentinel (= INT64_MAX) from events.py so the open
# interval ceiling and the timeline null-sink are on one scale. Importing the
# private name is deliberate: events.py is the single source of truth for it
# (its docstring explains why INT64_MAX over INT32_MAX), and F3 must not mint a
# second, drifting copy.
from app.db.neo4j_repos.events import _NULL_ORDER_SENTINEL
from app.db.neo4j_helpers import CypherSession, run_write

__all__ = [
    "ORDINAL_OPEN_CEILING",
    "AS_OF_ORDINAL_PREDICATE",
    "valid_to_ordinal_eff",
    "MAINTAIN_FACT_CHAIN_CYPHER",
    "MAINTAIN_RELATION_CHAIN_CYPHER",
    "restitch_chains_after_retract",
]

# The +∞ ceiling a NULL (open) ``valid_to_ordinal`` resolves to for the stored
# ``valid_to_ordinal_eff`` indexable column + range comparisons. = INT64_MAX.
ORDINAL_OPEN_CEILING: int = _NULL_ORDER_SENTINEL

# The LOCKED half-open as-of-N predicate (§12.3.1). A reusable Cypher fragment so
# every read path (and tests) shares ONE convention instead of re-spelling it.
# ``$as_of_ordinal`` is the chapter ordinal N; the property prefix is the bound
# node/edge alias (e.g. ``f`` or ``r``). Callers interpolate the alias at module
# load only (closed set), never from user input.
AS_OF_ORDINAL_PREDICATE = (
    "{a}.valid_from_ordinal <= $as_of_ordinal "
    "AND ({a}.valid_to_ordinal IS NULL "
    "OR $as_of_ordinal < {a}.valid_to_ordinal)"
)


def valid_to_ordinal_eff(valid_to_ordinal: int | None) -> int:
    """Resolve a (possibly-NULL/open) ``valid_to_ordinal`` to its effective
    indexable ceiling — the value stored in ``valid_to_ordinal_eff``.

    Open (NULL) → ``ORDINAL_OPEN_CEILING`` (+∞ null-sink). This is computed
    application-side (Neo4j has no STORED generated column like Postgres), and
    written by the same ``maintain_chain`` routine that writes
    ``valid_to_ordinal``, so the two never drift.
    """
    return ORDINAL_OPEN_CEILING if valid_to_ordinal is None else valid_to_ordinal


# ── maintain_chain — the ONE ordinal-aware interval-split writer (§12.3.2/.3) ──
#
# Re-derives the ENTIRE ``valid_to_ordinal`` chain for one scope from the
# surviving (open in TRANSACTION time: ``valid_until IS NULL``) instances,
# sorted by ``valid_from_ordinal``. Each instance's ``valid_to_ordinal`` = the
# NEXT survivor's ``valid_from_ordinal``; the last survivor stays open
# (``valid_to_ordinal = NULL``). ``valid_to_ordinal_eff`` is stamped in lockstep
# (null-sink for the open tail). This is an interval-tree rebuild, so it is
# correct regardless of arrival order (backfill / out-of-order / ATOM merge) and
# is idempotent (re-running over an already-consistent chain is a no-op write).
#
# Instances with a NULL ``valid_from_ordinal`` (legacy / positionless facts that
# never got a story ordinal — e.g. chat-tool facts) are EXCLUDED from the chain
# re-derivation: they have no place on the story axis, so they keep whatever
# ``valid_to_ordinal`` they had (NULL) and never shadow a positioned interval.
# The ``WHERE x.valid_from_ordinal IS NOT NULL`` guard enforces this.
#
# TRANSACTION-time invalidation (``valid_until``) is the retract/supersede
# mechanism and is NOT touched here — this routine only maintains the STORY-time
# ``valid_to_ordinal`` chain over whatever instances are currently believed.

# Fact chain: one ``(:Entity)`` + ``attr`` (the fact ``type`` — decision /
# preference / milestone / negation), scoped by ``$user_id``. A fact joins its
# subject entity via ``(:Fact)-[:ABOUT]->(:Entity)``; the chain is per
# (subject-entity, fact-type).
MAINTAIN_FACT_CHAIN_CYPHER = """
MATCH (f:Fact)-[:ABOUT]->(e:Entity {id: $entity_id})
WHERE f.user_id = $user_id
  AND e.user_id = $user_id
  AND f.type = $attr
  AND f.valid_until IS NULL
  AND f.valid_from_ordinal IS NOT NULL
WITH f ORDER BY f.valid_from_ordinal ASC, f.created_at ASC
WITH collect(f) AS chain
UNWIND range(0, size(chain) - 1) AS i
WITH chain, chain[i] AS cur
// STRICTLY-GREATER next bound (mirrors the Postgres maintain_chain core): the
// next-greater valid_from in the chain, never an EQUAL one. Two instances sharing
// a valid_from_ordinal (same-chapter ties — facts/relations stamp the chapter
// ordinal with no per-item offset) must NOT close each other into a zero-width
// [base, base) interval (invisible at every as-of read, the A2 bug). They both get
// the same next-greater bound (a real overlap) or both stay open if co-last.
WITH cur, [x IN chain WHERE x.valid_from_ordinal > cur.valid_from_ordinal
           | x.valid_from_ordinal] AS greaters
SET cur.valid_to_ordinal =
      CASE WHEN size(greaters) = 0 THEN NULL ELSE greaters[0] END,
    cur.valid_to_ordinal_eff =
      CASE WHEN size(greaters) = 0 THEN $open_ceiling ELSE greaters[0] END,
    cur.updated_at = datetime()
RETURN count(cur) AS maintained
"""

# ── retract re-stitch (§12.3.3 step B.3.5, A3) ──────────────────────────────
#
# When a re-extraction RETRACTS a fact/relation (transaction-time close via
# remove_evidence_* → zero-evidence sweep), the STORY-time interval it occupied
# is left dangling: its predecessor's valid_to_ordinal still points at the now-
# deleted instance's valid_from_ordinal, so an as-of read between them returns
# nothing (A3). The fix is to re-run the SAME ordinal-aware chain-maintenance
# over the SURVIVORS of every affected chain — the predecessor's valid_to is
# re-derived to the next surviving instance's valid_from (or NULL/open if it is
# now the last), auto-restitching the chain. This is the same single maintainer
# routine of §12.3.3, just driven across all chains in the partition rather than
# one. It only runs on a genuine retract (gated by the caller on removed > 0),
# so the O(distinct-chains) cost is off the hot first-extract path.
#
# These two re-derive EVERY fact-chain / relation-chain in the (user, project)
# partition in one pass. A chain that wasn't touched re-derives to its existing
# values (idempotent no-op write). Positionless instances (NULL
# valid_from_ordinal) are excluded from the re-derivation exactly as in the
# single-chain routine, so they never shadow a positioned interval.
_RESTITCH_ALL_FACT_CHAINS_CYPHER = """
MATCH (f:Fact)-[:ABOUT]->(e:Entity)
WHERE f.user_id = $user_id
  AND e.user_id = $user_id
  AND ($project_id IS NULL OR f.project_id = $project_id)
  AND f.valid_until IS NULL
  AND f.valid_from_ordinal IS NOT NULL
WITH e.id AS entity_id, f.type AS attr, f
ORDER BY f.valid_from_ordinal ASC, f.created_at ASC
WITH entity_id, attr, collect(f) AS chain
UNWIND range(0, size(chain) - 1) AS i
WITH chain, chain[i] AS cur
// STRICTLY-GREATER next bound (mirrors the Postgres maintain_chain core): the
// next-greater valid_from in the chain, never an EQUAL one. Two instances sharing
// a valid_from_ordinal (same-chapter ties — facts/relations stamp the chapter
// ordinal with no per-item offset) must NOT close each other into a zero-width
// [base, base) interval (invisible at every as-of read, the A2 bug). They both get
// the same next-greater bound (a real overlap) or both stay open if co-last.
WITH cur, [x IN chain WHERE x.valid_from_ordinal > cur.valid_from_ordinal
           | x.valid_from_ordinal] AS greaters
SET cur.valid_to_ordinal =
      CASE WHEN size(greaters) = 0 THEN NULL ELSE greaters[0] END,
    cur.valid_to_ordinal_eff =
      CASE WHEN size(greaters) = 0 THEN $open_ceiling ELSE greaters[0] END,
    cur.updated_at = datetime()
RETURN count(cur) AS restitched
"""

_RESTITCH_ALL_RELATION_CHAINS_CYPHER = """
MATCH (subj:Entity)-[r:RELATES_TO]->(obj:Entity)
WHERE r.user_id = $user_id
  AND subj.user_id = $user_id
  AND obj.user_id = $user_id
  AND ($project_id IS NULL OR subj.project_id = $project_id)
  AND r.valid_until IS NULL
  AND r.valid_from_ordinal IS NOT NULL
WITH subj.id AS subject_id, r.predicate AS predicate, r
ORDER BY r.valid_from_ordinal ASC, r.created_at ASC
WITH subject_id, predicate, collect(r) AS chain
UNWIND range(0, size(chain) - 1) AS i
WITH chain, chain[i] AS cur
// STRICTLY-GREATER next bound (mirrors the Postgres maintain_chain core): the
// next-greater valid_from in the chain, never an EQUAL one. Two instances sharing
// a valid_from_ordinal (same-chapter ties — facts/relations stamp the chapter
// ordinal with no per-item offset) must NOT close each other into a zero-width
// [base, base) interval (invisible at every as-of read, the A2 bug). They both get
// the same next-greater bound (a real overlap) or both stay open if co-last.
WITH cur, [x IN chain WHERE x.valid_from_ordinal > cur.valid_from_ordinal
           | x.valid_from_ordinal] AS greaters
SET cur.valid_to_ordinal =
      CASE WHEN size(greaters) = 0 THEN NULL ELSE greaters[0] END,
    cur.valid_to_ordinal_eff =
      CASE WHEN size(greaters) = 0 THEN $open_ceiling ELSE greaters[0] END,
    cur.updated_at = datetime()
RETURN count(cur) AS restitched
"""


async def restitch_chains_after_retract(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None = None,
) -> int:
    """Re-stitch every story-time interval chain in the partition after a
    retract (§12.3.3 step B.3.5, A3).

    Re-runs the ordinal-aware chain-maintenance over the SURVIVORS of every
    fact-chain ``(entity, type)`` and relation-chain ``(subject, predicate)`` so a
    predecessor whose successor was retracted re-extends to the next survivor (or
    re-opens if it is now the last). Idempotent on untouched chains (re-derives to
    the same values). Caller gates this on a genuine retract (``removed > 0``) so
    it never runs on a first-time extraction. Returns the total instances
    re-derived (facts + relations).
    """
    fact_res = await run_write(
        session,
        _RESTITCH_ALL_FACT_CHAINS_CYPHER,
        user_id=user_id,
        project_id=project_id,
        open_ceiling=ORDINAL_OPEN_CEILING,
    )
    fact_row = await fact_res.single()
    rel_res = await run_write(
        session,
        _RESTITCH_ALL_RELATION_CHAINS_CYPHER,
        user_id=user_id,
        project_id=project_id,
        open_ceiling=ORDINAL_OPEN_CEILING,
    )
    rel_row = await rel_res.single()
    facts = int(fact_row["restitched"]) if fact_row else 0
    rels = int(rel_row["restitched"]) if rel_row else 0
    return facts + rels


# Relation chain: one ``(subject)-[:RELATES_TO {predicate}]->`` scope, across ANY
# object, scoped by ``$user_id`` — mirrors the ``single_active`` scope (same
# subject + predicate) but ordinal-aware. A subject's drive/membership/etc. arc
# is the per-(subject, predicate) instance chain.
MAINTAIN_RELATION_CHAIN_CYPHER = """
MATCH (subj:Entity {id: $subject_id})-[r:RELATES_TO]->(obj:Entity)
WHERE r.user_id = $user_id
  AND subj.user_id = $user_id
  AND obj.user_id = $user_id
  AND r.predicate = $predicate
  AND r.valid_until IS NULL
  AND r.valid_from_ordinal IS NOT NULL
WITH r ORDER BY r.valid_from_ordinal ASC, r.created_at ASC
WITH collect(r) AS chain
UNWIND range(0, size(chain) - 1) AS i
WITH chain, chain[i] AS cur
// STRICTLY-GREATER next bound (mirrors the Postgres maintain_chain core): the
// next-greater valid_from in the chain, never an EQUAL one. Two instances sharing
// a valid_from_ordinal (same-chapter ties — facts/relations stamp the chapter
// ordinal with no per-item offset) must NOT close each other into a zero-width
// [base, base) interval (invisible at every as-of read, the A2 bug). They both get
// the same next-greater bound (a real overlap) or both stay open if co-last.
WITH cur, [x IN chain WHERE x.valid_from_ordinal > cur.valid_from_ordinal
           | x.valid_from_ordinal] AS greaters
SET cur.valid_to_ordinal =
      CASE WHEN size(greaters) = 0 THEN NULL ELSE greaters[0] END,
    cur.valid_to_ordinal_eff =
      CASE WHEN size(greaters) = 0 THEN $open_ceiling ELSE greaters[0] END,
    cur.updated_at = datetime()
RETURN count(cur) AS maintained
"""
