package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpSystemSoftDelete — chain step 0031 (G-C8). Makes System-tier deletes REVERSIBLE.
//
// Before this, system_genres/kinds/attributes were HARD-deleted (admin_core.go
// `DELETE FROM …`), and the FK `ON DELETE CASCADE` permanently destroyed the
// dependent system_kind_genres / system_attributes rows — irreversible loss on
// shared rows every tenant reads. This adds the `deprecated_at` soft-delete column
// (the same convention the book tier already uses — book_genres/kinds/attributes
// carry `deprecated_at`), so the delete cores can deprecate instead of DELETE and a
// restore core can clear it.
//
// Partial indexes mirror the book/user-tier "live" indexes (idx_bg_book,
// idx_ua_kind_genre …) so the post-sweep `WHERE deprecated_at IS NULL` reads stay
// indexed.
//
// Additive + idempotent (ADD COLUMN / CREATE INDEX … IF NOT EXISTS), routed through
// execGuarded (the migration advisory lock) like every other chain step.
func UpSystemSoftDelete(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "system-soft-delete", `
		ALTER TABLE system_genres     ADD COLUMN IF NOT EXISTS deprecated_at TIMESTAMPTZ;
		ALTER TABLE system_kinds      ADD COLUMN IF NOT EXISTS deprecated_at TIMESTAMPTZ;
		ALTER TABLE system_attributes ADD COLUMN IF NOT EXISTS deprecated_at TIMESTAMPTZ;
		CREATE INDEX IF NOT EXISTS idx_sg_live ON system_genres(sort_order, code)      WHERE deprecated_at IS NULL;
		CREATE INDEX IF NOT EXISTS idx_sk_live ON system_kinds(sort_order, code)       WHERE deprecated_at IS NULL;
		CREATE INDEX IF NOT EXISTS idx_sa_live ON system_attributes(kind_id, genre_id) WHERE deprecated_at IS NULL;`)
}
