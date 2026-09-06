package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// entityFactsStatusKindSQL — widen entity_facts_kind_chk for liveness-as-a-fact (plan T32 / D1).
//
// ── WHY 'status' ─────────────────────────────────────────────────────────────────────────
// D1: *"Liveness becomes a fact, not a column."* `fact_kind='status'`,
// `attr_or_predicate='life_status'`, over a small closed vocabulary. Then *"is X alive as of
// N"* is **the same query as every other as-of read** — no new store, no new mechanism — and
// it inherits evidence, supersession, invalidation and the episode citation for free.
//
// The column form was tried and measured, and that measurement is the argument:
// `glossary_entities.alive` is **7290 true / 0 false**, while `:EntityStatus` — which IS
// modelled correctly, as a transition at a reading position — sits on the wrong side of the
// identity seam at **0 of 21 reachable**. Death is a story event at a position, and a
// bitemporal fact is exactly what that is.
//
// ── WHY A NEW STEP AND NOT AN EDIT ───────────────────────────────────────────────────────
// The closed set is declared inside `entity_facts.go`'s `CREATE TABLE IF NOT EXISTS`. Editing
// it would be invisible to every already-migrated database — `IF NOT EXISTS` skips the whole
// statement, so the constraint would stay narrow there while fresh databases got the wide one.
// **That divergence is the bug this repo has already recorded** (a CHECK widened in one
// historical block and not the others). A separate DROP/ADD converges both: fresh databases
// create the narrow constraint and immediately widen it; migrated ones widen in place.
//
// `DROP CONSTRAINT IF EXISTS` then `ADD` rather than a conditional add, because ADD alone
// fails on a database that already has the constraint under the same name, and this chain step
// must be safe to re-run — `ApplyOnce` guarantees it runs once per database, not once ever
// across a restore-from-backup.
//
// ── WHAT THIS DOES NOT DO ────────────────────────────────────────────────────────────────
// It does not constrain the VALUE vocabulary (`life_status`'s allowed values). D1 says that
// vocabulary should *"seed the ONT existence ladder rather than invent a parallel enum"*, so
// pinning a second enum here in SQL would create the very duplication that decision refuses.
const entityFactsStatusKindSQL = `
ALTER TABLE entity_facts DROP CONSTRAINT IF EXISTS entity_facts_kind_chk;
ALTER TABLE entity_facts ADD CONSTRAINT entity_facts_kind_chk
  CHECK (fact_kind IN ('attribute','relation','event','name','alias','status'));
`

// UpEntityFactsStatusKind widens the fact-kind vocabulary to admit 'status' (T32 / D1).
func UpEntityFactsStatusKind(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "entity-facts-status-kind", entityFactsStatusKindSQL)
}
