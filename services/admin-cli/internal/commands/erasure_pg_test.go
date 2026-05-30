package commands

// PG-gated live-smoke for the erasure orchestrator's production drivers
// (PgConsentRevoker + PgBalanceReader) against a real Postgres. Gated on
// PIIKMS_TEST_PG_URL (skips in the normal job; run against infra/foundation-dev).
//
// Closes /review-impl finding #3: proves the consent-revoke MetaWrite path
// (with the migration-fixed `revoked_at IS NULL` CAS) actually lands +
// idempotently skips a re-revoke, and that the cost-ledger proxy sums correctly.
// MetaWrite runs with Outbox=nil (the platform-wide state today), so the
// user.consent.revoked event is intentionally not emitted — the revoked_at row
// state is the SSOT this test asserts.

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/sdks/go/metapg"
)

type testClock struct{}

func (testClock) NowUnixNano() int64 { return time.Now().UnixNano() }

type testUUID struct{}

func (testUUID) New() uuid.UUID { return uuid.New() }

// commandsPGEnv opens the test pool, applies the meta migrations the consent +
// cost paths need, and builds a MetaWrite Config wired to the real allowlist.
func commandsPGEnv(t *testing.T) (*pgxpool.Pool, *meta.Config) {
	t.Helper()
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping commands PG live-smoke")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	for _, f := range []string{
		"../../../../migrations/meta/011_user_consent_ledger.up.sql",
		"../../../../migrations/meta/013_meta_write_audit.up.sql",
		"../../../../migrations/meta/027_meta_write_audit_scrub_version.up.sql",
		"../../../../migrations/meta/018_user_cost_ledger.up.sql",
	} {
		sql, err := os.ReadFile(f)
		if err != nil {
			t.Fatalf("read %s: %v", f, err)
		}
		if _, err := pool.Exec(ctx, string(sql)); err != nil {
			t.Fatalf("apply %s: %v", f, err)
		}
	}
	allow, err := meta.LoadAllowlist("../../../../contracts/meta/events_allowlist.yaml")
	if err != nil {
		t.Fatalf("load allowlist: %v", err)
	}
	cfg := &meta.Config{
		DB: metapg.New(pool), Allowlist: allow, QueryBuilder: meta.PostgresQueryBuilder{},
		Clock: testClock{}, UUIDGen: testUUID{}, Scrubber: meta.NewRegexScrubber(nil),
		// Outbox intentionally nil: matches the platform-wide state (no appender
		// wired). The user_consent_ledger UPDATE's allowlisted event is skipped.
	}
	return pool, cfg
}

func seedConsent(t *testing.T, pool *pgxpool.Pool, user uuid.UUID, scope, version string, revoked bool) {
	t.Helper()
	q := `INSERT INTO user_consent_ledger (user_ref_id, consent_scope, scope_version, granted_at)
	      VALUES ($1, $2, $3, now() - interval '1 day')`
	if revoked {
		q = `INSERT INTO user_consent_ledger (user_ref_id, consent_scope, scope_version, granted_at, revoked_at, revoke_reason)
		     VALUES ($1, $2, $3, now() - interval '1 day', now(), 'pre-revoked')`
	}
	if _, err := pool.Exec(context.Background(), q, user, scope, version); err != nil {
		t.Fatalf("seed consent %s/%s: %v", scope, version, err)
	}
}

func TestLive_PgConsentRevoker_RevokeAndIdempotent(t *testing.T) {
	pool, cfg := commandsPGEnv(t)
	ctx := context.Background()
	user := uuid.New()
	// 2 active scopes + 1 already-revoked.
	seedConsent(t, pool, user, "core_service", "v1", false)
	seedConsent(t, pool, user, "byok_telemetry", "v1", false)
	seedConsent(t, pool, user, "marketing_comms", "v1", true)

	r := NewPgConsentRevoker(pool, cfg, "op-admin", time.Now)

	// ActiveScopes must return only the 2 unrevoked.
	active, err := r.ActiveScopes(ctx, user)
	if err != nil {
		t.Fatalf("ActiveScopes: %v", err)
	}
	if len(active) != 2 {
		t.Fatalf("expected 2 active scopes, got %d: %+v", len(active), active)
	}

	// First revoke of an active scope → not already-revoked.
	already, err := r.RevokeScope(ctx, user, ConsentScope{"core_service", "v1"}, "gdpr erasure")
	if err != nil {
		t.Fatalf("RevokeScope: %v", err)
	}
	if already {
		t.Fatal("first revoke of an active scope must report alreadyRevoked=false")
	}

	// Re-revoke the SAME scope → IS NULL CAS matches 0 rows → idempotent skip.
	already, err = r.RevokeScope(ctx, user, ConsentScope{"core_service", "v1"}, "gdpr erasure")
	if err != nil {
		t.Fatalf("re-RevokeScope: %v", err)
	}
	if !already {
		t.Fatal("re-revoke of an already-revoked scope must report alreadyRevoked=true (IS NULL CAS)")
	}

	// The row is genuinely revoked in the DB (the SSOT).
	var revoked bool
	if err := pool.QueryRow(ctx,
		`SELECT revoked_at IS NOT NULL FROM user_consent_ledger
		  WHERE user_ref_id=$1 AND consent_scope='core_service' AND scope_version='v1'`, user).Scan(&revoked); err != nil {
		t.Fatalf("query revoked_at: %v", err)
	}
	if !revoked {
		t.Error("core_service/v1 should be revoked in the DB")
	}

	// One active scope remains (byok_telemetry).
	active, err = r.ActiveScopes(ctx, user)
	if err != nil {
		t.Fatalf("ActiveScopes after revoke: %v", err)
	}
	if len(active) != 1 || active[0].Scope != "byok_telemetry" {
		t.Fatalf("expected only byok_telemetry active, got %+v", active)
	}
}

func TestLive_PgBalanceReader_Summary(t *testing.T) {
	pool, _ := commandsPGEnv(t)
	ctx := context.Background()
	user := uuid.New()
	ins := func(reason string, cost int64) {
		orig := "NULL"
		if reason != "charge" {
			orig = "'" + uuid.NewString() + "'"
		}
		_, err := pool.Exec(ctx,
			`INSERT INTO user_cost_ledger
			   (ledger_id, user_ref_id, provider_id, model_id, cost_micro_usd, tier, reason, original_ledger_id, created_at_nanos)
			 VALUES ($1,$2,'openai','gpt',$3,'paid',$4,`+orig+`,$5)`,
			uuid.New(), user, cost, reason, time.Now().UnixNano())
		if err != nil {
			t.Fatalf("insert cost row (%s): %v", reason, err)
		}
	}
	ins("charge", 1000)
	ins("charge", 500)
	ins("refund", 300) // subtracted

	b := NewPgBalanceReader(pool)
	rows, net, err := b.CostLedgerSummary(ctx, user)
	if err != nil {
		t.Fatalf("CostLedgerSummary: %v", err)
	}
	if rows != 3 {
		t.Errorf("rows=%d, want 3", rows)
	}
	if net != 1200 { // 1000 + 500 - 300
		t.Errorf("net=%d, want 1200 (lifetime cost proxy, refund subtracted)", net)
	}
}
