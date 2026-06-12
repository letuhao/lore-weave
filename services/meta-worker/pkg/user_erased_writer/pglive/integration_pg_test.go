package pglive_test

// End-to-end live-smoke for the 071 consumer (Slice 2): build the real Writer
// with the pglive adapters (+ MetaScrubber) against real PG, call Handle with a
// user.erased envelope, and assert BOTH PII copies are scrubbed — the
// per-reality pc_projection AND the meta player_character_index.pc_name — and
// that the meta scrub wrote a meta_write_audit row (MetaWrite self-audit).
// Gated on PIIKMS_TEST_PG_URL.

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
	apply("../../../../../migrations/meta/012_player_character_index.up.sql")
	apply("../../../../../migrations/meta/013_meta_write_audit.up.sql")
	apply("../../../../../migrations/meta/027_meta_write_audit_scrub_version.up.sql")
	if _, e := pool.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS pc_projection (
			pc_id UUID PRIMARY KEY, user_id UUID NOT NULL, name TEXT NOT NULL,
			status TEXT NOT NULL DEFAULT 'active',
			CONSTRAINT pc_projection_status_valid CHECK (status IN ('active','inactive','deleted')))`); e != nil {
		t.Fatalf("create pc_projection: %v", e)
	}

	userA := uuid.New()
	reality := uuid.New()
	pcID := uuid.New()
	// Meta index row (the cross-reality PII copy).
	if _, e := pool.Exec(ctx,
		`INSERT INTO player_character_index (pc_index_id, user_ref_id, reality_id, pc_id, pc_name, status)
		 VALUES ($1,$2,$3,$4,'Alice','active')`, uuid.New(), userA, reality, pcID); e != nil {
		t.Fatalf("seed pc index: %v", e)
	}
	// Per-reality projection row (the projection PII copy).
	if _, e := pool.Exec(ctx,
		`INSERT INTO pc_projection (pc_id, user_id, name, status) VALUES ($1,$2,'Alice','active')`, pcID, userA); e != nil {
		t.Fatalf("seed pc_projection: %v", e)
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

	// Per-reality projection scrubbed.
	var pName, pStatus string
	if err := pool.QueryRow(ctx, `SELECT name, status FROM pc_projection WHERE pc_id=$1`, pcID).Scan(&pName, &pStatus); err != nil {
		t.Fatalf("query pc_projection: %v", err)
	}
	if pName != "[erased]" || pStatus != "deleted" {
		t.Errorf("pc_projection not scrubbed: name=%q status=%q", pName, pStatus)
	}
	// Meta index scrubbed (the 2nd PII copy).
	var iName, iStatus string
	if err := pool.QueryRow(ctx, `SELECT pc_name, status FROM player_character_index WHERE user_ref_id=$1`, userA).Scan(&iName, &iStatus); err != nil {
		t.Fatalf("query pc index: %v", err)
	}
	if iName != "[erased]" || iStatus != "deleted" {
		t.Errorf("player_character_index not scrubbed: pc_name=%q status=%q", iName, iStatus)
	}
	// The meta scrub self-audited via MetaWrite.
	var audits int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM meta_write_audit WHERE table_name='player_character_index'`).Scan(&audits); err != nil {
		t.Fatalf("count audit: %v", err)
	}
	if audits < 1 {
		t.Error("meta scrub must write a meta_write_audit row (MetaWrite self-audit)")
	}

	// Idempotent re-delivery: re-Handle is a no-op (no error).
	if err := w.Handle(ctx, fields); err != nil {
		t.Fatalf("idempotent re-Handle: %v", err)
	}
}
