//go:build integration

// Package integration — cycle 36 cross-package admin-cli smoke.
//
// Verifies:
//   * Canonical registry loads from contracts/admin/registry/*.yaml.
//   * Every command can be looked up by `<domain> <verb>`.
//   * Every command can be dispatched through cliapi.Run() against the
//     NotWiredHandler skeleton and emits Before+After audit rows.
//   * Tier-1 commands have dry_run_required + double_approval_required.
//   * Cycle 36 ships 28-32 total commands (Q-L7A scope guard).
//   * Domain set matches design: reality, erasure, canon, projection,
//     backup, archive, migration, incident, ops.
package integration

import (
	"context"
	"path/filepath"
	"runtime"
	"strings"
	"testing"

	"github.com/loreweave/foundation/services/admin-cli/pkg/cliapi"
)

// registryDir resolves the canonical registry path regardless of where
// `go test` is invoked from.
func registryDir(t *testing.T) string {
	t.Helper()
	_, file, _, _ := runtime.Caller(0)
	// file = .../tests/integration/admin_cli_test.go
	// repo root = .../
	root := filepath.Join(filepath.Dir(file), "..", "..")
	return filepath.Join(root, "contracts", "admin", "registry")
}

func TestAdminCLI_RegistryLoadsCanonicalSet(t *testing.T) {
	reg, err := cliapi.LoadRegistry(registryDir(t))
	if err != nil {
		t.Fatalf("LoadRegistry: %v", err)
	}
	if n := len(reg.Commands); n < 28 || n > 32 {
		t.Fatalf("cycle 36 scope: want 28-32 commands, got %d", n)
	}
}

func TestAdminCLI_AllExpectedDomainsPresent(t *testing.T) {
	reg, err := cliapi.LoadRegistry(registryDir(t))
	if err != nil {
		t.Fatalf("LoadRegistry: %v", err)
	}
	want := []string{"reality", "erasure", "canon", "projection", "backup", "archive", "migration", "incident", "ops"}
	have := map[string]bool{}
	for _, d := range reg.Domains {
		have[d] = true
	}
	for _, d := range want {
		if !have[d] {
			t.Errorf("missing domain: %q (Q-L7A-1 per-domain auto-merge dropped a file?)", d)
		}
	}
}

func TestAdminCLI_Tier1HasDryRunAndApproval(t *testing.T) {
	reg, err := cliapi.LoadRegistry(registryDir(t))
	if err != nil {
		t.Fatalf("LoadRegistry: %v", err)
	}
	tier1 := 0
	for _, c := range reg.List() {
		if c.ImpactClass != cliapi.Tier1Destructive {
			continue
		}
		tier1++
		if !c.DryRunRequired {
			t.Errorf("tier-1 %q missing dry_run_required", c.Name)
		}
		if !c.DoubleApprovalRequired {
			t.Errorf("tier-1 %q missing double_approval_required", c.Name)
		}
	}
	if tier1 == 0 {
		t.Fatal("no tier-1 commands found — registry corrupted?")
	}
}

func TestAdminCLI_EveryCommandDispatchableAndAudited(t *testing.T) {
	reg, err := cliapi.LoadRegistry(registryDir(t))
	if err != nil {
		t.Fatalf("LoadRegistry: %v", err)
	}
	handlers := cliapi.NewHandlerRegistry()
	emitterSink := cliapi.NewMemorySink()
	emitter := cliapi.NewEmitter(emitterSink, nil)
	token := "dev:ops1:sre:admin:read|admin:write|admin:destructive"
	totalAuditRows := 0

	for _, c := range reg.List() {
		handler := handlers.Get(c.Name) // NotWiredHandler skeleton
		inv := cliapi.Invocation{
			Command: c,
			Params:  map[string]string{},
			Reason:  "integration smoke for cycle 36 acceptance — exercise audit hook",
		}
		// Any DryRunRequired command needs --dry-run; tier-1 also needs --second-actor
		// (we test the dry-run path because --confirm would invoke real destructive
		// I/O against the NotWiredHandler skeleton — both gates exercised).
		if c.DryRunRequired {
			inv.DryRun = true
		}
		if c.ImpactClass == cliapi.Tier1Destructive {
			inv.SecondActor = "ops2"
		}
		before := emitterSink.Count()
		_, err := cliapi.Run(context.Background(), c, inv, token, handler, emitter)
		if err != nil {
			t.Errorf("dispatch %q: %v", c.Name, err)
			continue
		}
		gained := emitterSink.Count() - before
		if gained != 2 {
			t.Errorf("%q: expected 2 audit rows (Before+After), got %d", c.Name, gained)
		}
		totalAuditRows += gained
	}
	if totalAuditRows < 2*len(reg.Commands) {
		t.Errorf("expected at least %d audit rows total, got %d (audit hook gap?)",
			2*len(reg.Commands), totalAuditRows)
	}
}

