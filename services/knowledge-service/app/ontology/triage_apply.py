"""Re-apply a resolved triage item through the central write path (lane LH).

When a KG-local resolution (`map` / `re_target` / `widen_target_kinds` /
`drop_edge` / `close_previous` / `set_multi_active`) makes a previously-parked
element schema-valid, the corrected edge/fact must be (re)written into Neo4j --
but ONLY via the **central write path** (D5: relations/facts repos), never raw
Cypher from here. This module is the seam between the PG-side triage state
machine (`app.db.repositories.triage`) and that write path.

WHY A SEAM, NOT THE WRITE ITSELF
================================
The actual Neo4j re-apply integrates at C4/L7 together with lane LB (extraction
park + the schema-aware write path that knows how to turn a parked
``payload`` back into a validated edge/fact). At LH-build time that consumer
does not exist yet, so this module:

  * fully classifies each action (KG-local re-apply vs glossary hand-off vs
    schema-mutating vs dismiss) -- the decision logic IS owned here, and
  * exposes ``apply_resolved(item, action, params, *, writer=...)`` that DELEGATES
    the Neo4j write to an injected ``ReapplyWriter``. The default writer raises
    ``NotImplementedError`` (the un-wired seam); tests pass a fake writer and
    assert it is called with the right corrected element.

DEFERRED: ``D-KG-LH-NEO4J-REAPPLY`` -- wire a real ``ReapplyWriter`` over the
relations/facts central write path when LB/L7 land. Until then the router
resolves the PG state (status -> resolved/pending_glossary) and, for KG-local
actions, MAY skip the live re-apply (tracked) rather than 500.

Spec: docs/specs/2026-06-20-knowledge-graph-customizable-ontology.md s11.2 / s11.4.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from app.db.ontology_models import TriageItem
from app.db.repositories.triage import (
    GLOSSARY_HANDOFF_ACTIONS,
    SCHEMA_MUTATING_ACTIONS,
)


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
