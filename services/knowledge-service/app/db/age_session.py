"""A `CypherSession` over Apache AGE — spec §10.1's *other* half.

§10.1 says what binds `neo4j_repos` to Neo4j is **"the Cypher dialect and the session type"**.
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


def return_columns(cypher: str) -> list[str]:
    """The column names a Cypher query's final `RETURN` produces, in order.

    Neo4j's rule, reproduced: an item aliased with `AS x` is named `x`; an unaliased item is
    named by its own text (`RETURN e` -> `e`). `DISTINCT` is not part of the first name.

    ⚠️ The scan takes the LAST `RETURN`, which is only safe because the repo layer has no
    `CALL { }` subqueries left (T81/T82 removed the last of them) — a subquery has its own
    `RETURN` and this would take the wrong one. That is a real coupling, so it is asserted
    rather than assumed: a query containing `CALL {` is refused.
    """
    if re.search(r"\bCALL\s*\{", cypher, re.I):
        raise ColumnParseError(
            "cypher contains a `CALL { }` subquery, whose own RETURN would be mistaken for the "
            "query's. AGE does not support the construct either — §10.1 removed all of them."
        )
    matches = list(re.finditer(r"\bRETURN\b", cypher, re.I))
    if not matches:
        raise ColumnParseError(f"cypher has no RETURN clause: {cypher[:80]!r}")
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


def decode_agtype(raw: Any) -> Any:
    """Turn one agtype column value into a Python value."""
    if raw is None:
        return None
    if not isinstance(raw, str):
        return raw
    text = raw.strip()
    typed = _TYPED.search(text)
    if typed:
        text = text[: typed.start()].strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return raw
    if typed and isinstance(value, dict):
        return AgeVertex(value)
    if isinstance(value, list):
        return [AgeVertex(v) if _looks_like_vertex(v) else v for v in value]
    if _looks_like_vertex(value):
        return AgeVertex(value)
    return value


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


class AgeCypherSession:
    """Runs `neo4j_repos` Cypher against an AGE graph. Satisfies `CypherSession` structurally.

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

    async def run(self, cypher: str, /, **params: Any) -> AgeResult:
        columns = return_columns(cypher)
        col_sql = ", ".join(f"{c} agtype" for c in columns)
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
