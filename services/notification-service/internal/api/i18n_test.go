package api

import (
	"encoding/json"
	"testing"
	"time"

	"github.com/google/uuid"
)

// TestSerializeNotification_IncludesI18nFields proves D-NOTIF-I18N (NOTIF-1):
// the GET/list row shape returns message_key + message_params ALONGSIDE the
// title/body fallback so a locale-aware FE can render per-locale. This tests
// the pure serializer the list handler uses (no DB), mirroring the consumer's
// pure-transform tests.
func TestSerializeNotification_IncludesI18nFields(t *testing.T) {
	t.Parallel()
	key := "notif.llm_job.completed"
	params := json.RawMessage(`{"operation":"entity_extraction"}`)
	bodyText := "some body"

	m := serializeNotification(
		uuid.New(),
		"llm_job",
		"Entity extraction completed",
		&bodyText,
		json.RawMessage(`{"job_id":"x"}`),
		&key,
		params,
		nil,
		time.Now(),
	)

	// Fallback text present.
	if m["title"] != "Entity extraction completed" {
		t.Errorf("title fallback missing/wrong: %v", m["title"])
	}
	if m["body"] != bodyText {
		t.Errorf("body fallback missing/wrong: %v", m["body"])
	}

	// i18n fields present.
	if _, ok := m["message_key"]; !ok {
		t.Fatal("message_key absent from serialized row")
	}
	if _, ok := m["message_params"]; !ok {
		t.Fatal("message_params absent from serialized row")
	}

	// Round-trip through JSON to prove the wire shape a client sees.
	b, err := json.Marshal(m)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var out map[string]any
	if err := json.Unmarshal(b, &out); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if out["message_key"] != key {
		t.Errorf("message_key on wire wrong: %v", out["message_key"])
	}
	mp, ok := out["message_params"].(map[string]any)
	if !ok {
		t.Fatalf("message_params not an object on wire: %v", out["message_params"])
	}
	if mp["operation"] != "entity_extraction" {
		t.Errorf("message_params.operation on wire wrong: %v", mp["operation"])
	}
}

// TestSerializeNotification_NullableI18nForLegacyRows proves backward
// compatibility: a legacy row (NULL message_key / message_params) serializes
// with both fields present but JSON null — no consumer breaks, and the client
// simply renders the title/body fallback.
func TestSerializeNotification_NullableI18nForLegacyRows(t *testing.T) {
	t.Parallel()
	m := serializeNotification(
		uuid.New(),
		"system",
		"Legacy notification",
		nil, // no body
		json.RawMessage(`{}`),
		nil, // NULL message_key
		nil, // NULL message_params
		nil,
		time.Now(),
	)

	// Keys must be present (so the FE can rely on them) ...
	if _, ok := m["message_key"]; !ok {
		t.Fatal("message_key must be present even when NULL")
	}
	if _, ok := m["message_params"]; !ok {
		t.Fatal("message_params must be present even when NULL")
	}

	// ... and must marshal to JSON null.
	b, err := json.Marshal(m)
	if err != nil {
		t.Fatalf("marshal: %v", err)
	}
	var out map[string]any
	if err := json.Unmarshal(b, &out); err != nil {
		t.Fatalf("unmarshal: %v", err)
	}
	if out["message_key"] != nil {
		t.Errorf("legacy message_key should be JSON null, got %v", out["message_key"])
	}
	if out["message_params"] != nil {
		t.Errorf("legacy message_params should be JSON null, got %v", out["message_params"])
	}
	// title fallback still there; body omitted (prior contract preserved).
	if out["title"] != "Legacy notification" {
		t.Errorf("title fallback missing: %v", out["title"])
	}
	if _, hasBody := out["body"]; hasBody {
		t.Errorf("body should be omitted when NULL, got %v", out["body"])
	}
}

// TestNullableHelpers covers the NULL-mapping helpers the create/batch paths
// use so an omitted i18n field stores as SQL NULL rather than ''/'{}'.
func TestNullableHelpers(t *testing.T) {
	t.Parallel()
	if nullableText("") != nil {
		t.Error("empty string should map to nil (SQL NULL)")
	}
	if nullableText("k") != "k" {
		t.Error("non-empty string should pass through")
	}
	if nullableJSONB(nil) != nil {
		t.Error("nil map should map to nil (SQL NULL)")
	}
	if nullableJSONB(map[string]any{}) != nil {
		t.Error("empty map should map to nil (SQL NULL)")
	}
	got := nullableJSONB(map[string]any{"operation": "chat"})
	b, ok := got.([]byte)
	if !ok {
		t.Fatalf("non-empty map should marshal to []byte, got %T", got)
	}
	var out map[string]any
	if err := json.Unmarshal(b, &out); err != nil {
		t.Fatalf("nullableJSONB output not JSON: %v", err)
	}
	if out["operation"] != "chat" {
		t.Errorf("nullableJSONB lost data: %v", out)
	}
}
