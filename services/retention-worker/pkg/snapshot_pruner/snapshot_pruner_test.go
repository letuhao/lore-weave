package snapshot_pruner

import (
	"context"
	"testing"

	"github.com/google/uuid"
)

func TestPruneReality_V1NoOp(t *testing.T) {
	rid := uuid.New()
	stats, err := New().PruneReality(context.Background(), rid)
	if err != nil {
		t.Fatal(err)
	}
	if stats.Deleted != 0 || stats.Scanned != 0 {
		t.Fatalf("V1 must be no-op, got %+v", stats)
	}
	if stats.RealityID != rid {
		t.Fatalf("RealityID preserved: got %s want %s", stats.RealityID, rid)
	}
}
