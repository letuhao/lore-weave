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
    #: The glossary entity this node mirrors, when it has one. **Load-bearing, not metadata.**
    #: `:Entity(user_id, project_id, glossary_entity_id)` is UNIQUE, so folding two nodes that
    #: carry DIFFERENT anchors either raises or silently unanchors one of them — and an
    #: unanchored glossary entity is invisible in the KG while looking perfectly healthy in
    #: the glossary. Defaulted so existing callers and tests keep working; the collision
    #: guard treats `None` as "no claim", which is what a pre-anchor node is.
    anchor: str | None = None


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
    #: Groups left untouched because their members mirror DIFFERENT glossary entities. Not a
    #: failure and not a deferral — a refusal. See the guard in `plan_recanon`.
    conflicts: list[tuple[str, ...]] = field(default_factory=list)
    conflicted: int = 0

    def __repr__(self) -> str:  # pragma: no cover (debug aid)
        return (
            f"RecanonPlan(scanned={self.scanned}, clean={self.clean}, "
            f"skipped_empty={self.skipped_empty}, rekeyed={self.rekeyed}, "
            f"merged={self.merged}, conflicted={self.conflicted}, "
            f"actions={len(self.actions)})"
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

        # 🔴 TWO DISTINCT GLOSSARY ENTITIES MUST NEVER BE FOLDED TOGETHER (T35e).
        #
        # Measured on the dev graph 2026-08-14: of 1826 planned actions, 7 were merges and
        # SIX of them would have folded a node carrying one anchor into a node carrying a
        # different one — 卡維嘉小姐, 精靈小姐, 魔王殿, 魔王大人. Honorific stripping is exactly
        # the operation that makes two different characters canonicalise together: 精靈小姐
        # ("Miss Elf") and 精靈 are one string apart, and the glossary knows they are two
        # entities even when the canonicaliser cannot see it.
        #
        # `merge_entity`'s own Cypher had already found this class and said so — *"ALL 17 are
        # multi-ANCHORED … a bare 'oldest wins' would have silently moved extraction writes
        # between those nodes"* — and this planner, written earlier, does a bare oldest-wins.
        #
        # Such a group is REPORTED and LEFT ALONE. Both nodes want the same derived id, so
        # they cannot both be re-keyed; leaving them stranded preserves the status quo (they
        # still fork on re-extraction) while destroying nothing, and a human decides whether
        # they are really one entity. Refusing to act is the only option here that cannot
        # lose an author's data.
        anchors = {r.anchor for r in group_sorted if r.anchor}
        target_anchor = next((r.anchor for r in rows if r.id == new_id and r.anchor), None)
        if target_anchor:
            anchors.add(target_anchor)
        if len(anchors) > 1:
            plan.conflicts.append(tuple(r.id for r in group_sorted))
            plan.conflicted += len(group_sorted)
            continue

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
       e.kind AS kind, e.name AS name, e.canonical_name AS canonical_name,
       // 🔴 WITHOUT THIS THE COLLISION GUARD IS DEAD CODE. It shipped for exactly as long as
       // it took to write a wiring test: every `EntityRow.anchor` defaulted to None, so the
       // "two distinct glossary entities" set never had more than one member and the guard
       // could not fire once in production. Built, unit-tested, and connected to nothing —
       // the defect class this plan has now hit in a cache, a port and a gate.
       e.glossary_entity_id AS anchor
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
            anchor=rec["anchor"],
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
            # 🔴 `:EntityStatus` carries `entity_id` as a PROPERTY, not as an edge, so the
            # re-key above STRANDS every status row that pointed at the old id. Proven by
            # EXECUTING the apply path (T35f) -- the assertion read `0 == 1`: the status row
            # survived and resolved to nothing. A canon read would then report the character
            # as never having died.
            #
            # Measured on the dev graph the same day, 0 of 33 resolvable status rows sit on an
            # entity this backfill re-keys, so the live run was safe BY LUCK. One new status on
            # a stale entity makes it real, and nothing here was checking.
            await session.run(
                """
                MATCH (st:EntityStatus {entity_id: $old_id})
                WHERE st.user_id = $user_id
                SET st.entity_id = $new_id
                """,
                old_id=a.from_id, new_id=a.into_id, user_id=a.user_id,
            )
            # 🔴 `:EntityStatus` carries `entity_id` as a PROPERTY, not as an edge, so the
            # re-key above STRANDS every status row that pointed at the old id. Proven by
            # execution (T35f) — the assertion read `0 == 1`: the status survived and resolved
            # to nothing. A canon read would then report the character as never having died.
            #
            # Measured on the dev graph the same day, 0 of 33 resolvable status rows sit on an
            # entity this backfill re-keys, so the live run was safe BY LUCK. One new status on
            # a stale entity makes it real, and nothing here was checking.
            
        else:  # merge
            merged = await merge_entity_at_id(
                session, user_id=a.user_id, id=a.into_id, project_id=a.project_id,
                name=a.name, kind=a.kind, source_type="recanon", provenance="recanon_backfill",
            )
            if merged is None:
                logger.warning("recanon merge target %s vanished; skipping %s", a.into_id, a.from_id)
                continue
            # Re-point the stranded node's relations to the survivor, then remove it.
            # 🔴 THREE DEFECTS IN THE STATEMENT THIS REPLACES, all found by executing it
            # (T35f) rather than by reading it:
            #
            # 1. `OPTIONAL MATCH (old)-[r]->(o) MERGE (new)-[:RELATES_TO]->(o)` RAISES when the
            #    stranded node has no outgoing relation: `o` is null and MERGE refuses to build
            #    an edge to a missing node. That is the COMMON case, so `--apply` would have
            #    died partway through and left the graph half-migrated.
            # 2. The re-created edge carried NO PROPERTIES. A relation's `predicate` is its
            #    meaning — "betrayed" and "guards" are one edge type and two different facts —
            #    so every folded relation became a typeless link.
            # 3. Only OUTGOING edges were re-pointed. An incoming `(x)-[:RELATES_TO]->(old)`
            #    was deleted with the node and never rebuilt.
            #
            # Rewritten as three statements: copy out, copy in, then delete. Each is guarded by
            # its own MATCH, so an absent edge is simply no rows rather than an exception.
            await session.run(
                """
                MATCH (old:Entity {id: $old_id})-[r:RELATES_TO]->(o)
                WHERE old.user_id = $user_id
                MATCH (new:Entity {id: $new_id})
                MERGE (new)-[n:RELATES_TO {predicate: r.predicate}]->(o)
                SET n += properties(r)
                """,
                old_id=a.from_id, new_id=a.into_id, user_id=a.user_id,
            )
            await session.run(
                """
                MATCH (x)-[r:RELATES_TO]->(old:Entity {id: $old_id})
                WHERE old.user_id = $user_id
                MATCH (new:Entity {id: $new_id})
                MERGE (x)-[n:RELATES_TO {predicate: r.predicate}]->(new)
                SET n += properties(r)
                """,
                old_id=a.from_id, new_id=a.into_id, user_id=a.user_id,
            )
            await session.run(
                """
                MATCH (old:Entity {id: $old_id}) WHERE old.user_id = $user_id
                DETACH DELETE old
                """,
                old_id=a.from_id, user_id=a.user_id,
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
