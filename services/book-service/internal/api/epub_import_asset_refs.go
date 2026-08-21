package api

import (
	"context"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
)

// refreshEPUBImportAssetReferences derives references from the durable chapter
// drafts. It is intentionally recomputed, not incremented, so retries and
// rollback cannot inflate the count.
func refreshEPUBImportAssetReferences(ctx context.Context, tx pgx.Tx, sourceID uuid.UUID) error {
	_, err := tx.Exec(ctx, `
UPDATE import_assets a
SET reference_count=refs.count,
    status=CASE WHEN refs.count=0 THEN 'orphaned' ELSE 'active' END
FROM (
  SELECT a2.id,COUNT(d.chapter_id)::int AS count
  FROM import_assets a2
  LEFT JOIN chapter_import_provenance p ON p.source_id=a2.source_id
  LEFT JOIN chapter_drafts d ON d.chapter_id=p.chapter_id
    AND a2.public_url IS NOT NULL
    AND d.body::text LIKE '%' || COALESCE(a2.public_url,'') || '%'
  WHERE a2.source_id=$1
  GROUP BY a2.id
) refs
WHERE a.id=refs.id AND a.source_id=$1
`, sourceID)
	return err
}
