package migrate

// Ledger adoption (schema_migrations) — proves RunChain runs each step exactly once,
// is idempotent across boots, and (the D-GKA-G4-SEED-CLEANUP win) does NOT recreate the
// legacy system_kind_attributes table on a second boot. Needs GLOSSARY_TEST_DB_URL;
// each test uses its own ephemeral DB so the fresh-boot precondition is real.
//
// db-safety-gate: file-ok — every destructive statement here (DROP DATABASE, and the
// DROP TABLE schema_migrations that simulates an un-ledgered DB) targets a THROWAWAY
// ephemeral DB each test CREATEs itself (unique name + PID) and drops on cleanup; none
// ever target the DB named in GLOSSARY_TEST_DB_URL. ephemeralDB additionally proves the
// target is a throwaway via testsafe.EnsureThrowawayDB before any CREATE/DROP.

import (
	"context"
	"fmt"
	"net/url"
	"os"
	"testing"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/glossary-service/internal/testsafe"
)

// ephemeralDB spins up a throwaway database and returns a pool to it. The caller gets a
// clean slate (no tables) so RunChain exercises the genuine fresh-DB path.
func ephemeralDB(t *testing.T, name string) *pgxpool.Pool {
	t.Helper()
	dbURL := os.Getenv("GLOSSARY_TEST_DB_URL")
	if dbURL == "" {
		t.Skip("GLOSSARY_TEST_DB_URL not set")
	}
	ctx := context.Background()
	base, err := url.Parse(dbURL)
	if err != nil {
		t.Fatalf("parse url: %v", err)
	}
	maint := *base
	maint.Path = "/postgres"
	admin, err := pgxpool.New(ctx, maint.String())
	if err != nil {
		t.Fatalf("admin pool: %v", err)
	}
	defer admin.Close()

	db := fmt.Sprintf("%s_tmp_%d", name, os.Getpid())
	// Layer-3 safety guard (mirrors book-service testsafe): refuse to CREATE/DROP unless
	// the target is a recognizable throwaway DB, so a broken ephemeral setup can never
	// destroy a real service DB — the pool handed back is proven throwaway before any DDL.
	if err := testsafe.EnsureThrowawayDB(db); err != nil {
		t.Fatal(err)
	}
	_, _ = admin.Exec(ctx, `DROP DATABASE IF EXISTS `+pgx.Identifier{db}.Sanitize()+` WITH (FORCE)`)
	if _, err := admin.Exec(ctx, `CREATE DATABASE `+pgx.Identifier{db}.Sanitize()); err != nil {
		t.Fatalf("create ephemeral db: %v", err)
	}
	t.Cleanup(func() {
		c, err := pgxpool.New(context.Background(), maint.String())
		if err != nil {
			return
		}
		defer c.Close()
		_, _ = c.Exec(context.Background(), `DROP DATABASE IF EXISTS `+pgx.Identifier{db}.Sanitize()+` WITH (FORCE)`)
	})

	target := *base
	target.Path = "/" + db
	pool, err := pgxpool.New(ctx, target.String())
	if err != nil {
		t.Fatalf("ephemeral pool: %v", err)
	}
	t.Cleanup(pool.Close)
	return pool
}

func regclass(t *testing.T, pool *pgxpool.Pool, rel string) *string {
	t.Helper()
	var reg *string
	if err := pool.QueryRow(context.Background(),
		`SELECT to_regclass($1)::text`, "public."+rel,
	).Scan(&reg); err != nil {
		t.Fatalf("to_regclass %s: %v", rel, err)
	}
	return reg
}

