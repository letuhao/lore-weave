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

import re
from typing import Any, Protocol

from app.db.cypher_dialect import assert_rendered

__all__ = [
    "CypherSafetyError",
    "CypherSession",
    "assert_user_id_param",
    "run_read",
    "run_write",
    "summary_index_name",
    "ensure_summary_indexes",
    "parse_summary_index_name",
    "list_summary_vector_indexes",
    "drop_summary_index",
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


# Match single- or double-quoted Cypher string literals with basic
# backslash-escape handling. Used to strip literal contents *before*
# scanning for `$user_id` — otherwise a query like
# `CREATE (e {note: '$user_id'})` silently passes the safety check
# while actually binding no parameter (R2).
_STRING_LITERAL_RE = re.compile(
    r"""'(?:[^'\\]|\\.)*'|"(?:[^"\\]|\\.)*\"""",
    re.DOTALL,
)

# Match `$user_id` as a whole parameter token, i.e. not followed by
# another word character. Prevents `$user_id_extra` / `$user_ids`
# from satisfying the check when the real `$user_id` is absent (R1).
_USER_ID_PARAM_RE = re.compile(r"\$user_id(?!\w)")


def assert_user_id_param(cypher: str) -> None:
    """Raise `CypherSafetyError` if `cypher` does not reference `$user_id`.

    Pure function, no I/O. Called by `run_read` / `run_write` before
    any driver call, and directly by anyone building Cypher strings
    for eventual execution.

    Rules:
      - `cypher` must contain `$user_id` as a complete parameter
        token. Case-sensitive — Cypher parameter names are
        case-sensitive. `$user_id_extra` does NOT satisfy the rule.
      - String-literal contents are stripped before the scan so a
        literal like `'$user_id'` inside `CREATE (e {note: '…'})`
        does not masquerade as a parameter reference.
      - Leading/trailing whitespace and newlines are ignored.
      - A `$user_id` inside a `// comment` is technically legal here
        but a developer mistake. We don't parse Cypher that deeply —
        integration tests at K11.5/K11.6 exercise real query shapes
        and would catch a commented-out filter via wrong-row counts.
    """
    if not isinstance(cypher, str):
        raise CypherSafetyError(f"cypher must be str, got {type(cypher).__name__}")
    if not cypher.strip():
        raise CypherSafetyError("cypher is empty")
    # Remove string-literal spans so their contents can't satisfy
    # the parameter check (R2). Then look for `$user_id` as a
    # whole token, not a prefix (R1).
    stripped = _STRING_LITERAL_RE.sub("", cypher)
    if not _USER_ID_PARAM_RE.search(stripped):
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
    assert_rendered(cypher)
    return await session.run(cypher, user_id=user_id, **params)


async def run_read_any_owner(
    session: CypherSession,
    cypher: str,
    **params: Any,
) -> Any:
    """Run a read-only Cypher query with **NO tenant filter**. Rare, and named loudly.

    This exists because `get_entity_by_id_any_owner` legitimately needs an unfiltered
    lookup — but it was calling `run_read`, whose `user_id` is a REQUIRED parameter and
    whose `assert_user_id_param` demands the cypher reference `$user_id`. Its cypher does
    neither, so the call raised
    ``TypeError: run_read() missing 1 required positional argument: 'user_id'`` on every
    invocation, and `kg_entity_edge_timeline` — its only consumer — could never work.
    Found by the deterministic capability sweep (`scripts/eval/tool_liveness/sweep.py`);
    nothing else ever called it.

    SAFETY. Omitting the tenant filter is sound ONLY when both hold:

    1. the match key is GLOBALLY UNIQUE, so there is no cross-tenant collision
       (``Entity.id`` is a hash of user_id+project_id+name+kind); and
    2. the caller grant-checks the returned row's project BEFORE exposing any of its data
       (``_resolve_entity_project_grant`` does exactly this).

    The assertion is INVERTED on purpose: a cypher that *does* carry ``$user_id`` has a
    tenant filter and must go through :func:`run_read`, where the filter is enforced rather
    than merely present. That keeps this unfiltered path from silently absorbing a query
    which meant to be filtered.
    """
    if not isinstance(cypher, str) or not cypher.strip():
        raise CypherSafetyError("cypher must be a non-empty str")
    if _USER_ID_PARAM_RE.search(_STRING_LITERAL_RE.sub("", cypher)):
        raise CypherSafetyError(
            "cypher references $user_id — use run_read(), which enforces the filter"
        )
    assert_rendered(cypher)
    return await session.run(cypher, **params)


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
    assert_rendered(cypher)
    return await session.run(cypher, user_id=user_id, **params)
