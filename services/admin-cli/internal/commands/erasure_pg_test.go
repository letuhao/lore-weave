package commands

// PG-gated live-smoke for the erasure orchestrator's production drivers
// (PgConsentRevoker + PgBalanceReader) against a real Postgres. Gated on
// PIIKMS_TEST_PG_URL (skips in the normal job; run against infra/foundation-dev).
//
// Proves the consent-revoke MetaWrite path (with the migration-fixed
// `revoked_at IS NULL` CAS) actually lands + idempotently skips a re-revoke,
// and that the cost-ledger proxy sums correctly. These two tests use Outbox=nil
// to isolate the CAS/idempotency behaviour from event emission; the WIRED
// outbox path (P2/101 — RevokeScope with a real appender emits
// user.consent.revoked into meta_outbox) is covered separately by
// TestLive_PgConsentRevoker_EmitsOutboxEvent below.

import (
	"context"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/sdks/go/metaoutbox"
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
		// Outbox left nil HERE to isolate the CAS/idempotency tests from event
		// emission; the wired path is exercised by TestLive_PgConsentRevoker_EmitsOutboxEvent.
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

// TestLive_PgConsentRevoker_EmitsOutboxEvent proves the WIRED producer path
// (P2/101 /review-impl #2): RevokeScope with a real meta-outbox appender set on
// cfg.Outbox emits a user.consent.revoked row into meta_outbox in the SAME TX as
// the data write — i.e. the headline 101 claim, exercised through the real
// PgConsentRevoker → MetaWrite → appender chain (not the appender in isolation).
func TestLive_PgConsentRevoker_EmitsOutboxEvent(t *testing.T) {
	pool, cfg := commandsPGEnv(t)
	ctx := context.Background()

	// commandsPGEnv applies the consent + audit migrations; add meta_outbox (030).
	sql, err := os.ReadFile("../../../../migrations/meta/030_meta_outbox.up.sql")
	if err != nil {
		t.Fatalf("read 030: %v", err)
	}
	if _, err := pool.Exec(ctx, string(sql)); err != nil {
		t.Fatalf("apply 030: %v", err)
	}

	// Wire a real appender (with the allowlist's xreality topics) — exactly as
	// buildErasureHandler does in production.
	topics, err := meta.LoadXRealityTopics("../../../../contracts/meta/events_allowlist.yaml")
	if err != nil {
		t.Fatalf("load xreality topics: %v", err)
	}
	cfg.Outbox = metaoutbox.New(topics)

	user := uuid.New()
	seedConsent(t, pool, user, "core_service", "v1", false)

	r := NewPgConsentRevoker(pool, cfg, "op-admin", time.Now)
	already, err := r.RevokeScope(ctx, user, ConsentScope{"core_service", "v1"}, "gdpr erasure")
	if err != nil {
		t.Fatalf("RevokeScope: %v", err)
	}
	if already {
		t.Fatal("first revoke must report alreadyRevoked=false")
	}

	// Assert exactly one meta_outbox row named user.consent.revoked for this user.
	var (
		count     int
		eventName string
		published bool
	)
	if err := pool.QueryRow(ctx,
		`SELECT count(*), max(event_name), bool_or(published)
		   FROM meta_outbox
		  WHERE event_name = 'user.consent.revoked' AND aggregate_id LIKE '%' || $1 || '%'`,
		user.String()).Scan(&count, &eventName, &published); err != nil {
		t.Fatalf("query meta_outbox: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected exactly 1 user.consent.revoked meta_outbox row for the user, got %d", count)
	}
	if eventName != "user.consent.revoked" {
		t.Errorf("event_name = %q, want user.consent.revoked", eventName)
	}
	if published {
		t.Error("a freshly-emitted meta_outbox row must be unpublished (the relay drains it)")
	}

	// A meta-only event (no per-reality consumer) ⇒ xreality_topic must be NULL.
	var xtopic *string
	if err := pool.QueryRow(ctx,
		`SELECT xreality_topic FROM meta_outbox
		  WHERE event_name='user.consent.revoked' AND aggregate_id LIKE '%' || $1 || '%'`,
		user.String()).Scan(&xtopic); err != nil {
		t.Fatalf("query xreality_topic: %v", err)
	}
	if xtopic != nil {
		t.Errorf("user.consent.revoked is meta-only; xreality_topic must be NULL, got %q", *xtopic)
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
