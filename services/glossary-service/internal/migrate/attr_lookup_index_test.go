package migrate

// D-GLOSSARY-ATTR-LOOKUP-SEQSCAN — guard the index the attribute-definition lookup
// depends on.
//
// Ten queries across four handlers resolve an attribute definition with a correlated
// subquery keyed on (kind_id, code) and NO book_id. Every other book_attributes index
// leads with book_id, so without a (kind_id, code) index Postgres seq-scans the whole
// table on EVERY evaluation — and because the subquery sits inside a hash-join
// condition, that is once per candidate pair, not once per entity.
//
// Measured on a 3,187-entity book before the index: /internal/books/{id}/known-entities
// took 56s with 71.9M shared buffer hits. After: 0.05s.
//
// This is deliberately NOT a DB-gated test. The consequence of losing this index is
// silent — a slow read, then a client timeout, then an extraction that runs un-anchored
// and mints duplicate entities — so the guard has to run on every commit, not only on a
// machine that happens to have GLOSSARY_TEST_DB_URL set.

import (
	"os"
	"path/filepath"
	"regexp"
	"strings"
	"testing"
)

func TestAttrLookupIndexExists(t *testing.T) {
	src, err := os.ReadFile("attr_lookup_index.go")
	if err != nil {
		t.Fatalf("read attr_lookup_index.go: %v", err)
	}
	// The index must lead with kind_id: an index on (code, kind_id) would NOT serve
	// the predicate the same way, and one leading with book_id is what we already had.
	re := regexp.MustCompile(
		`(?i)CREATE INDEX IF NOT EXISTS\s+idx_ba_kind_code\s+ON\s+book_attributes\s*\(\s*kind_id\s*,\s*code\s*\)`)
	if !re.Match(src) {
		t.Fatal(
			"attrLookupIndexSQL no longer declares idx_ba_kind_code ON book_attributes(kind_id, code).\n" +
				"Removing it re-introduces a 56s seq-scan on the known-entities read, which " +
				"times out knowledge-service's glossary client and makes extraction mint " +
				"duplicate entities. If the correlated (kind_id, code) lookups are genuinely " +
				"gone, delete this test in the same commit and say so.")
	}
}

func TestAttrLookupIndexIsRegisteredInTheChain(t *testing.T) {
	// The declaration existing is not enough — the chain is applied ONCE per database
	// and recorded in schema_migrations, so DDL that is not its own step never reaches
	// an existing deployment. The first version of this change put the CREATE INDEX
	// inside 0024_genre_kind_attr, which is long applied everywhere: it would have been
	// a silent no-op on every real DB and taken effect only on a fresh one.
	var found *Step
	for i := range chain {
		if chain[i].Name == "0061_attr_lookup_index" {
			found = &chain[i]
			break
		}
	}
	if found == nil {
		t.Fatal("0061_attr_lookup_index is not in the migration chain — the index " +
			"would only ever be created on a FRESH database")
	}
	if found.Fn == nil {
		t.Fatal("0061_attr_lookup_index has a nil migration func")
	}
	if last := chain[len(chain)-1].Name; last != "0061_attr_lookup_index" {
		// Not a failure — later steps are expected to be appended. Recorded so a
		// reorder (which re-runs steps on every DB) is visible in the log.
		t.Logf("note: chain now ends at %s, not 0059_attr_lookup_index", last)
	}
}

func TestAttrLookupCallSitesStillNeedTheIndex(t *testing.T) {
	// Pairs with the test above: it proves the index exists, this proves it is still
	// EARNING its place. If the handlers stop using the correlated lookup, the index
	// becomes dead weight and someone should be told, not left guessing.
	apiDir := filepath.Join("..", "api")
	entries, err := os.ReadDir(apiDir)
	if err != nil {
		t.Fatalf("read %s: %v", apiDir, err)
	}
	pattern := "ba.kind_id = e.kind_id AND ba.code"
	var sites []string
	for _, e := range entries {
		name := e.Name()
		if e.IsDir() || !strings.HasSuffix(name, ".go") || strings.HasSuffix(name, "_test.go") {
			continue
		}
		b, err := os.ReadFile(filepath.Join(apiDir, name))
		if err != nil {
			t.Fatalf("read %s: %v", name, err)
		}
		if n := strings.Count(string(b), pattern); n > 0 {
			sites = append(sites, name)
		}
	}
	if len(sites) == 0 {
		t.Errorf(
			"no handler still uses the correlated (kind_id, code) attribute lookup — "+
				"idx_ba_kind_code may now be dead weight; re-check %s and either drop the "+
				"index or update these tests", apiDir)
	}
	t.Logf("correlated (kind_id, code) attribute lookup lives in: %s",
		strings.Join(sites, ", "))
}
