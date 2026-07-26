package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// kindNameI18nSQL — KG-ML M5 (C4 / DD4): localized kind labels.
//
// Adds a `name_i18n JSONB` column to each ontology tier table (system_kinds,
// user_kinds, book_kinds) rather than a separate label table — the column
// inherits each tier's scope key for free (no new tenancy surface) and rides the
// existing tier-merge resolution (CLAUDE.md › User Boundaries; DD4). `{}` default
// means "no localized label" → resolution falls back to the canonical `name`.
//
// The System tier is admin-seeded here with vi labels for the 12 default kinds
// (the canonical English `name` stays the en label). The per-user / per-book
// tiers get the column now but are populated by their owner later — per-user
// label authoring is deferred (D-KG-ML-PERUSER-LABELS); System + Book cover the
// scenario. A regular user NEVER writes a System row (the entity_kinds tenancy
// bug): this seed runs only via the admin-gated migration chain.
//
// Idempotent: ADD COLUMN IF NOT EXISTS + a `||` jsonb merge that preserves any
// other languages already present. Ledgered (0037) so it runs exactly once.
const kindNameI18nSQL = `
ALTER TABLE system_kinds ADD COLUMN IF NOT EXISTS name_i18n JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE user_kinds   ADD COLUMN IF NOT EXISTS name_i18n JSONB NOT NULL DEFAULT '{}'::jsonb;
ALTER TABLE book_kinds   ADD COLUMN IF NOT EXISTS name_i18n JSONB NOT NULL DEFAULT '{}'::jsonb;

UPDATE system_kinds k
SET name_i18n = k.name_i18n || jsonb_build_object('vi', v.vi)
FROM (VALUES
  ('character',      'Nhân vật'),
  ('location',       'Địa điểm'),
  ('item',           'Vật phẩm'),
  ('event',          'Sự kiện'),
  ('terminology',    'Thuật ngữ'),
  ('power_system',   'Hệ thống sức mạnh'),
  ('organization',   'Tổ chức'),
  ('species',        'Chủng loài'),
  ('relationship',   'Mối quan hệ'),
  ('plot_arc',       'Tuyến truyện'),
  ('trope',          'Mô-típ'),
  ('social_setting', 'Bối cảnh xã hội')
) AS v(code, vi)
WHERE k.code = v.code;
`

// UpKindNameI18n adds the name_i18n column to the three kind tiers and admin-seeds
// the System vi labels (KG-ML M5 C4). Idempotent; chain step 0037.
func UpKindNameI18n(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "kind-name-i18n", kindNameI18nSQL)
}