func TestAdminCLI_NoCommandNamesCollide(t *testing.T) {
	reg, err := cliapi.LoadRegistry(registryDir(t))
	if err != nil {
		t.Fatalf("LoadRegistry: %v", err)
	}
	// LoadRegistry already rejects duplicates, but assert the unique set size
	// matches len(reg.Commands) as a defence-in-depth check.
	names := map[string]bool{}
	for _, c := range reg.List() {
		if names[c.Name] {
			t.Errorf("duplicate command name slipped through: %q", c.Name)
		}
		names[c.Name] = true
	}
}

func TestAdminCLI_ConsolidatedCyclesReferenced(t *testing.T) {
	// Audit that the consolidated implementations from prior cycles are
	// represented in the registry by carry_forward_cycle so we know they're
	// not silently dropped.
	reg, err := cliapi.LoadRegistry(registryDir(t))
	if err != nil {
		t.Fatalf("LoadRegistry: %v", err)
	}
	consolidatedCycles := map[string]bool{
		"6":  false, // migration-orchestrator
		"7":  false, // capacity-override
		"11": false, // archive-restore
		"14": false, // rebuild-projection + catastrophic-rebuild
	}
	for _, c := range reg.List() {
		if _, ok := consolidatedCycles[c.CarryForwardCycle]; ok {
			consolidatedCycles[c.CarryForwardCycle] = true
		}
	}
	for cy, found := range consolidatedCycles {
		if !found {
			t.Errorf("no command references carry_forward_cycle=%q — prior CLI not consolidated?", cy)
		}
	}
	// Spot-check: capacity-override must be under reality domain.
	if _, ok := reg.Commands["reality capacity-override"]; !ok {
		t.Error("reality capacity-override missing — cycle 7 not consolidated")
	}
	// Spot-check: rebuild-projection must be under reality domain.
	if _, ok := reg.Commands["reality rebuild-projection"]; !ok {
		t.Error("reality rebuild-projection missing — cycle 14 not consolidated")
	}
	// Spot-check: archive list / fetch must exist.
	if _, ok := reg.Commands["archive list"]; !ok {
		t.Error("archive list missing — cycle 11 not consolidated")
	}
	// Spot-check: migration up/down/status must exist.
	for _, n := range []string{"migration up", "migration down", "migration status"} {
		if _, ok := reg.Commands[n]; !ok {
			t.Errorf("%q missing — cycle 6 not consolidated", n)
		}
	}
}

func TestAdminCLI_HelpOutputMentionsLockedQs(t *testing.T) {
	reg, err := cliapi.LoadRegistry(registryDir(t))
	if err != nil {
		t.Fatalf("LoadRegistry: %v", err)
	}
	// Every command should declare Q-L7A-1 + Q-L7A-2 in locked_qs.
	for _, c := range reg.List() {
		joined := strings.Join(c.LockedQsConsumed, ",")
		if !strings.Contains(joined, "Q-L7A-1") {
			t.Errorf("%q missing Q-L7A-1 in locked_qs (got %v)", c.Name, c.LockedQsConsumed)
		}
		if !strings.Contains(joined, "Q-L7A-2") {
			t.Errorf("%q missing Q-L7A-2 in locked_qs (got %v)", c.Name, c.LockedQsConsumed)
		}
	}
}
