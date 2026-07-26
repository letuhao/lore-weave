"""Re-apply a resolved triage item through the central write path (lane LH).

When a KG-local resolution (`map` / `re_target` / `widen_target_kinds` /
`drop_edge` / `close_previous` / `set_multi_active`) makes a previously-parked
element schema-valid, the corrected edge/fact must be (re)written into Neo4j --
but ONLY via the **central write path** (D5: relations/facts repos), never raw
Cypher from here. This module is the seam between the PG-side triage state
machine (`app.db.repositories.triage`) and that write path.

THE REAL WRITER (E1, D-KG-LH-NEO4J-REAPPLY)
===========================================
``Neo4jReapplyWriter`` is the concrete ``ReapplyWriter`` over ``create_relation``
(D5). It reconstructs the corrected edge from the resolved triage item's parked
``payload`` (+ the resolution ``params``) and writes it through the central path:

  * ``map``           — write the (optionally code-mapped) edge.
  * ``re_target``     — write the edge with the corrected target entity.
  * ``close_previous``— write the new edge with ``cardinality="single_active"``,
    reusing Lane A's auto-close of the prior open instance.

Owner-scoped: the router injects the writer bound to the resolved project OWNER
(resolve-to-owner), so ``create_relation`` writes under the owner's tenant
partition — never the caller's. Fail-soft per item: a single item whose payload
can't be reconstructed into a valid edge raises ``TriageApplyError`` (or the
write returns ``None``), which the router's batch loop logs + continues — one
bad park never breaks the batch.

``NotWiredReapplyWriter`` is retained as the explicit "un-wired" default for the
pure-unit ``apply_resolved`` contract tests; the live router always injects the
real writer.

Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md s11.2 / s11.4;
docs/specs/2026-06-21-kg-deferred-clearance.md §5 (E1).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from app.db.neo4j_repos.relations import create_relation
from app.db.ontology_models import TriageItem
from app.db.repositories.triage import (
    GLOSSARY_HANDOFF_ACTIONS,
    SCHEMA_MUTATING_ACTIONS,
)

logger = logging.getLogger(__name__)


class TriageApplyError(Exception):
    """Raised when an action is not valid for an item / cannot be applied."""


# Actions that DON'T re-create an edge in Neo4j (no central-write-path call).
#   - dismiss / drop_edge: the parked element is intentionally discarded.
#   - glossary hand-off: the user acts in glossary; KG re-processes LATER (when
#     the kind appears), not synchronously here.
#   - schema-mutating: LC writes the schema; the *re-apply* of the now-valid
#     parked elements is a follow-on (LC bumps schema_version; re-extraction or a
#     later sweep re-applies). LH does not own the schema write.
_NO_REAPPLY_ACTIONS = (
    frozenset({"dismiss", "drop_edge"})
    | GLOSSARY_HANDOFF_ACTIONS
    | SCHEMA_MUTATING_ACTIONS
)

# KG-local actions whose resolution re-creates a schema-valid edge/fact that must
# be written into Neo4j via the central write path (D5).
REAPPLY_ACTIONS = frozenset({"map", "re_target", "close_previous"})


@runtime_checkable
class ReapplyWriter(Protocol):
    """The central write path LH delegates Neo4j re-apply to (D5).

    A concrete impl (LB/L7) turns a corrected parked ``payload`` into a validated
    edge/fact and writes it via the relations/facts repos -- this Protocol is the
    typed contract so LH can be built + unit-tested ahead of that consumer.
    """

    async def reapply(
        self, item: TriageItem, *, action: str, params: dict[str, Any]
    ) -> None:
        ...


class NotWiredReapplyWriter:
    """Default writer for the un-wired seam (``D-KG-LH-NEO4J-REAPPLY``).

    Raising here keeps the seam loud: nothing silently believes a parked edge was
    re-written into Neo4j. The router treats this as "PG state resolved, live
    re-apply deferred" rather than a 500 (it never instantiates the real write).
    """

    async def reapply(
        self, item: TriageItem, *, action: str, params: dict[str, Any]
    ) -> None:
        raise NotImplementedError(
            "Neo4j triage re-apply is not wired yet (D-KG-LH-NEO4J-REAPPLY); "
            "integrates at C4/L7 with lane LB over the relations/facts write path"
        )


def requires_reapply(action: str) -> bool:
    """True when the action's resolution must (re)write an edge/fact into Neo4j
    through the central write path. False for dismiss/drop/glossary-handoff/
    schema-mutating actions (which have no synchronous Neo4j write here)."""
    return action in REAPPLY_ACTIONS


async def apply_resolved(
    item: TriageItem,
    action: str,
    params: dict[str, Any] | None = None,
    *,
    writer: ReapplyWriter | None = None,
) -> bool:
    """Re-apply ONE resolved triage item through the central write path.

    Returns True if a Neo4j re-apply was performed, False if the action has no
    synchronous Neo4j write (dismiss / drop_edge / glossary hand-off /
    schema-mutating). For ``REAPPLY_ACTIONS`` it delegates to ``writer`` (default
    = the un-wired seam, which raises ``NotImplementedError`` -- caller catches
    and tracks ``D-KG-LH-NEO4J-REAPPLY``).

    This is the per-ITEM unit; the router loops it over every pending item of a
    signature (batch re-apply, s11.3).
    """
    if not requires_reapply(action):
        return False
    w = writer or NotWiredReapplyWriter()
    await w.reapply(item, action=action, params=params or {})
    return True


# ── E1 — the real writer over the central write path (create_relation) ─────────
def _edge_fields(item: TriageItem, params: dict[str, Any]) -> tuple[str, str, str]:
    """Reconstruct (subject_id, predicate, object_id) for the corrected edge from
    a parked triage payload + the resolution params.

    Two park sources feed this seam, with different key names, so we normalize
    both:
      * extraction off-schema park (pass2_writer) — ``subject_id`` / ``object_id``
        / ``predicate``.
      * agent draft (kg_propose_edge) — ``source_entity_id`` / ``target_entity_id``
        / ``predicate``.

    Resolution params override the parked values for the corrected write:
      * ``map``       — ``params.map_to`` (or ``params.predicate``) re-codes the
        predicate to the mapped edge-type.
      * ``re_target`` — ``params.target_entity_id`` (or ``params.object_id``)
        replaces the object endpoint.

    Raises ``TriageApplyError`` when a required field is absent — the router's
    batch loop catches it (fail-soft, log + continue)."""
    payload = item.payload or {}
    subject_id = payload.get("subject_id") or payload.get("source_entity_id")
    object_id = payload.get("object_id") or payload.get("target_entity_id")
    predicate = payload.get("predicate")

    # re_target — corrected object endpoint comes from the resolution params.
    if "target_entity_id" in params or "object_id" in params:
        object_id = params.get("target_entity_id") or params.get("object_id") or object_id
    # map — corrected predicate code comes from the resolution params.
    if "map_to" in params or "predicate" in params:
        predicate = params.get("map_to") or params.get("predicate") or predicate

    if not subject_id or not object_id or not predicate:
        raise TriageApplyError(
            f"triage item {item.triage_id} payload lacks the (subject, predicate, "
            f"object) needed to re-apply the edge (subject={subject_id!r}, "
            f"predicate={predicate!r}, object={object_id!r})"
        )
    return str(subject_id), str(predicate), str(object_id)


class Neo4jReapplyWriter:
    """Real ``ReapplyWriter`` (E1, D-KG-LH-NEO4J-REAPPLY).

    Writes the corrected edge for a resolved KG-local triage item through the
    central ``create_relation`` path under the project OWNER (resolve-to-owner —
    the router injects ``owner``). ``close_previous`` passes
    ``cardinality="single_active"`` so Lane A auto-closes the prior open
    instance between the same endpoints before the new one is MERGEd.

    A ``CypherSession`` is injected (so the router can reuse one session for the
    whole batch). The owner's id is the tenant partition key — NEVER the
    caller's — so a cross-tenant write is structurally impossible here."""

    def __init__(self, session: Any, *, owner_user_id: str) -> None:
        self._session = session
        self._owner = owner_user_id

    async def reapply(
        self, item: TriageItem, *, action: str, params: dict[str, Any]
    ) -> None:
        subject_id, predicate, object_id = _edge_fields(item, params)
        cardinality = "single_active" if action == "close_previous" else None
        rel = await create_relation(
            self._session,
            user_id=self._owner,
            subject_id=subject_id,
            predicate=predicate,
            object_id=object_id,
            confidence=1.0,  # human-confirmed resolution
            pending_validation=False,
            schema_version=item.schema_version,
            cardinality=cardinality,
        )
        if rel is None:
            # Endpoint missing under the owner (e.g. deleted entity / stale id) —
            # nothing to relate. Fail-soft: surface so the batch loop logs + skips.
            raise TriageApplyError(
                f"triage item {item.triage_id}: edge endpoint not found under the "
                f"owner (subject={subject_id!r}, object={object_id!r}) — skipped"
            )
