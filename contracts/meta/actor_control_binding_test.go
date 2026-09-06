package meta

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestActorControlBinding_ReplacedPlayerCharacterIndex_D_PLAYER_INDEX_PARKED is
// what `TestPlayerCharacterIndex_StillParked` BECAME when its parking ended.
//
// WHY THIS FILE WAS NOT SIMPLY DELETED
// ------------------------------------
// The old test asserted the three facts that made the parking valid, and said in
// its own header: *"If 012 was deleted, the parking is RESOLVED — remove this
// test and close the row."* That instruction is right about the row and wrong
// about the file, for a reason worth writing down:
//
//	012 was NOT deleted. A migration file is HISTORY — you never remove one, you
//	add a migration that drops what it created. So the old test's trigger could
//	never fire: it would have gone on passing over a table Postgres no longer has,
//	which is precisely the "a fixed item still listed as open" failure it was
//	built to prevent, wearing its own costume.
//
// So the mechanism is kept and re-pointed. The parking is over; what needs
// guarding now is that it STAYS over — that the vocabulary the decision deleted
// does not come back through a copy-paste, and that the replacement carries none
// of the six columns the audit rejected.
//
// The precedent is this project's own: per_reality/0017 DROPPED the sibling
// pc/npc projections, and the orphan-model gate is what keeps them gone.
func TestActorControlBinding_ReplacedPlayerCharacterIndex_D_PLAYER_INDEX_PARKED(t *testing.T) {
	const marker = "D-PLAYER-INDEX-PARKED"

	// contracts/meta -> repo root
	root, err := filepath.Abs(filepath.Join("..", ".."))
	if err != nil {
		t.Fatalf("abs root: %v", err)
	}
	read := func(rel string) string {
		b, err := os.ReadFile(filepath.Join(root, rel))
		if err != nil {
			t.Fatalf("%s: cannot read %s: %v", marker, rel, err)
		}
		return string(b)
	}

	// ── 1. the old table is DROPPED, by a migration that exists ───────────
	drop := read("migrations/meta/035_drop_player_character_index.up.sql")
	for _, want := range []string{
		// db-safety-gate: ok — this is a SQL-string ASSERTION, not a statement.
		// The strings below are needles for strings.Contains against a migration
		// file read off disk; this test opens no database connection at all
		// (there is no pool, no DSN and no Exec in this file). The gate is right
		// to look: a DROP in a test file is the shape that hard-deleted every
		// user's books once. It is right to look and wrong here.
		"DROP TABLE IF EXISTS player_character_index",
		"DROP FUNCTION IF EXISTS player_character_index_touch_updated_at",
	} {
		if !strings.Contains(drop, want) {
			t.Errorf("%s: 035 no longer contains %q — the drop is what closed this row",
				marker, want)
		}
	}

	// ── 2. the replacement exists, WITHOUT the six rejected columns ───────
	create := read("migrations/meta/034_actor_control_binding.up.sql")
	if !strings.Contains(create, "CREATE TABLE IF NOT EXISTS actor_control_binding") {
		t.Fatalf("%s: 034 does not create actor_control_binding", marker)
	}
	for _, want := range []string{"user_ref_id", "reality_id", "actor_id", "revoked_at"} {
		if !strings.Contains(create, want) {
			t.Errorf("%s: 034 is missing %q — the binding is the whole concept", marker, want)
		}
	}
	// The column audit's verdicts, as assertions. Each name here is a thing the
	// PO's decision REMOVED, with the reason it was removed; a reappearance is
	// the vocabulary coming back, which is the failure this file now guards.
	//
	// Scoped to the DDL BODY — `CREATE TABLE` through its closing `);`. The
	// first version scanned the whole file and fired on `COMMENT ON COLUMN
	// ... 'Not a status enum'`, i.e. on the header prose EXPLAINING the audit.
	// A guard that reds on its own rationale trains its reader to ignore it.
	ddlStart := strings.Index(create, "CREATE TABLE IF NOT EXISTS actor_control_binding")
	ddlEnd := strings.Index(create[ddlStart:], "\n);")
	if ddlEnd < 0 {
		t.Fatalf("%s: cannot find the end of 034's CREATE TABLE body", marker)
	}
	body := create[ddlStart : ddlStart+ddlEnd]
	for _, dead := range []struct{ token, why string }{
		{"pc_name", "PII and two-kind vocabulary"},
		{"npc_converted", "a transition between actor kinds that no longer exist"},
		{"deceased", "mortality in a lookup table — GoneState is the SSOT"},
		{"last_seen_at", "presence, which belongs to the transport"},
		{"pc_index_id", "a surrogate PK where (reality_id, actor_id) is the key"},
		{"status", "5 of 6 members were presence, mortality or a UI preference"},
	} {
		// Inline `--` comments inside the DDL body are still prose.
		for i, line := range strings.Split(body, "\n") {
			l := strings.TrimSpace(line)
			if strings.HasPrefix(l, "--") || l == "" {
				continue
			}
			if strings.Contains(l, dead.token) {
				t.Errorf("%s: 034 line %d reintroduces %q (%s):\n  %s",
					marker, i+1, dead.token, dead.why, l)
			}
		}
	}

	// ── 3. no CODE names the old table any more ──────────────────────────
	// The two migrations that legitimately mention it are its own definition and
	// its drop; everything else moved in the same commit. A reappearance here is
	// a reader or writer pointed at a table Postgres does not have — which does
	// not fail loudly, it wedges the GDPR pipeline shut (see pglive.go's header
	// for the last time that happened).
	var stale []string
	for _, f := range sourceFiles(t, root) {
		rel := filepath.ToSlash(mustRel(root, f))
		// 012 is its own definition, 035 is its drop, and 034's COMMENT ON names
		// its predecessor to say what it replaces. Everything else moved.
		if strings.HasPrefix(rel, "migrations/meta/012_") ||
			strings.HasPrefix(rel, "migrations/meta/034_") ||
			strings.HasPrefix(rel, "migrations/meta/035_") {
			continue
		}
		b, err := os.ReadFile(f)
		if err != nil {
			continue
		}
		for i, line := range strings.Split(string(b), "\n") {
			l := strings.TrimSpace(line)
			if strings.HasPrefix(l, "//") || strings.HasPrefix(l, "--") ||
				strings.HasPrefix(l, "#") || strings.HasPrefix(l, "*") {
				continue
			}
			if strings.Contains(l, "player_character_index") {
				stale = append(stale, rel+":"+itoa(i+1)+"  "+l)
			}
		}
	}
	if len(stale) > 0 {
		t.Errorf("%s: %d source line(s) still name the dropped table:\n  %s",
			marker, len(stale), strings.Join(stale, "\n  "))
	}

	// ── 4. the walk must have a SUBJECT ──────────────────────────────────
	// Inherited unchanged from the test this replaces, and for its reason: a scan
	// that reads nothing reports "clean" with total confidence and zero
	// information — how the orphan gate once certified world_kv_projection from a
	// #[cfg(test)] fixture.
	if n := countScanned(t, root); n < 500 {
		t.Fatalf("%s: the scan visited only %d source file(s) — it cannot have "+
			"looked. A clean result from a scan that read nothing is not a clean "+
			"result.", marker, n)
	}
}

