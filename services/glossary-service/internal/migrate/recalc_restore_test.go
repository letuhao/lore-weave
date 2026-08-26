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

func TestTheRestoreStepIsInTheChain(t *testing.T) {
	// A step that is not in the chain never runs, and this whole defect is a correct function
	// body that never reached the server.
	i := stepIndex(t, "0060_glossary_recalc_restore")
	if got := fnName(chain[i].Fn); got != "UpGlossaryRecalcRestore" {
		t.Fatalf("0060 runs %s", got)
	}
}

func TestTheBackfillRunsAFTERTheRestore(t *testing.T) {
	// Order is the whole point: run first, the backfill calls the BROKEN body, repairs nothing,
	// and reports success — a repair that reads as done is worse than no repair.
	restore := stepIndex(t, "0060_glossary_recalc_restore")
	backfill := stepIndex(t, "0061_backfill_null_cached_name")
	if backfill <= restore {
		t.Fatalf("backfill at %d runs before/at the restore at %d", backfill, restore)
	}
}

func TestTheRestoreIsANEWStepNotAnEditToTheAppliedOne(t *testing.T) {
	// ApplyOnce records a step by NAME, so DDL added to an already-applied step is a silent
	// no-op on every existing database. 0028 is recorded applied since 2026-06-20; editing it
	// would have shipped nothing, which is how the source and the server came to disagree.
	if stepIndex(t, "0028_glossary_cutover_g4_cache") < 0 {
		t.Fatal("0028 vanished — the restore's whole premise is that it already ran")
	}
	if fnName(chain[stepIndex(t, "0060_glossary_recalc_restore")].Fn) ==
		fnName(chain[stepIndex(t, "0028_glossary_cutover_g4_cache")].Fn) {
		t.Fatal("0060 and 0028 are the same Fn — then 0060 adds nothing")
	}
}

func TestTheRestoreREUSESTheCacheSQLRatherThanCopyingIt(t *testing.T) {
	// A second copy of a ~140-line function body is a second thing to drift, and the defect
	// under repair IS two versions of one function disagreeing about which table holds the name.
	if !strings.Contains(glossaryCutoverG4CacheSQL, "v_cached_name") {
		t.Fatal("the SQL the restore installs no longer maintains cached_name")
	}
	if !strings.Contains(glossaryCutoverG4CacheSQL, "search_vector") {
		t.Fatal("the SQL the restore installs no longer maintains search_vector")
	}
}

func TestTheNameIsResolvedThroughBOOKAttributes(t *testing.T) {
	// Measured 2026-08-26: 7,048 of 7,575 alive entities resolve their name through BOOK
	// attributes and ZERO through system ones. A body joining system_kind_attributes writes
	// NULL and looks exactly like the defect it was meant to fix.
	for _, tc := range []struct{ name, sql string }{
		{"0028 cache body", glossaryCutoverG4CacheSQL},
		{"0013 knowledge-memory body", knowledgeMemorySQL},
	} {
		i := strings.Index(tc.sql, "INTO v_cached_name")
		if i < 0 {
			t.Fatalf("%s: no cached_name lookup at all", tc.name)
		}
		seg := tc.sql[i:min(i+400, len(tc.sql))]
		if !strings.Contains(seg, "book_attributes") {
			t.Errorf("%s: the name lookup does not join book_attributes", tc.name)
		}
		if strings.Contains(seg, "system_kind_attributes") {
			t.Errorf("%s: the name lookup still joins system_kind_attributes, which has zero "+
				"matching rows — it would write NULL", tc.name)
		}
	}
}

func TestTheBackfillOnlyTouchesRowsThatCanBeREPAIRED(t *testing.T) {
	// A row with no name attribute value recalculates to the same NULL. Including it would be
	// churn that reports as repair — the count would look like work and mean nothing.
	if !strings.Contains(backfillNullCachedNameSQL, "cached_name IS NULL") {
		t.Fatal("the backfill is not scoped to the broken rows")
	}
	if !strings.Contains(backfillNullCachedNameSQL, "book_attributes") {
		t.Fatal("the backfill does not require a recoverable name")
	}
	for _, guard := range []string{"e.alive", "e.deleted_at IS NULL"} {
		if !strings.Contains(backfillNullCachedNameSQL, guard) {
			t.Errorf("the backfill does not exclude dead rows (%s)", guard)
		}
	}
}

func min(a, b int) int {
	if a < b {
		return a
	}
	return b
}
