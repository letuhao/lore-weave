package state

import (
	"context"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/services/archive-worker/pkg/types"
)

// Postgres is the production state.Store, backed by the per-reality
// `archive_state` table (migration 0011). Implements both state.Store and
// partition_picker.StateReader (via AlreadyArchived).
type Postgres struct {
	pool *pgxpool.Pool
}

// NewPostgres binds the per-reality pool.
func NewPostgres(pool *pgxpool.Pool) *Postgres { return &Postgres{pool: pool} }

// AlreadyArchived returns the set of partition names already recorded.
func (s *Postgres) AlreadyArchived(ctx context.Context, realityID uuid.UUID) (map[string]struct{}, error) {
	rows, err := s.pool.Query(ctx,
		`SELECT partition_name FROM archive_state WHERE reality_id = $1`, realityID)
	if err != nil {
		return nil, fmt.Errorf("state: already-archived query: %w", err)
	}
	defer rows.Close()
	out := map[string]struct{}{}
	for rows.Next() {
		var name string
		if err := rows.Scan(&name); err != nil {
			return nil, fmt.Errorf("state: already-archived scan: %w", err)
		}
		out[name] = struct{}{}
	}
	return out, rows.Err()
}

// RecordArchived idempotently inserts the manifest row (ON CONFLICT DO NOTHING
// on the (reality_id, partition_name) PK) — a re-run after a mid-flight crash
// is a no-op, never a double-row.
func (s *Postgres) RecordArchived(ctx context.Context, obj types.ArchivedObject) error {
	header := obj.FormatHeader[:]
	_, err := s.pool.Exec(ctx, `
		INSERT INTO archive_state
		    (reality_id, partition_name, object_key, byte_size, row_count, format_header, archived_at)
		VALUES ($1,$2,$3,$4,$5,$6,$7)
		ON CONFLICT (reality_id, partition_name) DO NOTHING
	`, obj.RealityID, obj.Partition, obj.ObjectKey, obj.ByteSize, obj.RowCount, header, obj.ArchivedAt)
	if err != nil {
		return fmt.Errorf("state: record %s/%s: %w", obj.RealityID, obj.Partition, err)
	}
	return nil
}

// List enumerates all manifest rows for a reality (newest first) — used by
// cmd/archive-restore.
func (s *Postgres) List(ctx context.Context, realityID uuid.UUID) ([]types.ArchivedObject, error) {
	rows, err := s.pool.Query(ctx, `
		SELECT reality_id, partition_name, object_key, byte_size, row_count, format_header, archived_at
		FROM archive_state WHERE reality_id = $1
		ORDER BY archived_at DESC`, realityID)
	if err != nil {
		return nil, fmt.Errorf("state: list query: %w", err)
	}
	defer rows.Close()
	var out []types.ArchivedObject
	for rows.Next() {
		var (
			o      types.ArchivedObject
			header []byte
		)
		if err := rows.Scan(&o.RealityID, &o.Partition, &o.ObjectKey, &o.ByteSize, &o.RowCount, &header, &o.ArchivedAt); err != nil {
			return nil, fmt.Errorf("state: list scan: %w", err)
		}
		copy(o.FormatHeader[:], header)
		out = append(out, o)
	}
	return out, rows.Err()
}
