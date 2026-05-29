package service_acl

import (
	"errors"
	"strings"
	"testing"

	"github.com/google/uuid"
)

const fixtureMinimal = `
version: 1
services:
  - name: meta-worker
    svid_spiffe_id: spiffe://loreweave.dev/sa/meta-worker
    rpcs:
      MetaWrite:
        allowed_callers:
          - publisher
          - migration-orchestrator
        principal_mode: either
      MetaReadSensitive:
        allowed_callers:
          - admin-cli
        principal_mode: requires_user
  - name: glossary-service
    svid_spiffe_id: spiffe://loreweave.dev/sa/glossary
    permissions:
      canon_entries: [SELECT, INSERT]
`

func mustLoad(t *testing.T, src string) *Matrix {
	t.Helper()
	m, err := LoadMatrix(strings.NewReader(src))
	if err != nil {
		t.Fatalf("LoadMatrix: %v", err)
	}
	return m
}

func TestLoadMatrix_Happy(t *testing.T) {
	m := mustLoad(t, fixtureMinimal)
	if m.Version != 1 {
		t.Fatalf("version: got %d want 1", m.Version)
	}
	if len(m.Services) != 2 {
		t.Fatalf("services: got %d want 2", len(m.Services))
	}
	svc, ok := m.FindService("meta-worker")
	if !ok || svc.Name != "meta-worker" {
		t.Fatalf("FindService(meta-worker) miss")
	}
	if _, ok := m.FindService("nobody"); ok {
		t.Fatalf("FindService(nobody) should miss")
	}
}

func TestLoadMatrix_RejectsBadVersion(t *testing.T) {
	_, err := LoadMatrix(strings.NewReader("version: 0\nservices: []"))
	if err == nil || !errors.Is(err, ErrInvalidMatrix) {
		t.Fatalf("want ErrInvalidMatrix on version 0, got %v", err)
	}
}

func TestLoadMatrix_RejectsDuplicateName(t *testing.T) {
	src := `
version: 1
services:
  - name: meta-worker
    svid_spiffe_id: a
  - name: meta-worker
    svid_spiffe_id: b
`
	_, err := LoadMatrix(strings.NewReader(src))
	if err == nil || !errors.Is(err, ErrInvalidMatrix) {
		t.Fatalf("want duplicate-name ErrInvalidMatrix, got %v", err)
	}
}

func TestLoadMatrix_RejectsEmptyAllowedCallers(t *testing.T) {
	src := `
version: 1
services:
  - name: meta-worker
    svid_spiffe_id: x
    rpcs:
      MetaWrite:
        allowed_callers: []
`
	_, err := LoadMatrix(strings.NewReader(src))
	if err == nil || !errors.Is(err, ErrInvalidMatrix) {
		t.Fatalf("want empty-allowed-callers ErrInvalidMatrix, got %v", err)
	}
}

func TestLoadMatrix_RejectsInvalidPrincipalMode(t *testing.T) {
	src := `
version: 1
services:
  - name: meta-worker
    svid_spiffe_id: x
    rpcs:
      MetaWrite:
        allowed_callers: [publisher]
        principal_mode: bogus
`
	_, err := LoadMatrix(strings.NewReader(src))
	if err == nil || !errors.Is(err, ErrInvalidMatrix) {
		t.Fatalf("want invalid-principal-mode ErrInvalidMatrix, got %v", err)
	}
}

func TestLoadMatrix_NilReader(t *testing.T) {
	_, err := LoadMatrix(nil)
	if err == nil || !errors.Is(err, ErrInvalidMatrix) {
		t.Fatalf("want nil-reader ErrInvalidMatrix, got %v", err)
	}
}

// ─────────────────────────────────────────────────────────────────────
// CheckRPCAllowed — the load-bearing default-DENY gate.
// ─────────────────────────────────────────────────────────────────────

func TestCheckRPCAllowed_Allow(t *testing.T) {
	m := mustLoad(t, fixtureMinimal)
	d, rule := m.CheckRPCAllowed("publisher", "meta-worker", "MetaWrite")
	if !d.IsAllow() {
		t.Fatalf("Allow expected, got %s", d)
	}
	if rule.PrincipalMode != PrincipalEither {
		t.Fatalf("rule principal mode either expected, got %q", rule.PrincipalMode)
	}
}

