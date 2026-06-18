package prompt

import (
	"context"
	"testing"
	"time"

	"github.com/google/uuid"
)

func validEntry() PromptAuditEntry {
	return PromptAuditEntry{
		AuditID:           uuid.New().String(),
		PromptContextHash: make([]byte, 32),
		TemplateID:        "session_turn",
		TemplateVersion:   1,
		Intent:            string(IntentSessionTurn),
		ActorUserRefID:    uuid.New().String(),
		RealityID:         uuid.New().String(),
		CreatedAtNanos:    time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC).UnixNano(),
	}
}

func TestEntry_Validate_OK(t *testing.T) {
	e := validEntry()
	if err := e.Validate(); err != nil {
		t.Fatalf("Validate() = %v; want nil", err)
	}
}

func TestEntry_Validate_HashMustBe32Bytes(t *testing.T) {
	e := validEntry()
	e.PromptContextHash = make([]byte, 16)
	if err := e.Validate(); err == nil {
		t.Errorf("Validate() = nil; want SHA-256 length error")
	}
	e.PromptContextHash = make([]byte, 64)
	if err := e.Validate(); err == nil {
		t.Errorf("Validate() = nil; want SHA-256 length error (64-byte case)")
	}
}

func TestEntry_Validate_AllRequiredFields(t *testing.T) {
	cases := []struct {
		name   string
		mutate func(e *PromptAuditEntry)
	}{
		{"audit_id", func(e *PromptAuditEntry) { e.AuditID = "" }},
		{"template_id", func(e *PromptAuditEntry) { e.TemplateID = "" }},
		{"template_version", func(e *PromptAuditEntry) { e.TemplateVersion = 0 }},
		{"intent", func(e *PromptAuditEntry) { e.Intent = "" }},
		{"actor_user", func(e *PromptAuditEntry) { e.ActorUserRefID = "" }},
		{"reality", func(e *PromptAuditEntry) { e.RealityID = "" }},
		{"created_at_nanos", func(e *PromptAuditEntry) { e.CreatedAtNanos = 0 }},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			e := validEntry()
			tc.mutate(&e)
			if err := e.Validate(); err == nil {
				t.Errorf("Validate() = nil; want error for missing %s", tc.name)
			}
		})
	}
}

func TestInMemoryWriter_AppendsValidated(t *testing.T) {
	w := &InMemoryAuditWriter{}
	if err := w.RecordAssembly(context.Background(), validEntry()); err != nil {
		t.Fatalf("RecordAssembly err = %v; want nil", err)
	}
	if len(w.Entries) != 1 {
		t.Errorf("Entries len = %d; want 1", len(w.Entries))
	}
	// Invalid entry must be rejected and NOT appended.
	bad := validEntry()
	bad.AuditID = ""
	if err := w.RecordAssembly(context.Background(), bad); err == nil {
		t.Errorf("RecordAssembly(invalid) = nil err; want validation error")
	}
	if len(w.Entries) != 1 {
		t.Errorf("Entries len after rejected = %d; want 1 (rejected entries must not append)", len(w.Entries))
	}
}
