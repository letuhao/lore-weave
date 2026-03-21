package mail

import (
	"strings"
	"testing"
)

func TestEnvelopeAddress(t *testing.T) {
	tests := []struct {
		in, want string
	}{
		{"noreply@example.com", "noreply@example.com"},
		{"LoreWeave <noreply@example.com>", "noreply@example.com"},
		{" Name <a@b.co> ", "a@b.co"},
	}
	for _, tt := range tests {
		if got := envelopeAddress(tt.in); got != tt.want {
			t.Errorf("envelopeAddress(%q) = %q, want %q", tt.in, got, tt.want)
		}
	}
}

func TestBuildRFC822HasHeaders(t *testing.T) {
	msg := buildRFC822("From <f@x.com>", "t@x.com", "Hi", "Line1\nLine2")
	if !strings.Contains(msg, "Subject: Hi") {
		t.Fatal(msg)
	}
	if !strings.Contains(msg, "To: t@x.com") {
		t.Fatal(msg)
	}
}