func TestCheckRPCAllowed_DenyCallerNotAllowed(t *testing.T) {
	m := mustLoad(t, fixtureMinimal)
	d, rule := m.CheckRPCAllowed("rogue-service", "meta-worker", "MetaWrite")
	if d != DenyCallerNotAllowed {
		t.Fatalf("DenyCallerNotAllowed expected, got %s", d)
	}
	// rule still returned so the audit row can carry principal_mode.
	if rule.PrincipalMode != PrincipalEither {
		t.Fatalf("rule principal mode either expected, got %q", rule.PrincipalMode)
	}
}

func TestCheckRPCAllowed_DenyDefault_UnknownCallee(t *testing.T) {
	m := mustLoad(t, fixtureMinimal)
	d, _ := m.CheckRPCAllowed("publisher", "unknown-service", "DoThing")
	if d != DenyDefault {
		t.Fatalf("DenyDefault expected, got %s", d)
	}
}

func TestCheckRPCAllowed_DenyDefault_UnknownRPC(t *testing.T) {
	m := mustLoad(t, fixtureMinimal)
	d, _ := m.CheckRPCAllowed("publisher", "meta-worker", "TotallyMadeUpRPC")
	if d != DenyDefault {
		t.Fatalf("DenyDefault expected, got %s", d)
	}
}

func TestCheckRPCAllowed_DenyDefault_NoRPCsDeclared(t *testing.T) {
	// glossary-service has only `permissions:` not `rpcs:` — so all RPC
	// checks against it default-DENY.
	m := mustLoad(t, fixtureMinimal)
	d, _ := m.CheckRPCAllowed("any", "glossary-service", "DoThing")
	if d != DenyDefault {
		t.Fatalf("DenyDefault expected for service with no rpcs map, got %s", d)
	}
}

func TestCheckRPCAllowed_NilMatrix_DenyDefault(t *testing.T) {
	var m *Matrix
	d, _ := m.CheckRPCAllowed("a", "b", "C")
	if d != DenyDefault {
		t.Fatalf("nil matrix must default-deny, got %s", d)
	}
}

func TestCheckRPCAllowed_EmptyStrings(t *testing.T) {
	m := mustLoad(t, fixtureMinimal)
	for _, tc := range []struct{ caller, callee, rpc string }{
		{"", "meta-worker", "MetaWrite"},
		{"publisher", "", "MetaWrite"},
		{"publisher", "meta-worker", ""},
	} {
		d, _ := m.CheckRPCAllowed(tc.caller, tc.callee, tc.rpc)
		if d != DenyDefault {
			t.Fatalf("empty input must default-deny: caller=%q callee=%q rpc=%q got %s",
				tc.caller, tc.callee, tc.rpc, d)
		}
	}
}

// ─────────────────────────────────────────────────────────────────────
// CheckPrincipalAllowed — only run AFTER Allow.
// ─────────────────────────────────────────────────────────────────────

func TestCheckPrincipalAllowed_Either(t *testing.T) {
	rule := RPCRule{AllowedCallers: []string{"x"}, PrincipalMode: PrincipalEither}
	if rule.CheckPrincipalAllowed(true) != Allow {
		t.Fatal("either accepts hasUser=true")
	}
	if rule.CheckPrincipalAllowed(false) != Allow {
		t.Fatal("either accepts hasUser=false")
	}
}

func TestCheckPrincipalAllowed_RequiresUser(t *testing.T) {
	rule := RPCRule{AllowedCallers: []string{"x"}, PrincipalMode: PrincipalRequiresUser}
	if rule.CheckPrincipalAllowed(true) != Allow {
		t.Fatal("requires_user accepts hasUser=true")
	}
	if rule.CheckPrincipalAllowed(false) != DenyPrincipalMismatch {
		t.Fatal("requires_user rejects hasUser=false")
	}
}

func TestCheckPrincipalAllowed_SystemOnly(t *testing.T) {
	rule := RPCRule{AllowedCallers: []string{"x"}, PrincipalMode: PrincipalSystemOnly}
	if rule.CheckPrincipalAllowed(false) != Allow {
		t.Fatal("system_only accepts hasUser=false")
	}
	if rule.CheckPrincipalAllowed(true) != DenyPrincipalMismatch {
		t.Fatal("system_only rejects hasUser=true")
	}
}

