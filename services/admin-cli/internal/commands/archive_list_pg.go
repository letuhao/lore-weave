package commands

import (
	"context"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// PgArchiveListReader reads archive_state (read-only) from a reality's
// PER-REALITY DB pool for `archive list`. Unlike the meta-backed reality-stats /
// migration-status readers, this binds a per-reality pool (the archive ledger
// lives in each reality's own DB, written by the archive-worker).
type PgArchiveListReader struct {
	pool *pgxpool.Pool
}

// NewPgArchiveListReader binds a per-reality pool (caller-owned).
func NewPgArchiveListReader(pool *pgxpool.Pool) *PgArchiveListReader {
	return &PgArchiveListReader{pool: pool}
}

var _ ArchiveListReader = (*PgArchiveListReader)(nil)

// ListArchives SELECTs the reality's archived partitions, newest-first. An empty
// result is not an error (nothing archived yet).
func (r *PgArchiveListReader) ListArchives(ctx context.Context, realityID uuid.UUID) ([]ArchiveEntry, error) {
	rows, err := r.pool.Query(ctx,
		`SELECT partition_name, object_key, byte_size, row_count, archived_at
		   FROM archive_state
		  WHERE reality_id = $1
		  ORDER BY archived_at DESC, partition_name DESC`,
		realityID)
	if err != nil {
		return nil, fmt.Errorf("query archive_state for %s: %w", realityID, err)
	}
	defer rows.Close()
	var out []ArchiveEntry
	for rows.Next() {
		var e ArchiveEntry
		if err := rows.Scan(&e.PartitionName, &e.ObjectKey, &e.ByteSize, &e.RowCount, &e.ArchivedAt); err != nil {
			return nil, fmt.Errorf("scan archive_state row: %w", err)
		}
		out = append(out, e)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate archive_state: %w", err)
	}
	return out, nil
}
