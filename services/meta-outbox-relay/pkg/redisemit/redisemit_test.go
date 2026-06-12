package redisemit

import (
	"encoding/json"
	"strings"
	"testing"
)

// fieldValue is the precision-critical bit of the xreality domain-field
// promotion (P2/113): a JSON int beyond float64 range must survive verbatim,
// strings/bools pass through, and nested objects re-encode to JSON.
func TestFieldValue(t *testing.T) {
	// Decode with UseNumber so the big int arrives as json.Number (as the
	// emitter does), not float64.
	dec := json.NewDecoder(strings.NewReader(`{"s":"hi","n":9007199254740993,"b":true,"nested":{"k":1},"nul":null}`))
	dec.UseNumber()
	var obj map[string]any
	if err := dec.Decode(&obj); err != nil {
		t.Fatalf("decode: %v", err)
	}

	if got := fieldValue(obj["s"]); got != "hi" {
		t.Errorf("string: got %v", got)
	}
	if got := fieldValue(obj["n"]); got != "9007199254740993" {
		t.Errorf("big int must survive verbatim, got %v", got)
	}
	if got := fieldValue(obj["b"]); got != true {
		t.Errorf("bool: got %v", got)
	}
	if got := fieldValue(obj["nested"]); got != `{"k":1}` {
		t.Errorf("nested object must re-encode to JSON, got %v", got)
	}
	if got := fieldValue(obj["nul"]); got != "" {
		t.Errorf("nil must become empty string, got %v", got)
	}
}
