// Package pglive is the production pgx implementation of user_erased_writer's
// UserRealityLookup + PerRealityDB interfaces (P2/071 Slice 1).
//
// The user_erased_writer package is driver-clean (interfaces only); these
// adapters add the pgx dependency:
//   - PgUserRealityLookup reads the META cross-reality index
//     (player_character_index) to find which realities a user has PCs in.
//   - PgPerRealityScrubber scrubs the user's PII in a PER-REALITY projection
//     (pc_projection.name → '[erased]', status → 'deleted'), idempotently.
//
// pc_projection is the ONLY per-reality projection that references user_id
// (verified against contracts/migrations/per_reality/0006_projections).
package pglive

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	uew "github.com/loreweave/foundation/services/meta-worker/pkg/user_erased_writer"
)

// erasedNameSentinel replaces pc_projection.name (NOT NULL, so a sentinel, not
// NULL). A consumer reading the projection sees the PC as erased.
const erasedNameSentinel = "[erased]"

// PgUserRealityLookup resolves the realities a user touched from the meta
// cross-reality PC index.
type PgUserRealityLookup struct {
	meta *pgxpool.Pool
}

// NewPgUserRealityLookup binds the meta pool.
func NewPgUserRealityLookup(meta *pgxpool.Pool) *PgUserRealityLookup {
	return &PgUserRealityLookup{meta: meta}
}

var _ uew.UserRealityLookup = (*PgUserRealityLookup)(nil)

// RealitiesForUser returns the distinct realities where the user has a PC.
// Q-L5H-1 inverted: over-inclusion is safe (scrub is idempotent); we return
// every reality the index knows, regardless of PC status (an inactive/deleted
// PC's projection may still carry the name until scrubbed).
func (l *PgUserRealityLookup) RealitiesForUser(ctx context.Context, userID uuid.UUID) ([]uuid.UUID, error) {
	rows, err := l.meta.Query(ctx,
		`SELECT DISTINCT reality_id FROM player_character_index WHERE user_ref_id = $1`, userID)
	if err != nil {
		return nil, fmt.Errorf("pglive: query realities for user %s: %w", userID, err)
	}
	defer rows.Close()
	var out []uuid.UUID
	for rows.Next() {
		var rid uuid.UUID
		if err := rows.Scan(&rid); err != nil {
			return nil, fmt.Errorf("pglive: scan reality_id: %w", err)
		}
		out = append(out, rid)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("pglive: iterate realities: %w", err)
	}
	return out, nil
}

// PoolResolver maps a reality_id to its per-reality DB pool. Production binds
// this to the meta-worker's per-reality pool set (realityreg); tests inject a
// single-pool resolver.
type PoolResolver func(realityID uuid.UUID) (*pgxpool.Pool, error)

// PgPerRealityScrubber scrubs a user's PII references in one reality's
// pc_projection. Idempotent: the `status <> 'deleted'` guard makes a re-run a
// 0-row no-op.
type PgPerRealityScrubber struct {
	resolve PoolResolver
}

// NewPgPerRealityScrubber binds the per-reality pool resolver.
func NewPgPerRealityScrubber(resolve PoolResolver) *PgPerRealityScrubber {
	return &PgPerRealityScrubber{resolve: resolve}
}

var _ uew.PerRealityDB = (*PgPerRealityScrubber)(nil)

// ScrubUserRefs NULLs/tombstones the user's PC PII in the named reality. A
// transient failure (unreachable reality, SQL error) returns an error so the
// caller NACKs (Q-L5H-1 inverted: leaving PII alive is the UNSAFE direction).
// A 0-row result is success (already scrubbed, or the user has no PC here —
// over-inclusion from the lookup is expected and safe).
func (s *PgPerRealityScrubber) ScrubUserRefs(ctx context.Context, in uew.ScrubIntent) error {
	pool, err := s.resolve(in.RealityID)
	if err != nil {
		return fmt.Errorf("pglive: resolve pool for reality %s: %w", in.RealityID, err)
	}
	if _, err := pool.Exec(ctx,
		`UPDATE pc_projection
		    SET name = $2, status = 'deleted'
		  WHERE user_id = $1 AND status <> 'deleted'`,
		in.UserID, erasedNameSentinel); err != nil {
		return fmt.Errorf("pglive: scrub pc_projection user %s in reality %s: %w", in.UserID, in.RealityID, err)
	}
	return nil
}

