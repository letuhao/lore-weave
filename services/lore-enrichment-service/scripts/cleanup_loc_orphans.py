"""One-off cleanup of the pre-fix `loc:` orphan entities (QC C6 / review-impl note).

Before the F-C13-2 fix, lore-enrichment promote minted PARALLEL glossary entities
named `loc:<name>` (e.g. `loc:蓬萊`) with a makeup `short_description`
("Location: loc:…"), orphaned from the real canonical entity, and pushed their
(wrongly canon-tagged) facts onto a parallel Neo4j node. The fix stops new ones;
this removes the existing dev cruft from all consumer surfaces.

SAFE by construction:
  * Glossary: SOFT-deletes (sets deleted_at) — reversible, and every read filters
    `deleted_at IS NULL`, so the orphans vanish from the API/wiki/glossary_sync.
  * Neo4j: DETACH DELETEs the `loc:` :Entity nodes + their :Fact neighbours —
    these are quarantined artifacts (pending_validation=TRUE) invisible to any
    canonical query; removing them tidies the graph.
  * Scoped to the artifact SIGNATURE: name starts with 'loc:' AND short_description
    LIKE 'Location: loc:%' (the exact mint pattern), so a legitimately-named
    entity can never match. Idempotent.

DRY-RUN by default. Pass --apply to execute. Usage:
  python scripts/cleanup_loc_orphans.py [--apply]

Env: GLOSSARY_DB_URL_H, NEO4J_CONTAINER, NEO4J_USER, NEO4J_PASSWORD.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import sys

import asyncpg

GLOSS_DB = os.environ.get(
    "GLOSSARY_DB_URL_H",
    "postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_glossary",
)
NEO4J_CONTAINER = os.environ.get("NEO4J_CONTAINER", "infra-neo4j-1")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "loreweave_dev_neo4j")

# The artifact signature — both conditions must hold so a real entity can't match.
_FIND_SQL = """
SELECT e.entity_id::text, av.original_value AS name, e.short_description
FROM glossary_entities e
JOIN entity_attribute_values av ON av.entity_id = e.entity_id
JOIN attribute_definitions ad ON ad.attr_def_id = av.attr_def_id
WHERE ad.code = 'name'
  AND av.original_value LIKE 'loc:%'
  AND e.short_description LIKE 'Location: loc:%'
  AND e.deleted_at IS NULL
ORDER BY av.original_value
"""


def _cypher(query: str) -> str | None:
    try:
        out = subprocess.run(
            ["docker", "exec", NEO4J_CONTAINER, "cypher-shell", "-u", NEO4J_USER,
             "-p", NEO4J_PASSWORD, "--format", "plain", query],
            capture_output=True, text=True, timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"  [neo4j] unreachable ({exc}) — skipping graph cleanup", file=sys.stderr)
        return None
    if out.returncode != 0:
        print(f"  [neo4j] query failed: {out.stderr.strip()}", file=sys.stderr)
        return None
    return out.stdout


async def _main() -> int:
    apply = "--apply" in sys.argv[1:]
    mode = "APPLY" if apply else "DRY-RUN"
    print(f"[cleanup-loc-orphans] mode={mode}")

    conn = await asyncpg.connect(GLOSS_DB)
    try:
        rows = await conn.fetch(_FIND_SQL)
        if not rows:
            print("[cleanup-loc-orphans] no loc: orphans found — nothing to do (idempotent).")
            return 0
        print(f"[cleanup-loc-orphans] {len(rows)} glossary loc: orphan(s):")
        for r in rows:
            print(f"  - {r['name']}  ({r['entity_id']})  sd={r['short_description']!r}")

        # Neo4j: count facts on the loc: nodes (for the summary).
        n = _cypher(
            "MATCH (e:Entity)--(f:Fact) WHERE e.name STARTS WITH 'loc:' "
            "RETURN count(DISTINCT e) AS nodes, count(f) AS facts;"
        )
        if n:
            print(f"[cleanup-loc-orphans] Neo4j loc: nodes/facts → {n.strip().splitlines()[-1]}")

        if not apply:
            print("[cleanup-loc-orphans] DRY-RUN — re-run with --apply to soft-delete "
                  "(glossary) + detach-delete (Neo4j).")
            return 0

        # Glossary: reversible soft-delete.
        ids = [r["entity_id"] for r in rows]
        tag = await conn.execute(
            "UPDATE glossary_entities SET deleted_at = now(), updated_at = now() "
            "WHERE entity_id = ANY($1::uuid[]) AND deleted_at IS NULL",
            ids,
        )
        print(f"[cleanup-loc-orphans] glossary soft-deleted: {tag}")

        # Neo4j: detach-delete the loc: nodes + their facts (quarantined artifacts).
        res = _cypher(
            "MATCH (e:Entity) WHERE e.name STARTS WITH 'loc:' "
            "OPTIONAL MATCH (e)--(f:Fact) "
            "DETACH DELETE e, f;"
        )
        if res is not None:
            print("[cleanup-loc-orphans] Neo4j loc: nodes + facts detach-deleted.")
        print("[cleanup-loc-orphans] DONE.")
        return 0
    finally:
        await conn.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
