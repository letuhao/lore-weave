// K11.3 — Neo4j schema for the Track 2 extraction graph.
//
// Spec: KSA §3.4 (Neo4j Amendments).
//
// Every statement is idempotent:
//   - CREATE CONSTRAINT ... IF NOT EXISTS
//   - CREATE INDEX ... IF NOT EXISTS
//   - CREATE VECTOR INDEX ... IF NOT EXISTS
//
// Re-running the script must not error and must not duplicate
// any constraint/index. The Python runner (`neo4j_schema.py`)
// splits the file on `;` and runs each statement separately —
// Neo4j's bolt protocol can only handle one Cypher statement
// per `session.run(...)` call.
//
// Vector indexes require Neo4j 2025.01+. We pin to 2026.03 in
// docker-compose.yml so this is satisfied; an older Neo4j would
// fail loudly when it hits the first CREATE VECTOR INDEX line.
//
// Multi-tenant enforcement: every node label has `user_id` as a
// first-class property and every Cypher query in repo code MUST
// filter on it via K11.4's `assert_user_id_param` helper. The
// schema indexes below include `user_id` in composite keys to
// keep those queries cheap.

// ─────────────────────────────────────────────────────────────────
// UNIQUE CONSTRAINTS — primary keys for each node label
// ─────────────────────────────────────────────────────────────────

CREATE CONSTRAINT entity_id_unique IF NOT EXISTS
FOR (e:Entity) REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT event_id_unique IF NOT EXISTS
FOR (e:Event) REQUIRE e.id IS UNIQUE;

CREATE CONSTRAINT fact_id_unique IF NOT EXISTS
FOR (f:Fact) REQUIRE f.id IS UNIQUE;

CREATE CONSTRAINT extraction_source_id_unique IF NOT EXISTS
FOR (s:ExtractionSource) REQUIRE s.id IS UNIQUE;

CREATE CONSTRAINT project_id_unique IF NOT EXISTS
FOR (p:Project) REQUIRE p.id IS UNIQUE;

CREATE CONSTRAINT session_id_unique IF NOT EXISTS
FOR (s:Session) REQUIRE s.id IS UNIQUE;

// K11.5b-R1/R1: glossary FK uniqueness. Two `:Entity` nodes
// must never share the same `glossary_entity_id` — the FK is
// the rename-aware lookup key for `get_entity_by_glossary_id`
// and a duplicate would crash `result.single()`. Neo4j
// uniqueness constraints allow multiple NULLs but reject
// duplicate non-NULL values, which is exactly the semantics we
// want for a nullable FK. Discovered entities (FK = NULL) are
// unaffected.
CREATE CONSTRAINT entity_glossary_id_unique IF NOT EXISTS
FOR (e:Entity) REQUIRE e.glossary_entity_id IS UNIQUE;

// ─────────────────────────────────────────────────────────────────
// user_id NOT NULL — enforced at the APPLICATION layer, not here.
//
// Property-existence constraints (`REQUIRE x IS NOT NULL`) are an
// Enterprise-only feature in Neo4j. Community edition rejects them
// with `Neo.DatabaseError.Schema.ConstraintCreationFailed`. We run
// community in dev + prod, so the user_id invariant is enforced by
// K11.4's `assert_user_id_param` query wrapper, which every repo
// helper goes through. The composite indexes below all start with
// `user_id`, so any write that omits it would also miss the index
// and surface during review.
// ─────────────────────────────────────────────────────────────────

// ─────────────────────────────────────────────────────────────────
// COMPOSITE INDEXES — hot-path lookups in K11.5+ entity repos
//
// All indexes are user_id-prefixed. Cross-user queries are not a
// supported access pattern; the index does not need to support
// them.
// ─────────────────────────────────────────────────────────────────

// "Find all entities with this canonical name belonging to this user."
CREATE INDEX entity_user_canonical IF NOT EXISTS
FOR (e:Entity) ON (e.user_id, e.canonical_name);

// "Find an entity by name within a user's namespace."
CREATE INDEX entity_user_name IF NOT EXISTS
FOR (e:Entity) ON (e.user_id, e.name);

// "Find all entities for a project owned by a user."
CREATE INDEX entity_user_project IF NOT EXISTS
FOR (e:Entity) ON (e.user_id, e.project_id);

// "Find all entities in a project that share an embedding model."
// This is the per-project-embedding-storage filter from KSA §3.4.B
// — vector_search routes on (user_id, project_id, embedding_model)
// so the composite index is the cheap pre-filter. user_id is the
// leading key for the same multi-tenant reason as every other
// index in this file.
CREATE INDEX entity_user_project_model IF NOT EXISTS
FOR (e:Entity) ON (e.user_id, e.project_id, e.embedding_model);

// "List events ordered by chronology for a user." Used by Mode 3
// L4 timeline retrieval.
CREATE INDEX event_user_order IF NOT EXISTS
FOR (e:Event) ON (e.user_id, e.event_order);

// "List events for a specific chapter." Powers the partial-
// re-extract delete-by-chapter cascade from KSA §3.4.C.
CREATE INDEX event_user_chapter IF NOT EXISTS
FOR (e:Event) ON (e.user_id, e.chapter_id);

