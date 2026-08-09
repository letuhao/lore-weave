// sql_helpers_test.go — shared `mustApply` helper for integration tests.
//
// Reads a .sql file from the repo root and runs it against the supplied DB.
// Fails the test on any error.
//
//go:build integration
// +build integration

package integration

import (
	"database/sql"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"strings"
	"testing"

	"github.com/loreweave/foundation/services/integrity-checker/pkg/testsafe"
)

// mustApplyEventSchema brings the event tables up to the CURRENT per-reality
// schema, by globbing the migration directory rather than naming files.
//
// THE BUG THIS REPLACES. The publisher live smoke hand-picked exactly two
// migrations — `0002_events_table` and `0005_events_outbox_table` — out of
// sixteen. Every additive column landed after `0005` was therefore invisible to
// it: `0013` content_sha256, `0014` channel_ordering, `0016` ruleset_digest.
// When the publisher's SELECT started reading `e.channel_id` (0014, 2026-07-27)
// the smoke went red against a schema two migrations behind production — and
// stayed red, unnoticed, because it is not in CI and nobody ran it.
//
// A hand-written list is default-UNCOVERED: a new migration is invisible until
// someone remembers to add a line. Globbing is default-COVERED — the same
// polarity fix `hot-path-gate.py` needed for exactly the same reason. Files are
// applied in lexical order, which is numeric order given the `NNNN_` prefix.
//
// `only` filters to the migrations a given test needs (substring match on the
// file name); pass nil to apply the whole set.
func mustApplyEventSchema(t *testing.T, db *sql.DB, only func(name string) bool) {
	t.Helper()
	requireThrowawayDB(t, db, "mustApplyEventSchema")

	dir := filepath.Join(repoRoot(t), "contracts", "migrations", "per_reality")
	paths, err := filepath.Glob(filepath.Join(dir, "*.up.sql"))
	if err != nil {
		t.Fatalf("glob per_reality migrations: %v", err)
	}
	if len(paths) == 0 {
		t.Fatalf("no per_reality migrations found under %s — the glob is wrong, "+
			"and silently applying nothing is how this helper's predecessor "+
			"tested against a two-migration-old schema for two days", dir)
	}
	sort.Strings(paths)
	applied := 0
	for _, p := range paths {
		name := filepath.Base(p)
		if only != nil && !only(name) {
			continue
		}
		b, err := os.ReadFile(p)
		if err != nil {
			t.Fatalf("read %s: %v", name, err)
		}
		if _, err := db.Exec(string(b)); err != nil {
			t.Fatalf("apply %s: %v", name, err)
		}
		applied++
	}
	if applied == 0 {
		t.Fatalf("the `only` filter matched no migration under %s", dir)
	}
	t.Logf("per-reality schema: applied %d migration(s)", applied)
}

// eventTableMigrations selects the migrations that create or alter the two
// tables the publisher reads. Deliberately a PREFIX RANGE rather than a list of
// names, so a future `0017_events_*.up.sql` is picked up with no edit here.
//
// The excluded ones need extensions or tables this smoke DB does not provision
// (`0008` pgvector, the projection/canon set) — excluding them is a statement
// about what this DB is, not a way to skip a failure.
func eventTableMigrations(name string) bool {
	switch {
	case strings.HasPrefix(name, "0002_events"),
		strings.HasPrefix(name, "0005_events_outbox"),
		strings.HasPrefix(name, "0012_events_outbox"),
		strings.HasPrefix(name, "0013_events"),
		strings.HasPrefix(name, "0014_channel"),
		strings.HasPrefix(name, "0016_events"):
		return true
	}
	return false
}

