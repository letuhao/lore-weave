package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpMaintainChain — chain step 0045. The SINGLE writer of entity_facts.valid_to_ordinal
// (spec §12.3.3, LOCKED). One routine, invoked at three entry points:
//
//   - §12.3.2 ordinal-aware interval-split insert (Path A close-prior),
//   - §12.3.3 retract chain re-stitch (Path B step B.3.5),
//   - §12.4.1 merge per-attribute chain reconciliation,
//
// are THE SAME routine, not three algorithms. Making maintain_chain the only
// thing that writes valid_to is what prevents the "second competing writer" trap
// the spec calls out, and what makes retract auto-restitch and backfill correct.
//
// Semantics: for a (entity, attr) single-valued chain, set each CURRENT-belief
// fact's valid_to_ordinal = the next STRICTLY-GREATER valid_from_ordinal in the
// chain (NULL => open, the latest). "Current belief" = invalidated_at IS NULL, so
// a retracted/superseded-by-belief fact is excluded and its predecessor
// automatically re-extends to the next survivor — restitch for free. Because the
// derivation is by sorted valid_from, it is correct under OUT-OF-ORDER arrival
// (Q5 backfill, ATOM parallel-merge): a back-filled ch.300 fact lands between
// ch.1 and ch.500 by ordinal, never closing the still-correct later fact (the A2
// bug the KG single_active datetime() close has).
//
// Why STRICTLY-GREATER (not lead()): two facts sharing a valid_from (an overlap
// from two merge sources, §12.4.1 step 3) must NOT produce a zero-length
// [v,v) interval (which violates entity_facts_interval_chk). Strictly-greater
// gives both tied rows the same next-bound => a real (overlapping) interval the
// merge tiebreak then resolves by invalidate-not-delete; it never crashes the
// CHECK. A clean chain (distinct valid_from) gets exact contiguous half-open
// intervals.
//
// Scope: cardinality='single' only. Multi-valued facts (aliases/tags/appears_in,
// §12.5.3/D9) coexist and do NOT supersede each other — they are closed only by
// explicit retract, never by chain maintenance.
//
// Idempotent (re-running yields the same valid_to), side-effect-free beyond the
// chain, IMMUTABLE-style derivation — so it is safe to call after every append,
// every retract, and inside the merge reconcile, and to wire as an AFTER trigger
// later without creating a second writer.
func UpMaintainChain(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "maintain-chain", `
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
