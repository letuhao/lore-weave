package backupscheduler

import (
	"errors"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

// TestLoadPolicyFile_ShippedYAML — load the actual contracts/backup/policy.yaml
// and verify the tier matrix matches R4 retention (7/14/30d).
func TestLoadPolicyFile_ShippedYAML(t *testing.T) {
	path, err := filepath.Abs("../../contracts/backup/policy.yaml")
	if err != nil {
		t.Fatal(err)
	}
	p, err := LoadPolicyFile(path)
	if err != nil {
		t.Fatalf("LoadPolicyFile: %v", err)
	}
	if p.Version != 1 {
		t.Errorf("Version = %d, want 1", p.Version)
	}
	if p.TargetBucket != "lw-db-backups" {
		t.Errorf("TargetBucket = %q, want lw-db-backups (Q-L1H-1)", p.TargetBucket)
	}
	// Q-L1H-2: monthly per-shard automated; quarterly full-system manual.
	if p.RestoreDrill.PerShardCadence != "monthly" || !p.RestoreDrill.PerShardAutomated {
		t.Errorf("per-shard drill = %q/%v, want monthly/true (Q-L1H-2)",
			p.RestoreDrill.PerShardCadence, p.RestoreDrill.PerShardAutomated)
	}
	if p.RestoreDrill.FullSystemCadence != "quarterly" || p.RestoreDrill.FullSystemAutomated {
		t.Errorf("full-system drill = %q/%v, want quarterly/false (Q-L1H-2)",
			p.RestoreDrill.FullSystemCadence, p.RestoreDrill.FullSystemAutomated)
	}
	if p.RestoreDrill.AlertOnDrillFailure != "page" {
		t.Errorf("AlertOnDrillFailure = %q, want page", p.RestoreDrill.AlertOnDrillFailure)
	}
	// Spot-check R4 retention matrix: active=14, frozen=30, default=14.
	if got := p.Tiers["active"].RetentionDays; got != 14 {
		t.Errorf("active retention = %d, want 14", got)
	}
	if got := p.Tiers["frozen"].RetentionDays; got != 30 {
		t.Errorf("frozen retention = %d, want 30", got)
	}
	// All known reality statuses must have a tier (8 lifecycle statuses + default = 9 minimum).
	wantStatuses := []string{
		"active", "pending_close", "frozen", "migrating",
		"archived", "archived_verified", "soft_deleted", "dropped", "default",
	}
	for _, s := range wantStatuses {
		if _, ok := p.Tiers[s]; !ok {
			t.Errorf("tier %q missing", s)
		}
	}
}

func TestTierFor_FallsBackToDefault(t *testing.T) {
	p := &Policy{
		Version:      1,
		TargetBucket: "x",
		Tiers: map[string]PolicyTier{
			"active":  {RetentionDays: 14, Compression: "zstd"},
			"default": {RetentionDays: 14, Compression: "zstd"},
		},
	}
	t1, err := p.TierFor("active")
	if err != nil || t1.RetentionDays != 14 {
		t.Errorf("active lookup: %v %+v", err, t1)
	}
	t2, err := p.TierFor("provisioning") // unknown status
	if err != nil {
		t.Errorf("default fallback err = %v", err)
	}
	if t2.RetentionDays != 14 {
		t.Errorf("fallback tier wrong: %+v", t2)
	}
}

func TestLoadPolicy_RejectsMissingDefault(t *testing.T) {
	body := `version: 1
target_bucket: x
tiers:
  active:
    full_interval: 7d
    retention_days: 14
    compression: zstd
`
	_, err := parsePolicyYAML(body)
	if !errors.Is(err, ErrPolicyInvalid) {
		t.Errorf("err = %v, want ErrPolicyInvalid", err)
	}
	if err != nil && !strings.Contains(err.Error(), "default") {
		t.Errorf("err should mention 'default': %v", err)
	}
}

func TestLoadPolicy_RejectsZeroRetention(t *testing.T) {
	body := `version: 1
target_bucket: x
tiers:
  active:
    full_interval: 7d
    retention_days: 0
    compression: zstd
  default:
    full_interval: 7d
    retention_days: 14
    compression: zstd
`
	_, err := parsePolicyYAML(body)
	if !errors.Is(err, ErrPolicyInvalid) {
		t.Errorf("err = %v, want ErrPolicyInvalid", err)
	}
}

func TestParseDuration_NullSemantics(t *testing.T) {
	if parseDurationPtrOrNull("null") != nil {
		t.Error("null should parse to nil")
	}
	if parseDurationPtrOrNull("") != nil {
		t.Error("empty should parse to nil")
	}
	d := parseDurationPtrOrNull("24h")
	if d == nil || *d != 24*time.Hour {
		t.Errorf("24h parse wrong: %v", d)
	}
}
