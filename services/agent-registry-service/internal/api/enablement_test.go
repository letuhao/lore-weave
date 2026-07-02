package api

import "testing"

func b(v bool) *bool { return &v }

// REG-P0-04 — the D1 precedence matrix, tested on the pure resolver.
// Effective = book override → user override → tier default (on).
func TestResolveEnabled_Matrix(t *testing.T) {
	cases := []struct {
		name     string
		userOv   *bool
		bookOv   *bool
		expected bool
	}{
		{"no overrides → default on", nil, nil, true},
		{"user disable", b(false), nil, false},
		{"user enable (explicit)", b(true), nil, true},
		{"book disable shadows nothing", nil, b(false), false},
		{"book enable", nil, b(true), true},
		{"user off + book on → book wins (on)", b(false), b(true), true},
		{"user on + book off → book wins (off)", b(true), b(false), false},
		{"user off + book off → off", b(false), b(false), false},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			if got := resolveEnabled(true, c.userOv, c.bookOv); got != c.expected {
				t.Fatalf("resolveEnabled(true, %v, %v) = %v, want %v", c.userOv, c.bookOv, got, c.expected)
			}
		})
	}
}
