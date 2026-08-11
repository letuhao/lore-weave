"""Apache AGE session bootstrap and graph naming (plan T42c).

WHY THIS EXISTS AS ITS OWN MODULE
---------------------------------
AGE needs per-database AND per-SESSION setup that Neo4j does not, and getting either wrong
fails in a way that reads like a missing graph rather than a missing setup step:

  * `CREATE EXTENSION age`            — once per database
  * `LOAD 'age'`                      — **once per SESSION**
  * `SET search_path = ag_catalog, …` — **once per SESSION**
  * `SELECT create_graph('<name>')`   — once per graph, and it ERRORS if the graph exists

The two session-scoped lines are the trap. A graph created on one connection and queried on
another fails with `function cypher(unknown, unknown) does not exist` — which looks like a
broken install, not a missing `LOAD`.

⚠️ **AND THE OBVIOUS FIX IS WRONG, measured.** Putting both on asyncpg's `init` hook — which
runs once per physical connection — looks right and fails on the SECOND use of every
connection:

    init hook, 1st acquire : ag_catalog, "$user", public
    init hook, 2nd acquire : "$user", public          <- RESET ALL wiped it
    server_settings, 1st   : ag_catalog, "$user", public
    server_settings, 2nd   : ag_catalog, "$user", public

**asyncpg issues `RESET ALL` when a connection is RELEASED to the pool**, and `RESET ALL`
returns every GUC to its startup value — so a `SET search_path` performed in `init` survives
exactly one acquire. The resulting bug is not "which connection served it" but "any
connection after its first release", which is worse: it works in a script that never
releases, and nowhere else.

⚠️ And the window is narrower still than that reads. Reverting to the `init`-only shape (the
bite for this task) failed on the FIRST acquire a caller makes, because `create_age_pool`
itself acquires and releases once to create the extension — so the reset has already
happened before any application code runs. There is effectively no working state at all,
which is why this was worth pinning with a test rather than a comment.

The split below follows from that, and each half is placed where it actually survives:

  * `search_path` → **`server_settings`**, which becomes the connection's STARTUP parameter,
    so `RESET ALL` resets *to* it rather than away from it.
  * `LOAD 'age'`  → the **`init`** hook, which is correct here because `LOAD` loads a shared
    library into the backend and is not a GUC, so `RESET ALL` does not undo it (verified).

Use `create_age_pool(...)` and neither has to be remembered.

GRAPH NAMING — MEASURED, NOT ASSUMED
------------------------------------
AGE's rules are undocumented in the places one looks first, so they were probed against a
running AGE 1.7.0 (see the table). Two of them will bite any scheme derived from a project
id:

    'q'                                       REJECT   graph name is invalid
    'qq'                                      REJECT   graph name is invalid
    'qqq'                                     OK       -> minimum is THREE characters
    '2abc'                                    REJECT   -> must not start with a digit
    '019f37f0-cb1c-70d1-9a3e-2c672b0086e5'    REJECT   -> a bare UUID is BOTH of the above
    'aa-bb-cc'                                OK
    'g_36ac14251224448eb6f71a7e42ff199c'      OK       -> the scheme below
    63 and 64 characters                      OK

A project id is a UUID, and a bare UUID fails on *both* counts: `019f…` starts with a digit,
and the dashes are rejected too. Hence `g_` + the hex with dashes stripped: 34 characters,
starts with a letter, no separators. The prefix is not cosmetic — it is what makes a
digit-leading id legal.

⚠️ The first version of this probe reported `g_<hex>` as REJECTED and nearly encoded the
wrong rule. The cause was the probe, not AGE: the name had been created by an earlier run,
so the error was *"graph already exists"* and the check counted any `ERROR` as invalid. That
is why `ensure_graph` below asks `ag_graph` rather than treating a failed `create_graph` as
"already there".
"""
from __future__ import annotations

import re
from uuid import UUID

__all__ = [
    "AGE_SEARCH_PATH",
    "AGE_SERVER_SETTINGS",
    "create_age_pool",
    "graph_name_for",
    "init_age_connection",
    "ensure_age_extension",
    "ensure_graph",
]

