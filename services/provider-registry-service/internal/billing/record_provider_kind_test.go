package billing

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/google/uuid"
)

// 🔴 D-BILL-PROVIDER-KIND — THE ROOT CAUSE, AND IT WAS WRITTEN DOWN.
//
// RecordUsage built its /record payload with a LITERAL `"provider_kind": ""`, under a
// comment naming the gap as accepted (D-PHASE5E-BILLING-PROVIDER-KIND-ANALYTICS). The
// UsageRecord struct had no such field, so no caller could have supplied one. Every row
// this path wrote — including streaming chat, the highest-volume producer — landed
// unattributable: 99,683 of 103,072 usage_logs rows (96.7%) carried no provider, last
// populated 2026-07-21.
//
// Nothing failed. usage-billing had already dropped its provider_kind CHECK, and the
// column is NOT NULL DEFAULT '', so an empty value writes cleanly forever. That is why
// this needs a test rather than a runtime guard: the failure mode is silence.
func TestRecordUsage_PutsProviderKindOnTheWire(t *testing.T) {
	var got map[string]any
	var seen bool
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen = true
		body, _ := io.ReadAll(r.Body)
		_ = json.Unmarshal(body, &got)
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{}`))
	}))
	defer srv.Close()

	c := NewGuardrailClient(srv.URL, "", srv.Client())
	err := c.RecordUsage(context.Background(), UsageRecord{
		RequestID:    uuid.New(),
		OwnerUserID:  uuid.New(),
		ModelRef:     uuid.New(),
		ModelSource:  "user_model",
		ProviderKind: "ollama",
		Operation:    "chat",
		InputTokens:  10,
		OutputTokens: 5,
	})
	if err != nil {
		t.Fatalf("RecordUsage: %v", err)
	}
	if !seen {
		t.Fatal("the client never reached the server — the assertion below would be vacuous")
	}
	if got["provider_kind"] != "ollama" {
		t.Errorf("provider_kind on the wire = %v, want \"ollama\". The audit row is written "+
			"from this payload, so an empty value here is a spend row that can never be "+
			"attributed to a provider — and it writes without error.", got["provider_kind"])
	}
}

// A caller that genuinely cannot resolve a provider must still record. Empty is the
// pre-fix value for every row, so rejecting it here would turn a silent gap into lost
// audit rows — strictly worse.
func TestRecordUsage_EmptyProviderKindStillRecords(t *testing.T) {
	var seen bool
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		seen = true
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{}`))
	}))
	defer srv.Close()

	c := NewGuardrailClient(srv.URL, "", srv.Client())
	if err := c.RecordUsage(context.Background(), UsageRecord{
		RequestID: uuid.New(), OwnerUserID: uuid.New(), ModelRef: uuid.New(),
		ModelSource: "user_model", Operation: "chat",
	}); err != nil {
		t.Fatalf("an unresolved provider_kind must not lose the audit row: %v", err)
	}
	if !seen {
		t.Fatal("no request reached the server")
	}
}
