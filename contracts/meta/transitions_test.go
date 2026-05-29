package meta

import (
	"errors"
	"strings"
	"testing"
)

func TestParseTransitions_RealityHappyPath(t *testing.T) {
	g, err := LoadTransitions("transitions.yaml")
	if err != nil {
		t.Fatalf("load shipped transitions.yaml: %v", err)
	}
	r, ok := g.Resources["reality"]
	if !ok {
		t.Fatal("reality resource missing from shipped transitions.yaml")
	}
	if r.Table != "reality_registry" || r.StateColumn != "status" {
		t.Errorf("unexpected reality config: table=%s state_column=%s", r.Table, r.StateColumn)
	}
	// All 10 states present (matches L1A §1.1)
	want := []string{
		"provisioning", "seeding", "active",
		"pending_close", "frozen", "migrating",
		"archived", "archived_verified",
		"soft_deleted", "dropped",
	}
	for _, s := range want {
		if _, ok := r.States[s]; !ok {
			t.Errorf("state %q missing from reality graph", s)
		}
	}
	if len(r.States) != len(want) {
		t.Errorf("state count mismatch: got %d want %d", len(r.States), len(want))
	}

	// Sanity check a few specific transitions
	cases := []struct {
		from, to string
		allowed  bool
	}{
		{"active", "pending_close", true},
		{"active", "migrating", true},
		{"active", "archived", false},      // not adjacent
		{"pending_close", "active", true},
		{"pending_close", "frozen", true},
		{"frozen", "archived", true},
		{"archived", "archived_verified", true},
		{"archived_verified", "soft_deleted", true},
		{"soft_deleted", "dropped", true},
		{"dropped", "active", false}, // terminal — no outgoing
	}
	for _, c := range cases {
		got, _ := r.Allows(c.from, c.to)
		if got != c.allowed {
			t.Errorf("reality %s→%s: got allowed=%v want %v", c.from, c.to, got, c.allowed)
		}
	}
}

func TestParseTransitions_MutualExclusionForbidsTransition(t *testing.T) {
	g, err := LoadTransitions("transitions.yaml")
	if err != nil {
		t.Fatalf("load: %v", err)
	}
	r := g.Resources["reality"]
	// transitions.yaml: if status=migrating, pending_close is forbidden.
	// (Note: migrating→pending_close isn't in the base graph either, so this
	// verifies the GRAPH check rejects it; mutex would also reject if it were.)
	// Test mutex set directly:
	if _, forbidden := r.MutualExclusions["migrating"]; !forbidden {
		t.Fatalf("mutual_exclusion for migrating not loaded")
	}
	if _, ok := r.MutualExclusions["migrating"]["pending_close"]; !ok {
		t.Errorf("mutex doesn't include pending_close as forbidden from migrating")
	}
}

func TestParseTransitions_UnreachableStateRejected(t *testing.T) {
	doc := []byte(`
version: 1
resources:
  thing:
    table: thing_table
    state_column: status
    initial_states: [a]
    terminal_states: [c]
    states: [a, b, c, isolated]
    transitions:
      - from: a
        to: [b]
      - from: b
        to: [c]
`)
	_, err := ParseTransitions(doc)
	if !errors.Is(err, ErrTransitionGraphInvalid) || !strings.Contains(err.Error(), "isolated") {
		t.Fatalf("expected unreachable-isolated error, got %v", err)
	}
}

func TestParseTransitions_UnknownToStateRejected(t *testing.T) {
	doc := []byte(`
version: 1
resources:
  thing:
    table: thing_table
    state_column: status
    initial_states: [a]
    terminal_states: [b]
    states: [a, b]
    transitions:
      - from: a
        to: [b, zzz]
`)
	_, err := ParseTransitions(doc)
	if !errors.Is(err, ErrTransitionGraphInvalid) || !strings.Contains(err.Error(), "zzz") {
		t.Fatalf("expected unknown-to-state error, got %v", err)
	}
}

func TestParseTransitions_TerminalCannotHaveOutgoing(t *testing.T) {
	doc := []byte(`
version: 1
resources:
  thing:
    table: thing_table
    state_column: status
    initial_states: [a]
    terminal_states: [b]
    states: [a, b]
    transitions:
      - from: a
        to: [b]
      - from: b
        to: [a]
`)
	_, err := ParseTransitions(doc)
	if !errors.Is(err, ErrTransitionGraphInvalid) || !strings.Contains(err.Error(), "terminal") {
		t.Fatalf("expected terminal-has-outgoing error, got %v", err)
	}
}

func TestParseTransitions_SelfLoopRejected(t *testing.T) {
	doc := []byte(`
version: 1
resources:
  thing:
    table: thing_table
    state_column: status
    initial_states: [a]
    terminal_states: [b]
    states: [a, b]
    transitions:
      - from: a
        to: [a, b]
`)
	_, err := ParseTransitions(doc)
	if !errors.Is(err, ErrTransitionGraphInvalid) || !strings.Contains(err.Error(), "self-loop") {
		t.Fatalf("expected self-loop error, got %v", err)
	}
}
