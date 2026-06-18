// Package pgio is the pgx-backed implementation of the archive-worker's
// Postgres IO boundaries: partition_picker.Catalog, archive_loop.RowSource,
// and archive_loop.PartitionDropper.
//
// All three operate on ONE per-reality DB's `events` table (cycle-9 0002,
// monthly RANGE partitions on recorded_at, named `events_p_YYYY_MM`).
package pgio

import (
	"context"
	"fmt"
	"regexp"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/services/archive-worker/pkg/types"
)

// partitionNameRe guards every DDL/DML that interpolates a partition name
// (table names can't be parameterized). The names come from pg_inherits so
// they are trusted, but this is defense-in-depth against any drift.
var partitionNameRe = regexp.MustCompile(`^events_p_[0-9]{4}_[0-9]{2}$`)

// ValidPartitionName reports whether name is a well-formed monthly partition.
func ValidPartitionName(name string) bool { return partitionNameRe.MatchString(name) }

// ── Catalog (partition_picker.Catalog) ─────────────────────────────────────

// Catalog enumerates the monthly partitions of `events` on one reality DB.
type Catalog struct {
	pool *pgxpool.Pool
}

// NewCatalog binds the per-reality pool.
func NewCatalog(pool *pgxpool.Pool) *Catalog { return &Catalog{pool: pool} }

// ListPartitions returns every `events_p_YYYY_MM` child with bounds parsed
// from the name + the reltuples row estimate. Children whose name doesn't
// match the monthly convention are skipped (defensive).
func (c *Catalog) ListPartitions(ctx context.Context, realityID uuid.UUID) ([]types.Partition, error) {
	rows, err := c.pool.Query(ctx, `
		SELECT child.relname, child.reltuples::bigint
		FROM pg_inherits
		JOIN pg_class child  ON child.oid  = pg_inherits.inhrelid
		JOIN pg_class parent ON parent.oid = pg_inherits.inhparent
		WHERE parent.relname = 'events'
		ORDER BY child.relname
	`)
	if err != nil {
		return nil, fmt.Errorf("pgio: list partitions: %w", err)
	}
	defer rows.Close()

	var out []types.Partition
	for rows.Next() {
		var name string
		var estimate int64
		if err := rows.Scan(&name, &estimate); err != nil {
			return nil, fmt.Errorf("pgio: scan partition: %w", err)
		}
		lower, upper, ok := parseMonthlyBounds(name)
		if !ok {
			continue // not a monthly partition (e.g. a default partition)
		}
		if estimate < 0 {
			estimate = 0 // reltuples can be -1 before ANALYZE
		}
		out = append(out, types.Partition{
			RealityID:        realityID,
			Name:             name,
			LowerBound:       lower,
			UpperBound:       upper,
			RowCountEstimate: estimate,
		})
	}
	return out, rows.Err()
}

// parseMonthlyBounds turns `events_p_2025_11` → [2025-11-01, 2025-12-01) UTC.
func parseMonthlyBounds(name string) (time.Time, time.Time, bool) {
	if !ValidPartitionName(name) {
		return time.Time{}, time.Time{}, false
	}
	// name = events_p_YYYY_MM — the last 7 chars are "YYYY_MM".
	var year, month int
	if _, err := fmt.Sscanf(name[len(name)-7:], "%4d_%2d", &year, &month); err != nil {
		return time.Time{}, time.Time{}, false
	}
	if month < 1 || month > 12 {
		return time.Time{}, time.Time{}, false
	}
	lower := time.Date(year, time.Month(month), 1, 0, 0, 0, 0, time.UTC)
	return lower, lower.AddDate(0, 1, 0), true
}

// ── RowSource (archive_loop.RowSource) ─────────────────────────────────────

