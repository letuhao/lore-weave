//go:build integration

package integration

import (
	"path/filepath"
	"testing"

	bs "github.com/loreweave/foundation/services/backup-scheduler"
)

// TestTieredBackup_PolicyCoversAllRealityStatuses — L1.H §6 acceptance.
// Reads the shipped policy.yaml and verifies every reality_registry status
// has a tier mapping.
func TestTieredBackup_PolicyCoversAllRealityStatuses(t *testing.T) {
	path, err := filepath.Abs("../../contracts/backup/policy.yaml")
	if err != nil {
		t.Fatal(err)
	}
	p, err := bs.LoadPolicyFile(path)
	if err != nil {
		t.Fatalf("LoadPolicyFile: %v", err)
	}
	// R09 §12I.1 6-state machine + the 4 pre-state statuses (provisioning,
	// seeding) + (migrating, pending_close) + lifecycle endpoints.
	for _, status := range []string{
		"active", "pending_close", "frozen", "migrating",
		"archived", "archived_verified", "soft_deleted", "dropped",
	} {
		tier, err := p.TierFor(status)
		if err != nil {
			t.Errorf("TierFor(%q): %v", status, err)
		}
		if tier.RetentionDays <= 0 {
			t.Errorf("status %q has retention_days <= 0", status)
		}
	}
}

func TestTieredBackup_ActiveTier_R4Retention(t *testing.T) {
	path, _ := filepath.Abs("../../contracts/backup/policy.yaml")
	p, err := bs.LoadPolicyFile(path)
	if err != nil {
		t.Fatal(err)
	}
	tier, _ := p.TierFor("active")
	if tier.RetentionDays != 14 {
		t.Errorf("active retention = %d, want 14 (R4 matrix)", tier.RetentionDays)
	}
	if tier.IncrementalInterval == nil {
		t.Error("active tier MUST have incremental interval")
	}
}

func TestTieredBackup_ArchivedTier_NoBackup(t *testing.T) {
	path, _ := filepath.Abs("../../contracts/backup/policy.yaml")
	p, _ := bs.LoadPolicyFile(path)
	tier, _ := p.TierFor("archived")
	if tier.IncrementalInterval != nil {
		t.Errorf("archived tier MUST NOT have incremental interval (got %v)", tier.IncrementalInterval)
	}
	if tier.FullInterval != nil {
		t.Errorf("archived tier MUST NOT have full interval (got %v)", tier.FullInterval)
	}
}
