"""Where a `GraphStore` actually comes from (plan T17 / T42d).

**This is the piece Phase 7 did not have, and its absence was invisible.** T18 defined the
port, T20 the fake, T42 built a second real adapter on Apache AGE — and
`scripts/port-adoption-gate.py` then measured the thing none of that revealed:

    71 module(s) bind `neo4j_repos` directly (ceiling 71); 0 import GraphStore

**Three conforming adapters, zero call sites.** Exactly the shape T25a found for vectors,
where ~1200 lines of tested code executed only in tests. A port with no callers is not a
boundary; it is a folder.

── WHY THIS BLOCKS T43, NOT MERELY DELAYS IT ────────────────────────────────────────────
T43's shadow comparison compares two adapters **on real traffic**, and the plan's coverage
floor says no cutover while any port operation has **zero shadow observations**. With no
callers, every operation is at zero — permanently. That floor cannot be satisfied by
waiting, only by adoption, so this file is the precondition for choosing an engine by
measurement rather than by argument (which is what **X1** insisted on).

── DEFAULT IS NEO4J, AND DEFAULT MEANS BEHAVIOUR-IDENTICAL ──────────────────────────────
`get_graph_store(session)` returns a `Neo4jGraphStore` wrapping the session the caller
already had. The adapter's methods are thin passthroughs to the same repo functions the
call sites used before, with the same defaults — so a migrated call site reaches the same
Cypher through one extra method call. **No second database, no new failure mode, nothing to
configure.** That property is what makes migrating a call site a safe, reviewable change
rather than a cutover; the engine choice stays with T43 where the design put it.

`KNOWLEDGE_GRAPH_BACKEND=age` selects the AGE adapter instead, and it is deliberately NOT
the default: AGE is a T43 *candidate*, and defaulting to a candidate would decide the engine
by configuration drift instead of by the shadow comparison.
"""

from __future__ import annotations

import logging
import os

from app.adapters.neo4j_graph_store import Neo4jGraphStore
from app.db.neo4j_helpers import CypherSession
from app.ports.graph_store import GraphStore

logger = logging.getLogger(__name__)

__all__ = ["get_graph_store"]

_BACKEND_ENV = "KNOWLEDGE_GRAPH_BACKEND"


def get_graph_store(session: CypherSession) -> GraphStore:
    """The configured `GraphStore` for this session. Neo4j unless told otherwise.

    Takes the session rather than opening one: every current call site already holds an open
    `neo4j_session()`, and having the provider open a second would double the connection
    count and silently move the work outside the caller's transaction scope — a behaviour
    change smuggled in by a refactor whose whole value is that it changes nothing.

    ⚠️ `age` is accepted but not defaulted, and it is not wired here. The AGE adapter needs
    an asyncpg pool and a per-project graph name (`age_bootstrap.create_age_pool` /
    `graph_name_for`), which is a different lifecycle from a Neo4j session — wiring it is
    T43's shadow harness, not this file's job. Asking for it now fails loudly rather than
    silently returning Neo4j, because a shadow comparison that quietly compared Neo4j
    against Neo4j would agree perfectly and mean nothing.
    """
    backend = os.environ.get(_BACKEND_ENV, "neo4j").strip().lower()
    if backend in ("", "neo4j"):
        return Neo4jGraphStore(session)
    if backend == "age":
        raise NotImplementedError(
            f"{_BACKEND_ENV}=age is not wired into this provider yet. The AGE adapter needs "
            "an asyncpg pool + a per-project graph name, which T43's shadow harness owns "
            "(D-T42D-GRAPHSTORE-HAS-NO-CALLERS). Raising rather than falling back to Neo4j: "
            "a comparison that silently ran Neo4j against Neo4j would agree perfectly and "
            "prove nothing."
        )
    raise ValueError(
        f"{_BACKEND_ENV}={backend!r} is not a known graph backend (neo4j | age)"
    )
