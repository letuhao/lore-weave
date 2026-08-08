package pglive

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

// The meta tree's equivalent of TestNoPerRealityTableCarriesAUserReference.
//
// WHY THIS EXISTS
// ---------------
// W6 added `owner_user_id` to `reality_registry` and declared
// `@erasure_method: reassign_to_system_on_user_erasure` in the migration header.
// Nothing implemented it. The user's identifier would have survived an erasure
// that reported success.
//
// Nothing caught it, and the reason is structural rather than careless. The
// mechanism this repo built for exactly this class —
// `TestNoPerRealityTableCarriesAUserReference` — already hunts the column name
// `owner_user_id`, but its `migrationDir` is
// `contracts/migrations/per_reality`. W6 put the column in `migrations/meta`,
// the one tree that walk never visits. **Default-uncovered** (`NV-3`): the
// question was asked of one directory and the answer was quietly assumed for
// the other.
//
// So this walks the meta tree and holds every user-referencing table to the
// same bargain: declare an erasure method, and have that method exist in code.

const metaMigrationDir = "../../../../../migrations/meta"

// A user reference is a COLUMN named user_id / user_ref_id / owner_user_id.
// Anchored at line start and followed by whitespace so an index definition or a
// REFERENCES clause cannot match — same rule the per-reality walk uses.
var metaUserColRe = regexp.MustCompile(`(?m)^\s*(user_id|user_ref_id|owner_user_id)\s`)

var (
	metaCreateHeadRe = regexp.MustCompile(`CREATE TABLE (?:IF NOT EXISTS )?(\w+) \(`)
	metaAddColRe     = regexp.MustCompile(`(?is)ALTER TABLE\s+(\w+)\s+ADD COLUMN`)
	erasureTagRe     = regexp.MustCompile(`@erasure_method:\s*(\S+)`)
	// db-safety-gate: ok — a PARSER for migration text, not a statement. This
	// test opens no database connection; it reads *.up.sql off disk to find
	// which tables still exist.
	metaDropTableRe = regexp.MustCompile(`DROP TABLE (?:IF EXISTS )?(\w+)`)
)

// metaTablesWithUserColumn returns table -> the file that gave it a user
// reference, plus every file scanned.
//
// It considers BOTH shapes, because W6 arrived as the second one and a walk
// that only understood CREATE TABLE would have missed it exactly as the
// per-reality walk did:
//
//	CREATE TABLE x (... user_ref_id UUID ...)
//	ALTER TABLE x ADD COLUMN owner_user_id UUID
func metaTablesWithUserColumn(t *testing.T, dir string) (map[string]string, int) {
	t.Helper()
	files, err := filepath.Glob(filepath.Join(dir, "*.up.sql"))
	if err != nil {
		t.Fatalf("glob %s: %v", dir, err)
	}
	out := map[string]string{}
	for _, f := range files {
		raw, err := os.ReadFile(f)
		if err != nil {
			t.Fatalf("read %s: %v", f, err)
		}
		body := stripSQLComments(string(raw))
		base := filepath.Base(f)

		// CREATE TABLE chunks: scan each head to the next one.
		heads := metaCreateHeadRe.FindAllStringSubmatchIndex(body, -1)
		for i, h := range heads {
			name := body[h[2]:h[3]]
			end := len(body)
			if i+1 < len(heads) {
				end = heads[i+1][0]
			}
			if metaUserColRe.MatchString(body[h[1]:end]) {
				out[name] = base
			}
		}

		// ALTER TABLE ... ADD COLUMN: check the statement's own text.
		for _, m := range metaAddColRe.FindAllStringSubmatchIndex(body, -1) {
			name := body[m[2]:m[3]]
			end := strings.Index(body[m[0]:], ";")
			if end < 0 {
				end = len(body) - m[0]
			}
			if metaUserColRe.MatchString(body[m[0] : m[0]+end]) {
				out[name] = base
			}
		}

		// A dropped table holds nothing. `player_character_index` was created
		// by 012 and dropped by 035; without this the walk reports a table that
		// does not exist, and a gate that cries wolf gets ignored — which is
		// how a real finding hides.
		for _, d := range metaDropTableRe.FindAllStringSubmatch(body, -1) {
			delete(out, d[1])
		}
	}
	return out, len(files)
}

