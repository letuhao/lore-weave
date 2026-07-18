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
    return await session.run(cypher, user_id=user_id, **params)


# ── P3 — per-project per-level summary vector index helpers (H1+M7+SR-2) ──

import re
from typing import Literal as _Literal

_SUMMARY_LEVELS = ("chapter", "part", "book")
# Cypher index names: ASCII letters, digits, underscores only.
_SAFE_NAME_RE = re.compile(r"^[a-z0-9_]+$")


def summary_index_name(
    project_id: str,
    embedding_model_uuid: str,
    level: _Literal["chapter", "part", "book"],
) -> str:
    """Build the Neo4j vector index name for a per-project per-level summary.

    Spec D2 (H1+M7+SR-2 fixes): full dash-stripped UUIDs for zero collision;
    namespaced by embedding_model_uuid so model change creates a NEW family.

    Format: `<level>_summary_emb_p<32hex>_e<32hex>`
    """
    if level not in _SUMMARY_LEVELS:
        raise ValueError(f"unknown level {level!r}; allowed: {_SUMMARY_LEVELS}")
    proj_short = project_id.replace("-", "").lower()
    emb_short = embedding_model_uuid.replace("-", "").lower()
    name = f"{level}_summary_emb_p{proj_short}_e{emb_short}"
    if not _SAFE_NAME_RE.match(name):
        # Defense-in-depth — should never trigger given UUID inputs.
        raise ValueError(f"unsafe index name: {name!r}")
    return name


# Parser for summary_index_name output. Used by the prune-orphans admin
# endpoint to extract (level, project_id_hex, embedding_model_uuid_hex)
# from an existing index name. Mirror of `summary_index_name`'s output
# format; the regex MUST stay in lockstep.
_SUMMARY_INDEX_NAME_RE = re.compile(
    r"^(?P<level>chapter|part|book)_summary_emb_p(?P<proj>[0-9a-f]{32})_e(?P<emb>[0-9a-f]{32})$"
)


def parse_summary_index_name(name: str) -> dict[str, str] | None:
    """Parse a summary vector index name into its components.

    Returns dict with `level`, `project_id` (hex without dashes), and
    `embedding_model_uuid` (hex without dashes) — or None if the name
    doesn't match the summary-index pattern (so non-P3 indexes are
    skipped, not misclassified).

    Inverse of `summary_index_name`; if the format ever changes, both
    must be updated together.
    """
    match = _SUMMARY_INDEX_NAME_RE.match(name)
    if match is None:
        return None
    return {
        "level": match.group("level"),
        "project_id": match.group("proj"),
        "embedding_model_uuid": match.group("emb"),
    }


async def list_summary_vector_indexes(
    session: CypherSession,
) -> list[dict[str, str]]:
    """Return all Neo4j vector indexes whose names match the P3 summary
    pattern.

    Each item: {name, level, project_id, embedding_model_uuid}. Non-summary
    indexes (e.g. entity-embedding indexes) are filtered out by the parser
    so the admin endpoint never accidentally targets them.

    Uses `SHOW VECTOR INDEXES` (Neo4j 5+); fallback callers can adjust
    the cypher per their server version. Direct `session.run` because
    SHOW/DROP are admin ops without `$user_id` semantics — mirrors
    `ensure_summary_indexes` which does the same.
    """
    rows = await session.run("SHOW VECTOR INDEXES YIELD name")
    parsed: list[dict[str, str]] = []
    async for record in rows:
        name = record["name"]
        components = parse_summary_index_name(name)
        if components is None:
            continue
        parsed.append({"name": name, **components})
    return parsed


