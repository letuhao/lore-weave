package api

import (
	"encoding/json"
	"reflect"
	"testing"
)

// K17.2a — unit tests for rewriteJSONBodyModel, the pure helper that
// doProxy calls when forwarding a JSON chat-completion body. These
// tests stay off the HTTP path entirely so they do not need a pgx
// pool or an upstream provider — the risky logic lives in the helper
// and end-to-end coverage comes from the knowledge-service
// ProviderClient tests (K17.2b).

func unmarshal(t *testing.T, raw []byte) map[string]any {
	t.Helper()
	var out map[string]any
	if err := json.Unmarshal(raw, &out); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	return out
}

func TestRewriteJSONBodyModel_ReplacesModel(t *testing.T) {
	parsed := unmarshal(t, []byte(`{"model":"foo","messages":[{"role":"user","content":"hi"}]}`))
	out, err := rewriteJSONBodyModel(parsed, "bar")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	got := unmarshal(t, out)
	if got["model"] != "bar" {
		t.Errorf("model = %v, want bar", got["model"])
	}
	msgs, ok := got["messages"].([]any)
	if !ok || len(msgs) != 1 {
		t.Errorf("messages not preserved: %v", got["messages"])
	}
}

func TestRewriteJSONBodyModel_AddsModelWhenMissing(t *testing.T) {
	parsed := unmarshal(t, []byte(`{"messages":[{"role":"user","content":"hi"}]}`))
	out, err := rewriteJSONBodyModel(parsed, "resolved-model")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	got := unmarshal(t, out)
	if got["model"] != "resolved-model" {
		t.Errorf("model = %v, want resolved-model", got["model"])
	}
}

func TestRewriteJSONBodyModel_PreservesNestedAndUnknownFields(t *testing.T) {
	body := []byte(`{
		"model":"old",
		"messages":[{"role":"user","content":[{"type":"text","text":"hi"}]}],
		"temperature":0.7,
		"max_tokens":512,
		"tools":[{"type":"function","function":{"name":"lookup"}}],
		"response_format":{"type":"json_object"},
		"metadata":{"trace":"abc"}
	}`)
	parsed := unmarshal(t, body)
	out, err := rewriteJSONBodyModel(parsed, "new")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	got := unmarshal(t, out)

	if got["model"] != "new" {
		t.Errorf("model = %v, want new", got["model"])
	}

	// Round-trip the original with the model swapped and compare
	// structurally. This catches any accidental field stripping.
	want := unmarshal(t, body)
	want["model"] = "new"
	if !reflect.DeepEqual(got, want) {
		t.Errorf("round-trip mismatch\n got=%v\nwant=%v", got, want)
	}
}

func TestRewriteJSONBodyModel_IgnoresClientSuppliedModel(t *testing.T) {
	// A malicious caller tries to bypass BYOK resolution by sending
	// its own model string. The helper MUST overwrite it with the
	// server-resolved name — never honor the client value.
	parsed := unmarshal(t, []byte(`{"model":"evil-override","messages":[]}`))
	out, err := rewriteJSONBodyModel(parsed, "server-resolved")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	got := unmarshal(t, out)
	if got["model"] != "server-resolved" {
		t.Errorf("client-supplied model leaked through: got %v", got["model"])
	}
}

func TestRewriteJSONBodyModel_RejectsInvalidJSON(t *testing.T) {
	// Sanity check: the caller is responsible for unmarshaling before
	// calling the helper, but if someone passes a map containing a
	// non-marshalable value (channel, func, complex number), we want
	// a clear error rather than a silent corruption. Channels are the
	// classic non-marshalable type.
	parsed := map[string]any{
		"model":    "foo",
		"messages": make(chan int),
	}
	_, err := rewriteJSONBodyModel(parsed, "bar")
	if err == nil {
		t.Fatalf("expected error for non-marshalable map, got nil")
	}
}
