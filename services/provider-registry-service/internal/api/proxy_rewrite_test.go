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

// C-LM-STUDIO-FIX — unit tests for normalizeResponseFormatForKind,
// which works around LM Studio's response_format quirk (rejects
// json_object, accepts only json_schema or text). Discovered during
// C19 quality eval — without this normalization, every knowledge-
// service extraction call against an LM Studio model fails with
// HTTP 400.

func TestNormalizeResponseFormat_LMStudioJSONObjectBecomesText(t *testing.T) {
	parsed := map[string]any{
		"model":           "doesnt-matter",
		"messages":        []any{},
		"response_format": map[string]any{"type": "json_object"},
	}
	normalizeResponseFormatForKind(parsed, "lm_studio")
	rf, ok := parsed["response_format"].(map[string]any)
	if !ok {
		t.Fatalf("response_format dropped or wrong type: %#v", parsed["response_format"])
	}
	if rf["type"] != "text" {
		t.Fatalf("expected type=text, got %v", rf["type"])
	}
	if len(rf) != 1 {
		t.Fatalf("expected single 'type' key (no leakage), got %#v", rf)
	}
}

func TestNormalizeResponseFormat_OpenAIJSONObjectUntouched(t *testing.T) {
	parsed := map[string]any{
		"model":           "gpt-4o-mini",
		"messages":        []any{},
		"response_format": map[string]any{"type": "json_object"},
	}
	normalizeResponseFormatForKind(parsed, "openai")
	rf := parsed["response_format"].(map[string]any)
	if rf["type"] != "json_object" {
		t.Fatalf("openai path must NOT rewrite — got %v", rf["type"])
	}
}

func TestNormalizeResponseFormat_LMStudioWithoutResponseFormatNoOp(t *testing.T) {
	parsed := map[string]any{
		"model":    "doesnt-matter",
		"messages": []any{},
	}
	normalizeResponseFormatForKind(parsed, "lm_studio")
	if _, exists := parsed["response_format"]; exists {
		t.Fatalf("response_format must NOT be added when caller didn't supply it")
	}
}

func TestNormalizeResponseFormat_LMStudioJSONSchemaIdempotent(t *testing.T) {
	// json_schema is what LM Studio actually accepts — must NOT rewrite
	// it to text (would silently drop the schema spec).
	original := map[string]any{
		"type":        "json_schema",
		"json_schema": map[string]any{"name": "Foo", "schema": map[string]any{}},
	}
	parsed := map[string]any{
		"response_format": original,
	}
	normalizeResponseFormatForKind(parsed, "lm_studio")
	rf := parsed["response_format"].(map[string]any)
	if !reflect.DeepEqual(rf, original) {
		t.Fatalf("json_schema must be left untouched; got %#v", rf)
	}
}

func TestNormalizeResponseFormat_LMStudioTextIdempotent(t *testing.T) {
	parsed := map[string]any{
		"response_format": map[string]any{"type": "text"},
	}
	normalizeResponseFormatForKind(parsed, "lm_studio")
	rf := parsed["response_format"].(map[string]any)
	if rf["type"] != "text" {
		t.Fatalf("text must remain text; got %v", rf["type"])
	}
}

func TestNormalizeResponseFormat_LMStudioMalformedResponseFormatNoOp(t *testing.T) {
	// Defensive: if response_format is a bare string or other shape,
	// don't crash — leave as-is. Upstream will reject if it's invalid.
	parsed := map[string]any{
		"response_format": "json",
	}
	normalizeResponseFormatForKind(parsed, "lm_studio")
	if parsed["response_format"] != "json" {
		t.Fatalf("malformed response_format must be left alone; got %v", parsed["response_format"])
	}
}

// C-EVAL-QWEN36-35B — unit tests for buildProxyTargetURL, the helper that
// joins endpoint_base_url with the per-request target path. The lm_studio
// branch strips a trailing /v1 to prevent the /v1/v1/ duplication that the
// LM-STUDIO-URL-FIX cycle missed for the transparent-proxy code path.

func TestBuildProxyTargetURL_LMStudioStripsTrailingV1(t *testing.T) {
	got := buildProxyTargetURL("lm_studio", "http://host.docker.internal:1234/v1", "v1/chat/completions")
	want := "http://host.docker.internal:1234/v1/chat/completions"
	if got != want {
		t.Fatalf("got %q, want %q (must strip trailing /v1 to avoid /v1/v1/)", got, want)
	}
}

func TestBuildProxyTargetURL_LMStudioBareHostUntouched(t *testing.T) {
	got := buildProxyTargetURL("lm_studio", "http://host.docker.internal:1234", "v1/chat/completions")
	want := "http://host.docker.internal:1234/v1/chat/completions"
	if got != want {
		t.Fatalf("got %q, want %q (bare host must work too)", got, want)
	}
}

func TestBuildProxyTargetURL_LMStudioTrailingSlashStripped(t *testing.T) {
	got := buildProxyTargetURL("lm_studio", "http://host.docker.internal:1234/", "v1/chat/completions")
	want := "http://host.docker.internal:1234/v1/chat/completions"
	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}

func TestBuildProxyTargetURL_OpenAIPathUnaffected(t *testing.T) {
	// Non-lm_studio kinds keep the original TrimRight-only behavior — no
	// /v1 stripping (some providers genuinely need /v1 in the base URL).
	got := buildProxyTargetURL("openai", "https://api.openai.com/v1", "embeddings")
	want := "https://api.openai.com/v1/embeddings"
	if got != want {
		t.Fatalf("got %q, want %q (openai path must NOT strip /v1)", got, want)
	}
}

func TestBuildProxyTargetURL_AnthropicPreservesBase(t *testing.T) {
	got := buildProxyTargetURL("anthropic", "https://api.anthropic.com", "v1/messages")
	want := "https://api.anthropic.com/v1/messages"
	if got != want {
		t.Fatalf("got %q, want %q", got, want)
	}
}
