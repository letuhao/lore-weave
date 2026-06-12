package lifecycle

import (
	"errors"
	"testing"
)

func TestAllPresenceStates_ExhaustiveExactly6(t *testing.T) {
	// SR11-D3 fixes the enum at 6 variants. Lock with a count test so
	// a future caller can't append "afk" without updating SQL CHECK + tests.
	if got := len(AllPresenceStates()); got != 6 {
		t.Fatalf("AllPresenceStates() = %d entries, want exactly 6 per SR11-D3", got)
	}
	want := []PresenceState{
		PresenceActive, PresenceIdle, PresenceTyping,
		PresenceWaitingAI, PresenceDisconnectedBrief, PresenceDisconnectedGhost,
	}
	for i, p := range want {
		if AllPresenceStates()[i] != p {
			t.Errorf("AllPresenceStates()[%d] = %q, want %q", i, AllPresenceStates()[i], p)
		}
	}
}

func TestParsePresenceState_RoundTrip(t *testing.T) {
	for _, p := range AllPresenceStates() {
		round, err := ParsePresenceState(string(p))
		if err != nil {
			t.Errorf("ParsePresenceState(%q): %v", p, err)
			continue
		}
		if round != p {
			t.Errorf("round-trip drift: %q→%q", p, round)
		}
	}
}

func TestParsePresenceState_ToleratesCaseAndWhitespace(t *testing.T) {
	cases := map[string]PresenceState{
		"ACTIVE":               PresenceActive,
		"  typing ":            PresenceTyping,
		"Waiting_AI":           PresenceWaitingAI,
		"DISCONNECTED_BRIEF":   PresenceDisconnectedBrief,
		"disconnected_ghost":   PresenceDisconnectedGhost,
	}
	for in, want := range cases {
		got, err := ParsePresenceState(in)
		if err != nil {
			t.Errorf("ParsePresenceState(%q) err=%v", in, err)
			continue
		}
		if got != want {
			t.Errorf("ParsePresenceState(%q) = %q, want %q", in, got, want)
		}
	}
}

func TestParsePresenceState_RejectsInvalid(t *testing.T) {
	for _, bad := range []string{"", "afk", "online", "presence_unknown", "disconnected"} {
		_, err := ParsePresenceState(bad)
		if !errors.Is(err, ErrInvalidPresenceState) {
			t.Errorf("ParsePresenceState(%q) err=%v, want ErrInvalidPresenceState", bad, err)
		}
	}
}

func TestPresenceState_IsConnected(t *testing.T) {
	connected := map[PresenceState]bool{
		PresenceActive:            true,
		PresenceIdle:              true,
		PresenceTyping:            true,
		PresenceWaitingAI:         true,
		PresenceDisconnectedBrief: false,
		PresenceDisconnectedGhost: false,
	}
	for p, want := range connected {
		if got := p.IsConnected(); got != want {
			t.Errorf("%q.IsConnected() = %v, want %v", p, got, want)
		}
		if got := p.IsDisconnected(); got == want {
			t.Errorf("%q.IsDisconnected() = %v, want %v (inverse)", p, got, !want)
		}
	}
}
