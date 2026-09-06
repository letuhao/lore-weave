"""The engine-neutral graph session — `async with graph_session() as s:`.

WHY THIS MODULE EXISTS, AND WHY IT IS NOT `db/neo4j.py` ANY MORE
────────────────────────────────────────────────────────────────
`graph_session` opens a session against **whichever engine is configured**, and it lived in
`app/db/neo4j.py` — a module named for one of the two engines it dispatches between. 81 import
sites across 55 files read the abstraction from a path that names the thing it exists to
abstract, and a file called `neo4j` exporting the function you call *to avoid caring about
Neo4j* is a name that teaches the wrong thing every time somebody follows it.

Split 2026-09-04 (row R1 of `docs/plans/2026-09-03-kal-x-fetools-MERGE-PLAN.md`). The plan
called this a rename and **measuring refuted that**: `db/neo4j.py` is a hybrid. Three of its
four public functions — `init_neo4j_driver`, `get_neo4j_driver`, `close_neo4j_driver` — are
genuinely Neo4j's driver lifecycle and belong under that name. Only `graph_session` is neutral.
Renaming the whole file would have moved the driver lifecycle under an abstraction's name, which
is the same misleading-name problem one level over rather than a fix. So this is a split: the
neutral half moves out, the engine-specific half stays where it is correctly named.

THE DIRECTION OF THE DEPENDENCY IS DELIBERATE
─────────────────────────────────────────────
This module imports the engines; the engines do not import it. A dispatcher has to know what it
dispatches to, and that is not a layering violation — it is what makes the 55 callers able to
know nothing. AGE is imported lazily inside the function for the reason its own comment gives:
`age_session` and `age_pool` both reach for configuration at import, and a module-level cycle
would make this unimportable by anything that never touches a graph.
"""

from __future__ import annotations

from typing import Any

from app.db.graph_backend import configured_backend

__all__ = ["graph_session"]


def graph_session(*, engine: str | None = None, **kwargs: Any) -> Any:
    """Open a repo-layer session against the **configured graph backend**.

    Call sites write `async with graph_session() as s:` and get whichever engine
    `KNOWLEDGE_GRAPH_BACKEND` names. Repo code must wrap the session's `run(...)`
    in K11.4's `run_read` / `run_write` helpers, NOT call it directly — those are
    also what render the dialect for the session's engine (T83).

    🔴 **THIS FUNCTION IS T54's BLOCKER, AND WAS ITS CAUSE.** Flipping the backend
    to AGE split one conceptual graph across two stores: the 19 `GraphStore`
    adopters read AGE while the 54 `graph_repos` binders read Neo4j, inside a
    single service, with AGE empty. T54b measured it live on dev — `Neo4j schema
    applied` and `AGE pool ready` one second apart — and reverted the pin.

    The split existed because this function could only ever return a Bolt session.
    Since T83/T84 the repo layer runs on either engine, so this returns whichever
    one is configured and BOTH halves of the service read the same store. That is
    §10.1's second path arriving where it was always aimed: one function, not 34
    module migrations.

    `engine=` pins a call site to one backend and is for the modules §1.3 puts out
    of port scope forever — the benchmarks, which exist to COMPARE engines and so
    must name one, and the one-shot migration scripts, which ran against a known
    engine. `port-adoption-gate` counts them and the count can only fall.
    """
    if configured_backend(engine) == "age":
        # Imported here, not at module scope: `age_session` and `age_pool` both reach for
        # configuration, and a module-level cycle would make this unimportable by
        # anything that never touches a graph.
        from app.db.age_pool import age_pool
        from app.db.age_session import age_repo_session

        return age_repo_session(age_pool())
    # Likewise lazy, and for the mirror reason: a module that only ever opens an AGE session
    # should not drag the Neo4j driver in behind it.
    from app.db.neo4j import get_neo4j_driver

    return get_neo4j_driver().session(**kwargs)
