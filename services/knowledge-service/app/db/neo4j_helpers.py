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

import asyncio
import re
from typing import Any, Protocol

from app.db.cypher_dialect import Engine, assert_rendered, render

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
    "require_neo4j_only",
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




def require_neo4j_only(
    session: CypherSession, operation: str, capability: str = "index administration",
) -> None:
    """Refuse an INDEX-ADMIN command on any engine that has no such command (rule 9).

    `SHOW VECTOR INDEXES`, `CREATE VECTOR INDEX` and `DROP INDEX` are Neo4j index administration,
    not Cypher — AGE wraps every statement in `SELECT * FROM cypher(...)`, where they are a SQL
    parse error. Measured on iso: `PostgresSyntaxError: syntax error at or near "SHOW"`.

    That raise was already happening; what it was not doing was SAYING anything. `purge_project`
    is a general repo function that called these unconditionally, and its caller wraps the whole
    purge in `except Exception` and logs "graph orphaned, re-sweep owed". On AGE -- the DEFAULT
    backend since T54 -- every project delete therefore reported an orphaned graph whose nodes
    had in fact been deleted, and the message could not be told apart from a real purge failure.

    A refusal that names itself is the difference. Engine comes from `engine_of`, which is the
    one home for it (§10.1: the session is the only thing that knows its dialect).
    """
    engine = engine_of(session)
    if engine != "neo4j":
        raise NotImplementedError(
            f"{operation} — {capability} is a Neo4j-only capability and this session speaks "
            f"{engine!r}, which has no such command: §3.1 moves the vector and passage layers "
            f"to Postgres, where the equivalents are tables and SQL indexes. Callers that must "
            f"tolerate this should catch NotImplementedError EXPLICITLY — a bare `except` here "
            f"also swallows a real Neo4j failure and reports the two identically."
        )


def engine_of(session: Any) -> Engine:
    """Which dialect `session` speaks.

    ⚠️ **This function exists because "the dialect backlog is zero" did not mean "the layer is
    engine-agnostic".** T77-T82 took every Neo4j-only construct out of `graph_repos`, and the
    ratchet duly read 0 — while **51 call sites across 11 modules still said
    `render(TEMPLATE, "neo4j")`**, naming the engine in a string literal the dialect scan
    cannot see. Running a real repo function against AGE failed on `function datetime does not
    exist`: the templates were portable and the RENDERING was pinned.

    So the engine comes from the session, which is the only thing that knows it. A session that
    declares `engine` is authoritative; one that does not is a Bolt `AsyncSession` or its
    transaction — the Neo4j driver's own types, which cannot be anything else. That fallback is
    a FACT about the type, not a default standing in for a missing declaration.
    """
    engine = getattr(session, "engine", None)
    # Only a STRING counts as a declaration. A `MagicMock` answers every attribute with another
    # mock, so `is not None` would hand `render` a mock and raise from inside two hundred unit
    # tests that legitimately do not care which engine they are pretending to be.
    return engine if isinstance(engine, str) else "neo4j"


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
    cypher = render(cypher, engine_of(session))
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
    cypher = render(cypher, engine_of(session))
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
    cypher = render(cypher, engine_of(session))
    assert_user_id_param(cypher)
    assert_rendered(cypher)
    return await session.run(cypher, user_id=user_id, **params)


# ── transient-failure retry (T80) ────────────────────────────────────

#: Neo4j's retryable class. Matched by CODE and by class NAME rather than by importing the
#: driver, because this module is deliberately importable without the `neo4j` package (see
#: `CypherSession`) — and because the same duck-typing lets a test raise a stand-in.
_TRANSIENT_CODE_PREFIX = "Neo.TransientError."
_TRANSIENT_CLASS_NAMES = frozenset({"TransientError", "ServiceUnavailable", "SessionExpired"})


def is_transient(exc: BaseException) -> bool:
    """Is `exc` the kind of failure that succeeds on a retry?"""
    code = getattr(exc, "code", None)
    if isinstance(code, str) and code.startswith(_TRANSIENT_CODE_PREFIX):
        return True
    return type(exc).__name__ in _TRANSIENT_CLASS_NAMES


async def in_retried_transaction(
    session: Any,
    op: Any,
    *,
    attempts: int = 3,
    base_delay: float = 0.02,
) -> Any:
    """Run `op(tx)` in an explicit transaction, retrying the whole transaction on a deadlock.

    ⚠️ **A deadlock here is expected, not exceptional.** T80's optimistic-concurrency path
    takes an exclusive lock and then reads under it, which is the only measured shape that
    stops two concurrent editors both being told their edit landed. The cost is that two
    transactions racing for the same node can form a lock cycle, and Neo4j resolves that by
    killing one with a `TransientError` — which is a *retryable* outcome and, unretried, is
    a 500 for a request that would have succeeded a millisecond later.

    So the whole transaction is replayed, not just the failed statement: on the retry the
    version is read again, and if the other writer won in the meantime the caller correctly
    gets a version mismatch instead of a stale success. Retrying is therefore safe for OCC
    specifically BECAUSE the operation re-derives its decision from the re-read state.

    `op` must be idempotent-on-replay for that reason. Non-transient errors — including
    `VersionMismatchError` when a caller raises inside — propagate on the first attempt.
    """
    last: BaseException | None = None
    for attempt in range(attempts):
        try:
            async with await session.begin_transaction() as tx:
                out = await op(tx)
                await tx.commit()
            return out
        except BaseException as exc:  # noqa: BLE001 — re-raised unless retryable
            if not is_transient(exc) or attempt == attempts - 1:
                raise
            last = exc
            await asyncio.sleep(base_delay * (2 ** attempt))
    raise last  # pragma: no cover — the loop always returns or raises above
