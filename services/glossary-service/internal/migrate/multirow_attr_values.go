package migrate

import (
	"context"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/textnorm"
)

// UpMultirowAttrValues — chain step 0035 (D-GLOSSARY-MULTIROW-ATTR-VALUES, slice 1).
//
// Adds the per-item child table for list-valued glossary attributes so a list element
// can carry its OWN confidence / status (tombstone) / source-chapter provenance, instead
// of the whole list sharing one row-level marker. `entity_attribute_values.original_value`
// stays the SSOT for the ~15 existing readers — it becomes a write-synced denormalized
// cache of the ACTIVE items (rebuilt by api.rebuildItemsCache after any item mutation).
//
// Two parts, both idempotent:
//  1. DDL (execGuarded under the migration advisory lock): the additive child table +
//     UNIQUE(attr_value_id, item_norm) (the per-item dedup key) + the FK lookup index.
//  2. Go backfill: for every EAV whose original_value is a JSON-array list, materialize one
//     child row per element (item_norm via the SHARED textnorm.Normalize so the child rows
//     dedup identically to the runtime append path). Scalars get ZERO items — original_value
//     stays their sole authority. ON CONFLICT DO NOTHING ⇒ a re-run (or a partial-failure
//     retry) is a no-op. No original_value is rewritten (the cache already equals the active
//     projection on day 1).
func UpMultirowAttrValues(ctx context.Context, pool *pgxpool.Pool) error {
	if err := execGuarded(ctx, pool, "multirow-attr-values", `
		CREATE TABLE IF NOT EXISTS entity_attribute_value_items (
		  item_id           uuid PRIMARY KEY DEFAULT uuidv7(),
		  attr_value_id     uuid NOT NULL REFERENCES entity_attribute_values(attr_value_id) ON DELETE CASCADE,
		  item_value        text NOT NULL,
		  item_norm         text NOT NULL,
		  sort_order        int  NOT NULL DEFAULT 0,
		  confidence        text NOT NULL DEFAULT 'machine',
		  status            text NOT NULL DEFAULT 'active',
		  source_chapter_id uuid,
		  created_at        timestamptz NOT NULL DEFAULT now(),
		  updated_at        timestamptz NOT NULL DEFAULT now(),
		  UNIQUE (attr_value_id, item_norm)
		);
		CREATE INDEX IF NOT EXISTS idx_eavi_attr_value ON entity_attribute_value_items(attr_value_id);
		CREATE INDEX IF NOT EXISTS idx_eavi_active
		  ON entity_attribute_value_items(attr_value_id, sort_order)
		  WHERE status = 'active';`); err != nil {
		return err
	}
	return backfillAttrValueItems(ctx, pool)
}

// backfillAttrValueItems materializes child rows for every existing list-valued EAV.
// Reads the whole set into memory first (the glossary attribute set is bounded), then
// inserts per item. Idempotent via ON CONFLICT (attr_value_id, item_norm) DO NOTHING.
func backfillAttrValueItems(ctx context.Context, pool *pgxpool.Pool) error {
	type row struct {
		attrValueID string
		value       string
		confidence  string
	}
	rows, err := pool.Query(ctx, `
		SELECT attr_value_id, original_value, confidence
		FROM entity_attribute_values
		WHERE original_value LIKE '[%'`)
	if err != nil {
		return fmt.Errorf("multirow backfill scan: %w", err)
	}
	var list []row
	for rows.Next() {
		var r row
		if err := rows.Scan(&r.attrValueID, &r.value, &r.confidence); err != nil {
			rows.Close()
			return fmt.Errorf("multirow backfill row: %w", err)
		}
		list = append(list, r)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return fmt.Errorf("multirow backfill iterate: %w", err)
	}

	for _, r := range list {
		items := textnorm.ParseList(r.value)
		if len(items) == 0 {
			continue
		}
		batch := &pgx.Batch{}
		seen := make(map[string]bool, len(items))
		order := 0
		for _, it := range items {
			n := textnorm.Normalize(it)
			if n == "" || seen[n] {
				continue // mirror runtime dedup; UNIQUE backstops anyway
			}
			seen[n] = true
			batch.Queue(`
				INSERT INTO entity_attribute_value_items
				  (attr_value_id, item_value, item_norm, sort_order, confidence, status)
				VALUES ($1, $2, $3, $4, $5, 'active')
				ON CONFLICT (attr_value_id, item_norm) DO NOTHING`,
				r.attrValueID, it, n, order, r.confidence)
			order++
		}
		if batch.Len() == 0 {
			continue
		}
		br := pool.SendBatch(ctx, batch)
		execErr := func() error {
			for i := 0; i < batch.Len(); i++ {
				if _, err := br.Exec(); err != nil {
					return err
				}
			}
			return nil
		}()
		if cerr := br.Close(); cerr != nil && execErr == nil {
			execErr = cerr
		}
		if execErr != nil {
			return fmt.Errorf("multirow backfill insert (attr_value=%s): %w", r.attrValueID, execErr)
		}
	}
	return nil
}
