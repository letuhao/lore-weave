package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpCanonicalSnapshotTranslations — chain step 0050 (per-episode translation surface, spec
// §6B/§7.6). A bounded, immutable, on-demand TRANSLATION cache over canonical_snapshot —
// the exact mirror of knowledge-service's event_text_translations (KG-TL M3): the substrate
// that owns the source prose (glossary owns canonical_snapshot) owns its translation cache.
//
// WHY HERE, NOT translation-service: the cached unit is a derived projection of glossary's
// canonical, co-located with it (CASCADE-clean on entity delete is the snapshot's own concern).
// The LLM itself still runs in translation-service (translate_text_core → provider-registry,
// BYOK) — glossary never imports a provider SDK (provider-gateway invariant). Glossary only
// stores the result + single-flights the fill.
//
// IMMUTABILITY / "translated exactly once" (§6B): the key is
// (entity_id, attr_scope, language_code, source_content_hash). source_content_hash = md5 of the
// canonical content this row translates, so a RE-FOLD (content changes → new hash) mints a NEW
// row and never collides with the prior translation — the old stays valid for its content.
//
// TENANCY — book-tier, NOT per-user: the canonical_snapshot is book-shared (read-only to
// collaborators, written by the fold). Its translation is an equally book-shared artifact, so
// user_id is NOT part of the key (the first authorized viewer mints; collaborators reuse).
// minted_by_user_id is audit only; access is grant-gated at the KAL.
//
// SINGLE-FLIGHT: status starts 'pending' on the claiming INSERT (ON CONFLICT DO NOTHING). Only
// the request that wins the insert launches the background fill → 'ready' (value set) or
// 'failed' (error_code set, attempts bumped; a later request may re-claim while attempts<budget).
//
// Forward-only, idempotent (CREATE TABLE/INDEX IF NOT EXISTS), execGuarded.
func UpCanonicalSnapshotTranslations(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "canonical-snapshot-translations", `
		CREATE TABLE IF NOT EXISTS canonical_snapshot_translations (
		  entity_id           uuid   NOT NULL,
		  attr_scope          text   NOT NULL DEFAULT 'narrative',
		  language_code       text   NOT NULL,
		  source_content_hash text   NOT NULL,
		  as_of_ordinal       bigint NOT NULL DEFAULT 0,
		  value               text   NOT NULL DEFAULT '',
		  status              text   NOT NULL DEFAULT 'pending',
		  error_code          text   NOT NULL DEFAULT '',
		  attempts            int    NOT NULL DEFAULT 0,
		  translator          text   NOT NULL DEFAULT 'glossary-snapshot',
		  minted_by_user_id   uuid,
		  book_id             uuid,
		  created_at          timestamptz NOT NULL DEFAULT now(),
		  updated_at          timestamptz NOT NULL DEFAULT now(),
		  PRIMARY KEY (entity_id, attr_scope, language_code, source_content_hash),
		  CONSTRAINT canonical_snapshot_translations_status_chk
		    CHECK (status IN ('pending','ready','failed')),
		  CONSTRAINT canonical_snapshot_translations_entity_fk
		    FOREIGN KEY (entity_id) REFERENCES glossary_entities(entity_id) ON DELETE CASCADE
		);
		CREATE INDEX IF NOT EXISTS idx_canon_snap_tr_book
		  ON canonical_snapshot_translations (book_id);`)
}