// erasureMethodsByFile maps migration file -> declared @erasure_method.
func erasureMethodsByFile(t *testing.T, dir string) map[string]string {
	t.Helper()
	files, err := filepath.Glob(filepath.Join(dir, "*.up.sql"))
	if err != nil {
		t.Fatalf("glob %s: %v", dir, err)
	}
	out := map[string]string{}
	for _, f := range files {
		raw, err := os.ReadFile(f)
		if err != nil {
			t.Fatalf("read %s: %v", f, err)
		}
		if m := erasureTagRe.FindStringSubmatch(string(raw)); m != nil {
			out[filepath.Base(f)] = m[1]
		}
	}
	return out
}

// TestMetaMigrationsDeclareAnImplementedErasure — every meta table holding a
// user reference must declare an erasure method, and that method must exist in
// this package.
//
// The second half is the point. A tag is a string; `pii-classify-lint.sh` only
// checks that one is PRESENT, so `@erasure_method: whatever_i_typed` satisfies
// it. What makes the tag load-bearing is a named implementation.
func TestMetaMigrationsDeclareAnImplementedErasure(t *testing.T) {
	withUser, scanned := metaTablesWithUserColumn(t, metaMigrationDir)
	if scanned == 0 {
		t.Fatal("walked 0 meta migrations — the walk found nothing, which is a " +
			"failure, not a clean bill of health")
	}
	if len(withUser) == 0 {
		t.Fatal("found 0 meta tables carrying a user reference; reality_registry " +
			"and actor_control_binding both do, so the walk is broken")
	}

	methods := erasureMethodsByFile(t, metaMigrationDir)

	for table, file := range withUser {
		method, ok := implemented[table]
		if !ok {
			if reason, known := knownUnhandled[table]; known {
				t.Logf("KNOWN GAP: %s (%s) — %s", table, file, reason)
				continue
			}
			t.Errorf(
				"meta table %q (introduced/extended by %s) carries a user reference but "+
					"nothing in PgMetaScrubber erases it — a GDPR erasure would report "+
					"success while the user's identifier survives. Implement it and add it "+
					"to `implemented`, or record it in `knownUnhandled` with the mechanism "+
					"that does discharge it.",
				table, file)
			continue
		}
		if declared, has := methods[file]; has && declared != method {
			t.Errorf(
				"%s declares @erasure_method %q for %q but this package implements %q — "+
					"the header and the code disagree about what erasure does",
				file, declared, table, method)
		}
	}

	// The register must SHRINK, never quietly outlive its reason: a table that
	// has since been handled (or dropped) must leave the list, or the list
	// becomes a place findings go to be forgotten.
	for table := range knownUnhandled {
		if _, still := withUser[table]; !still {
			t.Errorf("knownUnhandled still lists %q, which no longer carries a user "+
				"reference — remove the row", table)
		}
		if _, now := implemented[table]; now {
			t.Errorf("%q is in BOTH implemented and knownUnhandled — remove the gap row", table)
		}
	}
}

// The tables this package's scrubber actually handles, and how.
var implemented = map[string]string{
	"actor_control_binding": "hard_delete",
	"reality_registry":      "reassign_to_system_on_user_erasure",
}

