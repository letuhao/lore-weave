package entity_status

import "testing"

func TestGoneStateValidity(t *testing.T) {
	for _, s := range AllGoneStates() {
		if !s.IsValid() {
			t.Fatalf("AllGoneStates() includes invalid %q", s)
		}
	}
	if GoneState("bogus").IsValid() {
		t.Fatal("bogus must not validate")
	}
}

func TestGoneStateIsLive(t *testing.T) {
	if !StateActive.IsLive() {
		t.Fatal("active must be live")
	}
	for _, s := range []GoneState{StateSevered, StateArchived, StateDropped, StateUserErased} {
		if s.IsLive() {
			t.Fatalf("%q must not be live", s)
		}
	}
}

func TestGoneStateIsTerminal(t *testing.T) {
	if !StateDropped.IsTerminal() || !StateUserErased.IsTerminal() {
		t.Fatal("dropped + user_erased must be terminal")
	}
	for _, s := range []GoneState{StateActive, StateSevered, StateArchived} {
		if s.IsTerminal() {
			t.Fatalf("%q must not be terminal", s)
		}
	}
}

func TestParseGoneState(t *testing.T) {
	g, err := ParseGoneState("active")
	if err != nil || g != StateActive {
		t.Fatalf("active parse: %v, %v", g, err)
	}
	if _, err := ParseGoneState("nope"); err == nil {
		t.Fatal("nope must error")
	}
}

func TestPrecedenceWinners(t *testing.T) {
	cases := []struct {
		a, b GoneState
		want GoneState
	}{
		{StateActive, StateDropped, StateDropped},
		{StateUserErased, StateDropped, StateDropped},
		{StateSevered, StateArchived, StateSevered},
		{StateActive, StateActive, StateActive},
		{StateUserErased, StateSevered, StateUserErased},
	}
	for _, tc := range cases {
		if got := Higher(tc.a, tc.b); got != tc.want {
			t.Fatalf("Higher(%q,%q)=%q want %q", tc.a, tc.b, got, tc.want)
		}
	}
}

func TestReduce(t *testing.T) {
	if got := Reduce(); got != StateActive {
		t.Fatalf("empty Reduce should be active; got %q", got)
	}
	got := Reduce(StateActive, StateSevered, StateDropped, StateArchived)
	if got != StateDropped {
		t.Fatalf("Reduce winner = %q want dropped", got)
	}
}
