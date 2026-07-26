package jobs

import "testing"

// ParseJobMetaSpendCap (P4/Wave-C H-K) — nil-tolerant extraction of the public
// key's per-key USD sub-cap from job_meta. A malformed cap must never fail a
// submit; it just means "no per-key cap" (the owner guardrail still applies).
func TestParseJobMetaSpendCap(t *testing.T) {
	cases := []struct {
		name string
		meta string
		want *float64
	}{
		{"absent", `{"mcp_key_id":"x"}`, nil},
		{"empty bytes", ``, nil},
		{"null", `null`, nil},
		{"non-object", `"5.0"`, nil},
		{"string-not-number", `{"spend_cap_usd":"5.0"}`, nil}, // JSON string ≠ number → ignored
		{"negative", `{"spend_cap_usd":-1.0}`, nil},
		{"valid", `{"spend_cap_usd":5.5}`, f(5.5)},
		{"zero is valid", `{"spend_cap_usd":0}`, f(0)},
		{"alongside key", `{"mcp_key_id":"k","spend_cap_usd":2.25}`, f(2.25)},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := ParseJobMetaSpendCap([]byte(c.meta))
			switch {
			case c.want == nil && got != nil:
				t.Fatalf("want nil, got %v", *got)
			case c.want != nil && got == nil:
				t.Fatalf("want %v, got nil", *c.want)
			case c.want != nil && got != nil && *got != *c.want:
				t.Fatalf("want %v, got %v", *c.want, *got)
			}
		})
	}
}

func f(v float64) *float64 { return &v }
