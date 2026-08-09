"""Summary vector-index lifecycle on Neo4j (plan T13).

Moved out of `app/db/neo4j_helpers.py`, which is the multi-tenant Cypher GUARD module —
`assert_user_id_param`, `run_read`, `run_write`. Index DDL living alongside the thing that
polices queries made the guard module the one place in the service where Cypher was
expected, which is the opposite of what it is for.

These five functions are also the shape the `VectorStore` port takes in T14
(`ensure_index` / `drop_index` / the naming that pairs them), so isolating them now is
what makes that a wrapping rather than a rewrite.

WHY THESE DO NOT CARRY `$user_id`. `SHOW`/`CREATE`/`DROP INDEX` are admin DDL: they have
no rows and therefore no tenant to filter. `run_read`/`run_write` would reject them, which
is correct — the assertion exists for queries that read data. Tenancy for these is
STRUCTURAL instead: an index name embeds the project and embedding-model UUIDs, and every
name that reaches `DROP` is validated by `parse_summary_index_name` first, so one project
cannot name another's index. Cypher has no parameter form for index names, so that
validation is the injection barrier as well.
"""

from __future__ import annotations

import re
from typing import Literal as _Literal

from app.db.neo4j_helpers import CypherSession

__all__ = [
    "ensure_summary_indexes",
    "drop_summary_index",
    "list_summary_vector_indexes",
    "parse_summary_index_name",
    "summary_index_name",
]


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
