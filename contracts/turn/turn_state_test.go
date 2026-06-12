package turn

import "testing"

func TestAllTurnStates_ExhaustiveValid(t *testing.T) {
	all := AllTurnStates()
	if len(all) != 8 {
		t.Fatalf("expected 8 states; got %d", len(all))
	}
	for _, s := range all {
		if !s.IsValid() {
			t.Fatalf("%q must be valid", s)
		}
	}
	if TurnState("bogus").IsValid() {
		t.Fatal("bogus must not validate")
	}
}

func TestTerminalStates(t *testing.T) {
	terminal := []TurnState{StateCompleted, StateFailed, StateCancelled}
	for _, s := range terminal {
		if !s.IsTerminal() {
			t.Fatalf("%q must be terminal", s)
		}
	}
	nonTerminal := []TurnState{StatePending, StateValidating, StateRouting, StateExecuting, StateStreaming}
	for _, s := range nonTerminal {
		if s.IsTerminal() {
			t.Fatalf("%q must not be terminal", s)
		}
	}
}

func TestParseTurnState(t *testing.T) {
	s, err := ParseTurnState("validating")
	if err != nil || s != StateValidating {
		t.Fatalf("parse validating: %v %v", s, err)
	}
	if _, err := ParseTurnState("nope"); err == nil {
		t.Fatal("nope must error")
	}
}

func TestAssertTransition_AllowedPaths(t *testing.T) {
	happy := []struct{ from, to TurnState }{
		{StatePending, StateValidating},
		{StateValidating, StateRouting},
		{StateRouting, StateExecuting},
		{StateExecuting, StateStreaming},
		{StateStreaming, StateCompleted},
		{StateExecuting, StateCompleted}, // streaming optional
		{StatePending, StateCancelled},
		{StateExecuting, StateFailed},
	}
	for _, c := range happy {
		if err := AssertTransition(c.from, c.to); err != nil {
			t.Fatalf("%q->%q: %v", c.from, c.to, err)
		}
	}
}

func TestAssertTransition_RejectsBackwards(t *testing.T) {
	if err := AssertTransition(StateExecuting, StateRouting); err == nil {
		t.Fatal("executing->routing must error")
	}
}

func TestAssertTransition_RejectsFromTerminal(t *testing.T) {
	for _, term := range []TurnState{StateCompleted, StateFailed, StateCancelled} {
		if err := AssertTransition(term, StatePending); err == nil {
			t.Fatalf("%q->pending must error", term)
		}
	}
}

func TestAssertTransition_RejectsInvalidStates(t *testing.T) {
	if err := AssertTransition(TurnState("bogus"), StateValidating); err == nil {
		t.Fatal("bogus from must error")
	}
}