func TestCheckPrincipalAllowed_EmptyDefaultsEither(t *testing.T) {
	rule := RPCRule{AllowedCallers: []string{"x"}}
	if rule.CheckPrincipalAllowed(true) != Allow {
		t.Fatal("empty principal_mode defaults to either, accepts true")
	}
	if rule.CheckPrincipalAllowed(false) != Allow {
		t.Fatal("empty principal_mode defaults to either, accepts false")
	}
}

// ─────────────────────────────────────────────────────────────────────
// Decision.String + IsAllow
// ─────────────────────────────────────────────────────────────────────

func TestDecisionString(t *testing.T) {
	cases := map[Decision]string{
		DenyDefault:           "deny_default",
		Allow:                 "allow",
		DenyCallerNotAllowed:  "deny_caller_not_allowed",
		DenyPrincipalMismatch: "deny_principal_mismatch",
	}
	for d, want := range cases {
		if d.String() != want {
			t.Errorf("Decision(%d).String() = %q want %q", d, d.String(), want)
		}
	}
	if Decision(999).String() != "deny_unknown" {
		t.Error("unknown decision should render deny_unknown")
	}
}

func TestDefaultZeroValueIsDeny(t *testing.T) {
	// Anti-footgun: zero Decision MUST deny.
	var d Decision
	if d.IsAllow() {
		t.Fatal("zero Decision must NOT be Allow (default-deny invariant)")
	}
}

// ─────────────────────────────────────────────────────────────────────
// Live integration with the cycle-6 matrix.yaml — proves the SDK works
// against the actual checked-in file.
// ─────────────────────────────────────────────────────────────────────

func TestLoadMatrix_FromCheckedInMatrixYAML(t *testing.T) {
	// The package's own matrix.yaml is the source of truth.
	src := mustReadFile(t, "matrix.yaml")
	m, err := LoadMatrix(strings.NewReader(src))
	if err != nil {
		t.Fatalf("LoadMatrix(checked-in matrix.yaml): %v", err)
	}
	if m.Version < 1 {
		t.Fatalf("checked-in matrix.yaml must have version >= 1, got %d", m.Version)
	}

	// L4.M.1 meta-worker-rpcs entry must allow publisher → MetaWrite.
	d, _ := m.CheckRPCAllowed("publisher", "meta-worker-rpcs", "MetaWrite")
	if !d.IsAllow() {
		t.Fatalf("checked-in matrix must allow publisher → meta-worker-rpcs.MetaWrite, got %s", d)
	}

	// Negative: rogue caller must be denied.
	d, _ = m.CheckRPCAllowed("rogue", "meta-worker-rpcs", "MetaWrite")
	if d.IsAllow() {
		t.Fatalf("checked-in matrix must DENY rogue → meta-worker-rpcs.MetaWrite, got %s", d)
	}

	// requires_user principal mode honored for MetaReadSensitive.
	_, rule := m.CheckRPCAllowed("admin-cli", "meta-worker-rpcs", "MetaReadSensitive")
	if rule.PrincipalMode != PrincipalRequiresUser {
		t.Fatalf("MetaReadSensitive must declare requires_user, got %q", rule.PrincipalMode)
	}
}

func TestAuditEntry_Validate_Happy(t *testing.T) {
	uid := uuid.New()
	entry := AuditEntry{
		AuditID:        uuid.New(),
		CallerService:  "publisher",
		CalleeService:  "meta-worker",
		RPCName:        "MetaWrite",
		PrincipalMode:  PrincipalRequiresUser,
		UserRefID:      &uid,
		Result:         AuditResultOK,
		LatencyMillis:  42,
		CreatedAtNanos: 1700000000000000000,
	}
	if err := entry.Validate(); err != nil {
		t.Fatalf("happy validate: %v", err)
	}
}

