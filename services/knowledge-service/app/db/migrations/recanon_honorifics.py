"""D-ML-A5-RECANON-BACKFILL — one-time re-canonicalization for the A5 honorific
expansion (multilingual ML-2).

**Why.** A5 added native-script honorifics (様/大人/님/ông …) to
``loreweave_extraction.canonical.HONORIFICS``. `canonical_version` stays at 1
(DD-1: forward-only, no version bump — determinism is preserved because the same
input always maps to the same output under the new list). But entities extracted
*before* A5 had their honorific NOT stripped, so their stored ``canonical_name``
and node ``id`` are the un-stripped form. A *new* extraction of "田中様" now strips
to "田中" → a different ``canonical_id`` → it will NOT merge with the stranded
pre-A5 "田中様" node. This backfill reconciles those stranded nodes.

**Scope + safety (DD-1).** This is **operator-run, dry-run by default**. It is NOT
run against the shared dev DB from CI/tests — a re-key + cross-node merge is a
structural graph mutation barred by the "no destructive ops on shared dev DB"
rule. The reconciliation *planner* (`plan_recanon`) is a **pure function** and is
fully unit-tested; the apply path is a thin, explicit Cypher shim behind
``apply=True``.

    # dry-run (default): report what WOULD change, mutate nothing
    python -m app.db.migrations.recanon_honorifics
    # operator, after review:
    python -m app.db.migrations.recanon_honorifics --apply

Each stranded entity re-keys to its NEW canonical id. When a "clean" sibling
already exists at that id (extracted post-A5), the stranded node MERGEs into the
sibling (union of aliases/source_types/provenances, keeping the sibling as the
survivor). When several stranded variants collapse to the same new id with no
clean sibling, one is deterministically re-keyed as survivor and the rest merge
into it. Determinism → the plan is identical on every re-run (idempotent).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from loreweave_extraction.canonical import (
    canonicalize_entity_name,
    entity_canonical_id,
)

logger = logging.getLogger(__name__)

__all__ = ["EntityRow", "RecanonAction", "RecanonPlan", "plan_recanon", "run_recanon_backfill"]


@dataclass(frozen=True)
class EntityRow:
    """The minimal entity shape the planner needs. `id` is the stored
    (possibly pre-A5) canonical_id; `name` is the display name; `canonical_name`
    is the stored canonical form."""

    id: str
    user_id: str
    project_id: str | None
    kind: str
    name: str
    canonical_name: str


@dataclass(frozen=True)
class RecanonAction:
    """One reconciliation step. ``op`` is 'rekey' (survivor node moves to
    new_id) or 'merge' (from_id folds into into_id, then the old node is
    detached/removed by the apply path)."""

    op: str              # 'rekey' | 'merge'
    from_id: str         # the stranded node's current id
    into_id: str         # the target (new canonical) id
    user_id: str
    project_id: str | None
    kind: str
    name: str            # display name (carries the honorific spelling as an alias)


@dataclass
class RecanonPlan:
    actions: list[RecanonAction] = field(default_factory=list)
    scanned: int = 0
    clean: int = 0            # canonical_name already matches new canon — untouched
    skipped_empty: int = 0    # name canonicalizes to empty (degenerate) — untouched
    rekeyed: int = 0
    merged: int = 0

    def __repr__(self) -> str:  # pragma: no cover (debug aid)
        return (
            f"RecanonPlan(scanned={self.scanned}, clean={self.clean}, "
            f"skipped_empty={self.skipped_empty}, rekeyed={self.rekeyed}, "
            f"merged={self.merged}, actions={len(self.actions)})"
        )


def plan_recanon(rows: list[EntityRow]) -> RecanonPlan:
    """Pure planner — decide the reconciliation actions for a set of entities.

    No I/O. Deterministic: same input rows → same plan, every run. This is the
    unit-tested core; the apply path is a mechanical translation of the plan to
    Cypher.
    """
    plan = RecanonPlan()
    all_ids = {r.id for r in rows}

    # stranded[new_id] = list of rows whose stored canonical drifted from the
    # A5 re-canonicalization and now hash to new_id.
    stranded: dict[str, list[EntityRow]] = {}

    for r in rows:
        plan.scanned += 1
        new_canon = canonicalize_entity_name(r.name)
        if not new_canon:
            plan.skipped_empty += 1
            continue
        if new_canon == r.canonical_name:
            plan.clean += 1
            continue
        # Drifted: the A5 list strips a honorific the stored form kept.
        new_id = entity_canonical_id(r.user_id, r.project_id, r.name, r.kind)
        if new_id == r.id:
            # canonical_name text drifted but the id is unchanged (shouldn't
            # happen for an honorific strip, but guard anyway) — nothing to move.
            plan.clean += 1
            continue
        stranded.setdefault(new_id, []).append(r)

    for new_id, group in stranded.items():
        # Deterministic ordering so survivor selection is stable across runs.
        group_sorted = sorted(group, key=lambda r: r.id)
        clean_sibling_exists = new_id in all_ids and new_id not in {r.id for r in group}

        if clean_sibling_exists:
            # A post-A5 node already lives at new_id → every stranded node merges
            # into it; the sibling survives untouched.
            for r in group_sorted:
                plan.actions.append(RecanonAction(
                    op="merge", from_id=r.id, into_id=new_id,
                    user_id=r.user_id, project_id=r.project_id, kind=r.kind, name=r.name,
                ))
                plan.merged += 1
        else:
            # No clean sibling: promote the first stranded node to new_id, merge
            # the rest into it.
            survivor, *rest = group_sorted
            plan.actions.append(RecanonAction(
                op="rekey", from_id=survivor.id, into_id=new_id,
                user_id=survivor.user_id, project_id=survivor.project_id,
                kind=survivor.kind, name=survivor.name,
            ))
            plan.rekeyed += 1
            for r in rest:
                plan.actions.append(RecanonAction(
                    op="merge", from_id=r.id, into_id=new_id,
                    user_id=r.user_id, project_id=r.project_id, kind=r.kind, name=r.name,
                ))
                plan.merged += 1

    return plan


# ── real-I/O apply path (operator-run; not unit-tested — pure core is) ────────

_LIST_ENTITIES_CYPHER = """
MATCH (e:Entity)
WHERE e.archived_at IS NULL
RETURN e.id AS id, e.user_id AS user_id, e.project_id AS project_id,
       e.kind AS kind, e.name AS name, e.canonical_name AS canonical_name