// K19e.2 — "List events for a project owned by a user." Mirrors
// the entity_user_project index. Without it, the Timeline tab's
// project-scoped browse (POST-review LOW finding P-K19e-α-01) does
// a post-index scan on event_user_order matches for project_id.
// Bounded project-scoped browse keeps O(events-in-project) instead
// of O(events-for-user) when no date range is supplied.
CREATE INDEX event_user_project IF NOT EXISTS
FOR (e:Event) ON (e.user_id, e.project_id);

// ─────────────────────────────────────────────────────────────────
// EVIDENCE-COUNT INDEXES — partial-extraction cascade cleanup
//
// "Find all entities/events/facts belonging to a user whose
// EVIDENCED_BY count is zero so we can DETACH DELETE them after
// a partial re-extract." K11.8 maintains the denormalised
// `evidence_count` property.
//
// Composite (user_id, evidence_count) so the K11.8 cleanup
// `MATCH (e:Entity {user_id: $user_id}) WHERE e.evidence_count = 0`
// is bounded by the calling user's churn, not the global graph.
// These are full range indexes — Neo4j community 5.x does not
// support partial indexes (`CREATE INDEX ... WHERE ...`).
// ─────────────────────────────────────────────────────────────────

CREATE INDEX entity_user_evidence IF NOT EXISTS
FOR (e:Entity) ON (e.user_id, e.evidence_count);

CREATE INDEX event_user_evidence IF NOT EXISTS
FOR (e:Event) ON (e.user_id, e.evidence_count);

CREATE INDEX fact_user_evidence IF NOT EXISTS
FOR (f:Fact) ON (f.user_id, f.evidence_count);

// ─────────────────────────────────────────────────────────────────
// EXTRACTION SOURCE INDEXES — provenance lookup
// ─────────────────────────────────────────────────────────────────

CREATE INDEX extraction_source_user_project IF NOT EXISTS
FOR (s:ExtractionSource) ON (s.user_id, s.project_id);

CREATE INDEX extraction_source_user_source IF NOT EXISTS
FOR (s:ExtractionSource) ON (s.user_id, s.source_type, s.source_id);

// ─────────────────────────────────────────────────────────────────
// VECTOR INDEXES — per-embedding-dimension semantic search
//
// One index per supported dimension. KSA §3.4.B documents the four
// dimensions Track 2 supports:
//   384  — small models (e.g. all-MiniLM-L6-v2)
//   1024 — medium (bge-m3, voyage-3, cohere-embed-v3)
//   1536 — large (text-embedding-3-small)
//   3072 — extra-large (text-embedding-3-large)
//
// Cosine similarity for all four. Vector indexes can ONLY be
// created with `IF NOT EXISTS` since Neo4j 5.18+; earlier
// versions had no idempotent form.
// ─────────────────────────────────────────────────────────────────

CREATE VECTOR INDEX entity_embeddings_384 IF NOT EXISTS
FOR (e:Entity) ON (e.embedding_384)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX entity_embeddings_1024 IF NOT EXISTS
FOR (e:Entity) ON (e.embedding_1024)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX entity_embeddings_1536 IF NOT EXISTS
FOR (e:Entity) ON (e.embedding_1536)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX entity_embeddings_3072 IF NOT EXISTS
FOR (e:Entity) ON (e.embedding_3072)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 3072,
    `vector.similarity_function`: 'cosine'
  }
};

// Event embeddings — only the 1024-dim variant in Track 2 because
// the event extractor uses bge-m3 by default. Other dimensions
// can be added later if needed.

CREATE VECTOR INDEX event_embeddings_1024 IF NOT EXISTS
FOR (e:Event) ON (e.embedding_1024)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};

// ─────────────────────────────────────────────────────────────────
// K18.3 :Passage — L3 semantic-search surface.
//
// Holds the raw chunked text excerpted from source_type-scoped
// inputs (chapter chunks, project summary chunks, long bio chunks).
// Populated by a future ingestion pipeline — this commit ships the
// target schema + repo + selector so the code path is live, but
// the nodes stay empty until ingestion lands.
//
// `is_hub` flags chunks whose source is an L1 summary or long
// character bio. The K18.3 selector applies a penalty to these so
// specific-entity queries don't return the whole summary instead
// of the specific detail (ContextHub lesson L-CH-03).
// ─────────────────────────────────────────────────────────────────

CREATE CONSTRAINT passage_id_unique IF NOT EXISTS
FOR (p:Passage) REQUIRE p.id IS UNIQUE;

CREATE INDEX passage_user_project IF NOT EXISTS
FOR (p:Passage) ON (p.user_id, p.project_id);

CREATE INDEX passage_user_source IF NOT EXISTS
FOR (p:Passage) ON (p.user_id, p.source_type, p.source_id);

CREATE VECTOR INDEX passage_embeddings_384 IF NOT EXISTS
FOR (p:Passage) ON (p.embedding_384)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 384,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX passage_embeddings_1024 IF NOT EXISTS
FOR (p:Passage) ON (p.embedding_1024)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1024,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX passage_embeddings_1536 IF NOT EXISTS
FOR (p:Passage) ON (p.embedding_1536)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 1536,
    `vector.similarity_function`: 'cosine'
  }
};

CREATE VECTOR INDEX passage_embeddings_3072 IF NOT EXISTS
FOR (p:Passage) ON (p.embedding_3072)
OPTIONS {
  indexConfig: {
    `vector.dimensions`: 3072,
    `vector.similarity_function`: 'cosine'
  }
};
