package api

import (
	"context"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgconn"

	"github.com/loreweave/grantclient"
)

// P2·F glossary tenant-boundary audit — executable guards on the emit DECISION
// (which crossings audit, with what outcome) and the coalesced insert SHAPE.
// Grant resolution goes through a fake book-service (projection helpers in
// ownership_test.go); the emit is captured by a synchronous spy.

type auditCall struct {
	actor, book uuid.UUID
	outcome     string
}

// auditSpyServer wraps ownershipTestServer's grant wiring with a spy emit.
func auditSpyServer(t *testing.T, book, owner, grantee uuid.UUID) (*Server, *[]auditCall) {
	t.Helper()
	s := ownershipTestServer(t, projectionWithShare(book, owner, grantee))
	calls := &[]auditCall{}
	s.emitTenantAudit = func(actor, bk uuid.UUID, outcome string) {
		*calls = append(*calls, auditCall{actor, bk, outcome})
	}
	return s, calls
}

func TestCheckGrant_EmitsGrantedForCollaborator(t *testing.T) {
	owner, grantee, book := uuid.New(), uuid.New(), uuid.New()
	s, calls := auditSpyServer(t, book, owner, grantee)
	// grantee holds a manage SHARE (< owner) → a collaborator crossing; view is satisfied.
	if err := s.checkGrant(context.Background(), book, grantee, grantclient.GrantView); err != nil {
		t.Fatalf("collaborator view should pass, got %v", err)
	}
	if len(*calls) != 1 || (*calls)[0].outcome != auditOutcomeGranted ||
		(*calls)[0].actor != grantee || (*calls)[0].book != book {
		t.Fatalf("want one 'granted' emit for the collaborator, got %+v", *calls)
	}
}

func TestCheckGrant_EmitsDeniedForUnderGrantCollaborator(t *testing.T) {
	owner, grantee, book := uuid.New(), uuid.New(), uuid.New()
	s, calls := auditSpyServer(t, book, owner, grantee)
	// grantee has manage but needs owner → a denied cross-tenant attempt.
	_ = s.checkGrant(context.Background(), book, grantee, grantclient.GrantOwner)
	if len(*calls) != 1 || (*calls)[0].outcome != auditOutcomeDenied {
		t.Fatalf("want one 'denied' emit for the under-grant collaborator, got %+v", *calls)
	}
}

func TestCheckGrant_NoEmitForOwner(t *testing.T) {
	owner, grantee, book := uuid.New(), uuid.New(), uuid.New()
	s, calls := auditSpyServer(t, book, owner, grantee)
	if err := s.checkGrant(context.Background(), book, owner, grantclient.GrantView); err != nil {
		t.Fatalf("owner should pass, got %v", err)
	}
	if len(*calls) != 0 {
		t.Errorf("own-tenant access (owner) must not audit, got %+v", *calls)
	}
}

func TestCheckGrant_NoEmitForNonGrantee(t *testing.T) {
	owner, grantee, book := uuid.New(), uuid.New(), uuid.New()
	s, calls := auditSpyServer(t, book, owner, grantee)
	// A random caller with no grant → Level==none → skipped (can't confirm a
	// tenant from `none`; avoids auditing probes of nonexistent/unshared books).
	_ = s.checkGrant(context.Background(), book, uuid.New(), grantclient.GrantView)
	if len(*calls) != 0 {
		t.Errorf("a Level==none caller must not audit (no confirmed tenant), got %+v", *calls)
	}
}

// --- insert shape + bucket coalescing ------------------------------------

type fakeQuerier struct {
	sql  string
	args []any
}

func (f *fakeQuerier) Exec(ctx context.Context, sql string, args ...any) (pgconn.CommandTag, error) {
	f.sql, f.args = sql, args
	return pgconn.CommandTag{}, nil
}

func TestInsertTenantAudit_CoalescedInsertShape(t *testing.T) {
	t.Parallel()
	fq := &fakeQuerier{}
	actor, book := uuid.New(), uuid.New()
	bucket := time.Date(2026, 7, 5, 10, 0, 0, 0, time.UTC)
	if err := insertTenantAudit(context.Background(), fq, actor, book, auditOutcomeGranted, bucket); err != nil {
		t.Fatalf("insert: %v", err)
	}
	if !strings.Contains(fq.sql, "ON CONFLICT") || !strings.Contains(fq.sql, "DO NOTHING") {
		t.Errorf("insert must coalesce via ON CONFLICT DO NOTHING; sql:\n%s", fq.sql)
	}
	if !strings.Contains(fq.sql, "tenant_access_audit") {
		t.Errorf("wrong table:\n%s", fq.sql)
	}
	// 4 args (no owner column in glossary): actor, book, outcome, bucket. No
	// free-text detail arg — structural scrub.
	if len(fq.args) != 4 {
		t.Fatalf("want 4 args (actor, book, outcome, bucket), got %d: %v", len(fq.args), fq.args)
	}
	if fq.args[0] != actor || fq.args[1] != book || fq.args[2] != auditOutcomeGranted || fq.args[3] != bucket {
		t.Errorf("insert args out of order/shape: %v", fq.args)
	}
}

func TestBucketFor_TruncatesToWindow(t *testing.T) {
	t.Parallel()
	a := bucketFor(time.Date(2026, 7, 5, 10, 5, 0, 0, time.UTC), 3600)
	b := bucketFor(time.Date(2026, 7, 5, 10, 55, 0, 0, time.UTC), 3600)
	if !a.Equal(b) || !a.Equal(time.Date(2026, 7, 5, 10, 0, 0, 0, time.UTC)) {
		t.Errorf("same-window reads must share the 10:00 bucket: %v, %v", a, b)
	}
	if bucketFor(time.Now(), 0).IsZero() {
		t.Errorf("zero window must floor to 1s, not a zero time")
	}
}
