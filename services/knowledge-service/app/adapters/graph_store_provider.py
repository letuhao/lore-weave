"""Where a `GraphStore` actually comes from (plan T17 / T42d).

**This is the piece Phase 7 did not have, and its absence was invisible.** T18 defined the
port, T20 the fake, T42 built a second real adapter on Apache AGE — and
`scripts/port-adoption-gate.py` then measured the thing none of that revealed:

    71 module(s) bind `graph_repos` directly (ceiling 71); 0 import GraphStore

**Three conforming adapters, zero call sites.** Exactly the shape T25a found for vectors,
where ~1200 lines of tested code executed only in tests. A port with no callers is not a
boundary; it is a folder.

── WHY THIS BLOCKS T43, NOT MERELY DELAYS IT ────────────────────────────────────────────
T43's shadow comparison compares two adapters **on real traffic**, and the plan's coverage
floor says no cutover while any port operation has **zero shadow observations**. With no
callers, every operation is at zero — permanently. That floor cannot be satisfied by
waiting, only by adoption, so this file is the precondition for choosing an engine by
measurement rather than by argument (which is what **X1** insisted on).

── THE DEFAULT IS AGE, AND THIS PARAGRAPH SAID NEO4J UNTIL 2026-08-31 ────────────────────
T54 flipped the default to `age` (§8.1, PO 2026-08-22) and this docstring was not updated
with it, so the module explaining the engine choice asserted the opposite of the constant it
imports. Left uncorrected it is worse than absent: a reader deciding whether an upgrade is
safe would have concluded it changes nothing.
`get_graph_store(session)` returns a `Neo4jGraphStore` wrapping the session the caller
already had. The adapter's methods are thin passthroughs to the same repo functions the
call sites used before, with the same defaults — so a migrated call site reaches the same
Cypher through one extra method call. **No second database, no new failure mode, nothing to
configure.** That property is what makes migrating a call site a safe, reviewable change
rather than a cutover; the engine choice stays with T43 where the design put it.

`KNOWLEDGE_GRAPH_BACKEND=neo4j` selects the Neo4j adapter, which wraps the session the caller
already had: thin passthroughs to the same repo functions with the same defaults, so no second
database and no new failure mode. An existing installation that has only ever run Neo4j and
sets nothing still gets it — `configured_backend` resolves an UNSET variable from what the
deployment has actually provisioned, rather than naming a store it never created.
"""

from __future__ import annotations

import logging
import os

from app.adapters.age_graph_store import AgeGraphStore
from app.adapters.neo4j_graph_store import Neo4jGraphStore
from app.db.age_bootstrap import graph_name_for
from app.db.neo4j_helpers import CypherSession
from app.ports.graph_store import GraphStore

logger = logging.getLogger(__name__)

__all__ = ["get_graph_store", "init_age_pool"]

# T54c — one home. `db.graph_backend` owns the env name and the default; three layers read
# them now (this provider, `graph_session`, the AGE session) and a duplicated default is one
# edit away from putting half the service on each engine.
from app.db.graph_backend import BACKEND_ENV as _BACKEND_ENV  # noqa: E402
from app.db.graph_backend import DEFAULT_BACKEND as _DEFAULT_BACKEND  # noqa: E402
from app.db.graph_backend import configured_backend as _configured_backend  # noqa: E402
from app.db.graph_backend import known_backends as _known_backends  # noqa: E402



# T54c — the POOL moved to `db.age_pool`. It is a database handle, and keeping it here made
# `graph_session` import an adapter module to open a session, which `port-adoption-gate`
# counted as GraphStore adoption. Re-exported so the lifespan and any existing caller keep
# working; this module still owns WHICH store to build, which is the decision that belongs
# to a provider.
from app.db.age_pool import age_pool as _age_pool  # noqa: E402
from app.db.age_pool import init_age_pool  # noqa: E402


def get_graph_store(session: CypherSession) -> GraphStore:
    """The configured `GraphStore` for this session. Neo4j unless told otherwise.

    Takes the session rather than opening one: every current call site already holds an open
    `graph_session()`, and having the provider open a second would double the connection
    count and silently move the work outside the caller's transaction scope — a behaviour
    change smuggled in by a refactor whose whole value is that it changes nothing.

    ⚠️ `age` is accepted but not defaulted, and it is not wired here. The AGE adapter needs
    an asyncpg pool and a per-project graph name (`age_bootstrap.create_age_pool` /
    `graph_name_for`), which is a different lifecycle from a Neo4j session — wiring it is
    T43's shadow harness, not this file's job. Asking for it now fails loudly rather than
    silently returning Neo4j, because a shadow comparison that quietly compared Neo4j
    against Neo4j would agree perfectly and mean nothing.
    """
    # RESOLVED THROUGH `configured_backend`, not re-read here. This line used to be
    # `os.environ.get(_BACKEND_ENV, _DEFAULT_BACKEND)` -- a SECOND home for the default,
    # which is the duplication `db.graph_backend`'s own docstring warns about, and it
    # also skipped that module's validation: an unknown value fell through both
    # branches to the ValueError below instead of the registry's message, and an
    # UNSET variable named `age` on a deployment that has no AGE database at all.
    backend = _configured_backend()
    if backend == "neo4j":
        return Neo4jGraphStore(session)
    if backend == "age":
        pool = _age_pool()
        if pool is None:
            raise RuntimeError(
                f"{_BACKEND_ENV}=age but KNOWLEDGE_AGE_DB_URL is not set. Refusing to fall "
                "back to Neo4j: a backend that silently is not the one you selected is the "
                "exact defect T54 was written to fix — T42/T43 closed green while `age` "
                "could not be selected at all."
            )
        # The SHARED graph, which is not a compromise — it is the CURRENT topology. Neo4j
        # holds every project in one database and scopes by `user_id`/`project_id`
        # properties, so `g_shared` reproduces that exactly. Per-project graphs
        # (`graph_name_for(project_id)`) stay available and are what T43's harness uses;
        # adopting them HERE would smuggle an isolation-model change into an engine swap,
        # and then a divergence could not be attributed to either one.
        return AgeGraphStore(pool, graph_name_for(None))
    # UNREACHABLE VIA `configured_backend`, and kept as a belt: that function raises on
    # an empty value, an unknown name and a registered-but-not-selectable one, so a
    # name arriving here is a backend the REGISTRY accepts and this dispatch has not
    # learned to build. That is exactly the gap a new engine opens, so it names the
    # registry rather than repeating a hardcoded `(neo4j | age)` that would go stale
    # the moment one is added.
    raise ValueError(
        f"{_BACKEND_ENV}={backend!r} is a registered backend that "
        f"`get_graph_store` cannot construct. Known: {', '.join(_known_backends())}. "
        f"Adding an engine is a registry entry AND a branch here."
    )
