package migrate

import (
	"reflect"
	"runtime"
	"strings"
	"testing"
)

// The search fix existed in four places in the source and was ABSENT from the running database.
//
// glossary_search matches on `e.cached_name` and `search_vector`; both columns are maintained
// ONLY by recalculate_entity_snapshot. Read out of the live database with pg_get_functiondef on
// 2026-08-26, the deployed body was 3,465 chars / 103 lines with ZERO occurrences of either
// column — chain step 0004_snapshot's version — even though 0026 and 0028 were both recorded
// applied on 2026-06-20. An entity was created, listed by name in the curation inbox, and
// returned by recent_for_orientation, while the search built to find it returned nothing for its
// exact name. 549 of 7,575 alive entities carried a NULL cached_name; only 133 were drafts.
//
// These guards are about the CHAIN, not the SQL's behaviour against a live Postgres — the
// behavioural half needs a database and lives with the integration suite. What can go wrong
// silently here is ordering and naming, and that is what is pinned.
//
// ── 🔴 ANCHORED ON THE FUNCTION, NOT THE STEP NUMBER ────────────────────────
// These three tests hardcoded `0060_glossary_recalc_restore` and
// `0061_backfill_null_cached_name`, and they went RED on the kal-x-fetools merge:
//
//	recalc_restore_test.go:43: chain has no step "0060_glossary_recalc_restore"
//
// Nothing was lost. The merge RENUMBERED the pair to 0067/0068 — `0060` is now
// `0060_seed_genre_kind_attributes` from the other side — and a second repair pair
// (0069/0070) was added when 0060 turned out to have been reverted on the running database.
// Renumbering on merge is this ledger's normal practice; it carries three MERGE notes saying
// so. So a test keyed to a NUMBER fails on a merge that did nothing wrong, and — worse — would
// have gone quiet if some unrelated migration had later claimed the name `0060_glossary_
// recalc_restore`. The number is not the property.
//
// What IS the property: a step running `UpGlossaryRecalcRestore` is in the chain, every
// backfill runs after a restore, and neither is an edit to the already-applied 0028. All three
// are stated against the FUNCTION and the ORDER, so the next renumber cannot break them and
// cannot hide a real removal either.

func stepIndex(t *testing.T, name string) int {
	t.Helper()
	for i, s := range chain {
		if s.Name == name {
			return i
		}
	}
	t.Fatalf("chain has no step %q", name)
	return -1
}

func fnName(f any) string {
	full := runtime.FuncForPC(reflect.ValueOf(f).Pointer()).Name()
	return full[strings.LastIndex(full, ".")+1:]
}

// stepsRunning returns the chain positions of every step whose Fn is the named function,
// in chain order. Renumber-proof by construction: it never reads a step name.
func stepsRunning(fn string) []int {
	var at []int
	for i, s := range chain {
		if fnName(s.Fn) == fn {
			at = append(at, i)
		}
	}
	return at
}

func TestTheRestoreStepIsInTheChain(t *testing.T) {
	// A step that is not in the chain never runs, and this whole defect is a correct function
	// body that never reached the server.
	at := stepsRunning("UpGlossaryRecalcRestore")
	if len(at) == 0 {
		t.Fatal("no chain step runs UpGlossaryRecalcRestore — the restore never reaches a server")
	}
	// ApplyOnce records by NAME, so two steps sharing a name would run once and the second
	// repair would silently not happen. That is the failure mode the 0069 entry exists for.
	seen := map[string]bool{}
	for _, i := range at {
		if seen[chain[i].Name] {
			t.Fatalf("two restore steps share the name %q — ApplyOnce would run only the first",
				chain[i].Name)
		}
		seen[chain[i].Name] = true
	}
}

func TestTheBackfillRunsAFTERTheRestore(t *testing.T) {
	// Order is the whole point: run first, the backfill calls the BROKEN body, repairs nothing,
	// and reports success — a repair that reads as done is worse than no repair.
	restores := stepsRunning("UpGlossaryRecalcRestore")
	backfills := stepsRunning("BackfillNullCachedName")
	if len(restores) == 0 || len(backfills) == 0 {
		t.Fatalf("restore(s)=%d backfill(s)=%d — both must exist", len(restores), len(backfills))
	}
	// EVERY backfill must have a restore before it, not just the first pair. The second repair
	// (0069/0070) exists precisely because the first was reverted on the running database, and
	// a backfill that ran before its own restore would repair nothing while reporting success.
	for _, b := range backfills {
		ok := false
		for _, r := range restores {
			if r < b {
				ok = true
				break
			}
		}
		if !ok {
			t.Fatalf("backfill %q at %d has no restore before it", chain[b].Name, b)
		}
	}
	// And the LAST word must be a backfill: a restore added after the final backfill would
	// re-install the body over rows nothing then repairs.
	if backfills[len(backfills)-1] < restores[len(restores)-1] {
		t.Fatalf("the last restore (%q) runs after the last backfill (%q)",
			chain[restores[len(restores)-1]].Name, chain[backfills[len(backfills)-1]].Name)
	}
}

func TestTheRestoreIsANEWStepNotAnEditToTheAppliedOne(t *testing.T) {
	// ApplyOnce records a step by NAME, so DDL added to an already-applied step is a silent
	// no-op on every existing database. 0028 is recorded applied since 2026-06-20; editing it
	// would have shipped nothing, which is how the source and the server came to disagree.
	//
	// 0028 keeps its literal name here on purpose: the premise of the whole repair is that
	// THAT step already ran on every deployed database, so if it is ever renamed the premise
	// needs re-examining rather than silently re-pointing.
	cutover := stepIndex(t, "0028_glossary_cutover_g4_cache")
	for _, i := range stepsRunning("UpGlossaryRecalcRestore") {
		if i == cutover {
			t.Fatal("the restore IS 0028 — then it adds nothing on a database that already applied it")
		}
		if fnName(chain[i].Fn) == fnName(chain[cutover].Fn) {
			t.Fatalf("%q and 0028 are the same Fn — then it adds nothing", chain[i].Name)
		}
	}
}
