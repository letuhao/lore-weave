"""K11.4 — Multi-tenant Cypher query helpers.

Every Neo4j query in knowledge-service MUST filter by `$user_id`.
Missing that filter is a cross-tenant data leak — the single
highest-severity bug class in this service. The reviewer-lint
approach ("every PR is caught by eyes") is insufficient; this
module is the runtime safety net that catches the mistake at
call time instead of shipping it to production.

Two layers:

1. `assert_user_id_param(cypher)` — pure function, raises
   `CypherSafetyError` if the cypher string does not contain the
   literal token `$user_id`. Unit-testable offline, no driver needed.

2. `run_read(session, cypher, user_id, **params)` and
   `run_write(session, cypher, user_id, **params)` — async wrappers
   that assert first, then delegate to `session.run(...)` with
   `user_id` injected as a parameter. `session` is typed as a
   `CypherSession` Protocol so this module is importable today
   without the neo4j-python driver being installed (K11.2 will wire
   up the real driver).

Rule of thumb for callers: never touch `session.run(...)` directly.
If you need to write Cypher, import one of these helpers. A grep
in CI (planned) will reject direct `session.run(` outside this
module.
"""

from __future__ import annotations

from typing import Any, Protocol

__all__ = [
    "CypherSafetyError",
    "CypherSession",
    "assert_user_id_param",
    "run_read",
    "run_write",
]


class CypherSafetyError(Exception):
    """Raised when a Cypher query fails a multi-tenant safety check."""


class CypherSession(Protocol):
    """Minimal protocol the neo4j AsyncSession satisfies.

    Defined locally so this module is importable without the
    `neo4j` pip package installed. When K11.2 lands the real
    driver sessions satisfy this protocol structurally.
    """

    async def run(self, cypher: str, /, **params: Any) -> Any: ...  # pragma: no cover


def assert_user_id_param(cypher: str) -> None:
    """Raise `CypherSafetyError` if `cypher` does not reference `$user_id`.

    Pure function, no I/O. Called by `run_read` / `run_write` before
    any driver call, and directly by anyone building Cypher strings
    for eventual execution.

    Rules:
      - `cypher` must contain the literal token `$user_id`. Case-
        sensitive — Cypher parameter names are case-sensitive.
      - Leading/trailing whitespace and newlines are ignored by the
        substring check.
      - A `$user_id` inside a comment is technically legal here but
        a developer mistake. We don't parse Cypher to catch it —
        the integration tests at K11.5 / K11.6 exercise the real
        query shapes and would fail on a commented-out filter.
    """
    if not isinstance(cypher, str):
        raise CypherSafetyError(f"cypher must be str, got {type(cypher).__name__}")
    if not cypher.strip():
        raise CypherSafetyError("cypher is empty")
    if "$user_id" not in cypher:
        raise CypherSafetyError(
            "cypher must reference $user_id parameter (multi-tenant safety)"
        )


async def run_read(
    session: CypherSession,
    cypher: str,
    user_id: str,
    **params: Any,
) -> Any:
    """Run a read-only Cypher query with mandatory user_id filtering.

    `user_id` is always passed into the driver as a bound parameter —
    never interpolated into the cypher string — so Cypher injection
    is structurally impossible. The `assert_user_id_param` call is
    the belt to the driver's suspenders.
    """
    assert_user_id_param(cypher)
    return await session.run(cypher, user_id=user_id, **params)


async def run_write(
    session: CypherSession,
    cypher: str,
    user_id: str,
    **params: Any,
) -> Any:
    """Run a write Cypher query with mandatory user_id filtering.

    Identical semantics to `run_read` — the split exists so that a
    future read/write transaction router (K11.2) can route queries
    to different Neo4j routing contexts without parsing the cypher.
    """
    assert_user_id_param(cypher)
    return await session.run(cypher, user_id=user_id, **params)