// PgMetaScrubber scrubs the user's PII in the META cross-reality index
// (player_character_index.pc_name) — the copy the per-reality pc_projection
// scrub does not reach (P2/071). It routes through contracts/meta MetaWriteBatch
// (one UPDATE intent per non-deleted pc_index row) so each scrub is
// same-TX-audited in meta_write_audit + (if cfg.Outbox is set) emits
// pc.index.status.changed. Enumerate-then-batch (like the KEK shred) keeps the
// multi-PC scrub atomic; the `status <> 'deleted'` SELECT filter makes a re-run
// a no-op (idempotent).
type PgMetaScrubber struct {
	meta    *pgxpool.Pool
	cfg     *meta.Config
	actorID string
}

// NewPgMetaScrubber binds the meta pool + the MetaWrite Config + the actor
// recorded in meta_write_audit (the meta-worker service performing the scrub).
func NewPgMetaScrubber(metaPool *pgxpool.Pool, cfg *meta.Config, actorID string) *PgMetaScrubber {
	return &PgMetaScrubber{meta: metaPool, cfg: cfg, actorID: actorID}
}

var _ uew.MetaScrubber = (*PgMetaScrubber)(nil)

// ScrubUserMetaRefs tombstones every non-deleted player_character_index row for
// the user (pc_name → '[erased]', status → 'deleted') via MetaWriteBatch.
func (s *PgMetaScrubber) ScrubUserMetaRefs(ctx context.Context, userID uuid.UUID) error {
	rows, err := s.meta.Query(ctx,
		`SELECT pc_index_id FROM player_character_index WHERE user_ref_id = $1 AND status <> 'deleted'`, userID)
	if err != nil {
		return fmt.Errorf("pglive: enumerate pc_index for user %s: %w", userID, err)
	}
	var ids []uuid.UUID
	for rows.Next() {
		var id uuid.UUID
		if err := rows.Scan(&id); err != nil {
			rows.Close()
			return fmt.Errorf("pglive: scan pc_index_id: %w", err)
		}
		ids = append(ids, id)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return fmt.Errorf("pglive: iterate pc_index: %w", err)
	}
	if len(ids) == 0 {
		return nil // already scrubbed / no PCs — idempotent
	}
	intents := make([]meta.MetaWriteIntent, 0, len(ids))
	for _, id := range ids {
		intents = append(intents, meta.MetaWriteIntent{
			Table:     "player_character_index",
			Operation: meta.OpUpdate,
			PK:        map[string]any{"pc_index_id": id},
			NewValues: map[string]any{"pc_name": erasedNameSentinel, "status": "deleted"},
			Actor:     meta.Actor{Type: meta.ActorService, ID: s.actorID},
			Reason:    "gdpr erasure: scrub cross-reality PC index (P2/071)",
		})
	}
	if _, err := meta.MetaWriteBatch(ctx, s.cfg, intents); err != nil {
		return fmt.Errorf("pglive: meta-scrub player_character_index for user %s: %w", userID, err)
	}
	return nil
}

// LogAuditSink is a V1 structured-log AuditSink for the per-reality scrub
// (P2/071). Durable audit-table persistence is deferred — the per-reality scrub
// is a per-reality projection write (not a meta-table MetaWrite), so its audit
// home (a per-reality audit table vs service_to_service_audit) is a follow-up
// decision; for V1 we emit a structured log line per scrub (Q-L1A-3 visibility).
type LogAuditSink struct{}

var _ uew.AuditSink = LogAuditSink{}

// WriteAudit logs the scrub. Never errors (a log write must not NACK erasure).
func (LogAuditSink) WriteAudit(_ context.Context, e uew.AuditEntry) error {
	slog.Info("[user-erased] per-reality scrub",
		"event_id", e.EventID, "user_id", e.UserID, "reality_id", e.RealityID,
		"outcome", e.Outcome, "erased_at", e.ErasedAt, "scrubbed_at", e.ScrubbedAt)
	return nil
}
