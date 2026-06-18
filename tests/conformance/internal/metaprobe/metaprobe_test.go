// Package metaprobe is the S4 I9 live probe: it drives the REAL
// contracts/meta.AttemptStateTransition against a real Postgres meta DB and
// asserts the transition-graph + CAS semantics that a SQL CHECK cannot model
// (which is why the plan committed to a Go probe, not a SQL fallback).
//
// Run as the conformance catalog's `meta-lifecycle-cas` go-test case via
// `go test -C tests/conformance` (go on the runner's PATH; no shell). The case
// is gated requires:[foundation-stack], so the runner only executes it when PG
// is up; a manual run without PG skips.
package metaprobe

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"runtime"
	"sort"
	"testing"
	"time"

	_ "github.com/lib/pq"

	"github.com/google/uuid"
	meta "github.com/loreweave/foundation/contracts/meta"
)

// --- real meta.DB / meta.Tx adapters over *sql.DB (the only wiring the library
// leaves to the caller; everything else — PostgresQueryBuilder, LoadTransitions,
// LoadAllowlist — is shipped). ---

type pgDB struct{ db *sql.DB }

func (p pgDB) BeginTx(ctx context.Context) (meta.Tx, func() error, func() error, error) {
	tx, err := p.db.BeginTx(ctx, nil)
	if err != nil {
		return nil, nil, nil, err
	}
	return pgTx{tx}, tx.Commit, tx.Rollback, nil
}

type pgTx struct{ tx *sql.Tx }

func (t pgTx) Exec(ctx context.Context, q string, args ...any) (int64, error) {
	r, err := t.tx.ExecContext(ctx, q, args...)
	if err != nil {
		return 0, err
	}
	return r.RowsAffected()
}

type realClock struct{}

func (realClock) NowUnixNano() int64 { return time.Now().UnixNano() }

type realUUID struct{}

func (realUUID) New() uuid.UUID { return uuid.New() }

func repoRoot() string {
	_, file, _, _ := runtime.Caller(0) // .../tests/conformance/internal/metaprobe/metaprobe_test.go
	return filepath.Clean(filepath.Join(filepath.Dir(file), "..", "..", "..", ".."))
}

func pgPort() string {
	if v := os.Getenv("FOUNDATION_PG_PORT"); v != "" {
		return v
	}
	return "55432"
}

func dsn(dbname string) string {
	return fmt.Sprintf("postgres://foundation:foundation@127.0.0.1:%s/%s?sslmode=disable", pgPort(), dbname)
}

