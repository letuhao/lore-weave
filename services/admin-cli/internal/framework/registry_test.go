package framework

import (
	"context"
	"errors"
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/loreweave/foundation/services/admin-cli/internal/audit_emitter"
)

// fixtureDir returns the path to the canonical registry checked into
// contracts/admin/registry. We assume tests run from the package directory;
// repo-root layout means the registry is ../../../../contracts/admin/registry.
func fixtureDir(t *testing.T) string {
	t.Helper()
	// Walk up until we find a dir containing the registry.
	wd, err := os.Getwd()
	if err != nil {
		t.Fatalf("getwd: %v", err)
	}
	for i := 0; i < 6; i++ {
		cand := filepath.Join(wd, "contracts", "admin", "registry")
		if st, err := os.Stat(cand); err == nil && st.IsDir() {
			return cand
		}
		wd = filepath.Dir(wd)
	}
	t.Fatalf("could not locate contracts/admin/registry from cwd")
	return ""
}

// TestLoadRegistry_LoadsCanonicalSet exercises the Q-L7A-1 auto-merge
// behaviour against the real registry checked into contracts/admin/registry.
// Regression target: registry never silently shrinks below 30 commands.
func TestLoadRegistry_LoadsCanonicalSet(t *testing.T) {
	reg, err := LoadRegistry(fixtureDir(t))
	if err != nil {
		t.Fatalf("LoadRegistry: %v", err)
	}
	if len(reg.Commands) < 30 {
		t.Fatalf("Q-L7A-1 regression: only %d commands loaded; expected >=30", len(reg.Commands))
	}
	if len(reg.Commands) > 40 {
		t.Fatalf("registry bloat: %d commands; cycle 36 ceiling is ~32 (re-review scope)", len(reg.Commands))
	}
	// Every domain present.
	want := []string{"reality", "erasure", "canon", "projection", "backup", "archive", "migration", "incident", "ops"}
	have := map[string]bool{}
	for _, d := range reg.Domains {
		have[d] = true
	}
	for _, d := range want {
		if !have[d] {
			t.Errorf("Q-L7A-1: missing domain %q in registry (auto-merge dropped a file?)", d)
		}
	}
}

