"""Passage facts that belong to the CORPUS, not to whichever store holds it (T17 A5/A6).

Both constants below lived in `db/neo4j_repos/passages.py`, and both were being read by code
that has nothing to do with Neo4j — which made twelve modules count as bound to the concrete
layer for the sake of a tuple of integers.

`SUPPORTED_PASSAGE_DIMS` has the clearest proof of all: **the POSTGRES adapter validates
against it**, and says why in its own words —

    "`vector(n)` is a TYPED column: one table cannot hold 384- and 3072-dim embeddings. So
     the per-dim split is structural, and the dim set has to be closed for the table name to
     be safe to interpolate. It already is — `SUPPORTED_PASSAGE_DIMS`, which `passages.py`
     has been validating against for the same reason (Cypher could not parameterise a
     property name; SQL cannot parameterise a relation name). **Same barrier, same closed
     set, one place.**"
        — `app/adapters/pg_vector_store.py`

Two engines, opposite query languages, one closed set. A constant that both a Cypher store
and a SQL store must agree on is a fact about the PLATFORM; leaving it in one engine's
package made the other engine's adapter import its rival to learn what dimensions exist.

They are re-exported from `db/neo4j_repos/passages.py`, so every existing importer keeps
working and there is still exactly ONE definition. A second literal is the drift both
comments below warn about.
"""
from __future__ import annotations

__all__ = ["KNOWN_SOURCE_TYPES", "SUPPORTED_PASSAGE_DIMS", "SUPPORTED_VECTOR_DIMS"]

# C8 (D-K19e-γa-01) — closed set of recognised `source_type` values on :Passage nodes.
# Single source of truth consumed by:
#   - drawers.py router (Literal validation + response padding)
#   - count_passages_by_source_type (key padding so every type appears even at 0 count)
# Add a member here first, before writing a new source_type producer.
KNOWN_SOURCE_TYPES: frozenset[str] = frozenset({"chapter", "chat", "glossary"})

# The embedding dimensions this platform accepts. Closed because BOTH stores need it closed:
# Neo4j cannot parameterise a property name, Postgres cannot parameterise a relation name, so
# each interpolates a validated dim into its own DDL.
#
# ⚠️ A new dim here is not just a tuple edit — it needs a matching `CREATE VECTOR INDEX` in
# `neo4j_schema.cypher` AND a per-dim table in the pgvector store. The constant is the
# checklist; adding to it without the two index changes yields a dim that validates and then
# has nowhere to be written.
SUPPORTED_PASSAGE_DIMS: tuple[int, ...] = (384, 1024, 1536, 2560, 3072)

# ENTITY vectors use the SAME closed set, and that is not a convention — it is what the
# Postgres writer already does. `create_vector_tables` iterates `SUPPORTED_PASSAGE_DIMS` and
# creates BOTH tables from it:
#
#     for dim in dims or SUPPORTED_PASSAGE_DIMS:
#         ptable, etable = passage_table(dim), entity_table(dim)
#
# So a second literal here is not duplication that merely drifts, it is a latent bug with a
# direction: a dim in the entity set but NOT in the passage set validates at the embedder and
# then has no `entity_vectors_{dim}` table to be written to. It lived in
# `db/neo4j_repos/entities.py` as its own tuple, which is exactly the split that makes that
# reachable. One name, one object, one place to add a dim.
SUPPORTED_VECTOR_DIMS: tuple[int, ...] = SUPPORTED_PASSAGE_DIMS
