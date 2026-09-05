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
//
// TWO forms, because ONE was not enough and the omission made this gate
// vacuous against the exact table it was written for:
//
//	colDeclRe  — a column line in a CREATE TABLE body: line-start anchored, so
//	             `CREATE INDEX … (user_id)` and `REFERENCES users (user_id)`
//	             cannot match. This is the rule the per-reality walk uses.
//	addColRe   — `ADD COLUMN owner_user_id UUID`, where the name is NOT at line
//	             start.
//
// The first version had only the line-anchored form. Migration 036 introduces
// `owner_user_id` via `ALTER TABLE … ADD COLUMN`, so the name is preceded by
// `ADD COLUMN` and never matched — `owner_user_id` appears at line-start in
// ZERO files under migrations/meta. A cold-start review proved it by removing
// `reality_registry` from `implemented` and watching the suite stay GREEN, and
// again by adding a synthetic table the W6 way, also GREEN.
//
// So the gate written to catch a default-uncovered column was itself blind to
// that column: an adjacent decision (the anchor, correct for its own purpose)
// defeating the check (`NV-4`). The `metaAddColRe` branch below existed for
// precisely this shape and the anchor cancelled it.
var (
	colDeclRe = regexp.MustCompile(`(?m)^\s*(user_id|user_ref_id|owner_user_id)\s`)
	addColRe  = regexp.MustCompile(`(?i)\bADD COLUMN\s+(?:IF NOT EXISTS\s+)?(user_id|user_ref_id|owner_user_id)\b`)
)

// metaUserColRe reports whether a fragment of migration text declares a user
// reference, in either form.
func metaUserColMatch(fragment string) bool {
	return colDeclRe.MatchString(fragment) || addColRe.MatchString(fragment)
}

var (
	metaCreateHeadRe = regexp.MustCompile(`CREATE TABLE (?:IF NOT EXISTS )?(?:public\.)?(\w+)\s*\(`)
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
			if metaUserColMatch(body[h[1]:end]) {
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
			if metaUserColMatch(body[m[0] : m[0]+end]) {
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
			if how, other := handledElsewhere[table]; other {
				t.Logf("HANDLED ELSEWHERE: %s (%s) — %s", table, file, how)
				continue
			}
			if reason, known := knownUnhandled[table]; known {
				t.Logf("OPEN GAP: %s (%s) — %s", table, file, reason)
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
		if _, other := handledElsewhere[table]; other {
			t.Errorf("%q is in BOTH handledElsewhere and knownUnhandled — pick one", table)
		}
	}
}

// The tables this package's scrubber actually handles, and how.
var implemented = map[string]string{
	"actor_control_binding": "hard_delete",
	"reality_registry":      "reassign_to_system_on_user_erasure",
	"user_queue_metrics":    "hard_delete",
}

// Handled by a DIFFERENT erasure mechanism, not by PgMetaScrubber.
//
// The first version of this register did not have this category, and asked only
// "does PgMetaScrubber handle it". That framing recorded three tables as gaps
// which are in fact fully handled — the question is whether ANY mechanism
// discharges the obligation, not whether this one does. Verified in the source
// rather than assumed, which is how the over-count was found.
var handledElsewhere = map[string]string{
	"pii_kek":             "crypto-shred: admin-cli `erasure user-erasure` destroys the user's KEK (destroyed_at + KMS ScheduleKeyDeletion), which makes every envelope it wrapped unreadable. Deleting the row would remove the record that the shred happened.",
	"pii_registry":        "the envelope index the shred renders unreadable; admin-cli marks erased_at. Deleting it first would orphan the shred.",
	"user_consent_ledger": "admin-cli revokes (revoked_at CAS), deliberately NOT deleting: this ledger IS the evidence that consent existed and was withdrawn, so erasing it would destroy the proof the erasure was lawful.",
}

// Meta tables that carry a user reference and are genuinely NOT discharged by
// anything.
//
// Tracked as `D-META-ERASURE-COVERAGE`. The mechanism that wakes it is this
// test: a NEW user-referencing table cannot be added without either an
// implementation or a deliberate row here, and a row that stops applying fails.
//
// TWO of these declare NO @erasure_method at all, which is a product/legal
// decision rather than a coding one — what a billing aggregate and an
// inter-service audit owe a user who asks to be forgotten is not the engineer's
// call. They are named here so the question is visible instead of absent.
var knownUnhandled = map[string]string{
	"user_cost_ledger":         "declares pseudonymize_user_ref_at_2y; legal_basis legal_obligation (tax) so it must NOT be deleted on request. The declared method is a TIME-based retention job, not an erasure-time action, and that job is unbuilt.",
	"user_daily_cost":          "declares pseudonymize_user_ref_at_2y; same billing-retention basis and the same unbuilt job.",
	"session_cost_summary":     "declares NO @erasure_method. Billing aggregate — needs the same retention decision as user_cost_ledger. PO CALL.",
	"service_to_service_audit": "declares NO @erasure_method. Append-only inter-service audit; presumably retention-bounded rather than erasable on request, but nothing says so. PO CALL.",
}
