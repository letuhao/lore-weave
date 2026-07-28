package pgsource

import (
	"strings"
	"testing"
)

// D-PUBLISHER-DROPS-RULESET-PIN.
//
// The events table gained `ruleset_digest` (migration 0016) and the wire
// envelope gained the field (`contracts/events/envelope.go`), but THIS query
// never fetched it — and the envelope's json tag is `omitempty`, so the pin
// vanished the moment an event left its reality DB with nothing reporting it.
//
// RLS-A13 makes the digest what ties an event to the rules that produced it;
// QTY-A14 makes it what gives a per-reality quantity ordinal its meaning. A
// consumer holding ordinal 3 and no digest resolves it against whatever table
// it happens to have — reality A's `qi` silently becomes reality B's `mana`,
// and both replay it "correctly" forever.
//
// It is asserted textually because pgx binds by POSITION at runtime: a
// SELECT/Scan disagreement is not a compile error, it is a production one.
func TestSelectPendingSQL_FetchesRulesetDigest(t *testing.T) {
	if !strings.Contains(selectPendingSQL, "e.ruleset_digest") {
		t.Fatal("selectPendingSQL does not fetch e.ruleset_digest — the ruleset " +
			"pin is dropped the moment an event leaves its reality DB")
	}
}

// The count is the thing pgx cannot check for us, and it is checked from BOTH
// sides deliberately.
//
// `rows.Scan(...)` binds by POSITION: N destinations against M projected
// columns, and a mismatch is a runtime error per batch, in production. So
// `scanRows` asserts `len(dests) == selectColumns` at runtime, and this test
// asserts the SQL really projects `selectColumns`. One side alone is a
// half-check — declaring 16 and projecting 15 would satisfy the runtime guard
// and still fail on the first query.
func TestSelectPendingSQL_ProjectsDeclaredColumnCount(t *testing.T) {
	head := selectPendingSQL[strings.Index(selectPendingSQL, "SELECT")+len("SELECT"):]
	head = head[:strings.Index(head, "FROM")]
	// Commas at paren-depth 0 only. The projection has no function calls today,
	// but `make_interval(secs => …)` in the WHERE clause shows the shape is
	// possible, and a naive `strings.Count(head, ",")` would miscount the day it
	// appears — a test that breaks silently later is worse than no test.
	depth, cols := 0, 1
	for _, r := range head {
		switch r {
		case '(':
			depth++
		case ')':
			depth--
		case ',':
			if depth == 0 {
				cols++
			}
		}
	}
	if cols != selectColumns {
		t.Fatalf("SELECT projects %d column(s) but selectColumns declares %d — "+
			"pgx binds by POSITION, so this fails at runtime on the first batch",
			cols, selectColumns)
	}
}
