package api

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/google/uuid"
	"github.com/minio/minio-go/v7"
)

// RunEPUBAssetRetentionSweeper removes only source-scoped assets that have
// been orphaned past the configured retention window. Source EPUB objects are
// never touched by this job. A failed object delete remains orphaned for the
// next retry, so a transient MinIO outage cannot lose the database reference.
func (s *Server) RunEPUBAssetRetentionSweeper(ctx context.Context, interval, retention time.Duration) {
	if interval <= 0 || retention <= 0 {
		return
	}
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if deleted, err := s.reapOrphanedEPUBAssets(ctx, time.Now().Add(-retention), 100); err != nil {
				slog.WarnContext(ctx, "epub asset retention sweep failed", "error", err)
			} else if deleted > 0 {
				slog.InfoContext(ctx, "epub asset retention sweep completed", "deleted", deleted)
			}
		}
	}
}

func (s *Server) reapOrphanedEPUBAssets(ctx context.Context, cutoff time.Time, limit int) (int, error) {
	if s.minio == nil {
		return 0, fmt.Errorf("object storage is unavailable")
	}
	rows, err := s.pool.Query(ctx, `
SELECT id,object_key
FROM import_assets
WHERE status='orphaned' AND reference_count=0 AND created_at < $1
ORDER BY created_at
LIMIT $2
FOR UPDATE SKIP LOCKED
`, cutoff, limit)
	if err != nil {
		return 0, err
	}
	type candidate struct {
		id  uuid.UUID
		key string
	}
	candidates := make([]candidate, 0)
	for rows.Next() {
		var item candidate
		if err := rows.Scan(&item.id, &item.key); err != nil {
			rows.Close()
			return 0, err
		}
		candidates = append(candidates, item)
	}
	if err := rows.Err(); err != nil {
		rows.Close()
		return 0, err
	}
	rows.Close()
	deleted := 0
	for _, item := range candidates {
		if err := s.minio.RemoveObject(ctx, s.cfg.BooksStorageBucket, item.key, minio.RemoveObjectOptions{}); err != nil {
			continue
		}
		result, err := s.pool.Exec(ctx, `UPDATE import_assets SET status='deleted' WHERE id=$1 AND status='orphaned' AND reference_count=0`, item.id)
		if err == nil && result.RowsAffected() == 1 {
			deleted++
		}
	}
	return deleted, nil
}
