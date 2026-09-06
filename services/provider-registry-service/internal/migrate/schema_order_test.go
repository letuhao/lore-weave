package migrate

import (
	"fmt"
	"regexp"
	"strings"
	"testing"
)

// `schemaSQL` REPLAYS IN ORDER, so a statement may not touch a table declared below it.
//
// 🔴 MEASURED. CI, 2026-09-04, `Auth · provider-registry · billing · scheduler DB round-trips`:
//
//	web_search_live_test.go:43: migrate.Up: migrate: ERROR: relation "usage_outbox"
//	does not exist (SQLSTATE 42P01)
//
// `ALTER TABLE usage_outbox ADD COLUMN ... provider_kind` (D-BILL-PROVIDER-KIND) had been
// inserted about sixty lines ABOVE the `CREATE TABLE usage_outbox` it depends on. The whole
// string goes to one `pool.Exec`, so Postgres reached the ALTER first and aborted the
// migration — taking every table after it down too.
//
// ⚠️ WHY NOTHING CAUGHT IT, AND WHY THIS TEST IS STATIC.
// On a database that already HAS `usage_outbox` — every developer's, every long-lived
// environment — the ALTER is a fine no-op and the whole file applies. It fails only on a
// FRESH database, which in practice means CI and a new deployment. That is the worst shape a
// migration defect can have: invisible where it is written, fatal where it is first shipped.
// A live-DB test would have caught it, but only in the job that was already red for it; this
// one runs in the unit suite on every commit, needs no database, and answers the question
// before the code is pushed.
//
// It is deliberately NOT a full SQL parser. It answers one question — is any `ALTER TABLE x`
// written before the `CREATE TABLE x` it needs — and that is the entire class this defect
// belongs to.
var (
	createRe = regexp.MustCompile(`(?im)^\s*CREATE TABLE(?:\s+IF NOT EXISTS)?\s+([A-Za-z_][A-Za-z0-9_]*)`)
	alterRe  = regexp.MustCompile(`(?im)^\s*ALTER TABLE\s+(?:IF EXISTS\s+)?([A-Za-z_][A-Za-z0-9_]*)`)
)

// firstCreateLine maps each table to the 1-indexed line of its first CREATE TABLE.
func firstCreateLine(lines []string) map[string]int {
	at := map[string]int{}
	for i, l := range lines {
		if m := createRe.FindStringSubmatch(l); m != nil {
			if _, seen := at[m[1]]; !seen {
				at[m[1]] = i + 1
			}
		}
	}
	return at
}

func TestNoStatementTouchesATableDeclaredBelowIt(t *testing.T) {
	lines := strings.Split(schemaSQL, "\n")
	created := firstCreateLine(lines)

	// Anti-vacuity: if the scan found no tables at all, every assertion below would pass by
	// matching nothing — the exact failure this repo calls a check in the costume of evidence.
	if len(created) < 5 {
		t.Fatalf("the CREATE TABLE scan found %d table(s) in schemaSQL — it is not scanning",
			len(created))
	}

	var problems []string
	for i, l := range lines {
		m := alterRe.FindStringSubmatch(l)
		if m == nil {
			continue
		}
		table, line := m[1], i+1
		switch at, ok := created[table]; {
		case !ok:
			// Legitimate: a table this service does not own but does extend. Report it
			// rather than ignoring it, because the two look identical from here and a
			// typo'd table name is the same defect wearing a different hat.
			problems = append(problems, fmt.Sprintf(
				"line %d: ALTER TABLE %s — no CREATE TABLE %s anywhere in schemaSQL",
				line, table, table))
		case at > line:
			problems = append(problems, fmt.Sprintf(
				"line %d: ALTER TABLE %s runs BEFORE its CREATE TABLE at line %d — on a FRESH "+
					"database this aborts the whole migration with "+
					`relation "%s" does not exist (SQLSTATE 42P01)`,
				line, table, at, table))
		}
	}
	if len(problems) > 0 {
		t.Fatalf("schemaSQL replays in order and %d statement(s) break that:\n  %s\n\n"+
			"Move the statement below the CREATE it depends on. It will look fine on any "+
			"database that already has the table, which is why this is checked here.",
			len(problems), strings.Join(problems, "\n  "))
	}
}

func TestTheOrderCheckCanActuallyFail(t *testing.T) {
	// The guard's own teeth. A regex that matched nothing would make the test above green
	// forever, so the detector is driven over a SYNTHETIC schema carrying the exact defect
	// that was shipped — it stays red-able whatever happens to the real schemaSQL.
	synthetic := []string{
		"ALTER TABLE usage_outbox ADD COLUMN IF NOT EXISTS provider_kind TEXT;",
		"CREATE TABLE IF NOT EXISTS usage_outbox (id BIGSERIAL PRIMARY KEY);",
	}
	created := firstCreateLine(synthetic)
	if created["usage_outbox"] != 2 {
		t.Fatalf("the CREATE detector no longer finds the table it was built for: %v", created)
	}
	m := alterRe.FindStringSubmatch(synthetic[0])
	if m == nil || m[1] != "usage_outbox" {
		t.Fatalf("the ALTER detector no longer sees the statement that broke the build: %v", m)
	}
	if created[m[1]] <= 1 {
		t.Fatal("the comparison no longer flags an ALTER above its CREATE")
	}
}
