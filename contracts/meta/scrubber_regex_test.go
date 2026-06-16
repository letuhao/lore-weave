package meta

import (
	"strings"
	"testing"
)

// PRR-01: the production RegexScrubber must actually redact the seven L4.Q.6
// pattern classes (previously only a passthrough stub existed).

func TestRegexScrubber_AllSevenPatterns(t *testing.T) {
	s := NewRegexScrubber(nil)
	cases := []struct {
		name           string
		raw            string
		mustNotContain string
		mustContain    string
	}{
		{"email", "contact alice@example.com now", "alice@example.com", "[EMAIL]"},
		{"ssn", "ssn 123-45-6789 here", "123-45-6789", "[SSN]"},
		{"ipv6", "addr 2001:0db8:85a3:0000:0000:8a2e:0370:7334 ok", "2001:0db8", "[IPV6]"},
		{"ipv4", "from 192.168.1.100 today", "192.168.1.100", "[IPV4]"},
		{"cc", "card 4111 1111 1111 1111 charged", "4111 1111 1111 1111", "[CC]"},
		{"apikey", "key sk_live_abcdef0123456789ABCD leaked", "sk_live_abcdef0123456789ABCD", "[APIKEY]"},
		{"phone", "call 415-555-0132 asap", "415-555-0132", "[PHONE]"},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			got := s.Scrub(c.raw)
			if strings.Contains(got.Scrubbed, c.mustNotContain) {
				t.Errorf("scrubbed still contains raw %q: %q", c.mustNotContain, got.Scrubbed)
			}
			if !strings.Contains(got.Scrubbed, c.mustContain) {
				t.Errorf("scrubbed missing placeholder %q: %q", c.mustContain, got.Scrubbed)
			}
		})
	}
}

func TestRegexScrubber_HashAndVersionValid(t *testing.T) {
	got := NewRegexScrubber(nil).Scrub("alice@example.com")
	if len(got.RawHash) != 32 {
		t.Fatalf("RawHash must be SHA-256 (32 bytes), got %d", len(got.RawHash))
	}
	if got.Version != regexScrubberVersion {
		t.Errorf("Version = %q, want %q", got.Version, regexScrubberVersion)
	}
	if got.ScrubbedAt.IsZero() {
		t.Error("ScrubbedAt must be set")
	}
	if err := MustValidateScrubbedField(got); err != nil {
		t.Errorf("scrubbed field should be internally consistent: %v", err)
	}
}

func TestRegexScrubber_HashOfOriginalNotScrubbed(t *testing.T) {
	s := NewRegexScrubber(nil)
	a := s.Scrub("alice@example.com")
	b := s.Scrub("bob@example.com")
	// Distinct originals → distinct forensic hash, even though both scrub to the
	// same placeholder — proves the hash is of the raw input.
	if string(a.RawHash) == string(b.RawHash) {
		t.Error("distinct raw inputs must yield distinct RawHash")
	}
	if a.Scrubbed != "[EMAIL]" || b.Scrubbed != "[EMAIL]" {
		t.Errorf("both should scrub to [EMAIL]; got %q vs %q", a.Scrubbed, b.Scrubbed)
	}
}

func TestRegexScrubber_CleanTextUnchanged(t *testing.T) {
	got := NewRegexScrubber(nil).Scrub("user performed action on widget 7")
	if got.Scrubbed != "user performed action on widget 7" {
		t.Errorf("non-PII text should pass through unchanged, got %q", got.Scrubbed)
	}
}
