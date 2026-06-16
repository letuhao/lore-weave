package commands

import (
	"context"
	"fmt"
	"strings"
	"time"

	"github.com/google/uuid"
)

// ArchiveEntry is one archived monthly partition (a per-reality archive_state
// row). Read-only — the archive-worker is the sole writer.
type ArchiveEntry struct {
	PartitionName string // e.g. events_p_2025_11
	ObjectKey     string // MinIO key, e.g. events/<reality_id>/2025-11.parquet
	ByteSize      int64
	RowCount      int64
	ArchivedAt    time.Time
}

// ArchiveListReader lists a reality's archived partitions (read-only). The prod
// impl is PgArchiveListReader (over the reality's per-reality DB); tests use a fake.
type ArchiveListReader interface {
	ListArchives(ctx context.Context, realityID uuid.UUID) ([]ArchiveEntry, error)
}

// RunArchiveList reads + formats a reality's archived months (tier-3
// informational, read-only — no mutation). An empty list is reported plainly
// (a reality with nothing archived yet is normal, not an error).
func RunArchiveList(ctx context.Context, realityID uuid.UUID, reader ArchiveListReader) (string, error) {
	if reader == nil {
		return "", fmt.Errorf("archive list: reader not wired")
	}
	rows, err := reader.ListArchives(ctx, realityID)
	if err != nil {
		return "", err
	}
	var b strings.Builder
	fmt.Fprintf(&b, "reality %s — archived partitions (read-only): %d\n", realityID, len(rows))
	for _, e := range rows {
		fmt.Fprintf(&b, "  %-20s  %10d rows  %12d bytes  archived %s  [%s]\n",
			e.PartitionName, e.RowCount, e.ByteSize,
			e.ArchivedAt.UTC().Format(time.RFC3339), e.ObjectKey)
	}
	return b.String(), nil
}
