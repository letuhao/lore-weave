package migrate

// D-GLOSSARY-ATTR-LOOKUP-SEQSCAN — index the attribute-definition lookup.
//
// Ten queries across four handlers (extraction, canon_at_chapter, enrichment,
// pipeline_read_tools) resolve an attribute definition with a correlated subquery
// keyed on (kind_id, code) and NO book_id:
//
//	attr_def_id = (SELECT ba.attr_id FROM book_attributes ba
//	               JOIN book_genres g ON g.genre_id = ba.genre_id
//	               WHERE ba.kind_id = e.kind_id AND ba.code = 'name'
//	               ORDER BY (g.code = 'universal') DESC LIMIT 1)
//
// Every existing book_attributes index leads with book_id, so none could serve that
// predicate: Postgres seq-scanned all 441,848 rows on EVERY evaluation — and because
// the subquery sits inside a hash-join condition, that is once per candidate pair,
// not once per entity.
//
// Measured on a live 3,187-entity book:
//
//	before: /internal/books/{id}/known-entities = 56s, 71.9M shared buffer hits
//	after : 0.05s
//
// The cost was INDEPENDENT of the limit parameter, because the GROUP BY / HAVING
// aggregate runs over every row before LIMIT applies — so paging the read made it
// worse, not better.
//
// The latency was not merely slow, it was silent data loss of a kind: knowledge-service's
// glossary client had a 0.5s budget, so on any real-sized book the extraction anchor
// pre-load timed out, logged "skipping anchor pre-load (extractor will mint-on-no-match)",
// and the extractor minted duplicate entities a human then had to merge back by hand.
// The failure was size-gated, which is exactly why small books looked healthy.
//
// Why this is a NEW ledger step and not a line added to 0024 (which creates
// book_attributes and its sibling indexes): the chain is applied ONCE per database and
// recorded in schema_migrations. Appending DDL to an already-applied step is a no-op on
// every existing deployment and only takes effect on a fresh DB — the failure mode this
// file's own placement nearly shipped with.

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

const attrLookupIndexSQL = `
CREATE INDEX IF NOT EXISTS idx_ba_kind_code ON book_attributes(kind_id, code);
`

// UpAttrLookupIndex adds the (kind_id, code) index the correlated attribute-definition
// lookup needs. Idempotent.
func UpAttrLookupIndex(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "attr-lookup-index", attrLookupIndexSQL)
}
