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
// Idempotent + re-run-safe (ledger.go documents a manual re-run after clearing the row as
// supported): every statement is SCOPED TO COLD-START SEEDS via `source_episode_id IS NULL`.
// The cold-start seed (0046) is the ONLY producer of `attribute`-kind name/aliases facts —
// the F1d runtime writeback (emitChapterFacts) already emits names as `name` and aliases as
// `alias` and cites a real episode, so it can NEVER be swept by a re-run of this one-shot
// reconciliation. (Without the episode guard a re-run after runtime facts accumulate would be
// a one-shot conversion in name only — the comment would overstate idempotency; the guard
// makes "cold-start only" enforced by code, not just by the kind filter.)
func UpBitemporalNames(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "bitemporal-names", `
		-- name: attribute → name kind, in place (chain preserved). Cold-start seeds only.
		UPDATE entity_facts
		   SET fact_kind = 'name'
		 WHERE fact_kind = 'attribute' AND attr_or_predicate = 'name'
		   AND source_episode_id IS NULL;

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
		  AND ef.source_episode_id IS NULL
		  AND ef.invalidated_at IS NULL AND coalesce(btrim(elem), '') <> ''
		ON CONFLICT DO NOTHING;

		-- retire the original JSON aliases attribute fact (invalidate-not-delete)
		UPDATE entity_facts
		   SET invalidated_at = now(), invalidated_reason = 'converted_to_alias_facts'
		 WHERE fact_kind = 'attribute' AND attr_or_predicate = 'aliases'
		   AND source_episode_id IS NULL
		   AND invalidated_at IS NULL;`)
}
