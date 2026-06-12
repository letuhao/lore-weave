package commands

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// PgArchiveMetaReader resolves an archive_state manifest row from a reality's
// PER-REALITY DB pool (read-only). Exact object-key lookup — the canonical key is
// deterministic, so no fragile partition_name matching.
type PgArchiveMetaReader struct {
	pool *pgxpool.Pool
}

// NewPgArchiveMetaReader binds a per-reality pool (caller-owned).
func NewPgArchiveMetaReader(pool *pgxpool.Pool) *PgArchiveMetaReader {
	return &PgArchiveMetaReader{pool: pool}
}

var _ ArchiveMetaReader = (*PgArchiveMetaReader)(nil)

// LookupArchive returns the manifest row for (reality, objectKey). A missing row is
// (zero, false, nil) — nothing archived for that month is a normal answer, not an error.
func (r *PgArchiveMetaReader) LookupArchive(ctx context.Context, realityID uuid.UUID, objectKey string) (ArchiveObject, bool, error) {
	var o ArchiveObject
	err := r.pool.QueryRow(ctx,
		`SELECT object_key, byte_size, row_count, format_header, archived_at
		   FROM archive_state
		  WHERE reality_id = $1 AND object_key = $2`,
		realityID, objectKey).
		Scan(&o.ObjectKey, &o.ByteSize, &o.RowCount, &o.FormatHeader, &o.ArchivedAt)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return ArchiveObject{}, false, nil
		}
		return ArchiveObject{}, false, fmt.Errorf("query archive_state for %s key %s: %w", realityID, objectKey, err)
	}
	return o, true, nil
}
