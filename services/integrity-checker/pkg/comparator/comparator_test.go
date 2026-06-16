package comparator

import (
	"bytes"
	"testing"
)

// canon is a test helper: canonicalize or fail.
func canon(t *testing.T, in string) []byte {
	t.Helper()
	out, err := Canonicalize([]byte(in))
	if err != nil {
		t.Fatalf("Canonicalize(%q): %v", in, err)
	}
	return out
}

// equal reports whether two JSON docs canonicalize byte-equal (the drift test).
func equal(t *testing.T, a, b string) bool {
	t.Helper()
	return bytes.Equal(canon(t, a), canon(t, b))
}

func TestCanonicalize_KeyOrderIrrelevant(t *testing.T) {
	if !equal(t, `{"b":2,"a":1}`, `{"a":1,"b":2}`) {
		t.Error("key order must not affect canonical form")
	}
}

func TestCanonicalize_BytesDiffer_NotEqual(t *testing.T) {
	if equal(t, `{"value":42}`, `{"value":99}`) {
		t.Error("different values must NOT canonicalize equal")
	}
}

func TestCanonicalize_NestedStructures(t *testing.T) {
	a := `{"inv":[{"id":2,"name":"b"},{"id":1,"name":"a"}],"meta":{"z":1,"a":2}}`
	b := `{"meta":{"a":2,"z":1},"inv":[{"name":"b","id":2},{"name":"a","id":1}]}`
	if !equal(t, a, b) {
		t.Error("nested object key order must be canonicalized recursively")
	}
}

func TestCanonicalize_ArrayOrderIsSignificant(t *testing.T) {
	// Array element ORDER is meaningful (unlike object keys) — reordering is drift.
	if equal(t, `[1,2,3]`, `[3,2,1]`) {
		t.Error("array order must be significant")
	}
}

func TestCanonicalize_DistinguishesNumericTypes(t *testing.T) {
	// json.Number preserves int-vs-float — 1 and 1.0 are distinct (losing the
	// integer type is itself projection drift).
	if equal(t, `{"v":1}`, `{"v":1.0}`) {
		t.Error("1 and 1.0 must NOT canonicalize equal (json.Number preserves the distinction)")
	}
}

func TestCanonicalize_EmptyIsNull(t *testing.T) {
	out := canon(t, "")
	if string(out) != "null" {
		t.Errorf("empty input should canonicalize to null, got %q", out)
	}
	// Two empties compare equal.
	if !equal(t, "", "") {
		t.Error("empty == empty")
	}
}

func TestCanonicalize_RejectsInvalidJSON(t *testing.T) {
	if _, err := Canonicalize([]byte(`{not json`)); err == nil {
		t.Error("expected error on invalid JSON")
	}
}