async def drop_summary_index(session: CypherSession, name: str) -> None:
    """Idempotent DROP for a summary vector index.

    `DROP INDEX … IF EXISTS` is the no-op-on-missing form; tolerates
    concurrent drops (someone else pruned the same index between SHOW
    and DROP). Index name MUST come from `parse_summary_index_name` or
    `summary_index_name` — `_SUMMARY_INDEX_NAME_RE` constrains it to
    [a-z0-9_], structurally injection-safe.
    """
    if parse_summary_index_name(name) is None:
        # Defense-in-depth — only summary indexes are eligible here.
        raise ValueError(f"refusing to DROP non-summary index {name!r}")
    await session.run(f"DROP INDEX {name} IF EXISTS")


async def purge_project(session: CypherSession, project_id: str) -> dict[str, int]:
    """Delete ALL Neo4j nodes for a project + drop its per-project summary vector
    indexes — `D-KNOWLEDGE-PROJECT-DELETE-NEO4J-ORPHAN`: deleting a knowledge project
    must not orphan its graph.

    Every project node carries `project_id` (Entity/Event/Fact/Passage/
    ExtractionSource/EntityStatus — verified: no node connected to the project's nodes
    lacks `project_id`), so a single `project_id`-scoped `DETACH DELETE` is complete.
    The SHARED dimension-bucketed indexes (`entity_embeddings_1024`,
    `passage_embeddings_384`, …) are NEVER touched — other projects share them; only
    THIS project's `<level>_summary_emb_p<id>_e<model>` indexes are dropped (reusing the
    name-validated helpers). Returns `{nodes_deleted, indexes_dropped}`.

    The CALLER runs this best-effort: the authoritative owner-gated delete is the
    Postgres row removal; a Neo4j failure must not fail it (it just leaves an orphan to
    re-sweep). Perf follow-up: a very large graph is one `DETACH DELETE` transaction —
    batch via `CALL { … } IN TRANSACTIONS` if a huge project ever needs it.
    """
    rows = await session.run(
        "MATCH (n {project_id: $pid}) RETURN count(n) AS n", pid=project_id
    )
    nodes = 0
    async for rec in rows:
        nodes = int(rec["n"])
    if nodes:
        # count-then-delete: RETURN-after-DELETE isn't reliable across drivers.
        await session.run("MATCH (n {project_id: $pid}) DETACH DELETE n", pid=project_id)
    proj_hex = project_id.replace("-", "").lower()
    dropped = 0
    for idx in await list_summary_vector_indexes(session):
        if idx["project_id"] == proj_hex:
            await drop_summary_index(session, idx["name"])
            dropped += 1
    return {"nodes_deleted": nodes, "indexes_dropped": dropped}


async def ensure_summary_indexes(
    session: CypherSession,
    project_id: str,
    embedding_model_uuid: str,
    embedding_dimension: int,
) -> dict[str, str]:
    """Idempotent CREATE of the 3 per-project per-level summary vector indexes.

    Returns dict mapping level -> index name (caller persists for Mode-3 query).

    Spec D2 lifecycle: called lazily by extraction-job-processor BEFORE the
    first summary write for a given (project, embedding_model) pair. Safe
    to call every job start — `CREATE VECTOR INDEX IF NOT EXISTS` is no-op
    on existing indexes.
    """
    if embedding_dimension <= 0:
        raise ValueError(f"invalid embedding_dimension {embedding_dimension!r}")
    names: dict[str, str] = {}
    for level in _SUMMARY_LEVELS:
        idx_name = summary_index_name(project_id, embedding_model_uuid, level)
        node_label = level.capitalize()  # Chapter / Part / Book
        # Index name MUST be safely templated — Cypher doesn't support $ for names.
        # _SAFE_NAME_RE validation above guarantees safety.
        cypher = (
            f"CREATE VECTOR INDEX {idx_name} IF NOT EXISTS "
            f"FOR (n:{node_label}) ON (n.summary_embedding) "
            "OPTIONS {indexConfig: {"
            "`vector.dimensions`: $dim, "
            "`vector.similarity_function`: 'cosine'}}"
        )
        await session.run(cypher, dim=embedding_dimension)
        names[level] = idx_name
    return names
