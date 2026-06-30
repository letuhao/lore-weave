package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpBitemporalNames — chain step 0048 (F1g, spec §12.4.3). Names + aliases become
// FIRST-CLASS bi-temporal fact kinds instead of generic `attribute` facts, so a
// rename develops over story-time (as-of-name = spoiler-free names, §6B) and aliases
// are individually queryable. This RECONCILES the cold-start/F1d representation
// (the old `D-TK-F1G-NAME-RECONCILE`): the seed (0046) + the writeback (F1d) opened
// name/aliases as `fact_kind='attribute'`; this converts them once.
//
//   - name: `attribute`→`name` IN PLACE (preserves the whole supersession chain —
//     valid_from/to untouched; only the kind label changes). The natural-key unique
//     index can't collide (value_hash/valid_from/source_episode unchanged, and no
//     `name`-kind facts exist yet at first run).
//   - aliases: the single `attribute` JSON-array fact is SPLIT into one `alias`
//     (cardinality='multi') fact per element, preserving the interval + provenance;
//     the original JSON `attribute` fact is then invalidate-not-deleted (audit kept).
//     Multi-valued alias facts coexist (maintain_chain leaves them alone) and are the
//     resolver's across-time alias set.
//
// Idempotent: the name UPDATE is a no-op once converted; the alias split is
// ON CONFLICT DO NOTHING + the source invalidation is guarded on the still-active
// `attribute` rows. Forward-only, execGuarded.
func UpBitemporalNames(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "bitemporal-names", `
		-- name: attribute → name kind, in place (chain preserved)
		UPDATE entity_facts
		   SET fact_kind = 'name'
		 WHERE fact_kind = 'attribute' AND attr_or_predicate = 'name';

		-- aliases: split the JSON-array attribute fact into per-element multi alias facts
		INSERT INTO entity_facts
		  (book_id, entity_id, fact_kind, attr_or_predicate, value, valid_from_ordinal,
		   valid_to_ordinal, cardinality, source_episode_id, created_at)
		SELECT ef.book_id, ef.entity_id, 'alias', 'aliases', elem, ef.valid_from_ordinal,
		       ef.valid_to_ordinal, 'multi', ef.source_episode_id, ef.created_at
		FROM entity_facts ef
		CROSS JOIN LATERAL jsonb_array_elements_text(
		  CASE WHEN btrim(ef.value) ~ '^\[' THEN ef.value::jsonb ELSE '[]'::jsonb END
		) AS elem
		WHERE ef.fact_kind = 'attribute' AND ef.attr_or_predicate = 'aliases'
		  AND ef.invalidated_at IS NULL AND coalesce(btrim(elem), '') <> ''
		ON CONFLICT DO NOTHING;

		-- retire the original JSON aliases attribute fact (invalidate-not-delete)
		UPDATE entity_facts
		   SET invalidated_at = now(), invalidated_reason = 'converted_to_alias_facts'
		 WHERE fact_kind = 'attribute' AND attr_or_predicate = 'aliases'
		   AND invalidated_at IS NULL;`)
}
