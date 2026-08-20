"""The graph's LABEL vocabularies — facts about the corpus, not about the engine (T17 A10).

Both tuples below lived in `db/neo4j_repos/maintenance.py`, and both are read by code that
has nothing to do with Neo4j: a stats reconciler that writes Postgres columns, and an
extraction router that decides which parts of a project a rebuild is allowed to clear.

They are here for the same reason `SUPPORTED_PASSAGE_DIMS` is in `passage_contract.py` —
see spec §1.2, which decided this class explicitly:

    "Constants → `app/domain/`. `COUNTABLE_LABELS`, `PROJECT_GRAPH_LABELS`. Same class as
     `EVENT_ORDER_CHAPTER_STRIDE` and `SUPPORTED_PASSAGE_DIMS`: facts about the corpus, not
     the engine, and leaving them in `neo4j_repos` makes their importers look bound when
     they are not."

⚠️ **Both are INJECTION BARRIERS and that survives the move.** Cypher cannot parameterise a
label, so the label is interpolated into the query text and the closed tuple is the only
thing standing between a caller and an arbitrary string. Kuzu and AGE interpolate a table
name for the same reason. Moving a constant out of the engine package does not make it
decorative — the validation belongs wherever the interpolation happens, and every one of
those sites still checks membership before formatting.

They are re-exported from `db/neo4j_repos/maintenance.py`, so every existing importer keeps
working and there is still exactly ONE definition.
"""
from __future__ import annotations

__all__ = ["COUNTABLE_LABELS", "PROJECT_GRAPH_LABELS"]

# The labels a project's stats card counts. EXACTLY the three the `knowledge_projects`
# table has columns for (`stat_entity_count`/`stat_fact_count`/`stat_event_count`), which is
# why `Passage` is absent: passages are the vector layer's, and after the §3.1 cutover they
# do not live in the graph at all.
COUNTABLE_LABELS: tuple[str, ...] = ("Entity", "Fact", "Event")

# The labels a project-scoped graph delete is allowed to clear.
#
# ⚠️ `Passage` is NOT here, deliberately, and a test pins its absence: passage nodes carry
# chat- and glossary-sourced chunks that extraction did not create and must not destroy.
# Adding it here would make a re-extraction wipe a user's chat history embeddings.
PROJECT_GRAPH_LABELS: tuple[str, ...] = ("Entity", "Event", "Fact", "ExtractionSource")
