package prompt

import (
	"errors"
	"testing"
)

func TestAllIntentsCount(t *testing.T) {
	if got, want := len(AllIntents()), 7; got != want {
		t.Fatalf("AllIntents count = %d; want %d (S09 §12Y.2 vocabulary)", got, want)
	}
}

func TestAllIntentsExhaustive(t *testing.T) {
	want := map[Intent]bool{
		IntentSessionTurn:     true,
		IntentNPCReply:        true,
		IntentCanonCheck:      true,
		IntentCanonExtraction: true,
		IntentAdminTriggered:  true,
		IntentWorldSeed:       true,
		IntentSummary:         true,
	}
	got := map[Intent]bool{}
	for _, it := range AllIntents() {
		got[it] = true
	}
	if len(got) != len(want) {
		t.Fatalf("intent set mismatch; got %v want %v", got, want)
	}
	for it := range want {
		if !got[it] {
			t.Errorf("AllIntents missing %q", it)
		}
	}
}

func TestParseIntent_OK(t *testing.T) {
	for _, want := range AllIntents() {
		got, err := ParseIntent(string(want))
		if err != nil {
			t.Errorf("ParseIntent(%q) err = %v; want nil", want, err)
			continue
		}
		if got != want {
			t.Errorf("ParseIntent(%q) = %q; want %q", want, got, want)
		}
	}
}

func TestParseIntent_Unknown(t *testing.T) {
	_, err := ParseIntent("turn_resolution") // looks plausible but isn't in the enum
	if err == nil {
		t.Fatalf("ParseIntent(unknown) returned nil err; want ErrUnknownIntent")
	}
	if !errors.Is(err, ErrUnknownIntent) {
		t.Errorf("ParseIntent(unknown) err = %v; want wraps ErrUnknownIntent", err)
	}
}

func TestIntent_IsValid(t *testing.T) {
	for _, it := range AllIntents() {
		if !it.IsValid() {
			t.Errorf("IsValid(%q) = false; want true", it)
		}
	}
	if Intent("").IsValid() {
		t.Errorf("IsValid(empty) = true; want false")
	}
	if Intent("turn_resolution").IsValid() {
		t.Errorf("IsValid(turn_resolution) = true; want false")
	}
}
