"""A `CypherSession` over Apache AGE — spec §10.1's *other* half.

§10.1 says what binds `graph_repos` to Neo4j is **"the Cypher dialect and the session type"**.
T77–T82 took the dialect to zero, which is a ratchet reading, not a proof: every repo function
still runs through `session.run(cypher, **params)`, and until something other than a Neo4j
`AsyncSession` can answer that call the layer has one engine. This module is that something.

── THE CLAIM THIS MODULE REFUTES ────────────────────────────────────────────────────────────
`age_graph_store`'s header states, as difference 4:

    **Parameters do not reach Cypher.** AGE takes a `$1`-style argument to `cypher()` only as a
    whole agtype map, and referencing it inside the query is limited. Values are therefore
    **interpolated** …

That was load-bearing: it is why `_lit` exists and why that adapter calls its own escaper "the
tenancy boundary, not a formatting helper". **It is false on the AGE this project runs.**
Measured 2026-08-22 against AGE 1.7.0 on PostgreSQL 18.4:

    named $user_id from the agtype map      OK
    several parameters at once              OK
    a NULL parameter in an optional filter  OK   (every `$x IS NULL OR …` filter depends on it)
    a LIST parameter                        OK   (`IN $exclude_project_ids`)
    a parameter in MERGE + SET              OK
    a hostile string as a parameter         OK — treated as DATA, no injection

So values bind, and the hand-rolled escaper is unnecessary risk rather than a necessity. That
matters most for `user_id`: a bound parameter cannot be rewritten by another tenant's data,
which is precisely the property `run_read`'s docstring claims and `_lit` can only approximate.

── WHAT THIS IS NOT ─────────────────────────────────────────────────────────────────────────
It is not a second `GraphStore`. `GraphStore` stays the DOMAIN boundary and grows by demand
(§10.1 point 1); this is the ENGINE seam under the repo layer (§10.1 point 2), and it exists so
the same repo function can be executed against either engine and COMPARED.
"""

from __future__ import annotations

import json
import re
from typing import Any

__all__ = [
    "AgeCypherSession",
    "age_repo_session",
    "AgeTransaction",
    "AgeResult",
    "AgeVertex",
    "ColumnParseError",
    "return_columns",
]


class ColumnParseError(ValueError):
    """The RETURN clause could not be turned into a column list.

    AGE's `cypher()` is a table-valued function: unlike the Bolt driver it cannot infer the
    result shape, so every call must declare `AS t(col agtype, …)`. Raising names the query
    rather than guessing a shape, because a guessed column list does not fail — it silently
    returns the wrong column under the right name (rule 9).
    """


# ── deriving the column list ─────────────────────────────────────────────────────────────

_TAIL = re.compile(r"\b(ORDER\s+BY|SKIP|LIMIT|UNION)\b", re.I)


def _split_top_level(text: str) -> list[str]:
    """Split on commas that are not inside (), [], {} or a string literal."""
    out: list[str] = []
    depth = 0
    quote: str | None = None
    current: list[str] = []
    i = 0
    while i < len(text):
        ch = text[i]
        if quote:
            current.append(ch)
            if ch == "\\" and i + 1 < len(text):
                current.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "'\"":
            quote = ch
            current.append(ch)
        elif ch in "([{":
            depth += 1
            current.append(ch)
        elif ch in ")]}":
            depth -= 1
            current.append(ch)
        elif ch == "," and depth == 0:
            out.append("".join(current))
            current = []
        else:
            current.append(ch)
        i += 1
    out.append("".join(current))
    return [p.strip() for p in out if p.strip()]


