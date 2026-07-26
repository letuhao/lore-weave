package api

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"

	"github.com/loreweave/glossary-service/internal/textnorm"
)

// Per-item list-attribute helpers (D-GLOSSARY-MULTIROW-ATTR-VALUES slice 1).
//
// A list-valued glossary attribute stores one child row per element in
// entity_attribute_value_items (each with its own confidence/status/source-chapter),
// and entity_attribute_values.original_value is kept as a write-synced denormalized
// cache of the ACTIVE items so the existing readers stay unchanged. rebuildItemsCache
// is the ONLY writer of that cache (INV-MR1).

// dedupNormalized returns items deduped by normalized value, dropping empties and
// preserving first-seen order — the same dedup the child UNIQUE(attr_value_id, item_norm)
// enforces, used up-front to decide whether there's anything meaningful to append.
func dedupNormalized(items []string) []string {
	seen := make(map[string]bool, len(items))
	out := make([]string, 0, len(items))
	for _, it := range items {
		n := textnorm.Normalize(it)
		if n == "" || seen[n] {
			continue
		}
		seen[n] = true
		out = append(out, it)
	}
	return out
}

// ensureItemsMaterialized lazily seeds the child-item rows from the EAV's current
// original_value the FIRST time a list value is touched per-item. A value first written
// as a scalar (createExtractedEntity) or by pre-multirow code has ZERO child rows, so a
// naive rebuildItemsCache would DROP it. This seeds those existing elements (preserving
// the row's confidence; provenance unknown ⇒ NULL source_chapter) so the subsequent
// append + cache rebuild keeps them. No-op once any item exists. Returns whether it
// seeded anything — the caller rebuilds the cache when seeded (even on a no-op append) so
// a legacy scalar canonicalizes to the active-item JSON array (INV-MR1), never diverging.
func ensureItemsMaterialized(ctx context.Context, q pgxRWQuerier, attrValueID uuid.UUID, existingValue, confidence string) (bool, error) {
	var n int
	if err := q.QueryRow(ctx, `
		SELECT count(*) FROM entity_attribute_value_items WHERE attr_value_id = $1
	`, attrValueID).Scan(&n); err != nil {
		return false, fmt.Errorf("items count: %w", err)
	}
	if n > 0 {
		return false, nil
	}
	seeded := false
	for idx, it := range dedupNormalized(parseListValue(existingValue)) {
		ct, err := q.Exec(ctx, `
			INSERT INTO entity_attribute_value_items
			  (attr_value_id, item_value, item_norm, sort_order, confidence, status)
			VALUES ($1, $2, $3, $4, $5, 'active')
			ON CONFLICT (attr_value_id, item_norm) DO NOTHING
		`, attrValueID, it, textnorm.Normalize(it), idx, confidence)
		if err != nil {
			return seeded, fmt.Errorf("seed item: %w", err)
		}
		if ct.RowsAffected() > 0 {
			seeded = true
		}
	}
	return seeded, nil
}

// appendListItems inserts each incoming element as an ACTIVE child item of attrValueID,
// deduped by item_norm (UNIQUE + ON CONFLICT DO NOTHING ⇒ idempotent). New items are
// appended after the current max sort_order. Returns how many rows were actually inserted
// (0 ⇒ every item already present). confidence='machine' (an extraction write); a human
// curation stamps 'verified' through the slice-2 writers.
func appendListItems(ctx context.Context, q pgxRWQuerier, attrValueID uuid.UUID, incoming []string, srcChapter *uuid.UUID) (int, error) {
	var base int
	if err := q.QueryRow(ctx, `
		SELECT COALESCE(MAX(sort_order)+1, 0) FROM entity_attribute_value_items WHERE attr_value_id = $1
	`, attrValueID).Scan(&base); err != nil {
		return 0, fmt.Errorf("items max sort: %w", err)
	}
	added := 0
	for _, it := range dedupNormalized(incoming) {
		ct, err := q.Exec(ctx, `
			INSERT INTO entity_attribute_value_items
			  (attr_value_id, item_value, item_norm, sort_order, confidence, status, source_chapter_id)
			VALUES ($1, $2, $3, $4, 'machine', 'active', $5)
			ON CONFLICT (attr_value_id, item_norm) DO NOTHING
		`, attrValueID, it, textnorm.Normalize(it), base+added, srcChapter)
		if err != nil {
			return 0, fmt.Errorf("insert item: %w", err)
		}
		if ct.RowsAffected() > 0 {
			added++
		}
	}
	return added, nil
}

// syncListItems keeps the per-item child rows in step with a "replace the value" writer
// (fill/overwrite/editor/apply-edit/restore) for a LIST value: it resolves the EAV's
// surrogate id, then replaces the item set from the just-written value. A SCALAR value
// (textnorm.IsList false) is a no-op — scalars carry zero items, original_value is their
// sole authority. Call AFTER the original_value write; rebuildItemsCache then canonicalizes
// original_value to the deduped active-item array (INV-MR1, no divergence).
func syncListItems(ctx context.Context, q pgxRWQuerier, entityID, defID uuid.UUID, serialized, confidence string, srcChapter *uuid.UUID) error {
	var avid uuid.UUID
	if err := q.QueryRow(ctx, `
		SELECT attr_value_id FROM entity_attribute_values WHERE entity_id = $1 AND attr_def_id = $2
	`, entityID, defID).Scan(&avid); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return nil // no EAV row → nothing to sync (caller writes it first on the real path)
		}
		return fmt.Errorf("resolve attr_value_id: %w", err)
	}
	return syncListItemsByID(ctx, q, avid, serialized, confidence, srcChapter)
}

