package api

import (
	"context"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/loreweave/book-service/internal/config"
)

// P2·F tenant-boundary audit — executable guards on the emit DECISION (which
// crossings audit, with what outcome) and on the coalesced insert SHAPE. Both
// run without a real DB: authBook's emit fires before any pool access, and the
// insert is exercised through the auditQuerier seam with a capturing fake.

// auditCall records one emitTenantAudit invocation.
type auditCall struct {
	actor, book, owner uuid.UUID
	outcome            string
}

// auditTestServer builds a nil-pool Server with a stubbed resolver + a spy emit.
func auditTestServer(resolve func(ctx context.Context, bookID, userID uuid.UUID) (GrantLevel, uuid.UUID, string, error)) (*Server, *[]auditCall) {
	s := NewServer(nil, &config.Config{
		JWTSecret:            grantMapSecret,
		InternalServiceToken: "itok",
	})
	s.resolveBook = resolve
	calls := &[]auditCall{}
	s.emitTenantAudit = func(actor, book, owner uuid.UUID, outcome string) {
		*calls = append(*calls, auditCall{actor, book, owner, outcome})
	}
	return s, calls
}

// jwtForSubject mints a valid HS256 token whose subject is `sub` (the caller id).
func jwtForSubject(t *testing.T, sub uuid.UUID) string {
	t.Helper()
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, jwt.RegisteredClaims{
		Subject:   sub.String(),
		ExpiresAt: jwt.NewNumericDate(time.Now().Add(time.Hour)),
	})
	signed, err := tok.SignedString([]byte(grantMapSecret))
	if err != nil {
		t.Fatalf("sign jwt: %v", err)
	}
	return signed
}

// callAuthBook drives authBook directly with a caller-bearing request so the
// emit decision is observed without a handler/router (which would hit the nil
// pool on the allow path).
func callAuthBook(t *testing.T, s *Server, caller, book uuid.UUID, need GrantLevel) (ok bool, status int) {
	t.Helper()
	req := httptest.NewRequest("GET", "/v1/books/"+book.String(), nil)
	req.Header.Set("Authorization", "Bearer "+jwtForSubject(t, caller))
	rr := httptest.NewRecorder()
	_, _, _, ok = s.authBook(rr, req, book, need)
	return ok, rr.Code
}

func TestAuthBook_EmitsGrantedOnCrossTenantRead(t *testing.T) {
	t.Parallel()
	owner := uuid.New()
	caller := uuid.New() // != owner → a pure collaborator
	s, calls := auditTestServer(func(ctx context.Context, b, u uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantView, owner, "active", nil
	})
	book := uuid.New()
	ok, _ := callAuthBook(t, s, caller, book, GrantView)
	if !ok {
		t.Fatalf("expected authBook to allow a sufficient cross-tenant read")
	}
	if len(*calls) != 1 {
		t.Fatalf("expected exactly one audit emit, got %d", len(*calls))
	}
	c := (*calls)[0]
	if c.outcome != auditOutcomeGranted || c.owner != owner || c.book != book || c.actor != caller {
		t.Errorf("granted cross-tenant emit wrong: %+v (want granted, owner=%s, book=%s, actor=%s)", c, owner, book, caller)
	}
}

func TestAuthBook_EmitsDeniedOnUnderGrant(t *testing.T) {
	t.Parallel()
	owner := uuid.New()
	s, calls := auditTestServer(func(ctx context.Context, b, u uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantView, owner, "active", nil // has view…
	})
	_, status := callAuthBook(t, s, uuid.New(), uuid.New(), GrantEdit) // …but needs edit
	if status != 403 {
		t.Fatalf("under-grant expected 403, got %d", status)
	}
	if len(*calls) != 1 || (*calls)[0].outcome != auditOutcomeDenied {
		t.Errorf("expected one 'denied' emit, got %+v", *calls)
	}
}

func TestAuthBook_EmitsDeniedOnNoGrantExistingBook(t *testing.T) {
	t.Parallel()
	owner := uuid.New() // book EXISTS (owner known) but caller has no grant
	s, calls := auditTestServer(func(ctx context.Context, b, u uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantNone, owner, "", nil
	})
	_, status := callAuthBook(t, s, uuid.New(), uuid.New(), GrantView)
	if status != 404 {
		t.Fatalf("no-grant on existing book expected 404, got %d", status)
	}
	if len(*calls) != 1 || (*calls)[0].outcome != auditOutcomeDenied {
		t.Errorf("expected one 'denied' emit on a no-grant existing book, got %+v", *calls)
	}
}

func TestAuthBook_NoEmitOnOwnBook(t *testing.T) {
	t.Parallel()
	caller := uuid.New()
	s, calls := auditTestServer(func(ctx context.Context, b, u uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantOwner, caller, "active", nil // owner == caller
	})
	ok, _ := callAuthBook(t, s, caller, uuid.New(), GrantView)
	if !ok {
		t.Fatalf("owner should be allowed")
	}
	if len(*calls) != 0 {
		t.Errorf("own-book access must not audit, got %+v", *calls)
	}
}