def _strip_comments(text: str) -> str:
    """Cypher `//` line and `/* */` block comments removed, string literals untouched.

    A COMMENT BETWEEN `RETURN` AND `ORDER BY` TOOK A LIVE ROUTE DOWN. `fact_for_check`
    documents its tie-break where the tie-break happens -- between the RETURN list and
    the `ORDER BY` it explains, which is where a reader wants it. `return_columns` slices
    from the last `RETURN` to the first tail keyword and splits on commas, so the final
    item came out as `e.participants AS participants` with eleven lines of prose glued to
    it, stopped matching the identifier pattern, and raised. `POST fact-for-check`
    answered 502 to every caller, and the KAL read-surface smoke is what found it.

    AGE ITSELF WAS NEVER THE PROBLEM: that same query carries a `//` comment inside its
    WHERE clause and executes fine, as do its siblings. Only this parser could not read
    what the engine could, so the parser is what changes -- moving the one comment would
    leave the next one to find the same edge.

    Quote-aware for the same reason `_split_top_level` is: `RETURN "http://x" AS url`
    carries `//` inside a string literal, and a naive strip would truncate the query.
    """
    out: list[str] = []
    quote: str | None = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if quote:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == quote:
                quote = None
            i += 1
        elif ch in "'\"`":
            quote = ch
            out.append(ch)
            i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "/":
            while i < n and text[i] != "\n":
                i += 1
        elif ch == "/" and i + 1 < n and text[i + 1] == "*":
            end = text.find("*/", i + 2)
            i = n if end == -1 else end + 2
            out.append(" ")
        else:
            out.append(ch)
            i += 1
    return "".join(out)

def return_columns(cypher: str) -> list[str]:
    """The column names a Cypher query's final `RETURN` produces, in order.

    Neo4j's rule, reproduced: an item aliased with `AS x` is named `x`; an unaliased item is
    named by its own text (`RETURN e` -> `e`). `DISTINCT` is not part of the first name.

    ⚠️ The scan takes the LAST `RETURN`, which is only safe because the repo layer has no
    `CALL { }` subqueries left (T81/T82 removed the last of them) — a subquery has its own
    `RETURN` and this would take the wrong one. That is a real coupling, so it is asserted
    rather than assumed: a query containing `CALL {` is refused.
    """
    cypher = _strip_comments(cypher)
    if re.search(r"\bCALL\s*\{", cypher, re.I):
        raise ColumnParseError(
            "cypher contains a `CALL { }` subquery, whose own RETURN would be mistaken for the "
            "query's. AGE does not support the construct either — §10.1 removed all of them."
        )
    matches = list(re.finditer(r"\bRETURN\b", cypher, re.I))
    if not matches:
        # A pure write — `MERGE (f)-[:ABOUT]->(e)` with nothing to hand back. Neo4j is happy
        # to return no columns; AGE's `cypher()` is a table-valued function and needs a column
        # list regardless, so it gets one placeholder that yields no rows. Returning `[]` here
        # (and NOT raising) is what lets `merge_fact`'s second statement run at all.
        return []
    body = cypher[matches[-1].end():]
    tail = _TAIL.search(body)
    if tail:
        body = body[: tail.start()]
    body = body.strip()
    if body.upper().startswith("DISTINCT "):
        body = body[len("DISTINCT "):]

    columns: list[str] = []
    for item in _split_top_level(body):
        alias = re.split(r"\s+AS\s+", item, flags=re.I)
        name = alias[-1].strip() if len(alias) > 1 else item.strip()
        name = name.strip("`")
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name):
            raise ColumnParseError(
                f"cannot name the result column for {item.strip()!r} — alias it with `AS`. "
                f"AGE needs an explicit column list and a wrong name returns the wrong value "
                f"under the right key."
            )
        columns.append(name)
    if not columns:
        raise ColumnParseError(f"RETURN produced no columns: {cypher[:80]!r}")
    return columns


# ── agtype decoding ──────────────────────────────────────────────────────────────────────

_TYPED = re.compile(r"::(vertex|edge|path)\s*$")


