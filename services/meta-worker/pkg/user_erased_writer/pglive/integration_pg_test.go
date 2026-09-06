package pglive_test

// End-to-end live-smoke for the 071 consumer (Slice 2): build the real Writer
// with the pglive adapters (+ MetaScrubber) against real PG, call Handle with a
// user.erased envelope, and assert the PII copy is scrubbed and that the meta
// scrub wrote a meta_write_audit row (MetaWrite self-audit).
// Gated on PIIKMS_TEST_PG_URL.
//
// It used to assert BOTH copies — the meta index AND a per-reality pc_projection
// it CREATEd itself. `0017` dropped that table and the per-reality scrub became a
// no-op, so that half was removed 2026-08-04. Worth noting how it would have
// aged otherwise: because the test built its own subject, it would have kept
// passing against a table that exists nowhere but inside this test.

import (
	"context"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/sdks/go/metapg"
	uew "github.com/loreweave/foundation/services/meta-worker/pkg/user_erased_writer"
	"github.com/loreweave/foundation/services/meta-worker/pkg/user_erased_writer/pglive"
)

type clk struct{}

func (clk) NowUnixNano() int64 { return time.Now().UnixNano() }

type uid struct{}

func (uid) New() uuid.UUID { return uuid.New() }

func TestLive_UserErasedConsumer_ScrubsBothPIICopies(t *testing.T) {
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping 071 consumer e2e")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)

	apply := func(path string) {
		sql, rerr := os.ReadFile(path)
		if rerr != nil {
			t.Fatalf("read %s: %v", path, rerr)
		}
		for range 5 {
			_, e := pool.Exec(ctx, string(sql))
			if e == nil || !strings.Contains(e.Error(), "deadlock") {
				if e != nil {
					t.Fatalf("apply %s: %v", path, e)
				}
				break
			}
			time.Sleep(50 * time.Millisecond)
		}
	}
	apply("../../../../../migrations/meta/034_actor_control_binding.up.sql")
	apply("../../../../../migrations/meta/013_meta_write_audit.up.sql")
	apply("../../../../../migrations/meta/027_meta_write_audit_scrub_version.up.sql")
	userA := uuid.New()
	reality := uuid.New()
	actorID := uuid.New()
	// The user->actor control binding — the only meta reference to this user.
	if _, e := pool.Exec(ctx,
		`INSERT INTO actor_control_binding (user_ref_id, reality_id, actor_id)
		 VALUES ($1,$2,$3)`, userA, reality, actorID); e != nil {
		t.Fatalf("seed actor binding: %v", e)
	}
	allow, err := meta.LoadAllowlist("../../../../../contracts/meta/events_allowlist.yaml")
	if err != nil {
		t.Fatalf("allowlist: %v", err)
	}
	mwCfg := &meta.Config{
		DB: metapg.New(pool), Allowlist: allow, QueryBuilder: meta.PostgresQueryBuilder{},
		Clock: clk{}, UUIDGen: uid{},
	}
	w, err := uew.New(uew.Config{
		Lookup:       pglive.NewPgUserRealityLookup(pool),
		DB:           pglive.NewPgPerRealityScrubber(func(_ uuid.UUID) (*pgxpool.Pool, error) { return pool, nil }),
		Audit:        pglive.LogAuditSink{},
		MetaScrubber: pglive.NewPgMetaScrubber(pool, mwCfg, "meta-worker"),
	})
	if err != nil {
		t.Fatalf("New writer: %v", err)
	}

	fields := map[string]any{
		"user_id":   userA.String(),
		"event_id":  uuid.New().String(),
		"erased_at": "2026-05-31T00:00:00Z",
	}
	if err := w.Handle(ctx, fields); err != nil {
		t.Fatalf("Handle: %v", err)
	}

	// The binding is GONE, not tombstoned. `actor_control_binding` holds no PII
	// to overwrite, so erasure owes removal of the reference itself — the
	// `@erasure_method: hard_delete` migration 034 declares.
	var left int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM actor_control_binding WHERE user_ref_id=$1`, userA).Scan(&left); err != nil {
		t.Fatalf("query actor bindings: %v", err)
	}
	if left != 0 {
		t.Errorf("actor_control_binding not erased: %d row(s) still name the user", left)
	}
	// ...and it went through MetaWrite, so it self-audited. Without this the
	// assertion above would also pass on a raw DELETE that bypassed the audit.
	var audits int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM meta_write_audit WHERE table_name='actor_control_binding'`).Scan(&audits); err != nil {
		t.Fatalf("count audit: %v", err)
	}
	if audits < 1 {
		t.Error("meta erasure must write a meta_write_audit row (MetaWrite self-audit)")
	}

	// Idempotent re-delivery: re-Handle is a no-op (no error).
	if err := w.Handle(ctx, fields); err != nil {
		t.Fatalf("idempotent re-Handle: %v", err)
	}
}
