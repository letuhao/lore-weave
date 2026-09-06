package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// entityFactsAsOfIndexSQL — the covering index for the BOOK-WIDE as-of read (plan T9 / D9).
//
// `state@as_of` (api/state_handler.go) asks one question per drafting run: at story position
// N, what is every entity's current value for every single-valued attribute? Before this
// index the only usable path was `idx_entity_facts_book` (book_id alone), so the read scanned
// every fact the book ever wrote and discarded the ones whose interval does not cover N —
// measured at **17 254 of 26 192 rows** on the largest real book, and 1.06 M of 1.08 M at the
// 4 000-chapter ceiling.
//
// ── WHY THIS DEFINITION AND NOT THE ONE THE PLAN NAMED ───────────────────────────────────
// The plan specified the key columns only, with the stated goal *"removes the sort … which
// grows linearly with book length and spills work_mem"*. Both halves of that were measured
// and both are wrong, so shipping it literally would have been a 140 MB index that buys 1.4×
// while its stated purpose went unmet:
//
//   - **The sort does not grow with book length.** At any single position exactly one interval
//     per (entity, attribute) can match, so the sort input is cast size × attributes — not
//     chapter count. Measured **2 175 kB at 108 k facts and 2 175 kB at 1.08 M facts**. (It
//     can still spill, but on a book with a very large CAST, which is a different axis.)
//   - **The key-only index does not remove the sort either.** The read joins
//     `glossary_entities` for the recycle-bin filter, and a join above the scan destroys the
//     index ordering, so the plan keeps its `Sort` node whichever index it picks.
//
// What actually costs time is the heap: ~558 k random fetches to read `value` and `fact_kind`
// for candidate rows. INCLUDEing them makes the scan **index-only**, which is the whole win.
// Measured at the ceiling (2.16 M rows, 5 runs, median):
//
//	no index      281.1 ms   —         Index Scan on idx_entity_facts_book + Sort
//	key-only      197.6 ms   140 MB    Index Scan + Sort  (the plan's literal definition)
//	this index     78.9 ms   216 MB    Index ONLY Scan    (3.6× vs no index)
//
// The cost is honest and stated: +216 MB against a 422 MB table, because `value` is duplicated
// into the index. That is the price of not touching the heap, and it is the reason this is a
// PARTIAL index — `invalidated_at IS NULL AND cardinality = 'single'` is exactly the slice the
// as-of read wants, so superseded beliefs and multi-valued facts never enter it.
//
// ── WHY A PLAIN BUILD, INSIDE THE LEDGER STEP ────────────────────────────────────────────
// `CREATE INDEX CONCURRENTLY` **cannot run here at all**: the chain runner wraps every step in
// `pool.Begin` + `pg_advisory_xact_lock` (migrate.go, execGuarded), and CONCURRENTLY is
// forbidden inside a transaction block. That is a hard constraint, not a preference.
//
// So this takes the write-blocking build, with the window measured rather than assumed:
// **2.4–2.8 s at 2.16 M facts** (`CREATE INDEX CONCURRENTLY` was 3.2 s for comparison — it is
// not faster, it is only non-blocking). 2.16 M facts is ~45× the entire current corpus. Reads
// are unaffected throughout; only writes to `entity_facts` queue.
//
// An operator who cannot accept even that window has an escape hatch that needs no code
// change: build the index CONCURRENTLY out of band BEFORE upgrading. `IF NOT EXISTS` then makes
// this step a no-op that records itself in the ledger. The out-of-band route is deliberately
// NOT the default — a migration whose success depends on someone remembering to run something
// first is a migration that silently does not exist on every deployment where they forgot.
//
// Shipped as a NEW ledger step (0062). Never edit an applied step: the ledger records it as
// run, so an edit reaches only databases that have not migrated yet and the two histories
// diverge silently.
const entityFactsAsOfIndexSQL = `
CREATE INDEX IF NOT EXISTS idx_entity_facts_book_asof
  ON entity_facts (book_id, entity_id, attr_or_predicate, valid_from_ordinal DESC)
  INCLUDE (valid_to_eff, value, fact_kind)
  WHERE invalidated_at IS NULL AND cardinality = 'single';
`

// UpEntityFactsAsOfIndex adds the covering index behind the book-wide `state@as_of` read.
// Idempotent (IF NOT EXISTS). See entityFactsAsOfIndexSQL for the measurements behind the
// definition and for the operator escape hatch on the build window.
func UpEntityFactsAsOfIndex(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "entity-facts-asof-index", entityFactsAsOfIndexSQL)
}
