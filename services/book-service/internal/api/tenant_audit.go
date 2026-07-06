package api

import (
	"context"
	"log/slog"
	"sync"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"
)

// P2·F — tenant-boundary audit emit.
//
// A cross-tenant access is a caller touching a book they do NOT own — either a
// collaborator reading/writing (outcome 'granted') or an under-grant / no-grant
// attempt on an EXISTING book (outcome 'denied'). A missing book is NOT a crossing
// (there is no tenant to cross into) and is never audited; nor is an own-book
// access. See authBook for the emit decision.
//
// Volume: authBook runs on every per-book route with no request-scoped
// memoization, so a naive per-read emit would flood the table. We coalesce to the
// FIRST access per (actor, book, outcome) per configurable window via an
// ON CONFLICT DO NOTHING against uq_tenant_audit_window — "first-access-per-
// window" (the practical stand-in for first-access-per-session; there is no
// session id at this layer).
//
// The row carries ONLY ids + an outcome enum + a truncated bucket timestamp — no
// free text, path, or payload — so the "no un-scrubbed PII" guarantee is
// structural, not a scrub step.
//
// SCOPE (review LOW-1): this audits book-service's OWN per-book HTTP routes
// (authBook). A collaborator reaching a book through a SIBLING service (knowledge/
// translation/chat resolve grants via /internal/.../access) is audited by THAT
// service's own path (glossary does), not double-counted here — so
// `tenant_access_audit` is per-service, not one platform-wide log.
//
// COALESCE-KEY (review LOW-2): the window key is (actor,book,outcome), EXCLUDING
// owner_id (it matches the DB uq_tenant_audit_window index). A book whose ownership
// transferred mid-window would keep the first row's now-stale owner until the next
// window — an accepted edge (the row is bucketed/timestamped; forensics tolerate it).

const (
	auditOutcomeGranted = "granted"
	auditOutcomeDenied  = "denied"
)

// tenantAuditDedupCap bounds the in-process dedup cache so a wide burst of DISTINCT
// (actor,book,outcome) crossings can't grow it without limit. Past the cap we stop
// caching and emit anyway — correctness (one row per window) is still guaranteed by
// the DB ON CONFLICT; the cache is only an optimization to skip redundant work.
const tenantAuditDedupCap = 100_000

// tenantAuditDedup realizes the feature's "first-per-window" guarantee at the WRITE
// path, not just at stored rows. Without it, emitTenantAudit spawns a goroutine +
// DB round-trip on EVERY cross-tenant call (authBook runs per per-book route), so a
// collaborator paging N chapters would fire N goroutines + N inserts to persist ONE
// row (the DB ON CONFLICT dedups the row post-hoc, but the write amplification +
// pool contention with real request traffic is real). This skips the goroutine when
// the same (actor,book,outcome) was already emitted THIS window. Resets each window.
// The key deliberately EXCLUDES owner_id, matching the DB coalesce index columns.
type tenantAuditDedup struct {
	mu     sync.Mutex
	bucket time.Time
	seen   map[string]struct{}
}

// firstInWindow reports whether (key, bucket) has NOT yet been emitted this window
// (recording it if so). A new bucket resets the set. Past the cap it stops caching
// and returns true (emit; the DB still dedups the row).
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
// *pgxpool.Pool and by pgxmock, so the SQL is unit-testable without a real DB.
type auditQuerier interface {
	Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error)
}

// bucketFor truncates now to the coalescing window start. A window <= 0 is
// treated as 1s (the config loader already floors it, but guard here too so a
// struct-literal Server in a test can't produce a zero-duration truncate).
func bucketFor(now time.Time, windowSeconds int64) time.Time {
	if windowSeconds < 1 {
		windowSeconds = 1
	}
	return now.Truncate(time.Duration(windowSeconds) * time.Second)
}

// insertTenantAudit performs the coalesced append-only insert. Synchronous and
// pool-agnostic (takes the querier) so a pgxmock test can assert the exact SQL
// shape + the ON CONFLICT DO NOTHING coalescing. Returns any DB error to the
// caller (the async wrapper logs it); it never affects the request outcome.
func insertTenantAudit(ctx context.Context, q auditQuerier, actorID, bookID, ownerID uuid.UUID, outcome string, bucket time.Time) error {
	_, err := q.Exec(ctx, `
		INSERT INTO tenant_access_audit (actor_id, book_id, owner_id, outcome, coalesce_bucket)
		VALUES ($1, $2, $3, $4, $5)
		ON CONFLICT (actor_id, book_id, outcome, coalesce_bucket) DO NOTHING
	`, actorID, bookID, ownerID, outcome, bucket)
	return err
}

// asyncTenantAudit is the production emit wired into Server.emitTenantAudit. It
// fire-and-forgets on a background context (the request ctx cancels the moment
// the response is written, which would abort the insert) with a short timeout,
// recovers from panics, and logs any failure — a best-effort audit must NEVER
// block or fail a request. A nil pool (struct-literal Server) makes it a no-op.
func (s *Server) asyncTenantAudit(actorID, bookID, ownerID uuid.UUID, outcome string) {
	if s.pool == nil {
		return
	}
	window := int64(3600)
	if s.cfg != nil {
		window = s.cfg.TenantAuditCoalesceWindowSeconds
	}
	bucket := bucketFor(time.Now().UTC(), window)
	// First-per-window at the write path: skip the goroutine+DB round-trip when this
	// (actor,book,outcome) was already emitted this window. Key excludes owner_id to
	// match the DB coalesce index. nil guard keeps a struct-literal Server safe.
	if s.auditDedup != nil {
		key := actorID.String() + "|" + bookID.String() + "|" + outcome
		if !s.auditDedup.firstInWindow(key, bucket) {
			return
		}
	}
	go func() {
		defer func() {
			if r := recover(); r != nil {
				slog.Error("book-service: tenant-audit emit panicked",
					"actor", actorID, "book", bookID, "outcome", outcome, "panic", r)
			}
		}()
		ctx, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		defer cancel()
		if err := insertTenantAudit(ctx, s.pool, actorID, bookID, ownerID, outcome, bucket); err != nil {
			slog.Error("book-service: tenant-audit emit failed",
				"actor", actorID, "book", bookID, "outcome", outcome, "err", err)
		}
	}()
}
