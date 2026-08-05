// db-safety-gate: file-ok — this file OPENS NO DATABASE. It reads
// contracts/migrations/per_reality/*.up.sql as TEXT and pattern-matches the DDL
// to answer one question: does any surviving per-reality table declare a user
// reference? The `DROP TABLE IF EXISTS` strings it contains are the PATTERN it
// searches for and a quotation of the defect that motivated it — never a
// statement it executes. There is no pool, no DSN and no env var in the package
// path this file uses.
package pglive

import (
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"
	"testing"
)

// stripSQLComments removes `--` line comments.
//
// Not cosmetic: `DROP TABLE IF EXISTS pc_projection;` reads identically to a
// regex whether or not it is commented out, so without this a bite that
// comments out the DROP passes — the parser "sees" a drop that Postgres never
// performs. Measured: that is exactly how the first version of this test
// reported a clean tree while blind.
func stripSQLComments(s string) string {
	var b strings.Builder
	for _, line := range strings.Split(s, "\n") {
		if i := strings.Index(line, "--"); i >= 0 {
			line = line[:i]
		}
		b.WriteString(line)
		b.WriteByte('\n')
	}
	return b.String()
}

var createHeadRe = regexp.MustCompile(`CREATE TABLE IF NOT EXISTS (\w+) \(`)

// A user reference is a COLUMN named `user_id`/`user_ref_id`/`owner_user_id`.
// Anchored to the start of a line and followed by whitespace, so
// `CREATE INDEX ... (user_id)` and `REFERENCES users (user_id)` cannot match.
var userColRe = regexp.MustCompile(`(?m)^\s*(user_id|user_ref_id|owner_user_id)\s`)

var dropRe = regexp.MustCompile(`DROP TABLE IF EXISTS (\w+)`)

// perRealityTablesWithUserColumn returns the SURVIVING per-reality tables that
// declare a user reference, plus every table name it managed to see.
//
// It chunks the file at each `CREATE TABLE IF NOT EXISTS <name> (` and scans up
// to the NEXT one, rather than trying to find the statement's closing `);`.
// That is deliberate. The first version matched `(?s)CREATE TABLE ... \((.*?)\n\);`
// and `npc_session_memory_embedding` is created inside a `DO $$ ... EXECUTE $exec$`
// block, so its `)` is INDENTED — the lazy match ran straight past it and
// swallowed the whole of `region_projection` along with it. The parser could not
// see the table it most needed to watch, and reported a clean tree with total
// confidence. Chunking has no terminator to get wrong.
func perRealityTablesWithUserColumn(t *testing.T, dir string) (map[string]string, map[string]bool) {
	t.Helper()
	files, err := filepath.Glob(filepath.Join(dir, "*.up.sql"))
	if err != nil || len(files) == 0 {
		t.Fatalf("glob %s: %v (found %d) — the test lost its subject", dir, err, len(files))
	}
	sort.Strings(files) // migration order == filename order

	withUser := map[string]string{} // surviving table -> migration that gave it the column
	seen := map[string]bool{}

	for _, f := range files {
		raw, err := os.ReadFile(f)
		if err != nil {
			t.Fatalf("read %s: %v", f, err)
		}
		src := stripSQLComments(string(raw))

		heads := createHeadRe.FindAllStringSubmatchIndex(src, -1)
		drops := dropRe.FindAllStringSubmatchIndex(src, -1)

		// Creates and drops must be applied in DOCUMENT ORDER, not creates-then-
		// drops. `0002` drops `events` and immediately recreates it in the same
		// file; applying all drops afterwards deleted the live table and the walk
		// went blind to it. Within a file, later wins — as in Postgres.
		type stmt struct {
			at     int
			name   string
			create bool
			body   string
		}
		var stmts []stmt
		for i, h := range heads {
			end := len(src)
			if i+1 < len(heads) {
				end = heads[i+1][0]
			}
			stmts = append(stmts, stmt{h[0], src[h[2]:h[3]], true, src[h[1]:end]})
		}
		for _, d := range drops {
			stmts = append(stmts, stmt{d[0], src[d[2]:d[3]], false, ""})
		}
		sort.Slice(stmts, func(i, j int) bool { return stmts[i].at < stmts[j].at })

		for _, s := range stmts {
			if !s.create {
				delete(withUser, s.name)
				delete(seen, s.name)
				continue
			}
			seen[s.name] = true
			if userColRe.MatchString(s.body) {
				withUser[s.name] = filepath.Base(f)
			} else {
				delete(withUser, s.name) // recreated without the column
			}
		}
	}
	return withUser, seen
}

// TestPerRealityMigrationParserCanSeeTheSurvivingTables is the test's own
// non-vacuity check, and it exists because the parser it guards was silently
// blind on its first day (see perRealityTablesWithUserColumn).
//
// A parser that cannot NAME a table cannot notice that table gaining a user
// column. So before trusting a clean result, prove the walk actually sees the
// surviving per-reality projections.
func TestPerRealityMigrationParserCanSeeTheSurvivingTables(t *testing.T) {
	_, seen := perRealityTablesWithUserColumn(t, migrationDir)
	for _, must := range []string{
		"region_projection", "world_kv_projection", "session_participants",
		"canon_projection", "events",
	} {
		if !seen[must] {
			t.Errorf("the migration walk never saw %q — a table it cannot see is a "+
				"table it cannot check, and a clean result would mean nothing", must)
		}
	}
	// ...and the tables 0017 dropped must NOT be seen, or the walk is reading a
	// world that no longer exists.
	for _, gone := range []string{"pc_projection", "npc_projection"} {
		if seen[gone] {
			t.Errorf("the walk still sees %q, dropped by 0017", gone)
		}
	}
}

const migrationDir = "../../../../../contracts/migrations/per_reality"

// TestNoPerRealityTableCarriesAUserReference is what makes ScrubUserRefs's
// emptiness safe.
//
// `pc_projection` was the only per-reality projection with a `user_id` column,
// and `0017` dropped it, so the per-reality leg of the GDPR erasure cascade has
// nothing to scrub and now does nothing. That is correct TODAY and a silent
// erasure hole the day a per-reality table gains a user reference again: PII
// would live on in a shard while the cascade reported success.
//
// A comment cannot notice that day. This test can.
func TestNoPerRealityTableCarriesAUserReference(t *testing.T) {
	withUser, seen := perRealityTablesWithUserColumn(t, migrationDir)
	if len(seen) == 0 {
		t.Fatal("parsed 0 tables from the per_reality migrations — the walk found " +
			"nothing, which is a failure, not a clean bill of health")
	}
	if len(withUser) > 0 {
		var names []string
		for tbl, mig := range withUser {
			names = append(names, tbl+" (from "+mig+")")
		}
		sort.Strings(names)
		t.Fatalf(
			"a surviving per-reality table now carries a user reference: %s\n"+
				"PgPerRealityScrubber.ScrubUserRefs has been a no-op since 0017 dropped "+
				"pc_projection, the last such table. It must now actually scrub — otherwise "+
				"a GDPR erasure will report success while this PII survives in every shard. "+
				"Write the UPDATE (idempotent, guarded), cover it, then update this test.",
			strings.Join(names, ", "))
	}
}