func TestAuditEntry_Validate_Rejects(t *testing.T) {
	baseUID := uuid.New()
	cases := map[string]AuditEntry{
		"zero audit_id": {
			CallerService: "x", CalleeService: "y", RPCName: "Z",
			PrincipalMode: PrincipalEither, Result: AuditResultOK,
			CreatedAtNanos: 1700000000000000000,
		},
		"empty caller": {
			AuditID: uuid.New(), CalleeService: "y", RPCName: "Z",
			PrincipalMode: PrincipalEither, Result: AuditResultOK,
			CreatedAtNanos: 1700000000000000000,
		},
		"empty callee": {
			AuditID: uuid.New(), CallerService: "x", RPCName: "Z",
			PrincipalMode: PrincipalEither, Result: AuditResultOK,
			CreatedAtNanos: 1700000000000000000,
		},
		"empty rpc": {
			AuditID: uuid.New(), CallerService: "x", CalleeService: "y",
			PrincipalMode: PrincipalEither, Result: AuditResultOK,
			CreatedAtNanos: 1700000000000000000,
		},
		"invalid principal mode": {
			AuditID: uuid.New(), CallerService: "x", CalleeService: "y", RPCName: "Z",
			PrincipalMode: "bogus", Result: AuditResultOK,
			CreatedAtNanos: 1700000000000000000,
		},
		"invalid result": {
			AuditID: uuid.New(), CallerService: "x", CalleeService: "y", RPCName: "Z",
			PrincipalMode: PrincipalEither, Result: "boom",
			CreatedAtNanos: 1700000000000000000,
		},
		"negative latency": {
			AuditID: uuid.New(), CallerService: "x", CalleeService: "y", RPCName: "Z",
			PrincipalMode: PrincipalEither, Result: AuditResultOK,
			LatencyMillis:  -1,
			CreatedAtNanos: 1700000000000000000,
		},
		"implausible created_at": {
			AuditID: uuid.New(), CallerService: "x", CalleeService: "y", RPCName: "Z",
			PrincipalMode: PrincipalEither, Result: AuditResultOK,
			CreatedAtNanos: 1577836800000000000, // boundary value (== threshold, must fail)
		},
		"requires_user without user_ref_id": {
			AuditID: uuid.New(), CallerService: "x", CalleeService: "y", RPCName: "Z",
			PrincipalMode: PrincipalRequiresUser, Result: AuditResultOK,
			CreatedAtNanos: 1700000000000000000,
			UserRefID:      nil,
		},
	}
	for name, e := range cases {
		t.Run(name, func(t *testing.T) {
			if err := e.Validate(); err == nil {
				t.Fatalf("Validate must reject %q", name)
			}
		})
	}

	// Sanity: a row with all the right fields validates.
	good := AuditEntry{
		AuditID: uuid.New(), CallerService: "x", CalleeService: "y", RPCName: "Z",
		PrincipalMode: PrincipalRequiresUser, Result: AuditResultOK,
		CreatedAtNanos: 1700000000000000000,
		UserRefID:      &baseUID,
	}
	if err := good.Validate(); err != nil {
		t.Fatalf("good row must pass: %v", err)
	}
}

func TestInMemoryAuditWriter(t *testing.T) {
	w := &InMemoryAuditWriter{}
	good := AuditEntry{
		AuditID: uuid.New(), CallerService: "x", CalleeService: "y", RPCName: "Z",
		PrincipalMode: PrincipalEither, Result: AuditResultDeny,
		CreatedAtNanos: 1700000000000000000,
	}
	if err := w.WriteServiceToServiceAudit(good); err != nil {
		t.Fatalf("write good: %v", err)
	}
	if len(w.Entries) != 1 {
		t.Fatalf("Entries len got %d want 1", len(w.Entries))
	}
	// Bad row not appended.
	bad := AuditEntry{}
	if err := w.WriteServiceToServiceAudit(bad); err == nil {
		t.Fatal("bad row must be rejected")
	}
	if len(w.Entries) != 1 {
		t.Fatalf("bad row must not append; got Entries len %d want 1", len(w.Entries))
	}
}

func TestDecisionToAuditResult(t *testing.T) {
	if DecisionToAuditResult(Allow) != AuditResultOK {
		t.Error("Allow → ok")
	}
	for _, d := range []Decision{DenyDefault, DenyCallerNotAllowed, DenyPrincipalMismatch} {
		if DecisionToAuditResult(d) != AuditResultDeny {
			t.Errorf("Decision %s should map to deny", d)
		}
	}
}
