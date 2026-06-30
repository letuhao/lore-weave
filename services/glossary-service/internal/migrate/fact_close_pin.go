package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpFactClosePin — chain step 0049 (close_fact, spec §12.3.2). Adds an EXPLICIT valid-time
// close to the bi-temporal fact core: a user/consumer can declare that a fact's value stopped
// holding at a chosen ordinal even when no successor exists (the open last-in-chain fact that
// maintain_chain alone can only leave open).
//
// THE SINGLE-WRITER INVARIANT, PRESERVED (§12.3.3 LOCKED): maintain_chain stays the only thing
// that DERIVES valid_to from chain order. A pinned close is NOT a competing deriver — it is an
// authored INPUT that maintain_chain must respect. The new `valid_to_pinned` flag marks a fact
// whose valid_to was set by an explicit close_fact; maintain_chain skips it (never recomputes a
// pinned valid_to back to the next-survivor / NULL), so the manual close is stable across every
// subsequent append/retract that re-runs the chain. Unpinned facts derive exactly as before.
//
// Semantics of a pinned close on fact F (entity, attr, [from, NULL) open):
//   - close_fact(F, N) → F becomes [from, N) with valid_to_pinned = true (N > from enforced by
//     entity_facts_interval_chk). The attr has NO current value after N (until a later append at
//     M ≥ N opens a fresh [M, …) — the gap [N, M) is "value absent", which is the point).
//   - A later append at M > N: maintain_chain leaves F's pinned valid_to = N (skipped); the new
//     fact opens. A later append at M between (from, N): edge case — the pin wins (the user said
//     it ended at N); maintain_chain does not move it. (Documented; manual close is authoritative.)
//
// Forward-only, idempotent (ADD COLUMN IF NOT EXISTS + CREATE OR REPLACE FUNCTION), execGuarded.
// maintain_chain is re-defined here (not edited in 0045) because 0045 is ledger-applied already.
func UpFactClosePin(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "fact-close-pin", `
		ALTER TABLE entity_facts
		  ADD COLUMN IF NOT EXISTS valid_to_pinned boolean NOT NULL DEFAULT false;

		-- maintain_chain, now pin-aware: a pinned (explicitly-closed) fact's valid_to is an
		-- authored value the derivation must NOT overwrite. Everything else is identical to 0045.
		CREATE OR REPLACE FUNCTION maintain_chain(p_entity uuid, p_attr text)
		RETURNS void
		LANGUAGE sql
		AS $fn$
		  UPDATE entity_facts ef
		    SET valid_to_ordinal = (
		      SELECT min(o.valid_from_ordinal)
		      FROM entity_facts o
		      WHERE o.entity_id = ef.entity_id
		        AND o.attr_or_predicate = ef.attr_or_predicate
		        AND o.fact_kind = ef.fact_kind
		        AND o.cardinality = 'single'
		        AND o.invalidated_at IS NULL
		        AND o.valid_from_ordinal > ef.valid_from_ordinal
		    )
		    WHERE ef.entity_id = p_entity
		      AND ef.attr_or_predicate = p_attr
		      AND ef.cardinality = 'single'
		      AND ef.invalidated_at IS NULL
		      AND ef.valid_to_pinned = false   -- never recompute an explicitly-closed (pinned) fact
		      AND ef.valid_to_ordinal IS DISTINCT FROM (
		        SELECT min(o.valid_from_ordinal)
		        FROM entity_facts o
		        WHERE o.entity_id = ef.entity_id
		          AND o.attr_or_predicate = ef.attr_or_predicate
		          AND o.fact_kind = ef.fact_kind
		          AND o.cardinality = 'single'
		          AND o.invalidated_at IS NULL
		          AND o.valid_from_ordinal > ef.valid_from_ordinal
		      );
		$fn$;`)
}