func TestAuthBook_NoEmitOnMissingBook(t *testing.T) {
	t.Parallel()
	s, calls := auditTestServer(func(ctx context.Context, b, u uuid.UUID) (GrantLevel, uuid.UUID, string, error) {
		return GrantNone, uuid.Nil, "", nil // missing book — no owner, no tenant
	})
	_, status := callAuthBook(t, s, uuid.New(), uuid.New(), GrantView)
	if status != 404 {
		t.Fatalf("missing book expected 404, got %d", status)
	}
	if len(*calls) != 0 {
		t.Errorf("a missing book is not a tenant crossing; must not audit, got %+v", *calls)
	}
}

// --- insert shape + bucket coalescing ------------------------------------

// fakeQuerier captures the SQL + args of the one Exec insertTenantAudit runs.
type fakeQuerier struct {
	sql  string
	args []any
	err  error
}

func (f *fakeQuerier) Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error) {
	f.sql = sql
	f.args = args
	return pgconn.CommandTag{}, f.err
}

func TestInsertTenantAudit_CoalescedInsertShape(t *testing.T) {
	t.Parallel()
	fq := &fakeQuerier{}
	actor, book, owner := uuid.New(), uuid.New(), uuid.New()
	bucket := time.Date(2026, 7, 5, 10, 0, 0, 0, time.UTC)
	if err := insertTenantAudit(context.Background(), fq, actor, book, owner, auditOutcomeGranted, bucket); err != nil {
		t.Fatalf("insert: %v", err)
	}
	// The load-bearing coalescing clause — a redelivery/re-read in the same window
	// must be a no-op, not a duplicate row. Assert the EXACT ON CONFLICT column tuple
	// (not just "ON CONFLICT"): it must match uq_tenant_audit_window's columns in
	// migrate.go, or a real insert raises "no unique constraint matching" at runtime
	// (review MED-3 — book has no real-PG harness, so this string coupling + the
	// migrate index-column test are the guard; glossary proves the effect live).
	if !strings.Contains(fq.sql, "ON CONFLICT (actor_id, book_id, outcome, coalesce_bucket) DO NOTHING") {
		t.Errorf("insert must coalesce via the exact ON CONFLICT tuple matching uq_tenant_audit_window; sql:\n%s", fq.sql)
	}
	if !strings.Contains(fq.sql, "tenant_access_audit") {
		t.Errorf("insert targets the wrong table:\n%s", fq.sql)
	}
	// Args in declared order: actor, book, owner, outcome, bucket. No free-text
	// detail arg exists — the row is ids + enum + bucket only (structural scrub).
	if len(fq.args) != 5 {
		t.Fatalf("want 5 args (actor, book, owner, outcome, bucket), got %d: %v", len(fq.args), fq.args)
	}
	if fq.args[0] != actor || fq.args[1] != book || fq.args[2] != owner ||
		fq.args[3] != auditOutcomeGranted || fq.args[4] != bucket {
		t.Errorf("insert args out of order/shape: %v", fq.args)
	}
}

func TestTenantAuditDedup_FirstInWindow(t *testing.T) {
	t.Parallel()
	d := &tenantAuditDedup{}
	b1 := time.Date(2026, 7, 5, 10, 0, 0, 0, time.UTC)
	// First sighting of a key this window → true; repeat → false (skip the write).
	if !d.firstInWindow("a|b|granted", b1) {
		t.Fatal("first sighting must be first-in-window")
	}
	if d.firstInWindow("a|b|granted", b1) {
		t.Fatal("a repeat in the same window must be suppressed")
	}
	// A DIFFERENT outcome for the same (actor,book) is a distinct key → emitted.
	if !d.firstInWindow("a|b|denied", b1) {
		t.Fatal("a different outcome is a distinct key — must emit")
	}
	// A new window resets the set → the same key emits again (matches the DB
	// coalesce bucket rolling over).
	b2 := b1.Add(time.Hour)
	if !d.firstInWindow("a|b|granted", b2) {
		t.Fatal("a new window must re-emit (bucket reset)")
	}
}

func TestBucketFor_TruncatesToWindow(t *testing.T) {
	t.Parallel()
	now := time.Date(2026, 7, 5, 10, 42, 37, 500, time.UTC)
	// 1h window → floor to 10:00:00.
	if got := bucketFor(now, 3600); !got.Equal(time.Date(2026, 7, 5, 10, 0, 0, 0, time.UTC)) {
		t.Errorf("1h bucket = %v, want 10:00:00", got)
	}
	// Two reads in the same window share a bucket (⇒ ON CONFLICT collapses them).
	a := bucketFor(time.Date(2026, 7, 5, 10, 5, 0, 0, time.UTC), 3600)
	b := bucketFor(time.Date(2026, 7, 5, 10, 55, 0, 0, time.UTC), 3600)
	if !a.Equal(b) {
		t.Errorf("same-window reads must share a bucket: %v != %v", a, b)
	}
	// A zero/negative window is floored to 1s (never a zero-duration truncate).
	if got := bucketFor(now, 0); got.IsZero() {
		t.Errorf("zero window must floor to 1s, not produce a zero time")
	}
}
