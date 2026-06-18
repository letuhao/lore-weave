package confirmation

import (
	"errors"
	"testing"
)

func TestCheck_Match(t *testing.T) {
	if err := Check("reality-prod-1", "reality-prod-1"); err != nil {
		t.Fatalf("Check: %v", err)
	}
}

func TestCheck_MismatchRejected(t *testing.T) {
	err := Check("reality-prod-1", "reality-prod-2")
	if err == nil || !errors.Is(err, ErrConfirmation) {
		t.Fatalf("want ErrConfirmation, got %v", err)
	}
}

func TestCheck_EmptyExpectedRejected(t *testing.T) {
	if err := Check("", ""); err == nil {
		t.Fatal("empty expected must be rejected (no enter-to-confirm)")
	}
}

func TestCheck_WhitespaceTrimmed(t *testing.T) {
	if err := Check("foo", "  foo\n"); err != nil {
		t.Fatalf("trim mismatch: %v", err)
	}
}

func TestChallengeFor(t *testing.T) {
	if ChallengeFor("  abc  ") != "abc" {
		t.Fatal("ChallengeFor should trim")
	}
}
