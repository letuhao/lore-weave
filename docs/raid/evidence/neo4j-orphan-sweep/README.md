# Neo4j orphan sweep — 2026-06-18

One-off cleanup of Neo4j graphs orphaned by the pre-`3dfb2199` `delete_project` bug
(`D-KNOWLEDGE-PROJECT-DELETE-NEO4J-ORPHAN`): every knowledge-project delete removed only
the Postgres SSOT row, leaving the project's entire Neo4j graph behind forever.

## What was swept

- **Live projects in Postgres `knowledge_projects`:** 11 (incl. archived — no `WHERE`).
- **Distinct project graphs in Neo4j:** 108.
- **Orphans (graph pid ∉ live set):** **106 projects / 2342 nodes** → DETACH DELETE'd.
- **Summary vector indexes dropped:** 3 (only `019e3ba1…`, the one orphan that had them).
- **Untouched:** the 2 live graphs + all 9 shared dimension-bucketed indexes
  (`entity_embeddings_*`, `passage_embeddings_*`, `event_embeddings_1024`).

## Method (self-validating by the live set, not the orphan list)

```cypher
MATCH (n) WHERE n.project_id IS NOT NULL AND NOT n.project_id IN <11 live pids>
DETACH DELETE n
```

Then dropped the orphan's `<level>_summary_emb_p<id>_e<model>` indexes via the
name-validated helpers; the shared indexes were never eligible.

## Verification

- Post-sweep distinct project graphs: **2** (= the 2 live graphs), 2 nodes.
- Remaining vector indexes: shared dimension indexes only, **no summary indexes**.

`2026-06-18-orphan-audit.txt` — raw `project_id, node_count` for all 106 swept orphans
(captured immediately before deletion), descending by node count.
