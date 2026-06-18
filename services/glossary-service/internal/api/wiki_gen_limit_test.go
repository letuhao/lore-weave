package api

import (
	"encoding/json"
	"testing"
)

// D-WIKI-M7B-GEN-LIMIT — the delegate's 202 body is augmented with selection
// counts so the FE can warn when the genLimit silently dropped candidates.
func TestInjectGenSelectionCounts(t *testing.T) {
	t.Run("adds counts to a JSON object body", func(t *testing.T) {
		in := []byte(`{"job_id":"j1","status":"pending"}`)
		out := injectGenSelectionCounts(in, 87, 50)
		var obj map[string]any
		if err := json.Unmarshal(out, &obj); err != nil {
			t.Fatalf("output not valid JSON: %v", err)
		}
		if obj["job_id"] != "j1" || obj["status"] != "pending" {
			t.Fatalf("original fields lost: %v", obj)
		}
		// JSON numbers decode as float64.
		if obj["total_matched"].(float64) != 87 || obj["selected"].(float64) != 50 {
			t.Fatalf("counts not injected: %v", obj)
		}
	})

	t.Run("no truncation: total_matched == selected", func(t *testing.T) {
		out := injectGenSelectionCounts([]byte(`{"job_id":"j2"}`), 12, 12)
		var obj map[string]any
		_ = json.Unmarshal(out, &obj)
		if obj["total_matched"].(float64) != 12 || obj["selected"].(float64) != 12 {
			t.Fatalf("counts wrong: %v", obj)
		}
	})

	t.Run("non-object body is returned unchanged", func(t *testing.T) {
		for _, raw := range []string{`[1,2,3]`, `"hello"`, `not json`, ``} {
			out := injectGenSelectionCounts([]byte(raw), 5, 1)
			if string(out) != raw {
				t.Fatalf("non-object body %q mutated to %q", raw, string(out))
			}
		}
	})
}