class AgeVertex(dict):
    """A vertex or edge, exposing its PROPERTIES the way a Bolt `Node` does.

    `_node_to_entity` and its siblings read `node["id"]` and `dict(node.items())`. AGE returns
    `{"id": <graphid>, "label": …, "properties": {…}}`, where `id` is the internal graph id and
    NOT the domain `id` the repo layer means. Exposing the envelope would hand every caller the
    wrong `id` — a value of the right type, in the right place, that is silently not the id
    anything else in the system uses.
    """

    def __init__(self, envelope: dict) -> None:
        super().__init__(envelope.get("properties") or {})
        self.label = envelope.get("label")
        self.graph_id = envelope.get("id")


#: Every `::vertex` / `::edge` / `::path` annotation, wherever it appears -- NOT just the
#: trailing one `_TYPED` matches.
_TYPED_ANY = re.compile(r"::(vertex|edge|path)" + chr(92) + "b")


def _strip_type_annotations(text: str) -> str:
    """Remove agtype type annotations that are OUTSIDE JSON string literals.

    Quote-aware because a property VALUE may legitimately contain the text `::vertex`
    (a title, a summary, a quoted Cypher fragment in a note), and a blind
    `_TYPED_ANY.sub("", text)` would silently corrupt the row it was trying to read.
    """
    out: list[str] = []
    i, n, in_str = 0, len(text), False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
            continue
        if ch == '"':
            in_str = True
            out.append(ch)
            i += 1
            continue
        m = _TYPED_ANY.match(text, i)
        if m:
            i = m.end()
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _wrap_vertices(value: Any) -> Any:
    """Recursively turn every vertex/edge-shaped dict into an `AgeVertex`.

    The old code wrapped only the TOP level and one level into a list, which was enough
    while every query returned `RETURN e` or `RETURN collect(e)`. It is not enough for
    `collect({r: r, subj: subj, obj: obj})`: the vertices sit one level deeper, inside a
    plain map, and came back as bare dicts whose `.get("name")` is None because the
    properties live under `["properties"]`.
    """
    if isinstance(value, list):
        return [_wrap_vertices(v) for v in value]
    if isinstance(value, dict):
        if _looks_like_vertex(value):
            return AgeVertex(value)
        return {k: _wrap_vertices(v) for k, v in value.items()}
    return value


def decode_agtype(raw: Any) -> Any:
    """Turn one agtype column value into a Python value.

    🔴 A NESTED ANNOTATION USED TO MAKE THE WHOLE ROW UNDECODABLE, and the row came back
    as the RAW STRING rather than raising. `GET /v1/knowledge/entities/{id}` returns
    `collect({r: r, subj: subj, obj: obj}) AS edges`, and AGE annotates the INNER values:

        [{"a": {"id": 1125…, "label": "Event", "properties": {…}}::vertex}]

    `_TYPED` is anchored with `$`, so it matched none of those; `json.loads` then failed on
    the bare `::vertex` and the `except JSONDecodeError` handed the caller the string it
    had been given. The caller did `edge["r"]` and got
    `TypeError: string indices must be integers` -- a 500 on the entity-detail route,
    found by a browser e2e whose relation edge never rendered. A decoder that returns its
    input on failure turns "I could not read this" into "here is your data".
    """
    if raw is None:
        return None
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    trailing = _TYPED.search(text) is not None
    text = _strip_type_annotations(text).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return raw
    if trailing and isinstance(value, dict):
        return AgeVertex(value)
    return _wrap_vertices(value)


def _looks_like_vertex(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and "properties" in value
        and "label" in value
        and "id" in value
    )


# ── the session ──────────────────────────────────────────────────────────────────────────


class AgeRecord(dict):
    """One result row. `record["x"]` and `dict(record)` behave as the Bolt driver's do."""


