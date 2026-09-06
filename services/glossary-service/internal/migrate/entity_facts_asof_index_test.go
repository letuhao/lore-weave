package migrate

// D9 / plan T9 — guard the covering index behind the book-wide `state@as_of` read.
//
// Losing this index is SILENT: the read still returns the right answer, just 3.6× slower
// (281 ms vs 79 ms at the 4 000-chapter ceiling), and the first symptom is a drafting run
// that feels sluggish on a long book — which nobody traces back to an index. So the shape
// guard is deliberately NOT DB-gated: it runs on every commit, not only on a machine that
// happens to have GLOSSARY_TEST_DB_URL set.
//
// The INCLUDE list is the part most at risk of a well-meaning "simplification". It is not
// decoration — it is the whole difference between an Index Scan and an Index ONLY Scan, and
// therefore between 197 ms and 79 ms. Measured, see entity_facts_asof_index.go.

import (
	"context"
	"os"
	"regexp"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
)

// sqlLiteral returns the body of the file's raw-string SQL constant — everything between the
// first pair of backticks. Guards that grep source files need this: a doc comment explaining
// what NOT to write contains the forbidden text by construction.
func sqlLiteral(t *testing.T, src string) string {
	t.Helper()
	// Anchor on the DECLARATION, not on the first backtick in the file: the doc comment
	// above it quotes identifiers in backticks, so "first backtick" lands inside the prose.
	// (This helper's first version did, and reported the comment as a missing index.)
	const decl = "entityFactsAsOfIndexSQL = `"
	at := strings.Index(src, decl)
	if at < 0 {
		t.Fatal("entityFactsAsOfIndexSQL is no longer declared as a raw-string constant")
	}
	rest := src[at+len(decl):]
	closeAt := strings.Index(rest, "`")
	if closeAt < 0 {
		t.Fatal("unterminated raw-string SQL literal in entity_facts_asof_index.go")
	}
	return rest[:closeAt]
}

func TestEntityFactsAsOfIndex_KeepsItsCoveringShape(t *testing.T) {
	src, err := os.ReadFile("entity_facts_asof_index.go")
	if err != nil {
		t.Fatalf("read entity_facts_asof_index.go: %v", err)
	}
	// Read the SQL LITERAL, not the file. The doc comment above it necessarily contains the
	// string "CREATE INDEX CONCURRENTLY" — it exists to explain why that cannot be used here —
	// and a whole-file grep flags the explanation as the violation it warns about. (This test
	// did exactly that on its first run.)
	sql := sqlLiteral(t, string(src))

	// The key order is load-bearing: book_id must lead (every read is book-scoped) and
	// valid_from_ordinal must be DESC so the freshest interval covering a position sorts
	// first for the DISTINCT ON.
	keyRe := regexp.MustCompile(
		`(?is)CREATE INDEX IF NOT EXISTS\s+idx_entity_facts_book_asof\s+ON\s+entity_facts\s*\(\s*book_id\s*,\s*entity_id\s*,\s*attr_or_predicate\s*,\s*valid_from_ordinal\s+DESC\s*\)`)
	if !keyRe.MatchString(sql) {
		t.Fatal("idx_entity_facts_book_asof no longer declares " +
			"(book_id, entity_id, attr_or_predicate, valid_from_ordinal DESC).\n" +
			"That key order is what lets one scan answer a book-wide as-of read; a different " +
			"leading column makes the index unusable for it.")
	}

	// The INCLUDE columns ARE the win. Without them the scan must visit the heap for every
	// candidate row (~558k random fetches at the ceiling) and the index buys 1.4× instead
	// of 3.6×. state_handler.go selects exactly value + fact_kind from the heap, and
	// valid_to_eff is the other half of the as-of predicate.
	for _, col := range []string{"valid_to_eff", "value", "fact_kind"} {
		inc := regexp.MustCompile(`(?is)INCLUDE\s*\([^)]*\b` + col + `\b[^)]*\)`)
		if !inc.MatchString(sql) {
			t.Errorf("INCLUDE no longer carries %q — the scan stops being index-ONLY and the "+
				"index buys 1.4x instead of 3.6x. If state_handler.go genuinely stopped "+
				"selecting it, change both in the same commit and say so here.", col)
		}
	}

	// Partial on exactly the slice the as-of read wants. Widening it would index superseded
	// beliefs and multi-valued facts — rows this read can never return — for nothing.
	if !strings.Contains(sql, "WHERE invalidated_at IS NULL AND cardinality = 'single'") {
		t.Error("the index is no longer PARTIAL on (invalidated_at IS NULL AND cardinality='single') — " +
			"it now indexes rows the as-of read can never return")
	}

	// CONCURRENTLY cannot appear here: execGuarded wraps every step in a transaction and
	// Postgres forbids CREATE INDEX CONCURRENTLY inside one. This would not fail at build
	// time — it fails at MIGRATION time, on the deployment, which is the worst place to
	// discover it.
	if regexp.MustCompile(`(?i)CREATE\s+INDEX\s+CONCURRENTLY`).MatchString(sql) {
		t.Error("CREATE INDEX CONCURRENTLY cannot run inside the chain runner's transaction " +
			"(migrate.go execGuarded takes pg_advisory_xact_lock in a tx). This would fail at " +
			"migration time on a real deployment, not here.")
	}
}

func TestEntityFactsAsOfIndex_IsRegisteredInTheChain(t *testing.T) {
	// Declaring the SQL is not enough. The chain is applied ONCE per database and recorded
	// in schema_migrations, so DDL that is not its own step never reaches an existing
	// deployment — it would take effect only on a fresh DB, and nobody would notice until a
	// production read was slow and a local one was not.
	var found *Step
	for i := range chain {
		if chain[i].Name == "0062_entity_facts_asof_index" {
			found = &chain[i]
			break
		}
	}
	if found == nil {
		t.Fatal("0062_entity_facts_asof_index is not in the migration chain — the index would " +
			"only ever be created on a FRESH database")
	}
	if found.Fn == nil {
		t.Fatal("0062_entity_facts_asof_index has a nil migration func")
	}
}

func TestEntityFactsAsOfIndex_ExistsAfterTheChain(t *testing.T) {
	// The shape guards above read the SOURCE. This one reads the DATABASE, because those two
	// can disagree: a step that is declared, registered, and silently failing (or applied
	// under an older ledger name) leaves the source looking correct and the index absent.
	dbURL := os.Getenv("GLOSSARY_TEST_DB_URL")
	if dbURL == "" {
		t.Skip("GLOSSARY_TEST_DB_URL not set")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dbURL)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	defer pool.Close()
	if err := RunChain(ctx, pool); err != nil {
		t.Fatalf("RunChain: %v", err)
	}

	var def string
	if err := pool.QueryRow(ctx,
		`SELECT indexdef FROM pg_indexes
		  WHERE tablename = 'entity_facts' AND indexname = 'idx_entity_facts_book_asof'`,
	).Scan(&def); err != nil {
		t.Fatalf("idx_entity_facts_book_asof is absent after RunChain: %v", err)
	}
	// Postgres normalises the definition, so assert on what it reports rather than on the
	// literal we wrote — that is what catches a step that ran against an older definition.
	for _, want := range []string{"valid_from_ordinal DESC", "INCLUDE", "value", "fact_kind", "WHERE"} {
		if !strings.Contains(def, want) {
			t.Errorf("the LIVE index definition is missing %q:\n%s", want, def)
		}
	}
}
