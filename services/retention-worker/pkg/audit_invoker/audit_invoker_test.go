package audit_invoker

import (
	"context"
	"errors"
	"testing"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/services/retention-worker/pkg/types"
)

func TestInvokeReality_PassesConfig(t *testing.T) {
	m := NewMockRunner()
	cfg := types.RetentionConfig{
		OutboxBatchSize:     5000,
		AuditNonFlaggedDays: 14,
		AuditFlaggedDays:    60,
	}
	inv, err := New(m, cfg)
	if err != nil {
		t.Fatal(err)
	}
	rid := uuid.New()
	m.Outcomes[rid] = types.AuditPruneStats{NonFlaggedDeleted: 42, FlaggedDeleted: 3}

	stats, err := inv.InvokeReality(context.Background(), rid, "postgres://x")
	if err != nil {
		t.Fatal(err)
	}
	if stats.NonFlaggedDeleted != 42 {
		t.Fatalf("NonFlaggedDeleted: got %d want 42", stats.NonFlaggedDeleted)
	}
	if len(m.Calls) != 1 {
		t.Fatalf("expected 1 call, got %d", len(m.Calls))
	}
	c := m.Calls[0]
	if c.RealityID != rid || c.DSN != "postgres://x" {
		t.Fatalf("call args: %+v", c)
	}
	if c.BatchSize != 5000 || c.NonFlaggedDays != 14 || c.FlaggedDays != 60 {
		t.Fatalf("cfg propagation broken: %+v", c)
	}
}

func TestInvokeReality_EmptyDSN(t *testing.T) {
	m := NewMockRunner()
	inv, _ := New(m, types.DefaultConfig())
	_, err := inv.InvokeReality(context.Background(), uuid.New(), "")
	if err == nil {
		t.Fatal("expected empty-DSN error")
	}
}

func TestNew_RejectsNilRunner(t *testing.T) {
	if _, err := New(nil, types.DefaultConfig()); err == nil {
		t.Fatal("expected nil-runner error")
	}
}

func TestNew_ApplyDefaults(t *testing.T) {
	inv, _ := New(NewMockRunner(), types.RetentionConfig{})
	if inv.cfg.AuditNonFlaggedDays != 30 || inv.cfg.AuditFlaggedDays != 90 {
		t.Fatalf("defaults not applied: %+v", inv.cfg)
	}
}

func TestInvokeReality_ErrorPropagates(t *testing.T) {
	m := NewMockRunner()
	m.Err = errors.New("script failed")
	inv, _ := New(m, types.DefaultConfig())
	_, err := inv.InvokeReality(context.Background(), uuid.New(), "postgres://x")
	if err == nil {
		t.Fatal("expected error to propagate")
	}
}