// requireThrowawayDB refuses to let the caller touch a database whose name does not
// carry a throwaway marker. Call it BEFORE the first destructive statement.
//
// db-safety-gate: ok — every SQL fragment in THIS comment block is prose describing
// the hazard; the code below is the mitigation, not an instance of it.
//
// WHY THIS LIVES IN THE HELPER AND NOT AT THE CALL SITES. It used to be three lines
// inlined in `mustApplyEventSchema`, and exactly two of the seven harnesses in this
// repo had them. The other five applied migrations by hand and were unguarded — not
// because anyone decided to skip the guard, but because opting out looks exactly like
// ordinary code: you call `mustApply` and nothing tells you a guard exists. A safety
// check you have to REMEMBER to call is default-UNCOVERED, the same polarity bug as a
// hand-written migration list. So the guard now sits inside every helper that can
// execute a .sql file, and the only way to skip it is to not use the helpers.
//
// The hazard is real and not theoretical: `0002_events_table.up.sql` opens with
// `DROP TABLE IF EXISTS events`, and `0001_initial.down.sql` drops four tables. Point
// `LW_INTEGRATION_DB` at a live per-reality database and applying either one destroys
// that reality's entire event log. That is precisely how an unscoped `DELETE FROM
// books` once hard-deleted every user's books: the statement was fine, the DSN was not.
func requireThrowawayDB(t *testing.T, db *sql.DB, caller string) {
	t.Helper()
	var dbName string
	if err := db.QueryRow(`SELECT current_database()`).Scan(&dbName); err != nil {
		t.Fatalf("%s: resolve current_database() before applying migrations: %v", caller, err)
	}
	if err := testsafe.EnsureThrowawayDB(dbName); err != nil {
		t.Fatalf("%s: %v", caller, err)
	}
}

// mustApply reads the given .sql file (path relative to the repo root)
// and runs it against db. Fails the test if the file is missing or the
// statements error out.
//
// Guarded unconditionally rather than only for files that LOOK destructive: whether a
// migration drops a table is a property of its current contents, so a predicate over
// the SQL would have to be right about every file forever, and would go quietly wrong
// the day someone adds a DROP to a migration this helper already applies.
func mustApply(t *testing.T, db *sql.DB, relPath string) {
	t.Helper()
	requireThrowawayDB(t, db, "mustApply")
	root := repoRoot(t)
	abs := filepath.Join(root, filepath.FromSlash(relPath))
	b, err := os.ReadFile(abs)
	if err != nil {
		t.Fatalf("mustApply read %s: %v", abs, err)
	}
	if _, err := db.Exec(string(b)); err != nil {
		t.Fatalf("mustApply exec %s: %v", abs, err)
	}
}

// publisherEventColumns is every `events` column the publisher's pending-select names
// (services/publisher/pkg/pgsource/pgsource.go), mapped to the migration that adds it.
// The per-reality migration set is hand-picked per harness — 7 lists across this repo,
// none of them connected to what the code requires — so a migration a consumer STARTS
// depending on never arrives by itself.
var publisherEventColumns = map[string]string{
	"event_type":       "0002_events_table",
	"payload":          "0002_events_table",
	"channel_id":       "0014_channel_ordering",
	"channel_event_id": "0014_channel_ordering",
	"writer_epoch":     "0014_channel_ordering",
	"ruleset_digest":   "0016_events_ruleset_digest",
}

// requirePublisherColumns fails BEFORE the drain if the schema is short, naming the
// migration rather than the column.
//
// Without it the gap surfaces as `column e.channel_id does not exist (SQLSTATE 42703)`
// raised from inside `publisher drain`, which reads like a publisher bug — so it is
// investigated as one. That is why this test sat red from 2026-07-27: the message
// pointed at the wrong thing, and fixing the first missing column merely revealed the
// second. One assertion here reports ALL of them at once, before any work starts.
func requirePublisherColumns(t *testing.T, db *sql.DB) {
	t.Helper()
	var missing []string
	for col, migration := range publisherEventColumns {
		var exists bool
		err := db.QueryRow(
			`SELECT EXISTS (SELECT 1 FROM information_schema.columns
			                WHERE table_name = 'events' AND column_name = $1)`, col,
		).Scan(&exists)
		if err != nil {
			t.Fatalf("requirePublisherColumns: probing events.%s: %v", col, err)
		}
		if !exists {
			missing = append(missing, fmt.Sprintf("events.%s (add %s)", col, migration))
		}
	}
	if len(missing) > 0 {
		sort.Strings(missing)
		t.Fatalf("this harness's migration list is short — the publisher reads %d column(s) "+
			"the schema does not have:\n  %s\nApply the migration(s) above in the mustApply "+
			"list at the top of the test.", len(missing), strings.Join(missing, "\n  "))
	}
}

// repoRoot returns the foundation repo root. Found by walking up from
// this file's location until we hit the root `Cargo.toml`.
func repoRoot(t *testing.T) string {
	t.Helper()
	_, file, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	dir := filepath.Dir(file)
	for i := 0; i < 6; i++ { // expect to find within 6 ancestors
		if _, err := os.Stat(filepath.Join(dir, "Cargo.toml")); err == nil {
			return dir
		}
		dir = filepath.Dir(dir)
	}
	t.Fatalf("could not locate repo root walking up from %s", file)
	return ""
}
