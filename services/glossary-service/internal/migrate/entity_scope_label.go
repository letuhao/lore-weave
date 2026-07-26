package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpEntityScopeLabel — chain step 0051 (D-GLOSSARY-ENTITY-SCOPE). Real feedback,
// 2026-07-08 (D:\Works\novels\mi_de\loreweave-mcp-feedback.md, "entity identity
// should be world/namespace-scoped"): the dedup key is (book_id, kind_id,
// normalized_name) ONLY — two entities that share a name+kind but are genuinely
// different (e.g. a "Lâm gia" sect in one world vs. a same-named "Lâm gia" in a
// different world, in a multi-world/reincarnation story) get silently folded
// together, or an agent avoiding the collision has to hand-bake the world into the
// display name string.
//
// Scope decision (author + PO, 2026-07-08): a plain, author-set TEXT label — NOT a
// structured FK to a world_realm entity. No existing precedent for entity-to-entity
// references exists in this schema (attribute field_types are all scalar: text,
// textarea, select, number, date, tags, url, boolean — see enumFieldTypes), so a
// real FK-based "scope entity" would be a new primitive, out of scope for this
// pass. scope_label is OPTIONAL for every kind (no kind requires it) — most
// entities never set it and behave exactly as before (empty matches empty, same
// as today); an author sets it only when disambiguation is actually needed.
//
// Additive + non-destructive: every existing row defaults to scope_label='', so
// the new composite unique index is a strict superset of the current one and
// cannot fail on existing data (two entities already coexisting under the old
// 3-column key never collided; adding a 4th column that is constant '' for both
// cannot introduce a new collision).
func UpEntityScopeLabel(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "entity-scope-label", `
		ALTER TABLE glossary_entities
		  ADD COLUMN IF NOT EXISTS scope_label TEXT NOT NULL DEFAULT '';

		DROP INDEX IF EXISTS uq_entity_dedup;
		CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_dedup
		  ON glossary_entities (book_id, kind_id, normalized_name, scope_label)
		  WHERE deleted_at IS NULL AND normalized_name <> '';`)
}
