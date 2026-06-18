package api

import "testing"

// K12.1 — canEmbed gates the /internal/embed dispatch. It must be fail-OPEN on an
// empty/unknown flag set (so a model whose capability_flags were never populated is not
// wrongly blocked) and reject ONLY when the flags definitively classify the model as some
// other capability.
func TestCanEmbed(t *testing.T) {
	cases := []struct {
		name string
		caps map[string]any
		want bool
	}{
		{"nil flags fail open", nil, true},
		{"empty flags fail open", map[string]any{}, true},
		{"explicit embedding bool", map[string]any{"embedding": true}, true},
		{"capability token embedding", map[string]any{"_capability": "embedding"}, true},
		{"capability token embed", map[string]any{"_capability": "embed"}, true},
		// "chat" is the discovery DEFAULT, not an affirmative exclusion → fail open. A
		// BYOK embedding model whose name misses the "embed" heuristic is tagged chat;
		// rejecting it would break a working embedding call (review-impl HIGH-2).
		{"chat token fails open (not rejected)", map[string]any{"_capability": "chat"}, true},
		{"chat bool fails open (not rejected)", map[string]any{"chat": true}, true},
		// Affirmatively-detected non-embedding capabilities ARE rejected pre-dispatch.
		{"rerank bool rejected", map[string]any{"rerank": true}, false},
		{"capability token rerank rejected", map[string]any{"_capability": "rerank"}, false},
		{"capability token stt rejected", map[string]any{"_capability": "stt"}, false},
		{"image_gen bool rejected", map[string]any{"image_gen": true}, false},
		// Metadata-only flags with no capability signal → unknown, fail open.
		{"display-name only fails open", map[string]any{"_display_name": "text-embedding-3-small"}, true},
		// A model tagged embedding but also carrying a stale chat token still embeds
		// (an explicit positive wins over a definite-other below it).
		{"embedding wins over chat", map[string]any{"embedding": true, "chat": true}, true},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := canEmbed(c.caps); got != c.want {
				t.Fatalf("canEmbed(%v) = %v, want %v", c.caps, got, c.want)
			}
		})
	}
}
