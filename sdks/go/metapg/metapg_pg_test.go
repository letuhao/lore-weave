package metapg_test

// PG-gated contract test for the pgx meta.DB driver: a real MetaWrite() through
// metapg must INSERT the data row AND the same-TX meta_write_audit row, honor
// CAS (ErrConcurrentStateTransition), and roll back atomically on a failed
// statement. Gated on METAPG_TEST_PG_URL (skips in the normal job); run against
// a throwaway pg (pg16 ok — no uuidv7 needed).

import (
	"context"
	"errors"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/sdks/go/metapg"
)

type realClock struct{}

func (realClock) NowUnixNano() int64 { return time.Now().UnixNano() }

type realUUID struct{}

func (realUUID) New() uuid.UUID { return uuid.New() }

// allowlist permitting the throwaway test table + meta_write_audit (no outbox).
const allowlistYAML = `
version: 1
entries:
  - table: metapg_test_t
  - table: meta_write_audit
`

func setup(t *testing.T) (*meta.Config, *pgxpool.Pool) {
	t.Helper()
	dsn := os.Getenv("METAPG_TEST_PG_URL")
	if dsn == "" {
		t.Skip("METAPG_TEST_PG_URL not set; skipping metapg PG contract test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	// meta_write_audit (013) + its scrub_version column (027, Slice A).
	for _, f := range []string{
		"../../../migrations/meta/013_meta_write_audit.up.sql",
		"../../../migrations/meta/027_meta_write_audit_scrub_version.up.sql",
	} {
		sql, err := os.ReadFile(f)
		if err != nil {
			t.Fatalf("read %s: %v", f, err)
		}
		if _, err := pool.Exec(ctx, string(sql)); err != nil {
			t.Fatalf("apply %s: %v", f, err)
		}
	}
	if _, err := pool.Exec(ctx, `CREATE TABLE IF NOT EXISTS metapg_test_t (id TEXT PRIMARY KEY, v TEXT NOT NULL, ver INT NOT NULL DEFAULT 0)`); err != nil {
		t.Fatalf("create test table: %v", err)
	}
	allow, err := meta.ParseAllowlist([]byte(allowlistYAML))
	if err != nil {
		t.Fatalf("allowlist: %v", err)
	}
	cfg := &meta.Config{
		DB:           metapg.New(pool),
		Allowlist:    allow,
		QueryBuilder: meta.PostgresQueryBuilder{},
		Clock:        realClock{},
		UUIDGen:      realUUID{},
	}
	return cfg, pool
}

func TestMetaWrite_InsertWritesDataAndAudit(t *testing.T) {
	cfg, pool := setup(t)
	ctx := context.Background()
	id := uuid.NewString()

	res, err := meta.MetaWrite(ctx, cfg, meta.MetaWriteIntent{
		Table:     "metapg_test_t",
		Operation: meta.OpInsert,
		PK:        map[string]any{"id": id},
		NewValues: map[string]any{"v": "hello"},
		Actor:     meta.Actor{Type: meta.ActorAdmin, ID: "tester"},
	})
	if err != nil {
		t.Fatalf("MetaWrite: %v", err)
	}
	if res.RowsAffected != 1 {
		t.Errorf("RowsAffected=%d", res.RowsAffected)
	}
	// Data row committed.
	var v string
	if err := pool.QueryRow(ctx, `SELECT v FROM metapg_test_t WHERE id=$1`, id).Scan(&v); err != nil || v != "hello" {
		t.Errorf("data row: v=%q err=%v", v, err)
	}
	// Same-TX meta_write_audit row committed.
	var n int
	if err := pool.QueryRow(ctx, `SELECT count(*) FROM meta_write_audit WHERE table_name='metapg_test_t' AND row_pk->>'id'=$1`, id).Scan(&n); err != nil || n != 1 {
		t.Errorf("audit row count=%d err=%v", n, err)
	}
}

func TestMetaWrite_CASMismatch(t *testing.T) {
	cfg, pool := setup(t)
	ctx := context.Background()
	id := uuid.NewString()
	if _, err := pool.Exec(ctx, `INSERT INTO metapg_test_t (id, v, ver) VALUES ($1,'a',1)`, id); err != nil {
		t.Fatalf("seed: %v", err)
	}
	// UPDATE with a non-matching ExpectedBefore → 0 rows → ErrConcurrentStateTransition.
	_, err := meta.MetaWrite(ctx, cfg, meta.MetaWriteIntent{
		Table:          "metapg_test_t",
		Operation:      meta.OpUpdate,
		PK:             map[string]any{"id": id},
		ExpectedBefore: map[string]any{"ver": 999}, // wrong
		NewValues:      map[string]any{"v": "b"},
		Actor:          meta.Actor{Type: meta.ActorAdmin, ID: "tester"},
	})
	if !errors.Is(err, meta.ErrConcurrentStateTransition) {
		t.Fatalf("expected ErrConcurrentStateTransition, got %v", err)
	}
}

func TestMetaWrite_RollbackOnError(t *testing.T) {
	cfg, pool := setup(t)
	ctx := context.Background()
	id := uuid.NewString()
	// Pre-insert so the MetaWrite INSERT hits a duplicate-PK error.
	if _, err := pool.Exec(ctx, `INSERT INTO metapg_test_t (id, v) VALUES ($1,'x')`, id); err != nil {
		t.Fatalf("seed: %v", err)
	}
	before := auditCount(t, pool)
	_, err := meta.MetaWrite(ctx, cfg, meta.MetaWriteIntent{
		Table:     "metapg_test_t",
		Operation: meta.OpInsert,
		PK:        map[string]any{"id": id}, // duplicate → exec error
		NewValues: map[string]any{"v": "dup"},
		Actor:     meta.Actor{Type: meta.ActorAdmin, ID: "tester"},
	})
	if err == nil {
		t.Fatal("expected duplicate-PK error")
	}
	// The whole TX rolled back: NO meta_write_audit row was added.
	if after := auditCount(t, pool); after != before {
		t.Errorf("audit rows changed on rollback: before=%d after=%d", before, after)
	}
}

func auditCount(t *testing.T, pool *pgxpool.Pool) int {
	t.Helper()
	var n int
	if err := pool.QueryRow(context.Background(), `SELECT count(*) FROM meta_write_audit WHERE table_name='metapg_test_t'`).Scan(&n); err != nil {
		t.Fatalf("audit count: %v", err)
	}
	return n
}
