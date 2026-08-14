"""Kuzu database open/close and schema DDL (plan T42, the Kuzu half of X1's bake-off).

WHY THIS EXISTS AS ITS OWN MODULE — the same reason `age_bootstrap.py` does, for a different
engine's setup step. AGE needs per-session `LOAD`/`search_path`; Kuzu needs the schema to
EXIST before a single write, and getting that wrong fails in a way that reads like a bad query
rather than a missing setup step:

    Binder exception: Table Entity does not exist.

KUZU IS SCHEMA-FULL, AND NEITHER OTHER ADAPTER IS
-------------------------------------------------
Neo4j and AGE accept a property nobody declared. Kuzu rejects it at bind time:

    Binder exception: Cannot find property surprise for n.

So an adapter written against the AGE shape fails on its FIRST write. This module is where
that difference is absorbed, once, instead of at twenty call sites.

✅ **AND THE DDL IS DERIVABLE, which is a property of the port rather than luck.** `GraphStore`
is twenty methods of CLOSED, TYPED parameter lists — there is no free-form property bag on the
surface — and `domain/graph_models.py` is Pydantic with concrete field types. So the columns
below are read off the domain models and cannot drift from them. A port carrying
`attrs: dict[str, Any]` would have forced Kuzu's `MAP(STRING, STRING)`, which is string→string,
and every typed value (ordinals, confidences, timestamps) would have lost its type on the way
in. That question never arises here. It was checked before being relied on: *"the port probably
carries property bags"* was the assumption this work started from, and it was wrong.

⚠️ ONE PROCESS MAY HOLD THE DATABASE. MEASURED:

    IO exception: Could not set lock on file

Kuzu is EMBEDDED — a directory on disk, not a server — and a second `Database` handle on the
same path is refused outright. Today that is satisfied: `knowledge-service` is the only service
with `NEO4J_URI` in its environment, and its Dockerfile runs a bare `uvicorn app.main:app` with
**no `--workers`**. Nothing PINS that, and adding `--workers 4` or a second replica breaks Kuzu
and nothing else. **This is a T43 input, not a defect** — X1 asked for both candidates built so
the engine could be chosen by measurement, and "cannot scale out" is precisely the kind of fact
no amount of conformance-suite green will surface: an adapter can pass all 82 rules in one
process and still be unshippable behind two.

PROJECT SCOPING IS A COLUMN, NOT A DATABASE PER PROJECT
-------------------------------------------------------
AGE gives each project its own named graph. The mirror image here would be a Kuzu directory per
project — and it is not chosen, for a reason in the port rather than a preference:

    find_entities_by_name(..., exclude_project_ids: list[str] | None = None)

That operation is inherently cross-project: it asks one question of several projects at once.
Per-project databases make it unimplementable (and would hold N file locks besides). So
`project_id` is a column, and every query filters on it — which is what the other two adapters
effectively do anyway.

SHAPE, MIRRORED FROM THE ADAPTER THAT ALREADY WORKS
---------------------------------------------------
Read off `age_graph_store.py` rather than invented: four node labels and three edge types.
`EVIDENCED_BY` has a variable FROM label (`target_label` is a parameter there), which Kuzu
expresses as one rel table with several endpoint pairs — probed, works, and a single
`MATCH ()-[r:EVIDENCED_BY]->()` still spans all of them.

Two semantics the domain needs, probed against Kuzu 0.11.3 before this file was written:

  * **Two `RELATES_TO` edges between the SAME pair** — "Kai betrayed Mira" and "Kai guards
    Mira" are different claims about one pair. Kuzu keeps both (count = 2).
  * **`MERGE` on a relationship keyed by `predicate`** — matched the existing edge rather than
    creating a third, which is what `upsert_relation` requires to be idempotent.
"""
from __future__ import annotations

import os
from typing import Any

__all__ = [
    "KUZU_NODE_TABLES",
    "KUZU_REL_TABLES",
    "ensure_schema",
    "open_kuzu",
    "close_kuzu",
    "schema_statements",
]