func TestS4MetaLifecycleCAS(t *testing.T) {
	ctx := context.Background()
	root := repoRoot()

	// Connect to the maintenance DB to (re)create a throwaway meta DB. A failure
	// here = PG not reachable → skip (the catalog's requires:[foundation-stack]
	// gates the runner; this skip only matters for a manual no-stack run).
	base, err := sql.Open("postgres", dsn("foundation"))
	if err != nil {
		t.Skipf("open base DSN: %v", err)
	}
	defer base.Close()
	if err := base.PingContext(ctx); err != nil {
		t.Skipf("foundation Postgres not reachable on port %s: %v", pgPort(), err)
	}
	const probeDB = "meta_lifecycle_check"
	if _, err := base.ExecContext(ctx, "DROP DATABASE IF EXISTS "+probeDB); err != nil {
		t.Fatalf("drop %s: %v", probeDB, err)
	}
	if _, err := base.ExecContext(ctx, "CREATE DATABASE "+probeDB); err != nil {
		t.Fatalf("create %s: %v", probeDB, err)
	}

	db, err := sql.Open("postgres", dsn(probeDB))
	if err != nil {
		t.Fatalf("open probe DSN: %v", err)
	}
	defer db.Close()

	// Apply every meta migration via db.Exec (the lib/pq simple-query path handles
	// the dollar-quoted DO blocks + generated columns). This matches the repo's
	// canonical migration style (services apply schema via db.Exec/pgx plain SQL,
	// e.g. auth-service), so it is faithful — but it assumes meta migrations stay
	// psql-metacommand-free (no \-commands / COPY FROM STDIN); that holds repo-wide.
	files, err := filepath.Glob(filepath.Join(root, "migrations", "meta", "*.up.sql"))
	if err != nil || len(files) == 0 {
		t.Fatalf("glob meta migrations under %s: %v (n=%d)", root, err, len(files))
	}
	sort.Strings(files)
	for _, f := range files {
		raw, err := os.ReadFile(f)
		if err != nil {
			t.Fatalf("read %s: %v", f, err)
		}
		if _, err := db.ExecContext(ctx, string(raw)); err != nil {
			t.Fatalf("apply %s: %v", filepath.Base(f), err)
		}
	}

	// Seed a reality_registry row in 'active' (the CAS target).
	const rid = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
	if _, err := db.ExecContext(ctx, `
		INSERT INTO reality_registry
			(reality_id, db_host, db_name, status, locale,
			 session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
		VALUES ($1, 'pg-shard-1.internal', 'reality_probe', 'active', 'en', 10, 10, 20, 5)`, rid); err != nil {
		t.Fatalf("seed reality_registry: %v", err)
	}

	allow, err := meta.LoadAllowlist(filepath.Join(root, "contracts", "meta", "events_allowlist.yaml"))
	if err != nil {
		t.Fatalf("load allowlist: %v", err)
	}
	graph, err := meta.LoadTransitions(filepath.Join(root, "contracts", "meta", "transitions.yaml"))
	if err != nil {
		t.Fatalf("load transitions: %v", err)
	}
	cfg := &meta.Config{
		DB:           pgDB{db},
		Allowlist:    allow,
		Transitions:  graph,
		QueryBuilder: meta.PostgresQueryBuilder{},
		Clock:        realClock{},
		UUIDGen:      realUUID{},
	}
	attempt := func(from, to string) error {
		_, err := meta.AttemptStateTransition(ctx, cfg, meta.TransitionRequest{
			ResourceType: "reality",
			ResourceID:   rid,
			FromState:    from,
			ToState:      to,
			Reason:       "s4 metaprobe",
			// actor_id is UUID in lifecycle_transition_audit (the fake-DB unit
			// tests used non-UUID strings — a mock-only gap this live probe caught).
			Actor: meta.Actor{Type: meta.ActorSystem, ID: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"},
		})
		return err
	}

	// (a) legal edge: active → pending_close succeeds (CAS matches the active row).
	if err := attempt("active", "pending_close"); err != nil {
		t.Fatalf("I9 legal transition active→pending_close failed: %v", err)
	}
	var got string
	if err := db.QueryRowContext(ctx, "SELECT status FROM reality_registry WHERE reality_id=$1", rid).Scan(&got); err != nil {
		t.Fatalf("read back status: %v", err)
	}
	if got != "pending_close" {
		t.Fatalf("I9: status not advanced; got %q want pending_close", got)
	}

	// (b) illegal edge: active → archived is not adjacent in the graph → rejected
	// BEFORE any DB write (the graph guard, which a SQL CHECK cannot express).
	if err := attempt("active", "archived"); !errors.Is(err, meta.ErrInvalidTransition) {
		t.Fatalf("I9 illegal transition: want ErrInvalidTransition, got %v", err)
	}

	// (c) stale CAS: replay active→pending_close — the edge is legal, but the row
	// is now 'pending_close', so the CAS (WHERE status='active') matches 0 rows →
	// ErrConcurrentStateTransition. This is the optimistic-concurrency guard.
	if err := attempt("active", "pending_close"); !errors.Is(err, meta.ErrConcurrentStateTransition) {
		t.Fatalf("I9 stale CAS: want ErrConcurrentStateTransition, got %v", err)
	}
}
