// Package pgwrite is the pgx-backed implementation of the canon_writer
// dependency interfaces (PerRealityDB / RealitySubscriptionLookup / AuditSink).
//
//   - CanonDB     → UPSERT canon_projection on the subscriber reality's DB.
//   - Subscribers → book_reality_subscription ⨝ reality_registry (meta DB).
//   - Audit       → meta_write_audit (meta DB), idempotent on re-delivery.
package pgwrite

import (
	"context"
	"encoding/json"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/services/meta-worker/pkg/canon_writer"
)

// auditNamespace makes the meta_write_audit audit_id deterministic per
// (event_id, reality_id) so a re-delivered xreality message doesn't append a
// duplicate audit row (the table is append-only; ON CONFLICT DO NOTHING).
var auditNamespace = uuid.MustParse("6f1d2c00-0000-4000-8000-000000000001")

// ── CanonDB (PerRealityDB) ────────────────────────────────────────────────

// CanonDB upserts canon_projection across a set of per-reality pgx pools.
type CanonDB struct {
	pools map[string]*pgxpool.Pool
}

// NewCanonDB binds the reality_id → pool map. Begin/UpsertCanon guards a
// missing pool per-reality (subscriber reality not active at startup → NACK).
func NewCanonDB(pools map[string]*pgxpool.Pool) *CanonDB {
	if pools == nil {
		pools = map[string]*pgxpool.Pool{}
	}
	return &CanonDB{pools: pools}
}

// UpsertCanon writes an own-source canon_projection row (cascaded_from NULL).
func (c *CanonDB) UpsertCanon(ctx context.Context, in canon_writer.UpsertIntent) error {
	pool, ok := c.pools[in.RealityID.String()]
	if !ok {
		return fmt.Errorf("pgwrite: no pool for subscriber reality %s", in.RealityID)
	}
	value := in.Value
	if len(value) == 0 {
		value = []byte("null") // canon_projection.value DEFAULT 'null'::jsonb
	}
	_, err := pool.Exec(ctx, `
		INSERT INTO canon_projection
		    (canon_entry_id, book_id, attribute_path, value, canon_layer, lock_level,
		     source_event_id, cascaded_from_reality_id, last_synced_at,
		     event_id, aggregate_version, applied_at)
		VALUES ($1,$2,$3,$4::jsonb,$5,$6,$7,NULL,$8,$9,$10,NOW())
		ON CONFLICT (canon_entry_id) DO UPDATE SET
		    book_id                  = EXCLUDED.book_id,
		    attribute_path           = EXCLUDED.attribute_path,
		    value                    = EXCLUDED.value,
		    canon_layer              = EXCLUDED.canon_layer,
		    lock_level               = EXCLUDED.lock_level,
		    source_event_id          = EXCLUDED.source_event_id,
		    cascaded_from_reality_id = NULL,
		    last_synced_at           = EXCLUDED.last_synced_at,
		    event_id                 = EXCLUDED.event_id,
		    aggregate_version        = EXCLUDED.aggregate_version,
		    applied_at               = NOW()
	`,
		in.CanonEntryID, in.BookID, in.AttributePath, string(value), in.CanonLayer, in.LockLevel,
		in.SourceEventID, in.LastSyncedAt, in.SourceEventID, int64(in.AggregateVersion),
	)
	if err != nil {
		return fmt.Errorf("pgwrite: upsert canon_projection reality=%s entry=%s: %w",
			in.RealityID, in.CanonEntryID, err)
	}
	return nil
}

// ── Subscribers (RealitySubscriptionLookup) ───────────────────────────────

// Subscribers resolves the realities subscribing to a book's canon.
type Subscribers struct {
	meta *pgxpool.Pool
}

// NewSubscribers binds the meta DB pool.
func NewSubscribers(meta *pgxpool.Pool) *Subscribers { return &Subscribers{meta: meta} }

// SubscribersForBook returns the live (active/frozen) realities subscribed to
// the book. Empty result = no fan-out (not an error).
func (s *Subscribers) SubscribersForBook(ctx context.Context, bookID uuid.UUID) ([]uuid.UUID, error) {
	rows, err := s.meta.Query(ctx, `
		SELECT s.reality_id
		FROM book_reality_subscription s
		JOIN reality_registry r ON r.reality_id = s.reality_id
		WHERE s.book_id = $1 AND r.status IN ('active','frozen')
		ORDER BY s.reality_id
	`, bookID)
	if err != nil {
		return nil, fmt.Errorf("pgwrite: subscribers query book=%s: %w", bookID, err)
	}
	defer rows.Close()

	var out []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			return nil, fmt.Errorf("pgwrite: subscribers scan: %w", err)
		}
		out = append(out, id)
	}
	return out, rows.Err()
}

// ── Audit (AuditSink) ──────────────────────────────────────────────────────

// Audit writes the per-write canon audit to meta_write_audit (Q-L1A-3).
type Audit struct {
	meta *pgxpool.Pool
}

// NewAudit binds the meta DB pool.
func NewAudit(meta *pgxpool.Pool) *Audit { return &Audit{meta: meta} }

// WriteAudit appends one meta_write_audit row. audit_id is deterministic per
// (event_id, reality_id) so re-delivery is idempotent.
func (a *Audit) WriteAudit(ctx context.Context, e canon_writer.AuditEntry) error {
	auditID := uuid.NewSHA1(auditNamespace, []byte(e.EventID.String()+"|"+e.RealityID.String()))
	rowPK, _ := json.Marshal(map[string]string{
		"canon_entry_id": e.CanonEntryID.String(),
		"reality_id":     e.RealityID.String(),
	})
	after, _ := json.Marshal(map[string]any{
		"book_id":        e.BookID.String(),
		"attribute_path": e.AttributePath,
	})
	reqCtx, _ := json.Marshal(map[string]string{
		"event_id":   e.EventID.String(),
		"event_type": e.EventType,
	})
	_, err := a.meta.Exec(ctx, `
		INSERT INTO meta_write_audit
		    (audit_id, table_name, operation, row_pk, before_values, after_values,
		     actor_type, actor_id, reason, request_context, created_at_nanos)
		VALUES ($1,'canon_projection','INSERT',$2::jsonb,'{}'::jsonb,$3::jsonb,
		        'service','meta-worker','canon fan-out',$4::jsonb,$5)
		ON CONFLICT (audit_id) DO NOTHING
	`, auditID, string(rowPK), string(after), string(reqCtx), e.WrittenAt.UnixNano())
	if err != nil {
		return fmt.Errorf("pgwrite: audit insert event=%s reality=%s: %w", e.EventID, e.RealityID, err)
	}
	return nil
}