// TestLoadRegistry_Tier1RequiresDryRunAndApproval asserts the policy gate at
// load time — tier-1 destructive commands without dry_run_required +
// double_approval_required are rejected during LoadRegistry.
func TestLoadRegistry_Tier1RequiresDryRunAndApproval(t *testing.T) {
	dir := t.TempDir()
	bad := []byte(`domain: reality
commands:
  - name: reality bad-tier-1
    version: "1.0.0"
    summary: "missing dry-run + double-approval"
    handler: x
    impact_class: tier-1-destructive
    dry_run_required: false
    double_approval_required: false
    carry_forward_cycle: "36"
    locked_qs_consumed: [Q-L7A-1]
`)
	if err := os.WriteFile(filepath.Join(dir, "reality.yaml"), bad, 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	_, err := LoadRegistry(dir)
	if err == nil {
		t.Fatal("expected error rejecting tier-1 without dry_run_required")
	}
	if !errors.Is(err, ErrRegistry) {
		t.Fatalf("want ErrRegistry, got %v", err)
	}
	if !strings.Contains(err.Error(), "dry_run_required") {
		t.Fatalf("expected dry_run_required violation, got %v", err)
	}
}

// TestLoadRegistry_DomainPrefixEnforced — a command name MUST start with its
// domain (so dispatcher can route `<domain> <verb>`).
func TestLoadRegistry_DomainPrefixEnforced(t *testing.T) {
	dir := t.TempDir()
	bad := []byte(`domain: reality
commands:
  - name: erasure misplaced
    version: "1.0.0"
    summary: "wrong domain prefix"
    handler: x
    impact_class: tier-3-informational
    dry_run_required: false
    double_approval_required: false
    carry_forward_cycle: "36"
    locked_qs_consumed: [Q-L7A-1]
`)
	if err := os.WriteFile(filepath.Join(dir, "reality.yaml"), bad, 0o644); err != nil {
		t.Fatalf("write: %v", err)
	}
	_, err := LoadRegistry(dir)
	if err == nil {
		t.Fatal("expected domain-prefix violation")
	}
	if !strings.Contains(err.Error(), "domain prefix") {
		t.Fatalf("want domain prefix error, got %v", err)
	}
}

// TestRun_AuditEmittedBeforeAndAfter — the framework MUST write 2 audit rows
// (Before + After) on successful invocation. Verifies the audit hook lives at
// framework level (DRY) and handlers don't need to think about it.
func TestRun_AuditEmittedBeforeAndAfter(t *testing.T) {
	t.Setenv("ADMIN_CLI_ALLOW_DEV_TOKENS", "1")
	c := &Command{
		Domain:                 "reality",
		Name:                   "reality stats",
		Verb:                   "stats",
		Version:                "1.0.0",
		Summary:                "test",
		ImpactClass:            Tier3Informational,
		DryRunRequired:         false,
		DoubleApprovalRequired: false,
		Params:                 []Param{{Name: "reality_id", Type: "uuid", Required: true}},
	}
	mem := audit_emitter.NewMemorySink()
	emitter := audit_emitter.New(mem, nil)
	handler := func(_ context.Context, _ Invocation) (string, error) { return "ok", nil }
	inv := Invocation{Command: c, Params: map[string]string{"reality_id": "abc"}, Reason: "stats query test"}
	out, err := Run(context.Background(), c, inv, "dev:ops:sre:admin:read", handler, emitter)
	if err != nil {
		t.Fatalf("Run: %v", err)
	}
	if out != "ok" {
		t.Fatalf("want ok, got %q", out)
	}
	if got := mem.Count(); got != 2 {
		t.Fatalf("want 2 audit rows (Before + After), got %d", got)
	}
	rows := mem.All()
	if rows[0].Outcome != "started" {
		t.Fatalf("row 0 outcome want started, got %q", rows[0].Outcome)
	}
	if rows[1].Outcome != "succeeded" {
		t.Fatalf("row 1 outcome want succeeded, got %q", rows[1].Outcome)
	}
}

// TestRun_FailureEmitsAuditFailure — handler error => "failed" audit row.
func TestRun_FailureEmitsAuditFailure(t *testing.T) {
	t.Setenv("ADMIN_CLI_ALLOW_DEV_TOKENS", "1")
	c := &Command{
		Domain: "reality", Name: "reality stats", Verb: "stats",
		ImpactClass: Tier3Informational, Version: "1.0.0",
	}
	mem := audit_emitter.NewMemorySink()
	emitter := audit_emitter.New(mem, nil)
	handler := func(_ context.Context, _ Invocation) (string, error) { return "", errors.New("backend boom") }
	inv := Invocation{Command: c}
	_, err := Run(context.Background(), c, inv, "dev:ops:sre:admin:read", handler, emitter)
	if err == nil {
		t.Fatal("expected error from handler")
	}
	rows := mem.All()
	if len(rows) != 2 {
		t.Fatalf("want 2 rows (Before + Failure), got %d", len(rows))
	}
	if rows[1].Outcome != "failed" {
		t.Fatalf("want failed, got %q", rows[1].Outcome)
	}
	if rows[1].ErrorDetailHash == "" {
		t.Fatal("ErrorDetailHash should be set on failure")
	}
}

// TestRun_Tier1RequiresDryRunOrConfirm — operator must pass --dry-run or --confirm.
func TestRun_Tier1RequiresDryRunOrConfirm(t *testing.T) {
	t.Setenv("ADMIN_CLI_ALLOW_DEV_TOKENS", "1")
	c := &Command{
		Domain: "reality", Name: "reality force-close", Verb: "force-close",
		ImpactClass: Tier1Destructive, Version: "1.0.0",
		DryRunRequired: true, DoubleApprovalRequired: true,
	}
	mem := audit_emitter.NewMemorySink()
	emitter := audit_emitter.New(mem, nil)
	handler := func(_ context.Context, _ Invocation) (string, error) { return "ok", nil }
	// Neither dry-run nor confirm.
	inv := Invocation{Command: c, Reason: "incident response, freezing"}
	_, err := Run(context.Background(), c, inv, "dev:ops:sre:admin:destructive", handler, emitter)
	if err == nil {
		t.Fatal("expected dry_run gate failure")
	}
	if !strings.Contains(err.Error(), "--dry-run") || !strings.Contains(err.Error(), "--confirm") {
		t.Fatalf("expected dry-run/confirm message, got %v", err)
	}
}

// TestRun_Tier1RequiresSecondActor — --confirm + tier-1 without --second-actor rejected.
func TestRun_Tier1RequiresSecondActor(t *testing.T) {
	t.Setenv("ADMIN_CLI_ALLOW_DEV_TOKENS", "1")
	c := &Command{
		Domain: "reality", Name: "reality force-close", Verb: "force-close",
		ImpactClass: Tier1Destructive, Version: "1.0.0",
		DryRunRequired: true, DoubleApprovalRequired: true,
	}
	mem := audit_emitter.NewMemorySink()
	emitter := audit_emitter.New(mem, nil)
	handler := func(_ context.Context, _ Invocation) (string, error) { return "ok", nil }
	inv := Invocation{Command: c, Confirm: true, Reason: "incident response, freezing"}
	_, err := Run(context.Background(), c, inv, "dev:ops:sre:admin:destructive", handler, emitter)
	if err == nil {
		t.Fatal("expected double-approval gate failure")
	}
	if !strings.Contains(err.Error(), "second-actor") {
		t.Fatalf("expected --second-actor message, got %v", err)
	}
}

// TestRun_AuthRejectsBadScope — calling tier-1 with admin:read only is rejected.
func TestRun_AuthRejectsBadScope(t *testing.T) {
	t.Setenv("ADMIN_CLI_ALLOW_DEV_TOKENS", "1")
	c := &Command{
		Domain: "reality", Name: "reality force-close", Verb: "force-close",
		ImpactClass: Tier1Destructive, Version: "1.0.0",
		DryRunRequired: true, DoubleApprovalRequired: true,
	}
	mem := audit_emitter.NewMemorySink()
	emitter := audit_emitter.New(mem, nil)
	handler := func(_ context.Context, _ Invocation) (string, error) { return "ok", nil }
	inv := Invocation{Command: c, Confirm: true, SecondActor: "ops2", Reason: "incident, freezing"}
	_, err := Run(context.Background(), c, inv, "dev:ops:sre:admin:read", handler, emitter)
	if err == nil {
		t.Fatal("expected auth scope failure")
	}
	if !strings.Contains(err.Error(), "scope") {
		t.Fatalf("want scope failure, got %v", err)
	}
}

// TestParser_RejectsUnknownTopLevel — strictness: unknown keys must fail loudly.
func TestParser_RejectsUnknownTopLevel(t *testing.T) {
	dir := t.TempDir()
	bad := []byte(`domain: x
bogus_key: 1
commands: []
`)
	if err := os.WriteFile(filepath.Join(dir, "x.yaml"), bad, 0o644); err != nil {
		t.Fatal(err)
	}
	_, err := LoadRegistry(dir)
	if err == nil || !strings.Contains(err.Error(), "unknown top-level key") {
		t.Fatalf("expected unknown-top-level error, got %v", err)
	}
}

// TestParser_RejectsDuplicateDomain — collision of two files declaring the
// same domain must fail (Q-L7A-1 expects one file per domain).
func TestParser_RejectsDuplicateDomain(t *testing.T) {
	dir := t.TempDir()
	a := []byte(`domain: dup
commands:
  - name: dup one
    version: "1.0.0"
    summary: ""
    handler: h
    impact_class: tier-3-informational
    dry_run_required: false
    double_approval_required: false
`)
	if err := os.WriteFile(filepath.Join(dir, "a.yaml"), a, 0o644); err != nil {
		t.Fatal(err)
	}
	if err := os.WriteFile(filepath.Join(dir, "b.yaml"), a, 0o644); err != nil {
		t.Fatal(err)
	}
	_, err := LoadRegistry(dir)
	if err == nil || !strings.Contains(err.Error(), "duplicate") {
		t.Fatalf("expected duplicate-domain error, got %v", err)
	}
}