class AgeResult:
    """What `session.run` returns: `await .single()`, or `async for record in result`."""

    def __init__(self, records: list[AgeRecord]) -> None:
        self._records = records

    async def single(self) -> AgeRecord | None:
        return self._records[0] if self._records else None

    async def data(self) -> list[AgeRecord]:
        return list(self._records)

    def __aiter__(self):
        async def _gen():
            for record in self._records:
                yield record

        return _gen()



class AgeTransaction:
    """A `tx`-shaped handle over an open asyncpg transaction.

    The repo layer's transactional paths — the optimistic-concurrency pair (T80), the entity
    merge, the scoped erase — do `async with await session.begin_transaction() as tx:` and then
    `tx.run(...)`. On Neo4j that is the Bolt driver's own object; here it is this, so the same
    repo function works either side without an engine branch in it.

    ⚠️ The transaction is not decoration in the OCC path: statement 1 takes a lock and statement
    2 relies on it still being held. A `tx` that quietly ran each statement in its own
    transaction would leave every measurement T80 made about concurrency false, while every
    test that mocks a session still passed.
    """

    def __init__(self, session: "AgeCypherSession", pg_tx: Any) -> None:
        self._session = session
        self._pg_tx = pg_tx

    #: Mirrors the session's, so `engine_of(tx)` answers the same as `engine_of(session)`.
    engine = "age"

    async def run(self, cypher: str, /, **params: Any) -> "AgeResult":
        return await self._session.run(cypher, **params)

    async def commit(self) -> None:
        await self._pg_tx.commit()
        self._committed = True

    async def rollback(self) -> None:
        await self._pg_tx.rollback()
        self._committed = True

    async def __aenter__(self) -> "AgeTransaction":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        # The Bolt driver rolls back an uncommitted transaction on exit; asyncpg raises if the
        # transaction is already finished, so a committed one is left alone.
        if not getattr(self, "_committed", False):
            await self._pg_tx.rollback()
            self._committed = True
        return False

class AgeCypherSession:
    """Runs `graph_repos` Cypher against an AGE graph. Satisfies `CypherSession` structurally.

    `conn` is an `asyncpg` connection (or anything with the same `fetch`), already carrying
    `LOAD 'age'` and the `ag_catalog` search path — see `prepare`.

    ⚠️ `engine` is not decoration. `neo4j_helpers.engine_of` reads it to decide which dialect to
    render, and its fallback for a session that declares nothing is `"neo4j"` — correct for a
    Bolt session, silently wrong for this one. The first run of this class omitted the
    attribute and every query failed at the database with `function datetime does not exist`,
    which is the same fallback hazard one layer up from the 51 hardcoded literals T83 removed.
    """

    #: Read by `neo4j_helpers.engine_of`. Removing it renders Neo4j Cypher against AGE.
    engine = "age"

    def __init__(self, conn: Any, graph: str) -> None:
        if not graph or len(graph) < 2:
            # A one-character graph name is rejected by AGE itself; caught here so the error
            # names the cause rather than surfacing as `graph name is invalid` from the engine.
            raise ValueError(
                f"graph name {graph!r} is invalid — AGE refuses names shorter than two "
                f"characters (measured 2026-08-11)"
            )
        self._conn = conn
        self._graph = graph

    @staticmethod
    async def prepare(conn: Any) -> None:
        """Load the extension and put `ag_catalog` on the search path for this connection."""
        await conn.execute("LOAD 'age';")
        await conn.execute("SET search_path = ag_catalog, public;")

    async def begin_transaction(self) -> "AgeTransaction":
        """Open a real Postgres transaction and hand back a `tx`-shaped handle.

        Awaited then used as a context manager — `async with await session.begin_transaction()`
        — which is the Bolt driver's shape and therefore what the repo layer writes.
        """
        pg_tx = self._conn.transaction()
        await pg_tx.start()
        return AgeTransaction(self, pg_tx)

    async def run(self, cypher: str, /, **params: Any) -> AgeResult:
        columns = return_columns(cypher)
        # ⚠️ QUOTED. A Cypher alias may be a SQL reserved word, and `AS t(count agtype)` is a
        # syntax error at `count` — which is exactly how `maintenance.clear_embedding_model_tag`
        # failed on AGE (`RETURN count(n) AS count`). The Cypher is fine; the column list this
        # module builds around it was not. asyncpg still returns the key unquoted, so the row
        # lookup below is unchanged.
        col_sql = ", ".join(f'"{c}" agtype' for c in columns) or '"_void" agtype'
        # `$q$…$q$` dollar-quoting so the Cypher body needs no escaping, and `$1` for the
        # parameter map — the whole point of this module. Values are BOUND, never interpolated.
        sql = (
            f"SELECT * FROM cypher('{self._graph}', $q${cypher}$q$, $1) "
            f"AS t({col_sql});"
        )
        rows = await self._conn.fetch(sql, json.dumps(params, default=_json_default))
        return AgeResult([
            AgeRecord({c: decode_agtype(row[c]) for c in columns}) for row in rows
        ])


