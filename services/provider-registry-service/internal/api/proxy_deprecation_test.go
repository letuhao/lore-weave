package api

// Phase 4d — unit tests for the pure isDeprecatedProxyPath helper.
// The integration tests in proxy_integration_test.go cover the
// doProxy guard end-to-end, but they need a live Postgres + httptest
// upstream and only exercise the happy path of the helper. This file
// pins the normalization edge cases (case, leading slashes, double
// slashes, .. traversal, audio carve-out) so a future refactor of
// the helper can't silently drop a defense.
//
// Added in /review-impl follow-up (LOW#4) after MED#1 + MED#2
// hardening (path-traversal + case-sensitivity bypasses).

import "testing"

func TestIsDeprecatedProxyPath(t *testing.T) {
	t.Parallel()

	cases := []struct {
		name string
		path string
		want bool
	}{
		// ── exact deprecated paths ───────────────────────────────────
		{"chat-completions exact", "v1/chat/completions", true},
		{"completions exact", "v1/completions", true},
		{"embeddings exact", "v1/embeddings", true},

		// ── leading-slash variants (MED hardening — pre-fix bypass) ──
		{"single leading slash", "/v1/chat/completions", true},
		{"double leading slash", "//v1/chat/completions", true},
		{"triple leading slash", "///v1/chat/completions", true},

		// ── case-insensitivity (MED#2 — pre-fix bypass) ──────────────
		{"all uppercase", "V1/CHAT/COMPLETIONS", true},
		{"mixed case", "v1/Chat/Completions", true},
		{"mixed case embeddings", "V1/Embeddings", true},

		// ── path traversal (MED#1 — pre-fix bypass) ──────────────────
		{"audio dotdot to chat", "v1/audio/../chat/completions", true},
		{"deep dotdot", "a/b/c/../../../v1/chat/completions", true},
		{"single dot", "./v1/chat/completions", true},
		{"trailing dotdot resolves up", "v1/chat/completions/x/..", true},

		// ── double slashes inside path ───────────────────────────────
		{"double slash inside", "v1//chat/completions", true},

		// ── audio carve-out: MUST pass through ───────────────────────
		{"audio transcriptions", "v1/audio/transcriptions", false},
		{"audio speech", "v1/audio/speech", false},
		{"audio leading slash", "/v1/audio/speech", false},
		{"audio uppercase", "V1/AUDIO/SPEECH", false},

		// ── adjacent / suffix paths MUST NOT be denied ───────────────
		{"chat completions versioned", "v1/chat/completions/v2", false},
		{"chat completions extra suffix", "v1/chat/completionsextra", false},
		{"embeddings under audio", "v1/audio/embeddings", false},
		{"unrelated path", "v1/models", false},
		{"root", "v1", false},

		// ── degenerate inputs ────────────────────────────────────────
		{"empty", "", false},
		{"only slashes", "////", false},
		{"only dot", ".", false},
	}

	for _, tc := range cases {
		tc := tc
		t.Run(tc.name, func(t *testing.T) {
			t.Parallel()
			got := isDeprecatedProxyPath(tc.path)
			if got != tc.want {
				t.Errorf("isDeprecatedProxyPath(%q) = %v, want %v",
					tc.path, got, tc.want)
			}
		})
	}
}