"""


async def run_recanon_backfill(session, *, apply: bool = False) -> RecanonPlan:  # pragma: no cover (real I/O)
    """Walk Neo4j entities, build the plan, and (only when ``apply``) execute it.

    Cross-tenant read (operator-initiated, like the C17 alias-map backfill). With
    ``apply=False`` this mutates nothing — it returns the plan for review.
    """
    from app.db.neo4j_repos.entities import merge_entity_at_id  # local: avoid import cycle

    rows: list[EntityRow] = []
    result = await session.run(_LIST_ENTITIES_CYPHER)
    async for rec in result:
        if not rec["id"] or not rec["user_id"] or not rec["name"]:
            continue
        rows.append(EntityRow(
            id=rec["id"], user_id=rec["user_id"], project_id=rec["project_id"],
            kind=rec["kind"], name=rec["name"], canonical_name=rec["canonical_name"] or "",
        ))

    plan = plan_recanon(rows)
    if not apply:
        logger.info("recanon DRY-RUN: %r (pass --apply to execute)", plan)
        return plan

    for a in plan.actions:
        if a.op == "rekey":
            # Move the survivor node to its new canonical id + name. Relations
            # attach by node reference, so re-keying the id property is safe.
            await session.run(
                """
                MATCH (e:Entity {id: $old_id}) WHERE e.user_id = $user_id
                SET e.id = $new_id, e.canonical_name = $canon, e.updated_at = datetime()
                """,
                old_id=a.from_id, new_id=a.into_id, user_id=a.user_id,
                canon=canonicalize_entity_name(a.name),
            )
        else:  # merge
            merged = await merge_entity_at_id(
                session, user_id=a.user_id, id=a.into_id, project_id=a.project_id,
                name=a.name, kind=a.kind, source_type="recanon", provenance="recanon_backfill",
            )
            if merged is None:
                logger.warning("recanon merge target %s vanished; skipping %s", a.into_id, a.from_id)
                continue
            # Re-point the stranded node's relations to the survivor, then remove it.
            await session.run(
                """
                MATCH (old:Entity {id: $old_id}) WHERE old.user_id = $user_id
                MATCH (new:Entity {id: $new_id})
                OPTIONAL MATCH (old)-[r:RELATES_TO]->(o) MERGE (new)-[:RELATES_TO]->(o)
                WITH old MATCH (old)-[rel]-() DELETE rel WITH old DELETE old
                """,
                old_id=a.from_id, new_id=a.into_id, user_id=a.user_id,
            )
    logger.info("recanon APPLIED: %r", plan)
    return plan


async def _cli_main() -> None:  # pragma: no cover (integration-only)
    import argparse

    from app.db.neo4j import get_neo4j_driver, neo4j_session

    ap = argparse.ArgumentParser(description="A5 honorific re-canonicalization backfill")
    ap.add_argument("--apply", action="store_true", help="execute (default: dry-run)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO)
    get_neo4j_driver()
    async with neo4j_session() as session:
        plan = await run_recanon_backfill(session, apply=args.apply)
    logger.info(
        "recanon %s: scanned=%d clean=%d rekeyed=%d merged=%d",
        "APPLIED" if args.apply else "DRY-RUN",
        plan.scanned, plan.clean, plan.rekeyed, plan.merged,
    )


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    asyncio.run(_cli_main())
