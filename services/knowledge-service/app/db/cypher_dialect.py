"""Engine-neutral Cypher tokens — spec §10.2.

`graph_repos` is Neo4j-shaped in its **dialect**, not in its semantics: its functions are
already domain-shaped (`find_entities_by_name`, `status_at_order`), which the sealed plan
observed on day one. §10.1 decided the layer becomes engine-agnostic rather than being
absorbed into a 106-method port. This module is the smallest piece of that: the places where
one engine's *function name* is baked into a query string.

── WHY THIS IS AN INDIRECTION AND NOT A REWRITE ────────────────────────────────────────────
Five of the six Neo4j-only constructs are **semantics-preserving** on both engines and get
rewritten in place — `ON CREATE SET` → `coalesce`, `ON MATCH SET` → unconditional `SET`,
`CALL {}` → CTE/`LATERAL`, `FOREACH` → two statements in one transaction. T57–T59 shipped all
four on the three hardest queries in the codebase.

`datetime()` is the exception, and T63 measured why. Neo4j's `datetime()` returns a
`ZONED DATETIME`; its `timestamp()` returns an `INTEGER`. Rewriting one to the other changes
the **stored type**, existing rows keep the old one, and `created_at`/`updated_at` drive
`ORDER BY` at ten or more read sites. Neo4j does not error on a mixed-type `ORDER BY` — **it
sorts by type first**, so every time-ordered list silently returns a wrong order on live data:

    CREATE (a {t: datetime()})   first     ORDER BY t ASC ->  a  (DATETIME)
    CREATE (b {t: timestamp()})  second                       c  (DATETIME)   <- third
    CREATE (c {t: datetime()})   third                        b  (INTEGER)    <- second

So the token is chosen where the query is built, and each engine keeps the type its own reads
already expect. No data migration, and no window during which the two coexist in one property.

── USAGE ───────────────────────────────────────────────────────────────────────────────────
Write `{NOW}` in the template and render it once, at the call site that knows the engine::

    _CHAIN = "MATCH (f:Fact) SET f.updated_at = {NOW} RETURN f"
    await run_write(session, render(_CHAIN, "neo4j"), ...)

⚠️ This module lives OUTSIDE `graph_repos` on purpose. `port-adoption-gate`'s dialect ratchet
counts Neo4j-only constructs in that package's code strings; defining `"datetime()"` inside it
would make the gate count its own cure.
"""

from __future__ import annotations

from typing import Final, Literal

__all__ = ["Engine", "NOW_BY_ENGINE", "UnrenderedTemplateError", "assert_rendered", "render"]

Engine = Literal["neo4j", "age"]

#: `timestamp()` is AGE's spelling and returns epoch millis; Neo4j's `datetime()` returns a
#: zoned temporal. They are NOT interchangeable within one property — see the module docstring.
NOW_BY_ENGINE: Final[dict[str, str]] = {
    "neo4j": "datetime()",
    "age": "timestamp()",
}

_TOKEN: Final = "{NOW}"


def render(template: str, engine: Engine) -> str:
    """Substitute the dialect tokens in `template` for `engine`.

    Raises on an unknown engine rather than defaulting to Neo4j. A silent default is how a
    third engine would get Neo4j's function name and fail at the database with a message about
    a missing function, three layers from the cause — and rule 9 says an adapter that cannot
    honour an operation raises, naming its spec section.
    """
    try:
        now = NOW_BY_ENGINE[engine]
    except KeyError:
        raise ValueError(
            f"cypher_dialect.render: unknown engine {engine!r} — spec §10.2 defines "
            f"{sorted(NOW_BY_ENGINE)}. Add its timestamp spelling before rendering."
        ) from None
    return template.replace(_TOKEN, now)


class UnrenderedTemplateError(RuntimeError):
    """A template reached the driver with a dialect token still in it."""


def assert_rendered(cypher: str) -> None:
    """Raise if `cypher` still carries a dialect token.

    ⚠️ The whole `{NOW}` scheme has one failure mode, and it is the quiet one: a template gets
    the token but its call site never gains the `render()`. Neo4j then receives a literal
    `{NOW}`, which is a MAP LITERAL in Cypher, not a syntax error at the point of the mistake —
    the message comes back about something else entirely, three layers from the cause. Two of
    those already happened during T64: `.format()` running after `render()` (`KeyError:
    'datetime()'`), and `{NOW}` inside an f-string needing `{{NOW}}` (68 collection errors).

    So the token is checked at the same chokepoint `assert_user_id_param` uses. Rule 9: an
    adapter that cannot honour an operation raises, naming its spec section.
    """
    if _TOKEN in cypher:
        raise UnrenderedTemplateError(
            f"cypher still contains the dialect token {_TOKEN} — spec §10.2 requires "
            f"`render(template, engine)` at the call site that knows the engine. Without it "
            f"the database receives {_TOKEN} as a map literal and fails somewhere else."
        )
