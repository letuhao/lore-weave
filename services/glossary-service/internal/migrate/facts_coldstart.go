package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpFactsColdStart — chain step 0046. The cold-start seed (spec §12.5.4 / D5 / dec-5):
// every existing flat EAV value becomes ONE open bi-temporal fact so the new SSOT is
// non-empty on day one AND the derived "current" projection is byte-identical to the
// pre-migration flat store.
//
// Each single-valued EAV row (entity_attribute_values) seeds an entity_facts row:
//   - value            = the entity's CURRENT flat value (eav.original_value) — NOT a
//                        first-seen value; the projection must equal today's overwritten
//                        current value or "consumers keep working unchanged" is false (D5).
//   - valid_from_ordinal = -1, a synthetic "before-history" LOWER BOUND (no history
//                        backfill — append-only tolerates it; dec-5). -1 is strictly
//                        below every real chapter ordinal (chapter_index is 0-based, so
//                        chapter 0 exists; -1 is the same "before-all" sentinel the
//                        canon-at-chapter window uses), so a real ch.0 Path-A append
//                        NEVER collides with a seed fact at the same valid_from.
//                        valid_to_ordinal = NULL (open).
//   - source_episode_id = NULL (no episode for a migration seed; the natural key
//                        coalesces NULL → nil UUID so one fact per (entity, attr, value)).
//   - attr_or_predicate = the attribute CODE (book_attributes.code via attr_def_id), the
//                        same key the fact pipeline + refreshEAVProjection use.
//
// Because exactly one open fact per (entity, attr) carries the current value,
// maintain_chain leaves it open and the projection re-derived from facts equals the
// flat EAV for every entity. The MIGRATION TEST that locks this (projection(entity) ==
// flat_eav(entity) for all entities) lives in the api package's facts test.
//
// Idempotent: ON CONFLICT DO NOTHING on the natural key, so re-running seeds nothing.
// Skips empty values and soft-deleted entities. Forward-only data migration routed
// through execGuarded like every chain step. Multi-valued list attrs (the items child
// table) are a richer structured-fact follow-up (D9) — the single-valued EAV rows are
// the projection the backward-compat readers depend on.
//
// NOTE (F1g reconciliation debt, tracked as D-TK-F1G-NAME-RECONCILE): every EAV row —
// INCLUDING 'name' and 'aliases' — is seeded as a single-valued fact_kind='attribute'
// fact, because the projection==flat_eav guarantee (D5) is defined over the EAV and the
// projection reader is attribute-kind. F1g (§12.4.3) will introduce names/aliases as
// fact_kind IN ('name','alias') multi-valued bi-temporal facts; when it lands it MUST
// supersede (invalidate) these cold-start attribute-facts for name/aliases so an entity
// does not carry two representations. maintain_chain keeps them as separate chains
// (it matches fact_kind), so there is no corruption in the interim — only debt.
func UpFactsColdStart(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "facts-cold-start", `
		INSERT INTO entity_facts
		  (book_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal, cardinality)
		SELECT ge.book_id, eav.entity_id, 'attribute', ba.code, eav.original_value, -1, 'single'
		FROM entity_attribute_values eav
		JOIN glossary_entities ge ON ge.entity_id = eav.entity_id
		JOIN book_attributes ba   ON ba.attr_id = eav.attr_def_id
		WHERE coalesce(eav.original_value, '') <> ''
		  AND ge.deleted_at IS NULL
		ON CONFLICT DO NOTHING;`)
}
