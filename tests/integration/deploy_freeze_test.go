//go:build integration

package integration

import (
	"context"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"

	deploycmd "github.com/loreweave/foundation/services/admin-cli/commands/deploy"
)

// runFreezeCheck shells out to scripts/deploy-freeze-check.sh and returns its
// combined output + exit code. repoRoot() is the shared helper in
// sql_helpers_test.go (locates the repo root via Cargo.toml).
func runFreezeCheck(t *testing.T, root string, args ...string) (string, int) {
	t.Helper()
	script := filepath.Join(root, "scripts", "deploy-freeze-check.sh")
	if _, err := os.Stat(script); err != nil {
		t.Skipf("deploy-freeze-check.sh not found at %s", script)
	}
	full := append([]string{script}, args...)
	cmd := exec.Command("bash", full...)
	cmd.Dir = root
	out, err := cmd.CombinedOutput()
	code := 0
	if ee, ok := err.(*exec.ExitError); ok {
		code = ee.ExitCode()
	} else if err != nil {
		t.Fatalf("run freeze-check: %v", err)
	}
	return string(out), code
}

// TestDeployFreeze_BurnOver90Blocks — L7.K.11 acceptance: force burn ≥ 90% →
// the PR is blocked unless overridden. This shells out to the real
// deploy-freeze-check.sh CI lint (cross-cut: script + classification).
func TestDeployFreeze_BurnOver90Blocks(t *testing.T) {
	root := repoRoot(t)

	// burn 0.92 ≥ 0.90 threshold → slo_burn freeze active → minor class blocked.
	out, code := runFreezeCheck(t, root, "--class", "minor", "--burn-rate", "0.92", "--pr-labels", "")
	if code != 1 {
		t.Fatalf("expected exit 1 (blocked), got %d\n%s", code, out)
	}
}

// TestDeployFreeze_EmergencyExemptFromBurn — emergency class is exempt from the
// slo_burn freeze even without break-glass (§12AH.3).
func TestDeployFreeze_EmergencyExemptFromBurn(t *testing.T) {
	root := repoRoot(t)
	out, code := runFreezeCheck(t, root, "--class", "emergency", "--burn-rate", "0.99", "--pr-labels", "emergency")
	if code != 0 {
		t.Fatalf("emergency must be exempt from slo_burn; got exit %d\n%s", code, out)
	}
}

// TestDeployFreeze_BreakGlassLabelOverrides — the break-glass-deploy label lifts
// a scheduled freeze (the §12AH.3 escape hatch).
func TestDeployFreeze_BreakGlassLabelOverrides(t *testing.T) {
	root := repoRoot(t)
	// scheduled freeze active, no burn; minor class blocked WITHOUT label …
	_, blocked := runFreezeCheck(t, root, "--class", "minor", "--active-freezes", "scheduled", "--pr-labels", "")
	if blocked != 1 {
		t.Fatalf("scheduled freeze must block without label; got %d", blocked)
	}
	// … and allowed WITH the break-glass label.
	out, allowed := runFreezeCheck(t, root, "--class", "minor", "--active-freezes", "scheduled", "--pr-labels", "break-glass-deploy")
	if allowed != 0 {
		t.Fatalf("break-glass-deploy label must override; got exit %d\n%s", allowed, out)
	}
}

// TestDeployFreeze_BreakGlassCommand_RecordsOverride — the admin-cli
// `deploy break-glass` command validates the §12AH.3 policy and records the
// override to deploy_audit (cross-cut: CI freeze + the human escape command).
func TestDeployFreeze_BreakGlassCommand_RecordsOverride(t *testing.T) {
	w := &capturingWriter{}
	now := time.Date(2026, 5, 30, 16, 0, 0, 0, time.UTC)
	req := deploycmd.BreakGlassRequest{
		DeployID:         "d-int-bg",
		PRLabels:         []string{"emergency", "break-glass-deploy"},
		FreezeType:       deploycmd.FreezeIncident,
		TechLeadApprover: "tl-1",
		IncidentID:       "INC-2026-0530-0042",
		Actor:            "dev-2",
		Reason:           "SEV1 mitigation must ship while incident freeze is active",
	}
	rec, err := deploycmd.Apply(context.Background(), req, w, func() time.Time { return now })
	if err != nil {
		t.Fatalf("break-glass Apply: %v", err)
	}
	if !w.wrote {
		t.Fatal("override must be written to deploy_audit")
	}
	if rec.PostReviewDueNanos != now.Add(24*time.Hour).UnixNano() {
		t.Errorf("post-deploy review must be due within 24h")
	}
	if rec.FreezeType != deploycmd.FreezeIncident {
		t.Errorf("freeze type = %s", rec.FreezeType)
	}
}

type capturingWriter struct {
	wrote bool
	rec   deploycmd.OverrideRecord
}

func (c *capturingWriter) WriteFreezeOverride(_ context.Context, rec deploycmd.OverrideRecord) error {
	c.wrote = true
	c.rec = rec
	return nil
}