// syncListItemsByID keeps the per-item child rows in step with a "replace the value" write,
// keyed by the EAV surrogate id. Routes to the item model when the value is a list OR the
// attribute is ALREADY item-managed (has child rows) — the latter catches a list attr being
// overwritten with a scalar value, which must still update the items (else a later append
// rebuilds from stale items, the slice-1 divergence). A genuine scalar attribute (no items,
// scalar value) is a no-op — original_value stays its sole authority.
func syncListItemsByID(ctx context.Context, q pgxRWQuerier, attrValueID uuid.UUID, serialized, confidence string, srcChapter *uuid.UUID) error {
	managed := textnorm.IsList(serialized)
	if !managed {
		var n int
		if err := q.QueryRow(ctx, `
			SELECT count(*) FROM entity_attribute_value_items WHERE attr_value_id = $1
		`, attrValueID).Scan(&n); err != nil {
			return fmt.Errorf("items managed check: %w", err)
		}
		managed = n > 0
	}
	if !managed {
		return nil
	}
	return replaceListItems(ctx, q, attrValueID, parseListValue(serialized), confidence, srcChapter)
}

// resyncEntityListItems rebuilds the per-item child rows for EVERY list-valued EAV of an
// entity from its current original_value (the restore path: a batched snapshot restore sets
// original_value directly, leaving the items stale). Items of pruned EAVs are already gone
// via the FK ON DELETE CASCADE. Scalars are skipped (LIKE '[%'). confidence marks the
// resulting items (restore ⇒ 'verified', human curation).
func resyncEntityListItems(ctx context.Context, q pgxRWQuerier, entityID uuid.UUID, confidence string) error {
	rows, err := q.Query(ctx, `
		SELECT attr_value_id, original_value FROM entity_attribute_values
		WHERE entity_id = $1 AND original_value LIKE '[%'
	`, entityID)
	if err != nil {
		return fmt.Errorf("resync scan: %w", err)
	}
	type row struct {
		id  uuid.UUID
		val string
	}
	var list []row
	for rows.Next() {
		var r row
		if err := rows.Scan(&r.id, &r.val); err != nil {
			rows.Close()
			return fmt.Errorf("resync row: %w", err)
		}
		list = append(list, r)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return fmt.Errorf("resync iterate: %w", err)
	}
	for _, r := range list {
		if err := replaceListItems(ctx, q, r.id, parseListValue(r.val), confidence, nil); err != nil {
			return err
		}
	}
	return nil
}

// replaceListItems sets the ACTIVE item set of a list-valued attribute to exactly `items`
// (deduped, in first-seen order) with the given confidence + provenance, then rebuilds the
// cache (INV-MR1). The whole prior item set is removed first — this is a "replace the list"
// write (extraction overwrite, editor/apply-edit/restore, merge-alias union). Callers gate it
// to LIST values (textnorm.IsList); a scalar attribute never gets items. srcChapter may be nil
// (human writes have no extraction provenance).
func replaceListItems(ctx context.Context, q pgxRWQuerier, attrValueID uuid.UUID, items []string, confidence string, srcChapter *uuid.UUID) error {
	if _, err := q.Exec(ctx, `
		DELETE FROM entity_attribute_value_items WHERE attr_value_id = $1
	`, attrValueID); err != nil {
		return fmt.Errorf("replace items clear: %w", err)
	}
	for idx, it := range dedupNormalized(items) {
		if _, err := q.Exec(ctx, `
			INSERT INTO entity_attribute_value_items
			  (attr_value_id, item_value, item_norm, sort_order, confidence, status, source_chapter_id)
			VALUES ($1, $2, $3, $4, $5, 'active', $6)
			ON CONFLICT (attr_value_id, item_norm) DO NOTHING
		`, attrValueID, it, textnorm.Normalize(it), idx, confidence, srcChapter); err != nil {
			return fmt.Errorf("replace items insert: %w", err)
		}
	}
	return rebuildItemsCache(ctx, q, attrValueID)
}

// rebuildItemsCache re-derives entity_attribute_values.original_value as the write-synced
// JSON array of the ACTIVE child items (ordered by sort_order, item_norm). The SINGLE writer
// of the list cache (INV-MR1). Only original_value is touched — original_language is owned by
// the value writers, never clobbered here. Zero active items ⇒ "[]"; because the cache holds
// only active items, tombstoning an item drops it from every reader for free.
func rebuildItemsCache(ctx context.Context, q pgxRWQuerier, attrValueID uuid.UUID) error {
	rows, err := q.Query(ctx, `
		SELECT item_value FROM entity_attribute_value_items
		WHERE attr_value_id = $1 AND status = 'active'
		ORDER BY sort_order, item_norm
	`, attrValueID)
	if err != nil {
		return fmt.Errorf("items cache scan: %w", err)
	}
	items := []string{}
	for rows.Next() {
		var v string
		if err := rows.Scan(&v); err != nil {
			rows.Close()
			return fmt.Errorf("items cache row: %w", err)
		}
		items = append(items, v)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return fmt.Errorf("items cache iterate: %w", err)
	}
	b, _ := json.Marshal(items)
	if _, err := q.Exec(ctx, `
		UPDATE entity_attribute_values SET original_value = $1 WHERE attr_value_id = $2
	`, string(b), attrValueID); err != nil {
		return fmt.Errorf("items cache update: %w", err)
	}
	return nil
}