def _json_default(value: Any) -> Any:
    """Datetimes cross as ISO strings; anything else unknown is an error, not a `str()`.

    A silent `str()` fallback is how a value of the wrong type reaches the database looking
    plausible — the class of bug this whole plan keeps finding.
    """
    from datetime import date, datetime

    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(
        f"cannot bind a {type(value).__name__} as an AGE parameter: {value!r}. Convert it at "
        f"the call site rather than letting it cross as a string."
    )


# ── the repo layer's session, over the process AGE pool ──────────────────────────────────


class _PooledAgeSession:
    """`async with age_repo_session() as s:` — an `AgeCypherSession` on a pooled connection.

    T54's blocker was that flipping `KNOWLEDGE_GRAPH_BACKEND` split one conceptual graph across
    two stores: the 19 `GraphStore` adopters read AGE while the 54 `graph_repos` binders read
    Neo4j, **inside a single service**, with AGE empty. The measurement that stopped the row is
    in the plan (T54b): `Neo4j schema applied` and `AGE pool ready` seconds apart, extraction
    reading the empty one without erroring.

    That split existed because `graph_session()` could only ever return a Bolt session. It can
    now return this instead, so the same 135 call sites follow the configured backend and the
    two halves of the service read the SAME store. The cure is one function, not 34 module
    migrations — which is what §10.1 decided and what T83/T84 made true.
    """

    def __init__(self, pool: Any, graph: str) -> None:
        self._pool = pool
        self._graph = graph
        self._conn: Any = None

    async def __aenter__(self) -> AgeCypherSession:
        self._conn = await self._pool.acquire()
        # The pool's own init already loads the extension per connection; calling it again is
        # cheap and makes this usable against a bare pool in a test.
        await AgeCypherSession.prepare(self._conn)
        return AgeCypherSession(self._conn, self._graph)

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        if self._conn is not None:
            await self._pool.release(self._conn)
            self._conn = None
        return False


def age_repo_session(pool: Any, project_id: Any = None) -> _PooledAgeSession:
    """Open a repo-layer session against the process AGE pool.

    Raises when no pool exists rather than falling back to Neo4j. That refusal is the same law
    `graph_store_provider.get_graph_store` states and for the same reason: **a backend that
    silently is not the one you selected is the defect T54 exists to fix.** Half the service
    reading AGE and half reading Neo4j is exactly what T54b measured and reverted.
    """
    from app.db.age_bootstrap import graph_name_for

    if pool is None:
        raise RuntimeError(
            "the graph backend is `age` but no AGE pool exists — `KNOWLEDGE_AGE_DB_URL` is "
            "unset or `init_age_pool()` never ran. Refusing to fall back to Neo4j: that would "
            "put the repo layer on one engine and the port adopters on another, which is the "
            "split T54b measured on dev and reverted."
        )
    return _PooledAgeSession(pool, graph_name_for(project_id))
