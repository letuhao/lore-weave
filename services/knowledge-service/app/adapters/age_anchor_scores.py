"""T25p/T25q — resolve `anchor_score` from the AGE graph for a bounded set of entity hits.

Spec §3.3c. `PgVectorStore` holds vectors and deliberately does NOT store `anchor_score`: it is
`mention_count / max(mention_count)` across a bucket, so it changes when a DIFFERENT entity's
count moves and a copy on the vector row drifts by construction. §3.3 settled that in 2026-08-13
and T25p re-verified it rather than assuming it (394 of 5062 dev entities carry a fractional
value, so the "it's really a flag, just copy it" hypothesis is refuted).

What T25p changed is a FACT the decision rested on, not the decision: since T54 the graph is
AGE, so the authoritative score is readable per query instead of only copyable. This module is
that read, supplied to `PgVectorStore` as the `anchor_scores` collaborator.

⚠️ **This lives HERE and not in `PgVectorStore` on purpose.** The store's contract is that a
caller cannot tell which backend it holds; a Cypher join inside it would put `age` in a
vector store, and on a `neo4j` backend it would return NULL for every hit — which
`glossary.py`'s `anchor_score or 0.0` turns into a column of ZEROES and a silent fall back to
raw cosine order. The provider decides whether this resolver can be served at all; the store
just takes it or leaves the key absent.
"""

from __future__ import annotations

import logging

from app.adapters.age_graph_store import _lit
from app.db.age_bootstrap import graph_name_for

logger = logging.getLogger(__name__)


def age_anchor_scores(pool, project_id=None):
    """Build an `AnchorScores` resolver over the AGE pool.

    `pool` is the AGE pool, NOT the vector pool. Today both DSNs happen to resolve to the same
    database, and relying on that would be an assumption that breaks silently the moment they
    diverge: the query would run against a database with no graph, or worse an EMPTY one, and
    an empty answer is indistinguishable from "nothing is anchored".
    """
    graph = graph_name_for(project_id)

    async def resolve(user_id: str, entity_ids: list[str]) -> dict[str, float | None]:
        if not entity_ids:
            return {}
        # `_lit` is IMPORTED, not re-implemented. It is the tenancy boundary for this whole
        # adapter family — a `user_id` that escaped its quotes would let one tenant's filter
        # be rewritten by another tenant's data — and a second copy of an escaping rule is
        # the "one concept, two readers" pattern §8.4 names.
        ids = ", ".join(_lit(e) for e in entity_ids)
        cypher = (
            f"MATCH (e:Entity) "
            f"WHERE e.user_id = {_lit(user_id)} AND e.id IN [{ids}] "
            f"RETURN e.id AS id, e.anchor_score AS score"
        )
        sql = (
            f"SELECT * FROM cypher('{graph}', $anchor${cypher}$anchor$) "
            f"AS t(id agtype, score agtype)"
        )
        async with pool.acquire() as conn:
            rows = await conn.fetch(sql)

        out: dict[str, float | None] = {}
        for r in rows:
            eid = str(r["id"]).strip('"')
            raw = r["score"]
            # An entity present in the graph with NO `anchor_score` is genuinely un-anchored,
            # and `None` is the value the Neo4j arm already returns for one. It is NOT 0.0:
            # `glossary.py` maps None to 0.0 itself, and doing it here would hide the
            # difference between "no score" and "a score of zero" from anyone debugging.
            out[eid] = None if raw is None or str(raw) == "null" else float(str(raw))
        # ⚠️ Ids the graph did not return are simply ABSENT from this dict, and the store maps
        # a miss to None. Filling them in here would be inventing an answer for an entity the
        # authority does not know about.
        return out

    return resolve
