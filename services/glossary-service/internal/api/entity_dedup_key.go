package api

import (
	"context"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/loreweave/glossary-service/internal/textnorm"
)

// refreshEntityDedupKey recomputes glossary_entities.normalized_name for one
// entity from its current cached_name, using the shared multi-language fold
// (textnorm.Normalize → loreweave_extraction: NFKC + casefold + CJK
// traditional→simplified). D-GLOSSARY-ST-DEDUP M3a: normalized_name is now an
// APP-MAINTAINED column (no longer a GENERATED NFC+lower expression), so this MUST
// be called after any write that creates or changes an entity's name — otherwise
// the dedup-key backstop goes stale relative to the Go resolver. The M3b
// remediation also recomputes the whole table, so a missed call self-heals there;
// the resolver (the primary dedup) never depends on this column.
//
// It reads cached_name — the denormalized name maintained by the recalculate_
// entity_snapshot trigger from the 'name' OR 'term' EAV (the SAME input the old
// generated column folded). Since that trigger fires AFTER the EAV write within the
// same tx, calling this right after a name-bearing write sees the fresh value; and
// because it derives from cached_name, calling it after ANY attr write is safe —
// the IS DISTINCT guard makes it a true no-op when the name didn't change. No-op
// when the entity has no name yet (cached_name '' → normalized_name '', excluded by
// the partial uq_entity_dedup index) until the name arrives.
func refreshEntityDedupKey(ctx context.Context, q pgxRWQuerier, entityID uuid.UUID) error {
	var cached string
	err := q.QueryRow(ctx,
		`SELECT COALESCE(cached_name, '') FROM glossary_entities WHERE entity_id = $1`,
		entityID).Scan(&cached)
	if err == pgx.ErrNoRows {
		return nil
	}
	if err != nil {
		return err
	}
	_, err = q.Exec(ctx,
		`UPDATE glossary_entities SET normalized_name = $1
		 WHERE entity_id = $2 AND normalized_name IS DISTINCT FROM $1`,
		textnorm.Normalize(cached), entityID)
	return err
}
