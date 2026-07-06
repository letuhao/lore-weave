package api

import (
	"context"
	"log/slog"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"
)

// P2·F — tenant-boundary audit emit (glossary variant).
//
// glossary resolves grants via a cross-service ResolveAccess that returns only a
// Level (none<view<edit<manage<owner), NOT the book owner. So a crossing is
// detected as: the caller holds a REAL sub-owner grant (view/edit/manage) on a
// book — i.e. a collaborator reaching another user's book-scoped glossary. We emit
// 'granted' when that grant satisfies the required level, 'denied' when it is
// below it. Level==owner is the caller's own tenant (no emit); Level==none is
// skipped — at this layer it cannot be distinguished from a missing book (no
// confirmed tenant to cross), so auditing it would log probes of nonexistent
// books. The outcome reflects the GRANT (tenant-boundary) decision, not a
// downstream lifecycle/OD-8 gate.
//
// Coalesced first-per-window (ON CONFLICT DO NOTHING) because requireGrant fires a
// cross-service ResolveAccess per request. The row is ids + outcome enum + bucket
// only — no free text — so the "no un-scrubbed PII" guarantee is structural.

const (
	auditOutcomeGranted = "granted"
	auditOutcomeDenied  = "denied"
)

// tenantAuditDedupCap bounds the in-process dedup cache — past it we stop caching
// and emit anyway (the DB ON CONFLICT still guarantees one row per window).
const tenantAuditDedupCap = 100_000

// tenantAuditDedup realizes "first-per-window" at the WRITE path, not just at stored
// rows. checkGrant fires a cross-service ResolveAccess per request, so without this a
// collaborator browsing N entities would spawn N goroutines + N inserts to persist
// ONE row. This skips the goroutine when the same (actor,book,outcome) was already
// emitted this window; resets each window. Key excludes owner (glossary has none).
type tenantAuditDedup struct {
	mu     sync.Mutex
	bucket time.Time
	seen   map[string]struct{}
}

func (d *tenantAuditDedup) firstInWindow(key string, bucket time.Time) bool {
	d.mu.Lock()
	defer d.mu.Unlock()
	if !bucket.Equal(d.bucket) {
		d.bucket = bucket
		d.seen = make(map[string]struct{})
	}
	if _, ok := d.seen[key]; ok {
		return false
	}
	if len(d.seen) < tenantAuditDedupCap {
		d.seen[key] = struct{}{}
	}
	return true
}

// auditQuerier is the minimal DB surface insertTenantAudit needs — satisfied by
// *pgxpool.Pool and a capturing test fake.
type auditQuerier interface {
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
}

// bucketFor truncates now to the coalescing window start (window <= 0 → 1s).
func bucketFor(now time.Time, windowSeconds int64) time.Time {
	if windowSeconds < 1 {
		windowSeconds = 1
	}
	return now.Truncate(time.Duration(windowSeconds) * time.Second)
}

// insertTenantAudit performs the coalesced append-only insert (no owner column —
// glossary doesn't know the book owner at resolve time).
func insertTenantAudit(ctx context.Context, q auditQuerier, actorID, bookID uuid.UUID, outcome string, bucket time.Time) error {
	_, err := q.Exec(ctx, `
		INSERT INTO tenant_access_audit (actor_id, book_id, outcome, coalesce_bucket)
		VALUES ($1, $2, $3, $4)
		ON CONFLICT (actor_id, book_id, outcome, coalesce_bucket) DO NOTHING
	`, actorID, bookID, outcome, bucket)
	return err
}

// asyncTenantAudit is the production emit wired into Server.emitTenantAudit.
// Fire-and-forget on a background context (the request ctx cancels on response),
// panic-recovered, error-logged; a nil pool makes it a no-op.
func (s *Server) asyncTenantAudit(actorID, bookID uuid.UUID, outcome string) {
	if s.pool == nil {
		return
	}
	window := int64(3600)
	if s.cfg != nil {
		window = s.cfg.TenantAuditCoalesceWindowSeconds
	}
	bucket := bucketFor(time.Now().UTC(), window)
	// First-per-window at the write path: skip the goroutine+insert on a repeat this
	// window. nil guard keeps a struct-literal Server safe.
	if s.auditDedup != nil {
		key := actorID.String() + "|" + bookID.String() + "|" + outcome
		if !s.auditDedup.firstInWindow(key, bucket) {
			return
		}
	}
	go func() {
		defer func() {
			if r := recover(); r != nil {
				slog.Error("glossary: tenant-audit emit panicked",
					"actor", actorID, "book", bookID, "outcome", outcome, "panic", r)
			}
		}()
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := insertTenantAudit(ctx, s.pool, actorID, bookID, outcome, bucket); err != nil {
			slog.Error("glossary: tenant-audit emit failed",
				"actor", actorID, "book", bookID, "outcome", outcome, "err", err)
		}
	}()
}