// RowSource reads all event rows out of a partition.
//
// V1 ASSUMPTION (not enforced — see DEFERRED D-ARCHIVE-DETACH-FIRST): partitions
// past the 90d archive cutoff are treated as IMMUTABLE, so a plain SELECT is
// safe and no ATTACH-to-staging lock dance is used. `events.recorded_at` is
// `DEFAULT NOW()` but settable, so a backdated INSERT into an already-eligible
// partition BETWEEN this read and archive_loop's later DROP would be dropped
// unarchived (data loss). The foundation has no backdated-write path today; the
// principled fix is DETACH-the-partition-FIRST (removing it from the parent so
// no new routed inserts) THEN read the detached table THEN drop — the deferred
// "ATTACH-to-staging" pattern from row 057.
type RowSource struct {
	pool *pgxpool.Pool
}

// NewRowSource binds the per-reality pool.
func NewRowSource(pool *pgxpool.Pool) *RowSource { return &RowSource{pool: pool} }

// LoadPartition SELECTs every row of the partition into []EventRow.
func (s *RowSource) LoadPartition(ctx context.Context, p types.Partition) ([]types.EventRow, error) {
	if !ValidPartitionName(p.Name) {
		return nil, fmt.Errorf("pgio: refusing to read non-conforming partition %q", p.Name)
	}
	// #nosec G201 — name validated by ValidPartitionName; not parameterizable.
	q := fmt.Sprintf(`
		SELECT event_id, reality_id, aggregate_type, aggregate_id, aggregate_version,
		       event_type, event_version, payload, metadata, occurred_at, recorded_at,
		       audit_ref, registry_version
		FROM %s
		ORDER BY recorded_at, event_id`, p.Name)
	rows, err := s.pool.Query(ctx, q)
	if err != nil {
		return nil, fmt.Errorf("pgio: load %s: %w", p.Name, err)
	}
	defer rows.Close()

	var out []types.EventRow
	for rows.Next() {
		var (
			r        types.EventRow
			aggVer   int64
			auditRef *string
			regVer   *int32
		)
		if err := rows.Scan(
			&r.EventID, &r.RealityID, &r.AggregateType, &r.AggregateID, &aggVer,
			&r.EventType, &r.EventVersion, &r.Payload, &r.Metadata, &r.OccurredAt, &r.RecordedAt,
			&auditRef, &regVer,
		); err != nil {
			return nil, fmt.Errorf("pgio: scan %s: %w", p.Name, err)
		}
		r.AggregateVersion = uint64(aggVer)
		if auditRef != nil {
			if u, perr := uuid.Parse(*auditRef); perr == nil {
				r.AuditRef = &u
			}
		}
		if regVer != nil {
			v := int(*regVer)
			r.RegistryVersion = &v
		}
		out = append(out, r)
	}
	return out, rows.Err()
}

// ── PartitionDropper (archive_loop.PartitionDropper) ───────────────────────

// PartitionDropper detaches + drops a partition in one transaction.
type PartitionDropper struct {
	pool *pgxpool.Pool
}

// NewPartitionDropper binds the per-reality pool.
func NewPartitionDropper(pool *pgxpool.Pool) *PartitionDropper { return &PartitionDropper{pool: pool} }

// Drop runs `ALTER TABLE events DETACH PARTITION <p>; DROP TABLE <p>;` in one
// tx. The partition data is already safe in MinIO + recorded in archive_state.
func (d *PartitionDropper) Drop(ctx context.Context, p types.Partition) error {
	if !ValidPartitionName(p.Name) {
		return fmt.Errorf("pgio: refusing to drop non-conforming partition %q", p.Name)
	}
	tx, err := d.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("pgio: drop begin %s: %w", p.Name, err)
	}
	defer tx.Rollback(ctx) //nolint:errcheck — no-op after a successful Commit

	// #nosec G201 — name validated by ValidPartitionName.
	if _, err := tx.Exec(ctx, fmt.Sprintf(`ALTER TABLE events DETACH PARTITION %s`, p.Name)); err != nil {
		return fmt.Errorf("pgio: detach %s: %w", p.Name, err)
	}
	if _, err := tx.Exec(ctx, fmt.Sprintf(`DROP TABLE %s`, p.Name)); err != nil {
		return fmt.Errorf("pgio: drop %s: %w", p.Name, err)
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("pgio: drop commit %s: %w", p.Name, err)
	}
	return nil
}