// TestRunChain_FreshThenNoChurn — a fresh DB migrated once ends in the tiered final
// state with the legacy table dropped + a full ledger; a SECOND RunChain is a no-op and
// (the cleanup goal) does NOT recreate system_kind_attributes.
func TestRunChain_FreshThenNoChurn(t *testing.T) {
	ctx := context.Background()
	pool := ephemeralDB(t, "glossary_ledger_fresh")

	if err := RunChain(ctx, pool); err != nil {
		t.Fatalf("RunChain (fresh): %v", err)
	}

	// Final tiered state: legacy table gone, tiered tables present.
	if reg := regclass(t, pool, "system_kind_attributes"); reg != nil {
		t.Fatalf("system_kind_attributes still present after fresh chain (=%q)", *reg)
	}
	for _, want := range []string{"system_genres", "system_attributes", "book_kinds", "glossary_entities"} {
		if reg := regclass(t, pool, want); reg == nil {
			t.Fatalf("expected tiered table %s missing after chain", want)
		}
	}

	// Ledger holds exactly one row per chain step.
	var ledgerN int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM schema_migrations`).Scan(&ledgerN); err != nil {
		t.Fatalf("count ledger: %v", err)
	}
	if ledgerN != len(chain) {
		t.Fatalf("ledger row count=%d, want %d (one per chain step)", ledgerN, len(chain))
	}

	// Second boot: no-op, no error, and the legacy table is NOT recreated (this is the
	// D-GKA-G4-SEED-CLEANUP fix — pre-ledger this recreated it then dropped it again).
	if err := RunChain(ctx, pool); err != nil {
		t.Fatalf("RunChain (2nd boot): %v", err)
	}
	if reg := regclass(t, pool, "system_kind_attributes"); reg != nil {
		t.Fatalf("2nd boot recreated system_kind_attributes (=%q) — churn not eliminated", *reg)
	}
	var ledgerN2 int
	pool.QueryRow(ctx, `SELECT count(*) FROM schema_migrations`).Scan(&ledgerN2)
	if ledgerN2 != ledgerN {
		t.Fatalf("2nd boot changed ledger row count (%d → %d)", ledgerN, ledgerN2)
	}
}

// TestRunChain_Idempotent — three boots leave the system standards intact and error-free.
func TestRunChain_Idempotent(t *testing.T) {
	ctx := context.Background()
	pool := ephemeralDB(t, "glossary_ledger_idem")

	for i := range 3 {
		if err := RunChain(ctx, pool); err != nil {
			t.Fatalf("RunChain pass %d: %v", i+1, err)
		}
	}

	// The seeded SYSTEM standards survived three boots intact (seeds ledgered once;
	// 13 default kinds incl. 'unknown', the O3 genre vocabulary present).
	var kinds, genres int
	pool.QueryRow(ctx, `SELECT count(*) FROM system_kinds`).Scan(&kinds)
	if kinds < 13 {
		t.Fatalf("system_kinds=%d, want ≥13 default kinds", kinds)
	}
	pool.QueryRow(ctx, `SELECT count(*) FROM system_genres`).Scan(&genres)
	if genres < 7 {
		t.Fatalf("system_genres=%d, want ≥7 (universal + the genre vocabulary)", genres)
	}
}

// TestRunChain_TransitionPreservesData simulates the production transition: an EXISTING,
// already-migrated, already-cut-over DB that carries live data and is adopting the ledger
// for the FIRST time. It guards the data-loss-critical invariant — the G4 cutover's
// TRUNCATE must NOT re-fire on an already-cut-over DB, so entities survive the first
// ledgered boot. (Live-smoked once on the real dev DB; this is the repeatable CI guard.)
func TestRunChain_TransitionPreservesData(t *testing.T) {
	ctx := context.Background()
	pool := ephemeralDB(t, "glossary_ledger_transition")

	// 1) Bring the DB fully up via the normal chain → final tiered state, cutover done.
	if err := RunChain(ctx, pool); err != nil {
		t.Fatalf("RunChain (initial): %v", err)
	}

	// 2) Plant a live entity in the BOOK tier. That the FK accepts a book_kinds id also
	//    confirms the cutover repointed glossary_entities.kind_id off system_kinds.
	const book = "11111111-1111-1111-1111-111111111111"
	var bookKindID string
	if err := pool.QueryRow(ctx,
		`INSERT INTO book_kinds(book_id, code, name) VALUES ($1,'sentinel','Sentinel')
		 RETURNING book_kind_id`, book,
	).Scan(&bookKindID); err != nil {
		t.Fatalf("insert book_kind: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO glossary_entities(book_id, kind_id, short_description)
		 VALUES ($1,$2,'sentinel entity')`, book, bookKindID,
	); err != nil {
		t.Fatalf("insert sentinel entity: %v", err)
	}

	// 3) Simulate "already migrated but UN-LEDGERED" — drop the ledger. The DB now looks
	//    exactly like a pre-ledger dev/prod DB on its first boot of the new code.
	if _, err := pool.Exec(ctx, `DROP TABLE schema_migrations`); err != nil {
		t.Fatalf("drop ledger (simulate un-ledgered): %v", err)
	}

	// 4) Adopt the ledger: every step runs one idempotent pass. The cutover's TRUNCATE
	//    must be SKIPPED (old FK already gone) → the sentinel entity MUST survive.
	if err := RunChain(ctx, pool); err != nil {
		t.Fatalf("RunChain (transition): %v", err)
	}

	var n int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM glossary_entities`).Scan(&n); err != nil {
		t.Fatalf("count entities after transition: %v", err)
	}
	if n != 1 {
		t.Fatalf("DATA LOSS: entity count=%d after ledger adoption, want 1 (cutover TRUNCATE re-fired)", n)
	}
	var ledgerN int
	pool.QueryRow(ctx, `SELECT count(*) FROM schema_migrations`).Scan(&ledgerN)
	if ledgerN != len(chain) {
		t.Fatalf("ledger not fully repopulated after transition (=%d, want %d)", ledgerN, len(chain))
	}
	if reg := regclass(t, pool, "system_kind_attributes"); reg != nil {
		t.Fatalf("transition recreated system_kind_attributes (=%q)", *reg)
	}
}

// TestConsumedTokens_LedgerShapeAndSingleUse — 0030 creates the consumed_tokens table,
// UpConsumedTokens is idempotent, and the PK + ON CONFLICT DO NOTHING enforces single-use
// (a second insert of the same jti affects 0 rows — the C2 guarantee at the DDL level).
func TestConsumedTokens_LedgerShapeAndSingleUse(t *testing.T) {
	ctx := context.Background()
	pool := ephemeralDB(t, "glossary_consumed_tokens")

	if err := RunChain(ctx, pool); err != nil {
		t.Fatalf("RunChain: %v", err)
	}
	if reg := regclass(t, pool, "consumed_tokens"); reg == nil {
		t.Fatal("consumed_tokens table missing after chain")
	}
	// idempotent re-run
	if err := UpConsumedTokens(ctx, pool); err != nil {
		t.Fatalf("UpConsumedTokens (re-run): %v", err)
	}

	ins := `INSERT INTO consumed_tokens(jti, descriptor, exp) VALUES ('jti-1','book_delete', now()+interval '10 min')
	        ON CONFLICT (jti) DO NOTHING`
	tag, err := pool.Exec(ctx, ins)
	if err != nil {
		t.Fatalf("first claim: %v", err)
	}
	if tag.RowsAffected() != 1 {
		t.Fatalf("first claim should insert 1 row, got %d", tag.RowsAffected())
	}
	tag2, err := pool.Exec(ctx, ins)
	if err != nil {
		t.Fatalf("replay claim: %v", err)
	}
	if tag2.RowsAffected() != 0 {
		t.Fatalf("replay of the same jti must affect 0 rows (single-use), got %d", tag2.RowsAffected())
	}
}

// TestApplyOnce_SkipsApplied — a step runs exactly once even across repeated RunChain-
// style passes; a second ApplyOnce of the same name does not invoke fn again.
func TestApplyOnce_SkipsApplied(t *testing.T) {
	ctx := context.Background()
	pool := ephemeralDB(t, "glossary_ledger_applyonce")
	if err := EnsureLedger(ctx, pool); err != nil {
		t.Fatalf("EnsureLedger: %v", err)
	}

	runs := 0
	fn := func(context.Context, *pgxpool.Pool) error { runs++; return nil }

	for i := range 3 {
		if err := ApplyOnce(ctx, pool, "test_step", fn); err != nil {
			t.Fatalf("ApplyOnce pass %d: %v", i+1, err)
		}
	}
	if runs != 1 {
		t.Fatalf("fn ran %d times, want exactly 1", runs)
	}

	// A failing fn must NOT be recorded (so it retries next boot).
	wantErr := fmt.Errorf("boom")
	failFn := func(context.Context, *pgxpool.Pool) error { return wantErr }
	if err := ApplyOnce(ctx, pool, "failing_step", failFn); err == nil {
		t.Fatal("ApplyOnce swallowed a fn error")
	}
	var recorded bool
	pool.QueryRow(ctx, `SELECT EXISTS(SELECT 1 FROM schema_migrations WHERE name='failing_step')`).Scan(&recorded)
	if recorded {
		t.Fatal("a failed step was recorded in the ledger (must retry next boot)")
	}
}
