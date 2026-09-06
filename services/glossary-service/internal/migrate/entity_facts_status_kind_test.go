package migrate

import (
	"context"
	"os"
	"strings"
	"testing"

	"github.com/jackc/pgx/v5/pgxpool"
)

// The fact-kind widening for liveness-as-a-fact (plan T32 / D1).
//
// Asserted against a real Postgres, because the thing under test IS a database constraint:
// a unit test over the SQL string would prove the string, not that the constraint moved.

func openMigrateDB(t *testing.T) *pgxpool.Pool {
	t.Helper()
	dsn := os.Getenv("GLOSSARY_TEST_DB_URL")
	if dsn == "" {
		t.Skip("GLOSSARY_TEST_DB_URL not set — skipping DB integration test")
	}
	pool, err := pgxpool.New(context.Background(), dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	if err := RunChain(context.Background(), pool); err != nil {
		t.Fatalf("migrate.RunChain: %v", err)
	}
	return pool
}

func factKindConstraint(t *testing.T, pool *pgxpool.Pool) string {
	t.Helper()
	var def string
	if err := pool.QueryRow(context.Background(),
		`SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname='entity_facts_kind_chk'`,
	).Scan(&def); err != nil {
		t.Fatalf("read entity_facts_kind_chk: %v", err)
	}
	return def
}

func TestEntityFactsKindChk_AdmitsStatus(t *testing.T) {
	// D1's whole mechanism depends on this one word. Without it, "is X alive as of N" cannot
	// be stored as a fact at all, and liveness stays a column that is 7290 true / 0 false.
	pool := openMigrateDB(t)
	def := factKindConstraint(t, pool)
	if !strings.Contains(def, "'status'") {
		t.Fatalf("entity_facts_kind_chk does not admit 'status' — liveness cannot be a fact.\n  got: %s", def)
	}
}

func TestEntityFactsKindChk_StillRefusesUnknownKinds(t *testing.T) {
	// The positive control's other half. A constraint that admitted everything would pass the
	// test above for the wrong reason — the point of a CLOSED vocabulary is that it is closed,
	// and D1 widens it by exactly one word rather than opening it.
	pool := openMigrateDB(t)
	def := factKindConstraint(t, pool)
	for _, kind := range []string{"attribute", "relation", "event", "name", "alias", "status"} {
		if !strings.Contains(def, "'"+kind+"'") {
			t.Errorf("the widening dropped an existing kind: %q is no longer admitted.\n  got: %s", kind, def)
		}
	}
	if strings.Contains(def, "'liveness'") || strings.Contains(def, "'life_status'") {
		t.Errorf("the constraint admits a kind D1 never asked for — `life_status` is the "+
			"attr_or_predicate, NOT the fact_kind, and conflating them would put the "+
			"vocabulary on the wrong column.\n  got: %s", def)
	}
}
