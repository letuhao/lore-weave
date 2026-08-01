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

	// GUARD BEFORE YOU DESTROY (CLAUDE.md › "Destructive DB ops in tests").
	//
	// db-safety-gate: ok — every SQL fragment in THIS comment block is prose
	// describing the hazard; the guard below is the mitigation, and it runs
	// before the first destructive statement.
	//
	// `db-safety-gate` caught this the moment the helper was written, and it was
	// RIGHT — this is not a false positive. `0002_events_table.up.sql` opens with
	// `DROP TABLE IF EXISTS events`, so widening the applied set from two
	// hand-picked migrations to a globbed range made this helper strictly more
	// destructive than the code it replaced. Point `LW_INTEGRATION_DB` at a real
	// per-reality database and it drops that reality's entire event log.
	//
	// That is precisely how an unscoped `DELETE FROM books` once hard-deleted
	// every user's books: the statement was fine, the DSN was not. So refuse any
	// database whose name does not carry a throwaway marker, BEFORE the first
	// destructive statement rather than after.
	var dbName string
	if err := db.QueryRow(`SELECT current_database()`).Scan(&dbName); err != nil {
		t.Fatalf("resolve current_database() before destructive migrations: %v", err)
	}
	if err := testsafe.EnsureThrowawayDB(dbName); err != nil {
		t.Fatalf("mustApplyEventSchema: %v", err)
	}

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

// mustApply reads the given .sql file (path relative to the repo root)
// and runs it against db. Fails the test if the file is missing or the
// statements error out.
func mustApply(t *testing.T, db *sql.DB, relPath string) {
	t.Helper()
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
