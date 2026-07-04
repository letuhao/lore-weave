package api

import (
	"context"
	"log/slog"
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

const (
	auditOutcomeGranted = "granted"
	auditOutcomeDenied  = "denied"
)

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
