package piikms

// PG-gated test for PgKEKManager.DestroyKEK — the security-critical SQL +
// WARN-1/2 co-tenant guard. Gated on PIIKMS_TEST_PG_URL (skips in the normal
// job); run against a throwaway pg (e.g. infra/foundation-dev). Uses the
// faithful fake KMS so ScheduleKeyDeletion calls are deterministically
// inspectable.

import (
	"context"
	"errors"
	"os"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
	"github.com/loreweave/foundation/sdks/go/metaoutbox"
	"github.com/loreweave/foundation/sdks/go/metapg"
)

type kekTestClock struct{}

func (kekTestClock) NowUnixNano() int64 { return time.Now().UnixNano() }

type kekTestUUID struct{}

func (kekTestUUID) New() uuid.UUID { return uuid.New() }

// kekPGEnv opens the pool, applies the migrations DestroyKEK-via-MetaWrite needs
// (pii tables + meta_write_audit + meta_outbox), and builds the Outbox-wired
// MetaWrite Config (P2/113) so the shred emits a real user.erased row.
func kekPGEnv(t *testing.T) (*pgxpool.Pool, *meta.Config) {
	t.Helper()
	dsn := os.Getenv("PIIKMS_TEST_PG_URL")
	if dsn == "" {
		t.Skip("PIIKMS_TEST_PG_URL not set; skipping PgKEKManager PG test")
	}
	ctx := context.Background()
	pool, err := pgxpool.New(ctx, dsn)
	if err != nil {
		t.Fatalf("connect: %v", err)
	}
	t.Cleanup(pool.Close)
	for _, f := range []string{
		"../../../migrations/meta/009_pii_registry.up.sql",
		"../../../migrations/meta/010_pii_kek.up.sql",
		"../../../migrations/meta/013_meta_write_audit.up.sql",
		"../../../migrations/meta/027_meta_write_audit_scrub_version.up.sql",
		"../../../migrations/meta/028_pii_kek_single_active.up.sql",
		"../../../migrations/meta/030_meta_outbox.up.sql",
	} {
		sql, rerr := os.ReadFile(f)
		if rerr != nil {
			t.Fatalf("read %s: %v", f, rerr)
		}
		if _, eerr := pool.Exec(ctx, string(sql)); eerr != nil {
			// Tolerate the catalog deadlock from parallel migration apply.
			if strings.Contains(eerr.Error(), "deadlock") {
				if _, eerr = pool.Exec(ctx, string(sql)); eerr == nil {
					continue
				}
			}
			t.Fatalf("apply %s: %v", f, eerr)
		}
	}
	allow, err := meta.LoadAllowlist("../../../contracts/meta/events_allowlist.yaml")
	if err != nil {
		t.Fatalf("load allowlist: %v", err)
	}
	topics, err := meta.LoadXRealityTopics("../../../contracts/meta/events_allowlist.yaml")
	if err != nil {
		t.Fatalf("load xreality topics: %v", err)
	}
	cfg := &meta.Config{
		DB: metapg.New(pool), Allowlist: allow, QueryBuilder: meta.PostgresQueryBuilder{},
		Clock: kekTestClock{}, UUIDGen: kekTestUUID{}, Scrubber: meta.NewRegexScrubber(nil),
		Outbox: metaoutbox.New(topics),
	}
	return pool, cfg
}

// seedKEK inserts a pii_registry + active pii_kek row for a fresh user.
func seedKEK(t *testing.T, pool *pgxpool.Pool, kmsKeyRef string) (user, kek uuid.UUID) {
	t.Helper()
	ctx := context.Background()
	user, kek = uuid.New(), uuid.New()
	blob := make([]byte, 28) // satisfies encrypted_blob length CHECK
	if _, err := pool.Exec(ctx,
		`INSERT INTO pii_registry (user_ref_id, kek_id, encrypted_blob, blob_schema_ver) VALUES ($1,$2,$3,1)`,
		user, kek, blob); err != nil {
		t.Fatalf("insert pii_registry: %v", err)
	}
	if _, err := pool.Exec(ctx,
		`INSERT INTO pii_kek (kek_id, user_ref_id, key_material, kms_key_ref) VALUES ($1,$2,$3,$4)`,
		kek, user, make([]byte, 32), kmsKeyRef); err != nil {
		t.Fatalf("insert pii_kek: %v", err)
	}
	return user, kek
}

func destroyedAt(t *testing.T, pool *pgxpool.Pool, kek uuid.UUID) bool {
	t.Helper()
	var set bool
	if err := pool.QueryRow(context.Background(),
		`SELECT destroyed_at IS NOT NULL FROM pii_kek WHERE kek_id=$1`, kek).Scan(&set); err != nil {
		t.Fatalf("query destroyed_at: %v", err)
	}
	return set
}

