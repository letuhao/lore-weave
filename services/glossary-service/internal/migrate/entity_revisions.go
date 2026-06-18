package migrate

import (
	"context"

	"github.com/jackc/pgx/v5/pgxpool"
)

// UpEntityRevisions creates the append-only entity_revisions table — the
// glossary versioning history store (D-GLOSSARY-VERSIONING, VG-1).
//
// Each row is a whole-entity snapshot (a copy of glossary_entities.entity_snapshot
// at a point in time), materialized ASYNC by the revision-projection consumer off
// the glossary.entity_updated outbox stream — so the hot write path pays nothing
// for history. Idempotent on (entity_id, event_id) — the source outbox_id — so an
// at-least-once stream redelivery never double-writes a revision.
//
// Append-only: INSERT-only, no UPDATE churn. Volume is bounded by actor-granularity
// (human edits always kept; pipeline/bulk pruned to a rolling last-N by the
// consumer). See docs/specs/2026-06-07-glossary-entity-versioning.md.
func UpEntityRevisions(ctx context.Context, pool *pgxpool.Pool) error {
	return execGuarded(ctx, pool, "entity-revisions", `
CREATE TABLE IF NOT EXISTS entity_revisions (
  revision_id   UUID PRIMARY KEY DEFAULT uuidv7(),
  entity_id     UUID NOT NULL REFERENCES glossary_entities(entity_id) ON DELETE CASCADE,
  book_id       UUID NOT NULL,
  revision_num  INT  NOT NULL,
  snapshot      JSONB NOT NULL,
  op            TEXT NOT NULL DEFAULT 'update',   -- created | updated | delete | restore
  actor_type    TEXT NOT NULL DEFAULT 'system',   -- user | pipeline | system
  actor_id      UUID,
  event_id      UUID NOT NULL,                     -- source outbox_id → idempotent consume
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(entity_id, revision_num),
  UNIQUE(entity_id, event_id)
);
CREATE INDEX IF NOT EXISTS idx_er_entity ON entity_revisions(entity_id, revision_num DESC);
CREATE INDEX IF NOT EXISTS idx_er_book   ON entity_revisions(book_id);
`)
}

// BackfillEntityRevisions seeds a baseline revision (revision_num=1, op='baseline')
// for every entity that has none — its CURRENT whole-entity snapshot. Without this,
// a pre-existing entity's original state would be unprotected: the projection only
// captures state AFTER an edit fires, so the first accidental overwrite would be
// the first thing ever recorded. The baseline preserves the pre-edit state so the
// very first overwrite is recoverable. Idempotent (only entities lacking a revision
// get one); uses entity_id as the deterministic baseline event_id.
func BackfillEntityRevisions(ctx context.Context, pool *pgxpool.Pool) error {
	_, err := pool.Exec(ctx, `
INSERT INTO entity_revisions (entity_id, book_id, revision_num, snapshot, op, actor_type, event_id)
SELECT e.entity_id, e.book_id, 1,
       COALESCE(e.entity_snapshot, '{}'::jsonb), 'baseline', 'system', e.entity_id
FROM glossary_entities e
WHERE NOT EXISTS (SELECT 1 FROM entity_revisions r WHERE r.entity_id = e.entity_id)
ON CONFLICT DO NOTHING`)
	return err
}
