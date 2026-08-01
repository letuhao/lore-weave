package meta

import "testing"

// Q1 B2 — the Go half of a POLYGLOT contract check.
//
// `events_allowlist.yaml` is parsed by two independently written parsers:
// this package's `allowlist.go` and `crates/meta-rs/src/allowlist.rs`. They read
// the SAME bytes, so a disagreement can only come from a parser difference —
// an enum spelling, a defaulted field, a silently skipped entry. The mirror of
// this test is `crates/meta-rs/tests/reality_ruleset_binding.rs`, which asserts
// the identical facts; if one parser drops the row and the other does not, one
// side reds and the other stays green, which is exactly the signal wanted.
//
// See docs/standards/README.md §B (machine-contract SoT + mirrors).
func TestAllowlist_RealityRulesetBinding(t *testing.T) {
	a, err := LoadAllowlist("events_allowlist.yaml")
	if err != nil {
		t.Fatalf("load shipped file: %v", err)
	}

	const table = "reality_ruleset_binding"
	if !a.AllowsTable(table) {
		t.Fatalf("%s is not allowlisted — MetaWrite would refuse every binding "+
			"write, so a reality could not be created at all", table)
	}

	name, ok := a.EmitsEvent(table, OpInsert)
	if !ok {
		t.Fatalf("%s INSERT emits no event; binding a reality to its rules is "+
			"exactly the kind of fact other services subscribe to", table)
	}
	if want := "reality.ruleset.bound"; name != want {
		t.Errorf("INSERT event = %q, want %q", name, want)
	}

	// The table is append-only in the DB (033's trigger refuses UPDATE and
	// DELETE for every role). Declaring an event for either op would advertise
	// a write that cannot happen.
	for _, op := range []MetaWriteOp{OpUpdate, OpDelete} {
		if got, ok := a.EmitsEvent(table, op); ok {
			t.Errorf("%s declares an event %q for %s, but the table is "+
				"append-only — migration 033's trigger refuses that operation",
				table, got, op)
		}
	}
}