func TestDestroyKEK_HappyPath_MarksAndSchedules(t *testing.T) {
	pool, cfg := kekPGEnv(t)
	fk := newFakeKMS()
	m := NewPgKEKManager(pool, fk, 30, cfg, "op-admin")
	user, kek := seedKEK(t, pool, "aws-kms:cmk-"+uuid.NewString())

	if err := m.DestroyKEK(context.Background(), user, "INC-9", "gdpr erasure"); err != nil {
		t.Fatalf("DestroyKEK: %v", err)
	}
	if !destroyedAt(t, pool, kek) {
		t.Error("destroyed_at not set")
	}
	if len(fk.scheduled) != 1 {
		t.Errorf("expected 1 ScheduleKeyDeletion, got %d", len(fk.scheduled))
	}
	// P2/113: the shred emitted a user.erased meta_outbox row carrying the DOMAIN
	// payload (user_id + erased_at) + the xreality_topic that feeds 071. The
	// outbox row's aggregate_id is pkAsString({kek_id}) = the kek_id.
	var (
		evName     string
		xtopic     *string
		payloadRaw []byte
	)
	if err := pool.QueryRow(context.Background(),
		`SELECT event_name, xreality_topic, payload FROM meta_outbox WHERE aggregate_id=$1`,
		kek.String()).Scan(&evName, &xtopic, &payloadRaw); err != nil {
		t.Fatalf("query meta_outbox user.erased row: %v", err)
	}
	if evName != "user.erased" {
		t.Errorf("event_name = %q, want user.erased", evName)
	}
	if xtopic == nil || *xtopic != "xreality.user.erased" {
		t.Errorf("xreality_topic = %v, want xreality.user.erased", xtopic)
	}
	payload := string(payloadRaw)
	if !strings.Contains(payload, user.String()) {
		t.Errorf("domain payload must carry user_id %s; got %s", user, payload)
	}
	if !strings.Contains(payload, "erased_at") {
		t.Errorf("domain payload must carry erased_at; got %s", payload)
	}
	// The CDC keys must NOT be present (this is a domain payload, not CDC).
	if strings.Contains(payload, `"table"`) {
		t.Errorf("domain payload must not contain CDC keys; got %s", payload)
	}
}

func TestDestroyKEK_Idempotent_NoActiveKEK(t *testing.T) {
	pool, cfg := kekPGEnv(t)
	fk := newFakeKMS()
	m := NewPgKEKManager(pool, fk, 30, cfg, "op-admin")

	// Unknown user → no active KEK → nil, no KMS call, NO user.erased emit.
	unknown := uuid.New()
	if err := m.DestroyKEK(context.Background(), unknown, "INC-1", "x"); err != nil {
		t.Fatalf("DestroyKEK (no kek): %v", err)
	}
	if len(fk.scheduled) != 0 {
		t.Errorf("no-active-KEK must not schedule deletion; got %d", len(fk.scheduled))
	}
	var emitted int
	if err := pool.QueryRow(context.Background(),
		`SELECT count(*) FROM meta_outbox WHERE payload->>'user_id' = $1`, unknown.String()).Scan(&emitted); err != nil {
		t.Fatalf("count meta_outbox: %v", err)
	}
	if emitted != 0 {
		t.Errorf("no-active-KEK must emit no user.erased event; got %d", emitted)
	}
}

