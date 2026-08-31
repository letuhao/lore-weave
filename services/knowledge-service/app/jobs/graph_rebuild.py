"""Rebuild the graph from Postgres — the path three claims depended on (plan T41).

WHY IT MATTERS, AND WHY ITS ABSENCE WAS WORSE THAN IT LOOKED
------------------------------------------------------------
Sealed audit item **O6**: *"There is no rebuild-from-Postgres path at all. The only sweepers
are `reconcile_evidence_count` and `stats_updater`."* Three separate claims rested on it:

* **graph HA is unnecessary** — because the graph can be rebuilt
* **P3 engine-swap rollback** — point the adapter back and rebuild
* **disaster recovery** — the graph is derived, not primary

None of those was true while the path did not exist. `RESOLVED — WORSE THAN FEARED` is the
plan's own note, and it is the reason **T41 is a stop condition**: if a rebuild is impractical
at book scale, graph HA returns as a requirement and Phase 7's rollback story fails.

WHY IT IS ENGINE-INDEPENDENT — the reasoning that unblocked it
---------------------------------------------------------------
T41 was parked because *"its shape depends on the engine: if AGE wins, the graph IS Postgres"*.
**That was wrong, and the port is why.** The rebuild's job is to reconstruct graph nodes from
the authoritative Postgres data, and it does that **through `GraphStore`** — so one
implementation serves Neo4j, AGE, or anything T43 selects. Written before the port had
adopters it would have been Neo4j-specific; written now it is not, and it therefore no longer
waits on the engine decision.

That also makes it the honest backstop for the swap: the rollback story is not *"point the
adapter back"* (which strands whatever the new engine wrote) but *"point the adapter back and
rebuild from the source of truth"*.

WHAT IS AUTHORITATIVE, AND WHAT IS DERIVED
-------------------------------------------
`glossary_entities` in Postgres is the **SSOT** for entity identity. The graph node is a
projection of it — which is exactly why `purge_entity_by_glossary_id` exists and why 1632
orphaned anchors were reconcilable at all. So the rebuild reads the glossary and re-projects;
it does **not** try to reconstruct extraction-derived relations, because those have no
Postgres original to rebuild from.

⚠️ **That boundary is the honest limit of this task and is stated rather than glossed:** a
rebuild restores IDENTITY (nodes, anchors), not the full extracted edge set. Claiming
otherwise would make the DR story sound better than it is. See
`D-T41-RELATIONS-NOT-REBUILDABLE`.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app.ports.graph_store import GraphStore

logger = logging.getLogger(__name__)

__all__ = ["RebuildStats", "rebuild_entities_from_glossary"]


@dataclass
class RebuildStats:
    """What a rebuild did, and how long it took.

    `elapsed_s` is reported per run rather than left to a log line because **T41 is a stop
    condition**: the question is not only "does it work" but "is it affordable at book
    scale", and a path whose cost nobody measured cannot answer that.
    """

    entities_read: int = 0
    entities_written: int = 0
    failed: int = 0
    elapsed_s: float = 0.0
    # Rows that resolved onto a node an EARLIER row in the same run had already created.
    #
    # ⚠️ WITHOUT THIS THE REPORT OVERSTATES THE GRAPH. `entities_written` counts successful
    # CALLS, and `resolve_or_merge_entity` is keyed on the CANONICAL name, so two glossary
    # rows can legitimately be one node. Measured on a real book during the QC-7 drill:
    # 3187 rows written, `failed=0`, and 3171 nodes in the graph. The 16 were punctuation
    # variants and honorific forms the canonicaliser folds together on purpose.
    #
    # The graph was right; the REPORT was wrong, and during a disaster the report is all an
    # operator has. "3187 written, 0 failed" against 3171 nodes reads as silent data loss to
    # anyone who counts afterwards.
    merged_onto_existing: int = 0

    @property
    def distinct_nodes(self) -> int:
        """Nodes this run actually left in the graph — the number to reconcile against."""
        return self.entities_written - self.merged_onto_existing

    @property
    def rate(self) -> float:
        return self.entities_written / self.elapsed_s if self.elapsed_s else 0.0


async def rebuild_entities_from_glossary(
    store: GraphStore,
    *,
    user_id: str,
    project_id: str | None,
    entities: list[dict],
    batch_log_every: int = 100,
) -> RebuildStats:
    """Re-project glossary entities into the graph through the port. Idempotent.

    `entities` is the authoritative list from Postgres — passed in rather than fetched here so
    the caller owns paging and this function stays engine- AND transport-agnostic (a
    `GlossaryClient` page, a direct SQL read during DR, or a fixture in a drill).

    **Failures are counted, not raised.** A rebuild that aborts on the first bad row leaves a
    half-restored graph and no report, which during a disaster is the worst of both: the
    operator learns neither how far it got nor what stopped it. Every failure is logged with
    its entity id and the run continues.
    """
    stats = RebuildStats()
    seen_ids: set[str] = set()
    started = time.perf_counter()

    for i, ent in enumerate(entities, 1):
        stats.entities_read += 1
        name = (ent.get("name") or "").strip()
        kind = (ent.get("kind") or "").strip()
        if not name or not kind:
            # Neither is recoverable: the node's identity IS (name, kind), so a row missing
            # either cannot be projected into anything meaningful.
            stats.failed += 1
            logger.warning("rebuild: skipping entity %s — missing name/kind", ent.get("id"))
            continue
        try:
            written = await store.resolve_or_merge_entity(
                user_id=user_id,
                project_id=project_id,
                name=name,
                kind=kind,
                # `source_type='glossary'` and full confidence: these are user-curated rows
                # being restored, not extraction guesses being re-proposed. A rebuild that
                # re-entered them as low-confidence extractions would quietly demote the
                # author's own canon.
                source_type="glossary",
                confidence=1.0,
                provenance="human_authored",
            )
            stats.entities_written += 1
            # A canonical id we have already written in THIS run means two glossary rows
            # folded into one node. Counted here rather than inferred afterwards, because
            # the only other way to learn it is to count the graph and subtract — which is
            # exactly the reconciliation an operator should not have to invent mid-disaster.
            if written is not None:
                if written.id in seen_ids:
                    stats.merged_onto_existing += 1
                seen_ids.add(written.id)
        except Exception as exc:  # noqa: BLE001 — see the docstring: count, do not abort
            stats.failed += 1
            logger.warning("rebuild: entity %s failed: %s", ent.get("id"), exc)

        if batch_log_every and i % batch_log_every == 0:
            logger.info("rebuild: %d/%d entities", i, len(entities))

    stats.elapsed_s = time.perf_counter() - started
    logger.info(
        "rebuild complete: read=%d written=%d failed=%d elapsed=%.2fs rate=%.1f/s",
        stats.entities_read, stats.entities_written, stats.failed,
        stats.elapsed_s, stats.rate,
    )
    return stats
