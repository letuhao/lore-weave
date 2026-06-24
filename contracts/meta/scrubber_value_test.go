package meta

import (
	"bytes"
	"reflect"
	"strings"
	"testing"
	"unicode/utf8"
)

// TestScrubValue_BinaryBytesPassThrough is the D-SCRUB-BINARY-FIDELITY guard: a
// BINARY []byte leaf (e.g. a 32-byte SHA-256 like admin_action_audit.
// error_detail_raw_hash) must pass through the scrubber UNCHANGED — running the
// 7 PII text regexes over raw bytes could chance-match + mutate the blob in the
// audit copy. Valid-UTF-8 (text) []byte is still scrubbed (preserved behavior).
func TestScrubValue_BinaryBytesPassThrough(t *testing.T) {
	// A 32-byte binary blob with high bytes → invalid UTF-8 → must pass through.
	hash := make([]byte, 32)
	for i := range hash {
		hash[i] = byte(200 + i%56)
	}
	if utf8.Valid(hash) {
		t.Skip("crafted blob unexpectedly valid UTF-8")
	}
	out := ScrubValue(map[string]any{"error_detail_raw_hash": hash}, RegexScrubber{}).(map[string]any)
	if got := out["error_detail_raw_hash"].([]byte); !bytes.Equal(got, hash) {
		t.Errorf("binary blob mutated by scrubber: in=%x out=%x", hash, got)
	}

	// Discriminator: the SAME PII-looking content scrubs as TEXT (valid UTF-8),
	// but appending ONE invalid byte flips it to a verbatim pass-through.
	text := []byte("call 555-123-4567")
	binary := append([]byte("call 555-123-4567"), 0xff)
	outText := ScrubValue(map[string]any{"x": text}, RegexScrubber{}).(map[string]any)["x"].([]byte)
	outBin := ScrubValue(map[string]any{"x": binary}, RegexScrubber{}).(map[string]any)["x"].([]byte)
	if !strings.Contains(string(outText), "[PHONE]") {
		t.Errorf("valid-UTF8 []byte must still be scrubbed, got %q", outText)
	}
	if !bytes.Equal(outBin, binary) {
		t.Errorf("binary []byte must pass through unchanged, got %x", outBin)
	}
}

func TestScrubValue_StringLeavesOnly(t *testing.T) {
	in := map[string]any{
		"email":   "alice@example.com",
		"note":    "call me at 555-123-4567 please",
		"count":   42,   // number — must pass through untouched
		"active":  true, // bool — untouched
		"missing": nil,  // nil — untouched
		"ratio":   3.14, // float — untouched
		"nested": map[string]any{
			"ssn":  "123-45-6789",
			"tags": []any{"ok", "ip 10.0.0.1", 7},
		},
	}
	out := ScrubValue(in, RegexScrubber{}).(map[string]any)

	if got := out["email"].(string); !strings.Contains(got, "[EMAIL]") {
		t.Errorf("email not redacted: %q", got)
	}
	if got := out["note"].(string); !strings.Contains(got, "[PHONE]") {
		t.Errorf("phone not redacted: %q", got)
	}
	if out["count"] != 42 || out["active"] != true || out["ratio"] != 3.14 || out["missing"] != nil {
		t.Errorf("non-string leaf mutated: %+v", out)
	}
	nested := out["nested"].(map[string]any)
	if got := nested["ssn"].(string); !strings.Contains(got, "[SSN]") {
		t.Errorf("nested ssn not redacted: %q", got)
	}
	tags := nested["tags"].([]any)
	if !strings.Contains(tags[1].(string), "[IPV4]") {
		t.Errorf("nested slice ip not redacted: %v", tags)
	}
	if tags[2] != 7 {
		t.Errorf("nested slice number mutated: %v", tags)
	}
}

func TestScrubValue_IsImmutable_DeepCopy(t *testing.T) {
	in := map[string]any{
		"email":  "bob@example.com",
		"nested": map[string]any{"ip": "192.168.1.1"},
		"list":   []any{"sk_live_abcdef123456"},
	}
	_ = ScrubValue(in, RegexScrubber{})

	// The ORIGINAL must be byte-identical after scrubbing — ScrubValue must
	// never write back (the same maps feed the persisted write + outbox).
	if in["email"] != "bob@example.com" {
		t.Errorf("input email mutated: %v", in["email"])
	}
	if in["nested"].(map[string]any)["ip"] != "192.168.1.1" {
		t.Errorf("input nested map mutated: %v", in["nested"])
	}
	if in["list"].([]any)[0] != "sk_live_abcdef123456" {
		t.Errorf("input slice mutated: %v", in["list"])
	}
}