// TestDestroyKEK_ShredsAllActive_DefenseInDepth verifies the set-based shred is
// TOTAL (code-r1 BLOCK fix) + the cross-CMK fan-out. The UNIQUE index normally
// forbids ≥2 active KEKs per user, so we DROP it to fabricate the multi-active
// state the set-based UPDATE defends against, then assert ALL are shredded and
// each distinct CMK is scheduled.
func TestDestroyKEK_ShredsAllActive_DefenseInDepth(t *testing.T) {
	pool, cfg := kekPGEnv(t)
	ctx := context.Background()
	// Remove the structural singleton so we can create the pathological state.
	if _, err := pool.Exec(ctx, `DROP INDEX IF EXISTS uq_pii_kek_user_active`); err != nil {
		t.Fatalf("drop unique idx: %v", err)
	}
	fk := newFakeKMS()
	m := NewPgKEKManager(pool, fk, 30, cfg, "op-admin")

	user := uuid.New()
	blob := make([]byte, 28)
	if _, err := pool.Exec(ctx,
		`INSERT INTO pii_registry (user_ref_id, kek_id, encrypted_blob, blob_schema_ver) VALUES ($1,$2,$3,1)`,
		user, uuid.New(), blob); err != nil {
		t.Fatalf("insert registry: %v", err)
	}
	// Two ACTIVE KEKs for the SAME user, on DISTINCT CMKs.
	kek1, kek2 := uuid.New(), uuid.New()
	ref1 := "aws-kms:cmk-a-" + uuid.NewString()
	ref2 := "aws-kms:cmk-b-" + uuid.NewString()
	for _, kv := range []struct {
		kek uuid.UUID
		ref string
	}{{kek1, ref1}, {kek2, ref2}} {
		if _, err := pool.Exec(ctx,
			`INSERT INTO pii_kek (kek_id, user_ref_id, key_material, kms_key_ref) VALUES ($1,$2,$3,$4)`,
			kv.kek, user, make([]byte, 32), kv.ref); err != nil {
			t.Fatalf("insert kek: %v", err)
		}
	}

	if err := m.DestroyKEK(ctx, user, "INC-3", "gdpr erasure"); err != nil {
		t.Fatalf("DestroyKEK: %v", err)
	}
	// BOTH active KEKs must be shredded (erasure is TOTAL).
	if !destroyedAt(t, pool, kek1) || !destroyedAt(t, pool, kek2) {
		t.Error("set-based shred left an active KEK (erasure not total)")
	}
	// Each distinct CMK (now with no other live KEK) scheduled for deletion.
	if len(fk.scheduled) != 2 {
		t.Errorf("expected 2 ScheduleKeyDeletion (one per distinct CMK), got %d", len(fk.scheduled))
	}
	// MetaWriteBatch emits one user.erased per shredded KEK (both atomic).
	var emitted int
	if err := pool.QueryRow(ctx,
		`SELECT count(*) FROM meta_outbox WHERE event_name='user.erased' AND aggregate_id IN ($1,$2)`,
		kek1.String(), kek2.String()).Scan(&emitted); err != nil {
		t.Fatalf("count meta_outbox: %v", err)
	}
	if emitted != 2 {
		t.Errorf("expected 2 user.erased rows (one per shredded KEK), got %d", emitted)
	}
}

// failOutbox always errors on Append — to prove DestroyKEK fails CLOSED
// (P2/113 /review-impl #2): if the user.erased outbox append fails, the shred
// MetaWrite rolls back, so destroyed_at stays NULL (the KEK is NOT erased) and
// the admin retries. The authoritative erasure never half-completes.
type failOutbox struct{}

func (failOutbox) Append(_ context.Context, _ meta.Tx, _ meta.OutboxEvent) error {
	return errors.New("outbox unavailable")
}

func TestDestroyKEK_FailsClosed_WhenOutboxAppendFails(t *testing.T) {
	pool, cfg := kekPGEnv(t)
	cfg.Outbox = failOutbox{} // the outbox append will fail inside MetaWrite's TX
	fk := newFakeKMS()
	m := NewPgKEKManager(pool, fk, 30, cfg, "op-admin")
	user, kek := seedKEK(t, pool, "aws-kms:cmk-"+uuid.NewString())

	err := m.DestroyKEK(context.Background(), user, "INC-FC", "gdpr erasure")
	if err == nil {
		t.Fatal("DestroyKEK must return an error when the outbox append fails")
	}
	// FAIL CLOSED: the shred rolled back — the KEK is NOT destroyed.
	if destroyedAt(t, pool, kek) {
		t.Error("destroyed_at MUST stay NULL when the outbox append fails (shred must roll back)")
	}
	// And no KMS deletion was scheduled (we never reached step 3).
	if len(fk.scheduled) != 0 {
		t.Errorf("no KMS deletion may be scheduled on a failed shred; got %d", len(fk.scheduled))
	}
}

func TestDestroyKEK_SuppressedWhenCMKShared(t *testing.T) {
	pool, cfg := kekPGEnv(t)
	fk := newFakeKMS()
	m := NewPgKEKManager(pool, fk, 30, cfg, "op-admin")

	// Two users share ONE kms_key_ref (mis-provisioned shared CMK). Erasing one
	// must NOT schedule the shared CMK's deletion (would mass-erase the other).
	shared := "aws-kms:shared-cmk-" + uuid.NewString()
	user1, kek1 := seedKEK(t, pool, shared)
	_, _ = seedKEK(t, pool, shared) // user2 still live on the same CMK

	if err := m.DestroyKEK(context.Background(), user1, "INC-2", "gdpr erasure"); err != nil {
		t.Fatalf("DestroyKEK: %v", err)
	}
	if !destroyedAt(t, pool, kek1) {
		t.Error("destroyed_at not set (the authoritative shred must still happen)")
	}
	if len(fk.scheduled) != 0 {
		t.Errorf("ScheduleKeyDeletion must be SUPPRESSED when another live KEK shares the CMK; got %d", len(fk.scheduled))
	}
}