# `ag_catalog` must precede "$user"/public so `cypher(...)`, `create_graph(...)` and the
# `agtype` operators resolve unqualified. Keeping public on the path matters too: the graph
# lives beside ordinary tables and a query that touches both must see both.
AGE_SEARCH_PATH = 'ag_catalog, "$user", public'

# Belt and braces for the naming rules above. Not a substitute for them — the authority is
# AGE — but a caller who invents a name gets a clear Python error instead of
# `graph name is invalid` from three layers down.
_VALID_GRAPH_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]{2,62}$")


def graph_name_for(project_id: str | UUID | None) -> str:
    """The graph holding one project's entities, or the shared graph when unscoped.

    `g_` + the UUID hex, dashes stripped. Both transformations are load-bearing: a bare UUID
    is rejected by AGE for starting with a digit AND for its dashes, and roughly half of all
    UUIDs start with a digit — so a scheme that merely stripped dashes would work in testing
    and fail for half of real projects. That is the kind of bug that reaches production
    because the sample that exercised it was small.
    """
    if project_id is None:
        return "g_shared"
    hexed = str(project_id).replace("-", "").strip()
    if not hexed:
        raise ValueError("project_id is empty; refusing to derive a graph name from it")
    name = f"g_{hexed}"
    if not _VALID_GRAPH_NAME.match(name):
        raise ValueError(
            f"derived graph name {name!r} is not a legal AGE graph name "
            "(3-63 chars, leading letter or underscore, then letters/digits/_/-)"
        )
    return name


# Passed to `asyncpg.create_pool(server_settings=…)`. This is a STARTUP parameter, which is
# the only placement that survives the `RESET ALL` asyncpg runs on release — see the module
# docstring for the measurement. Setting the same value with `SET` in `init` does not.
AGE_SERVER_SETTINGS = {"search_path": AGE_SEARCH_PATH}


async def init_age_connection(conn) -> None:
    """Per-connection AGE setup: `LOAD 'age'` only.

    ⚠️ `SET search_path` deliberately does NOT live here. `RESET ALL` on release would undo
    it, so it goes in `server_settings` instead (see the module docstring). `LOAD` belongs
    here precisely because it is not a GUC: it loads a library into the backend, and the
    reset leaves it alone — measured, not assumed.
    """
    await conn.execute("LOAD 'age'")


async def create_age_pool(dsn: str, **kwargs):
    """An asyncpg pool wired for AGE, with the extension ensured.

    Exists so the `server_settings` / `init` split is made once rather than remembered at
    each call site. A caller who builds their own pool and only sets `init` gets a pool that
    works until a connection is released — which is the failure this module is about.
    """
    import asyncpg

    settings = {**AGE_SERVER_SETTINGS, **(kwargs.pop("server_settings", None) or {})}
    pool = await asyncpg.create_pool(
        dsn, server_settings=settings, init=init_age_connection, **kwargs
    )
    await ensure_age_extension(pool)
    return pool


async def ensure_age_extension(pool) -> None:
    """Idempotent `CREATE EXTENSION age`, mirroring `ensure_vector_schema`.

    Created rather than assumed for the same reason the vector layer gives: the T42b image
    ships AGE, but a self-hoster pointing at their own Postgres gets a comprehensible error
    at boot instead of a baffling one at the first `cypher(...)` call.
    """
    async with pool.acquire() as conn:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS age")


async def ensure_graph(conn, project_id: str | UUID | None) -> str:
    """Create this project's graph if absent; return its name. Idempotent.

    ⚠️ `create_graph` has **no `IF NOT EXISTS`** — it raises when the graph is already there.
    So existence is asked of `ag_catalog.ag_graph` rather than inferred from a failed create:
    swallowing the error would also swallow a genuinely invalid name, and that is precisely
    the confusion that made the naming probe report a false rejection.
    """
    name = graph_name_for(project_id)
    exists = await conn.fetchval(
        "SELECT count(*) FROM ag_catalog.ag_graph WHERE name = $1", name
    )
    if not exists:
        # `create_graph` takes the name as a STRING literal, and the value here is derived
        # from a validated UUID rather than free text — but it is still interpolated, so the
        # regex above is the gate that keeps it a safe identifier.
        await conn.execute(f"SELECT ag_catalog.create_graph('{name}')")
    return name
