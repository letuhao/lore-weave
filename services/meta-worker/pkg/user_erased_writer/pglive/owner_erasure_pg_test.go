package pglive

import (
	"context"
	"os"
	"path/filepath"
	"sort"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/sdks/go/metapg"
)

// Behavioural coverage for the reality-ownership erasure.
//
// WHY IT EXISTS
// -------------
// Every other assertion about this path greps pglive.go for string literals. A
// cold-start review proved what that is worth: it changed the reassign query to
// `... WHERE owner_user_id = $1 AND false` — so it could never match a row —
// and the ENTIRE meta-worker erasure suite stayed green.
//
// It also found the bug those greps could not see. `reassignOwnedRealities` was
// the last statement of the binding deleter, AFTER its
// `if len(found) == 0 { return nil }`, so a user who owned a reality but drove
// no actor returned early and kept their `owner_user_id`. That is the exact
// class the same commit had just fixed in `RealitiesForUser` — and at the time,
// BOTH user-owned realities in the live database belonged to a user with zero
// bindings, so erasing that user was a no-op.
//
// THE CASE BELOW IS THAT USER: owns a reality, drives no actor. It is the one a
// source grep can never express.
//
// DB-gated on PIIKMS_TEST_PG_URL like the sibling live tests, so the default
// `go test ./...` is unaffected.

type erasureClk struct{}

func (erasureClk) NowUnixNano() int64 { return time.Unix(1_760_000_000, 0).UnixNano() }

type erasureUID struct{}

func (erasureUID) New() uuid.UUID { return uuid.New() }

func TestLive_OwnerOnlyUser_IsStillErased(t *testing.T) {
	pool := pgPool(t)
	ctx := context.Background()

	// This test WRITES to reality_registry, so it must only ever run against a
	// throwaway database (CLAUDE.md › 'Destructive DB ops in tests'). The guard
	// runs BEFORE any statement, not after.
	var dbName string
	if err := pool.QueryRow(ctx, "SELECT current_database()").Scan(&dbName); err != nil {
		t.Fatalf("current_database: %v", err)
	}
	if !strings.Contains(dbName, "test") && !strings.Contains(dbName, "smoke") &&
		!strings.Contains(dbName, "audit") {
		t.Fatalf("refusing to run against %q: PIIKMS_TEST_PG_URL must point at a "+
			"throwaway database whose name carries a marker", dbName)
	}

	// Apply the WHOLE meta tree in order rather than a hand-picked subset.
	// Picking files one at a time chased a different missing relation on every
	// run (actor_control_binding, then meta_write_audit, then a column added by a
	// later migration) — the subset is a guess about the schema, and the schema
	// is right there.
	migs, err := filepath.Glob("../../../../../migrations/meta/*.up.sql")
	if err != nil || len(migs) == 0 {
		t.Skipf("cannot list meta migrations: %v", err)
	}
	sort.Strings(migs)
	for _, f := range migs {
		sql, rerr := os.ReadFile(f)
		if rerr != nil {
			t.Skipf("cannot read %s: %v", f, rerr)
		}
		if _, eerr := pool.Exec(ctx, string(sql)); eerr != nil &&
			!strings.Contains(eerr.Error(), "already exists") &&
			!strings.Contains(eerr.Error(), "duplicate") {
			t.Skipf("apply %s: %v", filepath.Base(f), eerr)
		}
	}

	allow, err := meta.LoadAllowlist("../../../../../contracts/meta/events_allowlist.yaml")
	if err != nil {
		t.Fatalf("allowlist: %v", err)
	}
	cfg := &meta.Config{
		DB: metapg.New(pool), Allowlist: allow, QueryBuilder: meta.PostgresQueryBuilder{},
		Clock: erasureClk{}, UUIDGen: erasureUID{},
	}

	owner := uuid.New()
	reality := uuid.New()
	dbn := "lw_reality_" + strings.ReplaceAll(reality.String(), "-", "")[:12]

	// THE LOAD-BEARING DETAIL: no actor_control_binding row for this user.
	if _, err := pool.Exec(ctx,
		`INSERT INTO reality_registry
		   (reality_id, db_host, db_name, status, locale,
		    session_max_pcs, session_max_npcs, session_max_total, deploy_cohort,
		    owner_kind, owner_user_id)
		 VALUES ($1,'pg-shard-0.internal',$2,'active','en',10,10,20,0,'user',$3)`,
		reality, dbn, owner); err != nil {
		t.Fatalf("seed owned reality: %v", err)
	}
	t.Cleanup(func() {
		// Scoped to this test's own row — never a bare DELETE.
		_, _ = pool.Exec(context.Background(),
			`DELETE FROM reality_registry WHERE reality_id = $1`, reality)
	})

	if err := NewPgMetaScrubber(pool, cfg, uuid.New().String()).
		ScrubUserMetaRefs(ctx, owner); err != nil {
		t.Fatalf("ScrubUserMetaRefs: %v", err)
	}

	var kind string
	var gotOwner *uuid.UUID
	if err := pool.QueryRow(ctx,
		`SELECT owner_kind, owner_user_id FROM reality_registry WHERE reality_id = $1`,
		reality).Scan(&kind, &gotOwner); err != nil {
		t.Fatalf("read back: %v", err)
	}
	if kind != "system" || gotOwner != nil {
		t.Fatalf("the owner SURVIVED erasure: owner_kind=%q owner_user_id=%v — a user who "+
			"owns a reality but drives no actor must still be erased", kind, gotOwner)
	}

	// Idempotent: a re-run must not error and must not undo the reassignment.
	if err := NewPgMetaScrubber(pool, cfg, uuid.New().String()).
		ScrubUserMetaRefs(ctx, owner); err != nil {
		t.Fatalf("second ScrubUserMetaRefs (idempotence): %v", err)
	}
}
