package notifyevent

import (
	"encoding/json"
	"testing"

	"github.com/google/uuid"
)

// TestRoutingKey pins the topic-key convention the consumer's binding (`user.*.llm.#`)
// depends on. A change here would silently stop the consumer from receiving events.
func TestRoutingKey(t *testing.T) {
	owner := uuid.MustParse("11111111-1111-1111-1111-111111111111")
	ev := TerminalEvent{OwnerUserID: owner, Operation: "chat", Status: "completed"}
	want := "user.11111111-1111-1111-1111-111111111111.llm.chat.completed"
	if got := ev.RoutingKey(); got != want {
		t.Fatalf("RoutingKey = %q, want %q", got, want)
	}
}

// TestWireContract pins the on-the-wire JSON field names. Both the producer
// (provider-registry) and the consumer (notification-service) marshal/unmarshal
// this exact type now, so this guards the field names the wire depends on.
func TestWireContract(t *testing.T) {
	ev := TerminalEvent{
		JobID:        uuid.MustParse("22222222-2222-2222-2222-222222222222"),
		OwnerUserID:  uuid.MustParse("33333333-3333-3333-3333-333333333333"),
		Operation:    "extraction",
		Status:       "failed",
		TraceID:      "tr-1",
		ErrorCode:    "E_X",
		ErrorMessage: "boom",
		FinishReason: "error",
	}
	b, err := json.Marshal(ev)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var m map[string]any
	if err := json.Unmarshal(b, &m); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	for _, k := range []string{"job_id", "owner_user_id", "operation", "status", "trace_id", "error_code", "error_message", "finish_reason"} {
		if _, ok := m[k]; !ok {
			t.Errorf("wire contract missing field %q", k)
		}
	}
	// omitempty fields absent when zero.
	if _, ok := m["result"]; ok {
		t.Error("result should be omitted when empty")
	}
	// Round-trips back to identical bytes (the struct holds a json.RawMessage, so
	// re-marshal rather than `==`).
	var back TerminalEvent
	if err := json.Unmarshal(b, &back); err != nil {
		t.Fatalf("round-trip unmarshal: %v", err)
	}
	b2, _ := json.Marshal(back)
	if string(b2) != string(b) {
		t.Fatalf("round-trip mismatch:\n got=%s\nwant=%s", b2, b)
	}
}
