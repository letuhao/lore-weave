package scriptrun

import (
	"testing"

	"github.com/google/uuid"
)

func TestParseOutput_RealScriptShape(t *testing.T) {
	out := `[audit-retention] dropped 3 fully-expired event_audit partitions (cutoff_month=2024_11)
[audit-retention] deleted non_flagged=42 flagged=7`
	rid := uuid.New()
	s := ParseOutput(out, rid)
	if s.RealityID != rid {
		t.Errorf("RealityID not set")
	}
	if s.PartitionsDropped != 3 {
		t.Errorf("PartitionsDropped=%d want 3", s.PartitionsDropped)
	}
	if s.NonFlaggedDeleted != 42 {
		t.Errorf("NonFlaggedDeleted=%d want 42", s.NonFlaggedDeleted)
	}
	// The bug guard: `flagged=7` must NOT be captured as the non_flagged value.
	if s.FlaggedDeleted != 7 {
		t.Errorf("FlaggedDeleted=%d want 7 (must not pick up non_flagged)", s.FlaggedDeleted)
	}
}

func TestParseOutput_ZeroCounts(t *testing.T) {
	out := `[audit-retention] dropped 0 fully-expired event_audit partitions (cutoff_month=2024_11)
[audit-retention] deleted non_flagged=0 flagged=0`
	s := ParseOutput(out, uuid.New())
	if s.PartitionsDropped != 0 || s.NonFlaggedDeleted != 0 || s.FlaggedDeleted != 0 {
		t.Errorf("expected all zero, got %+v", s)
	}
}

func TestParseOutput_MissingLines(t *testing.T) {
	s := ParseOutput("garbage with no counters", uuid.New())
	if s.PartitionsDropped != 0 || s.NonFlaggedDeleted != 0 || s.FlaggedDeleted != 0 {
		t.Errorf("missing lines should parse to zero, got %+v", s)
	}
}