// TestScrubValue_TypedContainersRedacted is the code-r1-BLOCK1 regression guard:
// the reflect fallback must redact string leaves in containers the type switch
// does NOT enumerate ([]byte, map[string]string, []string, named string types).
// Under-redaction is the risk this slice exists to prevent.
func TestScrubValue_TypedContainersRedacted(t *testing.T) {
	type namedStr string
	in := map[string]any{
		"raw_bytes":  []byte("leak alice@example.com here"),
		"typed_map":  map[string]string{"k": "ssn 123-45-6789"},
		"typed_list": []string{"ok", "card 4111111111111111"},
		"named":      namedStr("ping 10.0.0.1"),
	}
	out := ScrubValue(in, RegexScrubber{}).(map[string]any)

	if got := string(out["raw_bytes"].([]byte)); strings.Contains(got, "alice@example.com") || !strings.Contains(got, "[EMAIL]") {
		t.Errorf("[]byte leaf not redacted: %q", got)
	}
	tm := out["typed_map"].(map[string]any)
	if got := tm["k"].(string); strings.Contains(got, "123-45-6789") || !strings.Contains(got, "[SSN]") {
		t.Errorf("map[string]string value not redacted: %q", got)
	}
	tl := out["typed_list"].([]any)
	if got := tl[1].(string); strings.Contains(got, "4111111111111111") || !strings.Contains(got, "[CC]") {
		t.Errorf("[]string element not redacted: %q", got)
	}
	if got := out["named"].(string); strings.Contains(got, "10.0.0.1") || !strings.Contains(got, "[IPV4]") {
		t.Errorf("named string type not redacted: %q", got)
	}
}

// TestScrubValue_RedactsMapKeys: a map keyed on PII must have its KEY redacted
// (review-impl #3) — under-redaction is the risk for the general helper.
func TestScrubValue_RedactsMapKeys(t *testing.T) {
	in := map[string]any{"alice@example.com": "consented"}
	out := ScrubValue(in, RegexScrubber{}).(map[string]any)
	if _, raw := out["alice@example.com"]; raw {
		t.Errorf("PII map key not redacted: %v", out)
	}
	if _, ok := out["[EMAIL]"]; !ok {
		t.Errorf("expected redacted key [EMAIL], got %v", out)
	}
}

// TestScrubValue_StructValueRedacted: a struct VALUE with exported string fields
// is scrubbed via the JSON round-trip (closes code-review WARN2). json tags are
// honored in the resulting shape.
func TestScrubValue_StructValueRedacted(t *testing.T) {
	type contact struct {
		Email string `json:"email"`
		Note  string `json:"note"`
		Count int    `json:"count"`
	}
	in := map[string]any{
		"c": contact{Email: "eve@example.com", Note: "ssn 123-45-6789", Count: 3},
	}
	out := ScrubValue(in, RegexScrubber{}).(map[string]any)
	c := out["c"].(map[string]any) // struct → JSON map
	if got := c["email"].(string); strings.Contains(got, "eve@example.com") || !strings.Contains(got, "[EMAIL]") {
		t.Errorf("struct email field not redacted: %q", got)
	}
	if got := c["note"].(string); !strings.Contains(got, "[SSN]") {
		t.Errorf("struct note field not redacted: %q", got)
	}
	if c["count"].(float64) != 3 { // JSON numbers decode to float64
		t.Errorf("struct numeric field altered: %v", c["count"])
	}
}

func TestScrubValuesMap_NilReturnsNil(t *testing.T) {
	if ScrubValuesMap(nil, RegexScrubber{}) != nil {
		t.Error("ScrubValuesMap(nil) should return nil")
	}
}

func TestScrubValue_CycleGuardDoesNotOverflow(t *testing.T) {
	// Self-referential map: must not stack-overflow (depth cap kicks in).
	a := map[string]any{"k": "x"}
	a["self"] = a
	out := ScrubValue(a, RegexScrubber{}).(map[string]any)
	if out["k"] != "x" {
		t.Errorf("scalar leaf lost under cycle guard: %v", out["k"])
	}
	// Deep chain past the cap truncates rather than panicking.
	deep := map[string]any{}
	cur := deep
	for range maxScrubDepth + 10 {
		next := map[string]any{}
		cur["next"] = next
		cur = next
	}
	_ = ScrubValue(deep, RegexScrubber{}) // must not panic
}

func TestScrubValuesMap_ReturnsFreshMap(t *testing.T) {
	in := map[string]any{"email": "c@d.com"}
	out := ScrubValuesMap(in, RegexScrubber{})
	if reflect.ValueOf(out).Pointer() == reflect.ValueOf(in).Pointer() {
		t.Error("ScrubValuesMap returned the SAME backing map (must be a fresh copy)")
	}
}