// Meta tables that carry a user reference and are NOT discharged by
// PgMetaScrubber.
//
// This register is the honest half of the gate, and it exists because writing
// it revealed a gap far wider than the one it was built for: the walk that
// caught W6's missing erasure also found EIGHT pre-existing meta tables holding
// a user reference with no scrubber path, five of them declaring no
// @erasure_method at all. That is a real GDPR finding, it predates this work,
// and several rows need a retention/legal decision rather than code — so
// pretending they are handled would be the exact dishonesty this gate exists to
// prevent, and silently omitting them would make the gate vacuous.
//
// Tracked as `D-META-ERASURE-COVERAGE`. The mechanism that wakes it is this
// test: a NEW user-referencing table cannot be added without either an
// implementation or a deliberate row here, and a row that stops applying fails.
var knownUnhandled = map[string]string{
	"user_cost_ledger":         "declares pseudonymize_user_ref_at_2y; legal_basis legal_obligation (tax) — must NOT be deleted on request. Retention job unbuilt.",
	"user_daily_cost":          "declares pseudonymize_user_ref_at_2y; same billing-retention basis as user_cost_ledger.",
	"user_queue_metrics":       "declares hard_delete; no deleter exists in this package yet.",
	"user_consent_ledger":      "the record OF consent, including its withdrawal — erasing it destroys the evidence that erasure was requested. Needs a product/legal decision, not code.",
	"pii_kek":                  "erased by CRYPTO-SHRED (KEK destruction via piikms), not by row deletion — a different mechanism, not a missing one.",
	"pii_registry":             "the index the crypto-shred walks; erasing it first would orphan the shred.",
	"session_cost_summary":     "declares no @erasure_method; billing aggregate, needs the same retention decision as user_cost_ledger.",
	"service_to_service_audit": "an append-only audit of inter-service calls; retention-bounded rather than erasable on request.",
}

// The scrubber must actually NAME the tables it claims to handle. Deleting the
// reassign call would leave the test above passing on a map entry alone, which
// is a claim, not a mechanism.
func TestScrubberSourceNamesEveryTableItClaims(t *testing.T) {
	src, err := os.ReadFile("pglive.go")
	if err != nil {
		t.Fatalf("read pglive.go: %v", err)
	}
	body := string(src)
	for _, table := range []string{"actor_control_binding", "reality_registry"} {
		if !strings.Contains(body, `Table:     "`+table+`"`) {
			t.Errorf("PgMetaScrubber builds no MetaWriteIntent for %q, but the erasure "+
				"map claims it is handled", table)
		}
	}
	// ...and the reassignment must set BOTH columns: clearing owner_user_id
	// alone is refused by reality_registry_owner_user_set, so a half-written
	// erasure would fail at runtime rather than in a test.
	if !strings.Contains(body, `"owner_kind": "system", "owner_user_id": nil`) {
		t.Error("the reality_registry erasure must set owner_kind AND owner_user_id " +
			"together; the CHECK constraints reject either one alone")
	}
}

// RealitiesForUser feeds the per-reality erasure cascade. It used to read only
// `actor_control_binding`, so a user who OWNS a reality but drives no actor in
// it was invisible: every per-reality scrub skipped that reality and it kept
// their data, while the erasure reported success.
//
// Asserted against the SOURCE because the behaviour needs a live meta database
// and this package's unit tests must run without one — the live path is covered
// by the erasure integration tests. A source assertion is weaker than a
// behavioural one and is chosen deliberately over having no check at all.
func TestRealitiesForUser_IncludesOwnedRealities(t *testing.T) {
	src, err := os.ReadFile("pglive.go")
	if err != nil {
		t.Fatalf("read pglive.go: %v", err)
	}
	body := string(src)
	i := strings.Index(body, "func (l *PgUserRealityLookup) RealitiesForUser")
	if i < 0 {
		t.Fatal("RealitiesForUser not found — this test is watching the wrong symbol")
	}
	j := strings.Index(body[i:], "\n}")
	if j < 0 {
		t.Fatal("could not find the end of RealitiesForUser")
	}
	fn := body[i : i+j]
	if !strings.Contains(fn, "reality_registry") || !strings.Contains(fn, "owner_user_id") {
		t.Error("RealitiesForUser does not consult reality_registry.owner_user_id — a user " +
			"who owns a reality but drives no actor in it would be skipped by the entire " +
			"erasure cascade")
	}
}
