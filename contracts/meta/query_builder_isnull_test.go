package meta

import (
	"strings"
	"testing"
)

// BuildUpdate must render a nil ExpectedBefore value as `col IS NULL` (a SQL
// NULL predicate, no bound arg) rather than `col = $N` — because `col = NULL`
// is never true and would make every CAS-on-unset-column update match 0 rows.
// This is the mechanism migration 011 documents for single-transition consent
// revocation (revoke only while revoked_at IS NULL) and the cost-ledger
// pseudonymize-once guard.
func TestBuildUpdate_NilExpectedBeforeIsNull(t *testing.T) {
	in := MetaWriteIntent{
		Table:     "user_consent_ledger",
		Operation: OpUpdate,
		PK: map[string]any{
			"user_ref_id":   "u1",
			"consent_scope": "core_service",
			"scope_version": "v1",
		},
		NewValues:      map[string]any{"revoked_at": int64(123), "revoke_reason": "erasure"},
		ExpectedBefore: map[string]any{"revoked_at": nil},
	}
	q, args, err := PostgresQueryBuilder{}.BuildUpdate(in)
	if err != nil {
		t.Fatalf("BuildUpdate: %v", err)
	}
	if !strings.Contains(q, `"revoked_at" IS NULL`) {
		t.Fatalf("expected `\"revoked_at\" IS NULL` predicate, got: %s", q)
	}
	// The WHERE clause must use IS NULL, not a bound predicate. (The SET clause
	// legitimately contains `"revoked_at" = $N` — that's NewValues, not the CAS.)
	where := q[strings.Index(q, " WHERE "):]
	if strings.Contains(where, `"revoked_at" = $`) {
		t.Fatalf("nil ExpectedBefore must NOT bind a placeholder in WHERE: %s", where)
	}
	// args = NewValues (2) + PK (3); the nil ExpectedBefore contributes NO arg.
	if len(args) != 5 {
		t.Fatalf("expected 5 bound args (2 SET + 3 PK, 0 for IS NULL), got %d: %v", len(args), args)
	}
	for _, a := range args {
		if a == nil {
			t.Fatalf("no bound arg may be nil (the IS NULL predicate must not bind one): %v", args)
		}
	}
}

// A non-nil ExpectedBefore value still binds `col = $N` (regression guard).
func TestBuildUpdate_NonNilExpectedBeforeBinds(t *testing.T) {
	in := MetaWriteIntent{
		Table:          "realities",
		Operation:      OpUpdate,
		PK:             map[string]any{"id": "r1"},
		NewValues:      map[string]any{"status": "ready"},
		ExpectedBefore: map[string]any{"status": "provisioning"},
	}
	q, args, err := PostgresQueryBuilder{}.BuildUpdate(in)
	if err != nil {
		t.Fatalf("BuildUpdate: %v", err)
	}
	if !strings.Contains(q, `"status" = $`) {
		t.Fatalf("non-nil ExpectedBefore must bind a placeholder: %s", q)
	}
	// SET status + PK id + ExpectedBefore status = 3 args.
	if len(args) != 3 {
		t.Fatalf("expected 3 bound args, got %d: %v", len(args), args)
	}
}
