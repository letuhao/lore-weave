#!/usr/bin/env python3
"""kg-orphan-anchor-reconcile — delete KG nodes whose glossary anchor no longer exists.

WHY THIS EXISTS. `glossary.entity_purged` → `purge_entity_by_glossary_id` cascades a
Postgres purge into Neo4j, and it works — on this branch. `D-T27-LIVE-REPLAY` records
that these lifecycle handlers *never worked* until it repaired them, so every entity
purged while they were dead left its KG node behind. The events are long gone: a working
handler will never revisit them, and nothing else reconciles history.

Measured 2026-08-11 before the first run:

    KG anchors   5771
    resolve      4139
    DANGLING     1632   (28.3 %)   ← one project holds 1535 of them

Those orphans are also why `D-T35-COLLISION-GROUPS` looked like a dedup problem: 18 of
the 34 nodes in its 17 "duplicate" groups have no glossary row at all, so the pairs are
a live node plus a tombstone-less orphan, not two live duplicates.

WHAT IT DOES NOT DO. It does not merge, rename, or archive anything, and it never
touches a node whose anchor resolves. One decision per node — "does this glossary id
still exist?" — answered by a join, not a heuristic.

DRY-RUN BY DEFAULT. `--apply` is required to delete, and the count is printed before and
after either way.

    python scripts/kg-orphan-anchor-reconcile.py                    # report only
    python scripts/kg-orphan-anchor-reconcile.py --apply            # delete
    python scripts/kg-orphan-anchor-reconcile.py --project <uuid>   # one project at a time

Exit 0 = ran · 1 = a precondition failed (no container, unreachable store).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

NEO4J_CONTAINER = "infra-neo4j-1"
PG_CONTAINER = "infra-postgres-1"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "loreweave_dev_neo4j"
GLOSSARY_DB = "loreweave_glossary"
PG_USER = "loreweave"


def cypher(query: str) -> list[str]:
    """Run a read/write query, return non-header rows. Raises on a non-zero exit."""
    out = subprocess.run(
        ["docker", "exec", NEO4J_CONTAINER, "cypher-shell",
         "-u", NEO4J_USER, "-p", NEO4J_PASSWORD, "--format", "plain", query],
        capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"cypher failed: {out.stderr.strip()[:400]}")
    rows = [r.strip() for r in out.stdout.splitlines() if r.strip()]
    return rows[1:] if rows else []


def anchors(project: str | None) -> list[tuple[str, str, str, str]]:
    """(node id, glossary id, user_id, project_id) for every anchored :Entity."""
    where = "e.glossary_entity_id IS NOT NULL"
    if project:
        where += f" AND e.project_id = '{project}'"
    rows = cypher(
        f"MATCH (e:Entity) WHERE {where} "
        "RETURN e.id + '|' + e.glossary_entity_id + '|' + e.user_id + '|' "
        "+ coalesce(e.project_id, '') AS row;"
    )
    out = []
    for r in rows:
        parts = r.strip('"').split("|")
        if len(parts) == 4:
            out.append(tuple(parts))  # type: ignore[arg-type]
    return out


def resolve(glossary_ids: list[str]) -> set[str]:
    """The subset of `glossary_ids` that still exists in `glossary_entities`.

    A LEFT JOIN over a temp table, not an IN-list: the id set runs to thousands and a
    generated IN-list is both slow and a statement-size hazard.
    """
    if not glossary_ids:
        return set()
    sql = (
        "CREATE TEMP TABLE g(id text); COPY g FROM STDIN; "
        "SELECT ge.entity_id FROM g JOIN glossary_entities ge ON ge.entity_id::text = g.id;"
    )
    out = subprocess.run(
        ["docker", "exec", "-i", PG_CONTAINER, "psql", "-U", PG_USER, "-d", GLOSSARY_DB,
         "-t", "-A", "-c", sql],
        input="\n".join(glossary_ids) + "\n", capture_output=True, text=True,
    )
    if out.returncode != 0:
        raise RuntimeError(f"psql failed: {out.stderr.strip()[:400]}")
    return {
        line.strip() for line in out.stdout.splitlines()
        if line.strip() and "COPY" not in line and "CREATE" not in line
    }


def purge(node_ids: list[str]) -> int:
    """DETACH DELETE by node id, in batches.

    Deliberately the same shape as `purge_entity_by_glossary_id` — a DETACH DELETE of the
    :Entity, edges included — so there is ONE delete semantic for an orphaned anchor and
    not a second one that drifts from it.
    """
    deleted = 0
    for i in range(0, len(node_ids), 200):
        batch = node_ids[i:i + 200]
        rows = cypher(
            "UNWIND " + json.dumps(batch) + " AS nid "
            "MATCH (e:Entity {id: nid}) DETACH DELETE e RETURN count(*) AS n;"
        )
        deleted += int(rows[0].strip('"')) if rows else 0
    return deleted


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true",
                    help="actually delete (default: report only)")
    ap.add_argument("--project", default=None, help="limit to one project_id")
    args = ap.parse_args()

    try:
        rows = anchors(args.project)
    except RuntimeError as exc:
        print(f"[orphan-reconcile] FAIL — {exc}")
        return 1
    if not rows:
        print("[orphan-reconcile] no anchored :Entity nodes found — nothing to do")
        return 0

    gids = [r[1] for r in rows]
    try:
        live = resolve(gids)
    except RuntimeError as exc:
        print(f"[orphan-reconcile] FAIL — {exc}")
        return 1

    orphans = [r for r in rows if r[1] not in live]
    print(f"[orphan-reconcile] anchors {len(rows)} · resolve {len(rows) - len(orphans)} "
          f"· DANGLING {len(orphans)} ({100 * len(orphans) / len(rows):.1f} %)")

    by_project: dict[str, int] = {}
    for _, _, _, proj in orphans:
        by_project[proj] = by_project.get(proj, 0) + 1
    for proj, n in sorted(by_project.items(), key=lambda kv: -kv[1])[:5]:
        print(f"    {proj or '<none>'}  {n}")

    if not orphans:
        print("[orphan-reconcile] clean")
        return 0
    if not args.apply:
        print("[orphan-reconcile] DRY RUN — re-run with --apply to delete")
        return 0

    deleted = purge([o[0] for o in orphans])
    print(f"[orphan-reconcile] deleted {deleted} node(s)")

    # Re-verify from the store rather than from the in-memory list — the point of the
    # check is that the DELETE actually landed, which the list cannot tell us.
    # ONE `anchors()` + ONE `resolve()`: the first cut of this called `anchors()` twice
    # and `resolve()` inside a comprehension, which re-ran the whole join per row and
    # turned a 2-second check into a 10-minute one on 5k anchors.
    after = anchors(args.project)
    still_live = resolve([r[1] for r in after])
    remaining = [r for r in after if r[1] not in still_live]
    print(f"[orphan-reconcile] dangling after: {len(remaining)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
