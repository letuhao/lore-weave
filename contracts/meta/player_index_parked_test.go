package meta

import (
	"os"
	"path/filepath"
	"strings"
	"testing"
)

// TestPlayerCharacterIndex_StillParked_D_PLAYER_INDEX_PARKED is the MECHANISM
// behind a parked decision, not a reminder.
//
// WHAT IS PARKED
// --------------
// `migrations/meta/012_player_character_index.up.sql` is the last surviving
// artifact of the pc/npc split that `0017` and `0018` removed from the
// per-reality tier. It carries three separable things:
//
//	(user_ref_id, reality_id, pc_id)   the BINDING — which human drives which
//	                                   actor in which reality. Under the world-
//	                                   simulator framing this is CONTROL, and it
//	                                   is real.
//	pc_name, status='npc_converted'    the OLD TWO-KIND VOCABULARY. "PC was
//	                                   promoted to permanent NPC" is a transition
//	                                   between actor kinds that no longer exist:
//	                                   there is only ACTOR now, and "player" is an
//	                                   interface that drives one, not a kind of one.
//	status='deceased'                  MORTALITY, in an index. An actor's death is
//	                                   a fact of the reality, not of a lookup
//	                                   table — a second SSOT waiting to happen, the
//	                                   same shape as the `stats JSONB` that 0017
//	                                   removed.
//
// It has NO PRODUCER — nothing in the repo INSERTs a row — so nothing depends on
// it today and the decision costs nothing to defer. The PO parked it deliberately:
// the verdict depends on what the player/control feature turns out to need, and
// deciding before that is guessing.
//
// WHY A TEST AND NOT A NOTE
// -------------------------
// A row in a deferral list is prose. Nine of nineteen game-tier deferrals were
// prose-only, and the class of failure is documented: a fixed item still listed
// as open, an open item nobody re-reads. This test asserts the three facts that
// make the parking VALID. When any of them stops holding — a writer lands, the
// table is dropped, the vocabulary is cleaned — it goes red and names the row,
// because at that moment the parking is over whether or not anyone remembers it.
//
// It deliberately does NOT assert that the table is good, or that it should
// survive. It asserts only that the world it was parked in is still the world
// we are in.
func TestPlayerCharacterIndex_StillParked_D_PLAYER_INDEX_PARKED(t *testing.T) {
	const marker = "D-PLAYER-INDEX-PARKED"

	// contracts/meta -> repo root
	root, err := filepath.Abs(filepath.Join("..", ".."))
	if err != nil {
		t.Fatalf("abs root: %v", err)
	}

	// ── 1. the table still exists, unchanged in the parts that matter ──────
	ddlPath := filepath.Join(root, "migrations", "meta",
		"012_player_character_index.up.sql")
	raw, err := os.ReadFile(ddlPath)
	if err != nil {
		t.Fatalf("%s: cannot read %s: %v\n"+
			"If 012 was deleted, the parking is RESOLVED — remove this test and "+
			"close the row.", marker, ddlPath, err)
	}
	ddl := string(raw)

	for _, want := range []string{
		"CREATE TABLE IF NOT EXISTS player_character_index",
		"user_ref_id", "reality_id", "pc_id", // the BINDING half
		"pc_name",         // the vocabulary half
		"'npc_converted'", // the two-kind transition
		"'deceased'",      // mortality in an index
	} {
		if !strings.Contains(ddl, want) {
			t.Errorf("%s: 012 no longer contains %q.\n"+
				"The table changed while the decision was parked, so the parking no "+
				"longer describes reality. Re-read the row and either finish the "+
				"cleanup or close it.", marker, want)
		}
	}

	// ── 2. it still has NO producer ───────────────────────────────────────
	// The parking rests on nothing depending on it. A writer landing is the
	// single event that makes this urgent, and the one thing a prose row could
	// never notice.
	producers := findProducers(t, root, "player_character_index")
	if len(producers) > 0 {
		t.Errorf("%s: something now WRITES player_character_index:\n  %s\n"+
			"The parking assumed no producer. A writer means the player/control "+
			"design has moved — decide the table's shape now, before more code "+
			"binds to `pc_name` / `npc_converted`.",
			marker, strings.Join(producers, "\n  "))
	}

	// ── 3. the walk must have a SUBJECT ───────────────────────────────────
	// A producer scan that reads nothing reports "no producer" with total
	// confidence and zero information — the exact way the orphan gate certified
	// world_kv_projection from a #[cfg(test)] fixture. Prove the scan can see.
	if n := countScanned(t, root); n < 500 {
		t.Fatalf("%s: the producer scan visited only %d source file(s) — it cannot "+
			"have looked. A clean result from a scan that read nothing is not a "+
			"clean result.", marker, n)
	}
}

// findProducers returns non-test, non-comment lines that INSERT into table.
func findProducers(t *testing.T, root, table string) []string {
	t.Helper()
	var out []string
	for _, f := range sourceFiles(t, root) {
		b, err := os.ReadFile(f)
		if err != nil {
			continue
		}
		for i, line := range strings.Split(string(b), "\n") {
			l := strings.TrimSpace(line)
			// Comments are prose that happens to live in a source file — the
			// exact trap that certified three prose-only deferrals as covered.
			if strings.HasPrefix(l, "//") || strings.HasPrefix(l, "--") ||
				strings.HasPrefix(l, "#") || strings.HasPrefix(l, "*") {
				continue
			}
			if !strings.Contains(l, table) {
				continue
			}
			lower := strings.ToLower(l)
			if strings.Contains(lower, "insert into") || strings.Contains(l, "OpInsert") {
				rel, _ := filepath.Rel(root, f)
				out = append(out, filepath.ToSlash(rel)+":"+itoa(i+1))
			}
		}
	}
	return out
}

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
