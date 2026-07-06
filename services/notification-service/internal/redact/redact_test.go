package redact

import (
	"strings"
	"testing"
)

func TestBody_RedactsSecretShapes(t *testing.T) {
	cases := []struct {
		name string
		in   string
	}{
		{"bearer", "upstream 401: Authorization: Bearer abc123DEF456ghi returned"},
		{"sk key", "provider error: invalid key sk-proj-abcdef0123456789ABCDEF"},
		{"api_key assign", "config bad: api_key=abcd1234efgh5678"},
		{"api-key colon", "header api-key:ZYXW9876vuts5432"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			out := Body(c.in)
			if !strings.Contains(out, mask) {
				t.Errorf("expected a %s in output, got %q", mask, out)
			}
			// The raw secret token must not survive verbatim.
			for _, tok := range []string{"abc123DEF456ghi", "sk-proj-abcdef0123456789ABCDEF", "abcd1234efgh5678", "ZYXW9876vuts5432"} {
				if strings.Contains(out, tok) {
					t.Errorf("secret %q survived redaction: %q", tok, out)
				}
			}
		})
	}
}

// The narrow scope is load-bearing: legitimate content (emails, names, plain
// prose, short codes) must pass through untouched — over-redaction corrupts real
// notifications. A drift toward an email/name pattern reds this.
func TestBody_PreservesLegitimateContent(t *testing.T) {
	for _, s := range []string{
		"Chapter shared with alice@example.com",
		"Translation of 第一章 completed",
		"[LLM_STUCK_TIMEOUT] job stalled",
		"Entity extraction completed",
		"",
	} {
		if got := Body(s); got != s {
			t.Errorf("legit content changed: %q -> %q", s, got)
		}
	}
}
