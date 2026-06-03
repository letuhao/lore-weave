package audit_emitter

// PG-gated test for MetaWriteSink: maps Actions → real admin_action_audit rows
// (every migration-015 CHECK) via MetaWrite, with the same-TX meta_write_audit
// row. Gated on ADMINCLI_TEST_PG_URL (skips in the normal job); pg16 ok.

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
)

type tClock struct{}

func (tClock) NowUnixNano() int64 { return time.Now().UnixNano() }

type tUUID struct{}

func (tUUID) New() uuid.UUID { return uuid.New() }

const sinkAllowlist = `
version: 1
entries:
  - table: admin_action_audit
  - table: meta_write_audit
`

func sinkSetup(t *testing.T) (*MetaWriteSink, *pgxpool.Pool) {
	t.Helper()
	dsn := os.Getenv("ADMINCLI_TEST_PG_URL")
	if dsn == "" {
		t.Skip("ADMINCLI_TEST_PG_URL not set; skipping MetaWriteSink PG test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	for _, f := range []string{
		"../../../../migrations/meta/013_meta_write_audit.up.sql",
		"../../../../migrations/meta/015_admin_action_audit.up.sql",
		"../../../../migrations/meta/027_meta_write_audit_scrub_version.up.sql",
	} {
		sql, err := os.ReadFile(f)
		if err != nil {
			t.Fatalf("read %s: %v", f, err)
		}
		if _, err := pool.Exec(ctx, string(sql)); err != nil {
			t.Fatalf("apply %s: %v", f, err)
		}
	}
	allow, err := meta.ParseAllowlist([]byte(sinkAllowlist))
	if err != nil {
		t.Fatalf("allowlist: %v", err)
	}
	cfg := &meta.Config{
		DB: metapg.New(pool), Allowlist: allow, QueryBuilder: meta.PostgresQueryBuilder{},
		Clock: tClock{}, UUIDGen: tUUID{}, Scrubber: meta.NewRegexScrubber(nil),
	}
	return NewMetaWriteSink(cfg), pool
}

func countAdmin(t *testing.T, pool *pgxpool.Pool, actorID uuid.UUID) (n int, resultKind string) {
	t.Helper()
	rows, _ := pool.Query(context.Background(),
		`SELECT result_kind FROM admin_action_audit WHERE actor_id=$1`, actorID)
	defer rows.Close()
	for rows.Next() {
		var rk string
		_ = rows.Scan(&rk)
		resultKind = rk
		n++
	}
	return n, resultKind
}

func TestSink_SuccessRow(t *testing.T) {
	sink, pool := sinkSetup(t)
	actor := uuid.New()
	if err := sink.Write(context.Background(), Action{
		CommandName: "reality status", Actor: actor.String(), ActorRole: "sre",
		ParamsHash: "abc123", Outcome: "succeeded",
	}); err != nil {
		t.Fatalf("Write: %v", err)
	}
	n, rk := countAdmin(t, pool, actor)
	if n != 1 || rk != "success" {
		t.Errorf("got n=%d result_kind=%q, want 1/success", n, rk)
	}
}

func TestSink_DryRunRow(t *testing.T) {
	sink, pool := sinkSetup(t)
	actor := uuid.New()
	_ = sink.Write(context.Background(), Action{CommandName: "c", Actor: actor.String(), Outcome: "succeeded", DryRun: true})
	if n, rk := countAdmin(t, pool, actor); n != 1 || rk != "dry_run" {
		t.Errorf("got n=%d rk=%q want 1/dry_run", n, rk)
	}
}

func TestSink_ErrorRow_ScrubberQuad(t *testing.T) {
	sink, pool := sinkSetup(t)
	actor := uuid.New()
	// 099: pass the RAW error (incl. PII) — the Sink scrubs it into the row.
	if err := sink.Write(context.Background(), Action{
		CommandName: "reality rebuild", Actor: actor.String(), Outcome: "failed",
		ErrorDetailRaw: "rebuild failed for user test@example.com",
	}); err != nil {
		t.Fatalf("Write: %v", err)
	}
	n, rk := countAdmin(t, pool, actor)
	if n != 1 || rk != "error" {
		t.Fatalf("got n=%d rk=%q want 1/error", n, rk)
	}
	// Scrubber-quad fully populated (the 015 error_kind_has_scrubber + quad CHECKs).
	var rawHashLen int
	var scrubbed, scrubVer string
	if err := pool.QueryRow(context.Background(),
		`SELECT length(error_detail_raw_hash), error_detail_scrubbed, scrub_version FROM admin_action_audit WHERE actor_id=$1`,
		actor).Scan(&rawHashLen, &scrubbed, &scrubVer); err != nil {
		t.Fatalf("read quad: %v", err)
	}
	if rawHashLen != 32 || scrubVer == "" {
		t.Errorf("scrubber-quad wrong: hashlen=%d ver=%q", rawHashLen, scrubVer)
	}
	// 099: REAL scrubber-rewritten text retained (not a hash-only sentinel) +
	// PII redacted out of it.
	if strings.Contains(scrubbed, "test@example.com") {
		t.Errorf("raw PII email leaked into error_detail_scrubbed: %q", scrubbed)
	}
	if !strings.Contains(scrubbed, "rebuild failed") {
		t.Errorf("scrubbed text should retain the non-PII error context, got %q", scrubbed)
	}
}

// 098: a started row for a NON-destructive command is skipped (avoids doubling
// low-value read/informational audit volume).
func TestSink_StartedNonDestructiveSkipped(t *testing.T) {
	sink, pool := sinkSetup(t)
	actor := uuid.New()
	if err := sink.Write(context.Background(), Action{
		CommandName: "reality stats", Actor: actor.String(), Outcome: "started",
		ImpactClass: "tier-3-informational",
	}); err != nil {
		t.Fatalf("Write started: %v", err)
	}
	if n, _ := countAdmin(t, pool, actor); n != 0 {
		t.Errorf("non-destructive started must NOT persist a row; got %d", n)
	}
}

// 098: a started row for a destructive command IS persisted (forensic trace for
// a crash between Before and the terminal hook).
func TestSink_StartedDestructivePersisted(t *testing.T) {
	sink, pool := sinkSetup(t)
	actor := uuid.New()
	if err := sink.Write(context.Background(), Action{
		CommandName: "reality rebuild-projection", Actor: actor.String(),
		Outcome: "started", ImpactClass: impactTier1Destructive,
	}); err != nil {
		t.Fatalf("Write started destructive: %v", err)
	}
	if n, rk := countAdmin(t, pool, actor); n != 1 || rk != "started" {
		t.Errorf("destructive started must persist as 'started'; got n=%d rk=%q", n, rk)
	}
}

func TestSink_NonUUIDActorRejected(t *testing.T) {
	sink, _ := sinkSetup(t)
	err := sink.Write(context.Background(), Action{CommandName: "c", Actor: "ops1", Outcome: "succeeded"})
	if err == nil {
		t.Fatal("expected non-UUID actor to be rejected")
	}
}
