package main

import (
	"testing"

	"github.com/loreweave/foundation/services/retention-worker/pkg/types"
)

func TestDefaultConfig_AllFieldsPositive(t *testing.T) {
	cfg := types.DefaultConfig()
	if cfg.OutboxPublishedGrace <= 0 {
		t.Fatal("OutboxPublishedGrace must be > 0")
	}
	if cfg.OutboxBatchSize <= 0 {
		t.Fatal("OutboxBatchSize must be > 0")
	}
	if cfg.AuditNonFlaggedDays <= 0 {
		t.Fatal("AuditNonFlaggedDays must be > 0")
	}
	if cfg.AuditFlaggedDays <= 0 {
		t.Fatal("AuditFlaggedDays must be > 0")
	}
}

func TestDefaultConfig_AuditFlaggedLongerThanNonFlagged(t *testing.T) {
	// Per R01 §12A.3: flagged audit rows MUST be retained at least as long
	// as non-flagged. Anti-regression on someone bumping non-flagged past
	// flagged.
	cfg := types.DefaultConfig()
	if cfg.AuditFlaggedDays < cfg.AuditNonFlaggedDays {
		t.Fatalf("AuditFlaggedDays (%d) must be >= AuditNonFlaggedDays (%d)",
			cfg.AuditFlaggedDays, cfg.AuditNonFlaggedDays)
	}
}
