"""Project-scoped graph lifecycle on Neo4j (plan T13).

One function, moved out of `app/db/neo4j_helpers.py` so the multi-tenant Cypher guard
module holds no Cypher of its own. It is not an index concern (that is
`vector_indexes.py`) and not a passage concern (`passages.py` deletes by label); it is
the whole-project teardown that a project delete owes the graph.

WHY THIS HAS NO `$user_id` FILTER, deliberately. `project_id` is globally unique, and the
ONLY caller (`routers/public/projects.py::delete_project`) is gated by
`require_project_grant(GrantLevel.OWNER)` and has already completed the authoritative
Postgres delete for that (user, project) pair before calling. This is the same
justification `run_read_any_owner` is documented under: an unfiltered match is sound when
the key is globally unique AND the caller grant-checked first. Adding a user filter here
would also be WRONG in one case that matters — a node written under a different owner id
in a shared project would survive the purge and orphan the graph, which is the exact
defect (`D-KNOWLEDGE-PROJECT-DELETE-NEO4J-ORPHAN`) this function exists to close.
"""

from __future__ import annotations

from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.vector_indexes import (
    drop_summary_index,
    list_summary_vector_indexes,
)

__all__ = ["purge_project"]


async def purge_project(session: CypherSession, project_id: str) -> dict[str, int]:
    """Delete ALL Neo4j nodes for a project + drop its per-project summary vector
    indexes — `D-KNOWLEDGE-PROJECT-DELETE-NEO4J-ORPHAN`: deleting a knowledge project
    must not orphan its graph.

    Every project node carries `project_id` (Entity/Event/Fact/Passage/
    ExtractionSource/EntityStatus — verified: no node connected to the project's nodes
    lacks `project_id`), so a single `project_id`-scoped `DETACH DELETE` is complete.
    The SHARED dimension-bucketed indexes (`entity_embeddings_1024`,
    `passage_embeddings_384`, …) are NEVER touched — other projects share them; only
    THIS project's `<level>_summary_emb_p<id>_e<model>` indexes are dropped (reusing the
    name-validated helpers). Returns `{nodes_deleted, indexes_dropped}`.

    The CALLER runs this best-effort: the authoritative owner-gated delete is the
    Postgres row removal; a Neo4j failure must not fail it (it just leaves an orphan to
    re-sweep). Perf follow-up: a very large graph is one `DETACH DELETE` transaction —
    batch via `CALL { … } IN TRANSACTIONS` if a huge project ever needs it.
    """
    rows = await session.run(
        "MATCH (n {project_id: $pid}) RETURN count(n) AS n", pid=project_id
    )
    nodes = 0
    async for rec in rows:
        nodes = int(rec["n"])
    if nodes:
        # count-then-delete: RETURN-after-DELETE isn't reliable across drivers.
        await session.run("MATCH (n {project_id: $pid}) DETACH DELETE n", pid=project_id)
    proj_hex = project_id.replace("-", "").lower()
    dropped = 0
    # The node purge above is PORTABLE Cypher and has already happened. Index administration
    # is not: on AGE `SHOW VECTOR INDEXES` is a SQL parse error, and there are no per-project
    # summary indexes there to drop (§3.1 makes the vector layer per-dim Postgres TABLES).
    #
    # Catching the NAMED refusal only. Before this, the helper raised a bare PostgresSyntaxError
    # that propagated to the caller's `except Exception`, which logs "graph orphaned, re-sweep
    # owed" -- so on the DEFAULT backend every project delete reported an orphan whose nodes had
    # in fact been deleted, indistinguishable from a purge that really did fail. A bare `except`
    # here would restore exactly that: it would also swallow a genuine Neo4j index failure.
    try:
        for idx in await list_summary_vector_indexes(session):
            if idx["project_id"] == proj_hex:
                await drop_summary_index(session, idx["name"])
                dropped += 1
    except NotImplementedError as exc:
        return {"nodes_deleted": nodes, "indexes_dropped": 0, "indexes_skipped": str(exc)}
    return {"nodes_deleted": nodes, "indexes_dropped": dropped}