func mustRel(root, p string) string {
	rel, err := filepath.Rel(root, p)
	if err != nil {
		return p
	}
	return rel
}

// NOTE — `findProducers` was deleted with the parking it served. Its job was to
// answer "has a writer landed yet", which was the parked decision's trigger; the
// decision is taken, so the question is gone. It is recorded here rather than
// silently dropped, because a helper vanishing from a guard file is exactly the
// kind of quiet scope loss this file exists to notice.

func sourceFiles(t *testing.T, root string) []string {
	t.Helper()
	var out []string
	for _, dir := range []string{"crates", "services", "contracts", "migrations"} {
		_ = filepath.Walk(filepath.Join(root, dir), func(p string, fi os.FileInfo, err error) error {
			if err != nil || fi == nil || fi.IsDir() {
				return nil
			}
			s := filepath.ToSlash(p)
			if strings.Contains(s, "node_modules") || strings.Contains(s, "/target/") ||
				strings.Contains(s, "/.claude/") {
				return nil
			}
			switch filepath.Ext(p) {
			case ".go", ".rs", ".ts", ".sql":
				// A test that seeds a fixture row is not a producer.
				if strings.HasSuffix(s, "_test.go") || strings.Contains(s, "/tests/") {
					return nil
				}
				out = append(out, p)
			}
			return nil
		})
	}
	return out
}

func countScanned(t *testing.T, root string) int {
	t.Helper()
	return len(sourceFiles(t, root))
}

func itoa(n int) string {
	if n == 0 {
		return "0"
	}
	var b []byte
	for n > 0 {
		b = append([]byte{byte('0' + n%10)}, b...)
		n /= 10
	}
	return string(b)
}