#: Columns are read off `app/domain/graph_models.py`. Kuzu's `STRING[]` holds the list-valued
#: fields the merge contract accumulates (`source_types`, `participants`), and
#: `list_distinct(list_concat(...))` gives the union-merge those fields specify — probed.
#:
#: `datetime` fields land as `TIMESTAMP`; the *ordinal* fields stay `INT64` and are the ones
#: the as-of read actually uses. Keeping both is deliberate: the story axis and the wall clock
#: are different axes, and collapsing them is the bug T45 exists to prevent.
KUZU_NODE_TABLES: dict[str, str] = {
    "Entity": """
        id STRING, user_id STRING, project_id STRING,
        name STRING, canonical_name STRING, kind STRING,
        aliases STRING[], canonical_version INT64,
        source_types STRING[], confidence DOUBLE,
        glossary_entity_id STRING, anchor_score DOUBLE,
        archived_at TIMESTAMP, archive_reason STRING,
        evidence_count INT64, mention_count INT64,
        user_edited BOOLEAN, version INT64, auto_created BOOLEAN,
        provenance STRING, job_id STRING,
        created_at TIMESTAMP, updated_at TIMESTAMP,
        PRIMARY KEY(id)
    """,
    "Event": """
        id STRING, user_id STRING, project_id STRING,
        title STRING, canonical_title STRING, summary STRING,
        chapter_id STRING, chapter_title STRING,
        event_order INT64, chronological_order INT64,
        event_date_iso STRING, time_cue STRING,
        narrative_thread STRING, realized_motif_code STRING, mined_motif_code STRING,
        participants STRING[], participant_entity_ids STRING[],
        confidence DOUBLE, source_types STRING[],
        evidence_count INT64, mention_count INT64,
        version INT64,
        created_at TIMESTAMP, updated_at TIMESTAMP,
        archived_at TIMESTAMP,
        PRIMARY KEY(id)
    """,
    "Fact": """
        id STRING, user_id STRING, project_id STRING,
        type STRING, content STRING, canonical_content STRING,
        confidence DOUBLE, pending_validation BOOLEAN,
        valid_from TIMESTAMP, valid_until TIMESTAMP,
        source_types STRING[], source_chapter STRING,
        from_order INT64,
        valid_from_ordinal INT64, valid_to_ordinal INT64, valid_to_ordinal_eff INT64,
        event_date_iso STRING, predicate STRING, object STRING,
        provenance STRING, evidence_count INT64,
        archived_at TIMESTAMP, created_at TIMESTAMP,
        PRIMARY KEY(id)
    """,
    # T43 — the source `status_at_order` reads. Mirrors Neo4j's `:EntityStatus`: a TRANSITION
    # at a story position, not a field on the entity. Keeping it a separate node is what lets
    # the status be asked "as of chapter N" instead of only "now".
    "EntityStatus": """
        id STRING, user_id STRING, project_id STRING, entity_id STRING,
        status STRING, from_order INT64, evidence_count INT64,
        PRIMARY KEY(id)
    """,
    # The EVIDENCED_BY target. Its own columns are thin — it exists to be pointed at.
    "ExtractionSource": """
        id STRING, user_id STRING, project_id STRING,
        chapter_id STRING, kind STRING, created_at TIMESTAMP,
        PRIMARY KEY(id)
    """,
}

#: `(name, endpoint-pairs, columns)`. EVIDENCED_BY carries three FROM labels in ONE table —
#: the AGE adapter parameterises `target_label`, and Kuzu's multi-pair form is the direct
#: equivalent. Probed: a single `MATCH ()-[r:EVIDENCED_BY]->()` spans all three.
KUZU_REL_TABLES: list[tuple[str, str, str]] = [
    (
        "RELATES_TO", "FROM Entity TO Entity",
        # `predicate` is the MERGE key, not the edge type: the type is fixed at RELATES_TO
        # because the predicate is domain data, exactly as the AGE adapter records.
        "id STRING, user_id STRING, predicate STRING, confidence DOUBLE, "
        "source_event_ids STRING[], source_chapter STRING, "
        "valid_from TIMESTAMP, valid_until TIMESTAMP, "
        "valid_from_ordinal INT64, valid_to_ordinal INT64, valid_to_ordinal_eff INT64, "
        "event_date_iso STRING, pending_validation BOOLEAN, "
        "created_at TIMESTAMP, updated_at TIMESTAMP",
    ),
    ("ABOUT", "FROM Fact TO Entity", "user_id STRING"),
    (
        "EVIDENCED_BY",
        "FROM Entity TO ExtractionSource, FROM Event TO ExtractionSource, "
        "FROM Fact TO ExtractionSource",
        "job_id STRING, extraction_model STRING, confidence DOUBLE, quote STRING",
    ),
]


def schema_statements() -> list[str]:
    """The DDL, in dependency order: node tables before the rel tables that reference them.

    `IF NOT EXISTS` throughout, so this is safe to run on every boot — probed idempotent, and
    it has to be: there is no migration runner on this side and a bootstrap that only works on
    an empty directory is one nobody can call twice.
    """
    out = [f"CREATE NODE TABLE IF NOT EXISTS {name}({cols.strip()})"
           for name, cols in KUZU_NODE_TABLES.items()]
    out += [f"CREATE REL TABLE IF NOT EXISTS {name}({pairs}, {cols})"
            for name, pairs, cols in KUZU_REL_TABLES]
    return out


def ensure_schema(conn: Any) -> int:
    """Apply the DDL. Returns the number of statements run."""
    stmts = schema_statements()
    for s in stmts:
        conn.execute(s)
    return len(stmts)


def open_kuzu(path: str, *, read_only: bool = False) -> tuple[Any, Any]:
    """`(database, connection)` for the Kuzu database at `path`, schema ensured.

    Imported lazily so that neither the module nor the service requires `kuzu` installed
    unless a Kuzu store is actually opened — the other two adapters must keep working on a
    host that has never heard of it, and an import-time dependency would make the engine
    choice a deployment fact instead of a configuration one.
    """
    import kuzu  # noqa: PLC0415 — see the docstring

    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    db = kuzu.Database(path, read_only=read_only)
    conn = kuzu.Connection(db)
    if not read_only:
        ensure_schema(conn)
    return db, conn


def close_kuzu(db: Any, conn: Any) -> None:
    """Release the handles, and with them the file lock.

    Explicit rather than left to GC: the lock is process-wide and held until the `Database`
    object is gone, so a test that opens a second store — or a caller that reopens the same
    path — fails with `Could not set lock on file` for a reason that looks like corruption
    rather than a live handle.
    """
    for obj in (conn, db):
        close = getattr(obj, "close", None)
        if callable(close):
            close()
