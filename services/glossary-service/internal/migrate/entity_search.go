package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// glossarySearchSQL adds the raw lexical-search infrastructure for the glossary
// entity list (D-GLOSSARY-RAW-SEARCH-BE / plan 2026-06-14-glossary-list-overhaul.md).
//
// Mirrors the chapter raw-search (book-service search.go): ILIKE exact-substring
// is the PRIMARY matcher (CJK-safe — catches short CJK runs the trigram `%`
// operator misses at the default similarity threshold), pg_trgm `similarity()`
// only ranks. Both legs are accelerated by GIN trigram indexes.
//
// Why trigram and not the existing search_vector: search_vector (idx_ge_search
// _vector) is built with the 'simple' FTS config which does NOT segment CJK
// (no whitespace → the whole run is one token → substring search impossible).
// So for a Chinese/Japanese novel glossary the FTS index can't answer a
// substring query; trigram is the right matcher (DESIGN REVIEW §3.5).
//
// Idempotent: CREATE EXTENSION / OR REPLACE / INDEX IF NOT EXISTS throughout.
// Runs through execGuarded, so the whole batch holds the migration advisory lock
// — no concurrent migration can be creating these (or the base-schema) objects at
// the same time, so the cross-table index creation can't deadlock against another
// package's migrate.Up on a shared test DB.
const glossarySearchSQL = `
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- IMMUTABLE wrapper so the aliases expression can be indexed. array_to_string
-- over a text[] is treated as non-immutable by Postgres 18 in a generated-column
-- / index-expression context (see knowledgeMemorySQL's note on search_vector);
-- an explicit IMMUTABLE SQL function sidesteps that so the GIN index can build.
-- COALESCE keeps it total (cached_aliases is NOT NULL today, but an index
-- expression must never error).
CREATE OR REPLACE FUNCTION glossary_aliases_text(p_aliases TEXT[])
RETURNS TEXT
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT array_to_string(COALESCE(p_aliases, ARRAY[]::TEXT[]), ' ')
$$;

-- GIN trigram indexes powering both legs (ILIKE substring + % similarity) of the
-- raw search over the denormalised entity row (cached_name / cached_aliases,
-- maintained by recalculate_entity_snapshot).
CREATE INDEX IF NOT EXISTS idx_ge_cached_name_trgm
  ON glossary_entities USING gin (cached_name gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_ge_cached_aliases_trgm
  ON glossary_entities USING gin (glossary_aliases_text(cached_aliases) gin_trgm_ops);

-- Display-language translated names also need a trigram index so a raw search in
-- the user's display language doesn't degrade to a sequential scan.
CREATE INDEX IF NOT EXISTS idx_attr_trans_value_trgm
  ON attribute_translations USING gin (value gin_trgm_ops);
`

// UpGlossarySearch installs pg_trgm + the GIN trigram indexes + the immutable
// aliases helper used by the raw entity search. Idempotent.
func UpGlossarySearch(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "glossary-search", glossarySearchSQL)
}
