package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// entityFactsOriginSQL — chain step 0066 (plan T37c / SPEC §4.2b). Records WHO authored a
// fact, so a producer can retract its own claims without touching anyone else's.
//
// ── THE DEFECT THIS PREVENTS, MEASURED BEFORE IT SHIPPED ─────────────────────────────────
// T37 gave roles TWO producers: the studio (an author declaring a tie directly) and planforge
// (the roles a plan implies). §4.2b noted that the plan-time half owes a retraction path — a
// role appended when a plan was designed outlives the plan that justified it, and an as-of
// read would then hand the canon guard a role the book abandoned.
//
// Building that close revealed the problem. `entity_facts` had **no authorship column at
// all**: both producers write `fact_kind='relation'` with `source_episode_id = NULL`, and
// nothing else distinguishes them. So "close the roles this plan no longer implies" would
// have closed **the author's own declarations** too — silently erasing what a human
// deliberately said, on a plan revision they may not even associate with it. That is worse
// than the staleness it was meant to fix: a stale role is wrong, an erased one is gone.
//
// ── WHY NO CHECK CONSTRAINT ON THE VALUE ─────────────────────────────────────────────────
// The same reasoning `0064_entity_facts_status_kind` records for `life_status`: pinning a
// second enum in SQL creates a vocabulary that must be migrated every time a producer is
// added, and extraction is an obvious future third. The closed set is enforced where it can
// fail LOUDLY and cheaply instead — the Go handler rejects an unknown origin with 400, and
// the KAL contract declares the enum. A bad value never reaches this column.
//
// ── NULL IS 'UNKNOWN', AND THAT IS DELIBERATE ────────────────────────────────────────────
// Every fact written before this step has NULL. Backfilling them to a guess would be an
// authorship claim nobody made, and the close path is written to treat NULL as *not mine* —
// so a legacy fact is never retracted by a producer that cannot prove it wrote it. Facts are
// only ever closed by a producer that recognises its own mark.
const entityFactsOriginSQL = `
ALTER TABLE entity_facts ADD COLUMN IF NOT EXISTS origin TEXT
`

// entityFactsOriginIndexSQL — the close path's access pattern is
// "my open facts for this book", which without an index is a scan of every fact the book has.
// Partial on the open interval because a closed fact is never a retraction candidate, which
// keeps the index proportional to live facts rather than to history.
const entityFactsOriginIndexSQL = `
CREATE INDEX IF NOT EXISTS entity_facts_origin_open_idx
  ON entity_facts (book_id, origin)
  WHERE valid_to_ordinal IS NULL AND invalidated_at IS NULL
`

// UpEntityFactsOrigin applies chain step 0066. Additive + idempotent, routed through
// execGuarded like every other step (the migration advisory lock — concurrent startup is an
// acknowledged scenario here).
func UpEntityFactsOrigin(ctx context.Context, pool *pgxpool.Pool) error {
	if err := execGuarded(ctx, pool, "entity-facts-origin", entityFactsOriginSQL); err != nil {
		return err
	}
	return execGuarded(ctx, pool, "entity-facts-origin-idx", entityFactsOriginIndexSQL)
}
