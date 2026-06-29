package api

import (
	"strings"
	"testing"
)

// Pure-unit tests (no DB) for the key-generation + prefix primitives.

func TestGenerateMcpAPIKey(t *testing.T) {
	full, prefix, err := generateMcpAPIKey()
	if err != nil {
		t.Fatalf("generate: %v", err)
	}
	if !strings.HasPrefix(full, mcpKeyVisiblePrefix) {
		t.Fatalf("full key missing scheme: %q", full)
	}
	wantPrefixLen := len(mcpKeyVisiblePrefix) + mcpKeyPrefixBodyLen
	if len(prefix) != wantPrefixLen {
		t.Fatalf("prefix len = %d, want %d (%q)", len(prefix), wantPrefixLen, prefix)
	}
	if !strings.HasPrefix(full, prefix) {
		t.Fatalf("prefix %q is not a prefix of full %q", prefix, full)
	}
	if len(full) <= wantPrefixLen+8 {
		t.Fatalf("full key suspiciously short: %q", full)
	}
	// Two keys must differ (random body).
	full2, _, _ := generateMcpAPIKey()
	if full == full2 {
		t.Fatal("two generated keys are identical")
	}
}

func TestMcpKeyPrefixOf(t *testing.T) {
	full, prefix, _ := generateMcpAPIKey()
	if got := mcpKeyPrefixOf(full); got != prefix {
		t.Fatalf("prefixOf(full) = %q, want %q", got, prefix)
	}
	// Non-lw_pk or too-short keys yield "" (cheap reject before any DB/hash work).
	for _, bad := range []string{"", "lw_pk_", "lw_pk_ab", "nope_abcdefghij", "sk-1234567890"} {
		if got := mcpKeyPrefixOf(bad); got != "" {
			t.Fatalf("prefixOf(%q) = %q, want empty", bad, got)
		}
	}
}

func TestMcpResolveLimiter_CapsAttemptsPerPrefix(t *testing.T) {
	// H-H: the per-prefix limiter must stop letting attempts through after the cap,
	// so a known prefix can't drive unbounded Argon2id verifications.
	rl := newMcpResolveLimiter()
	const key = "mcpkey:lw_pk_AAAAAA"
	allowed := 0
	for range mcpResolveMaxPerWindow + 5 {
		if rl.Allow(key) {
			allowed++
		}
	}
	if allowed != mcpResolveMaxPerWindow {
		t.Fatalf("allowed %d attempts, want exactly the cap %d", allowed, mcpResolveMaxPerWindow)
	}
	// A different prefix is independently allowed (not collateral-damaged).
	if !rl.Allow("mcpkey:lw_pk_BBBBBB") {
		t.Fatal("a fresh prefix should be allowed after another prefix is capped")
	}
}
