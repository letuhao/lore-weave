package piikms

// PG-gated test for PgKEKManager.DestroyKEK — the security-critical SQL +
// WARN-1/2 co-tenant guard. Gated on PIIKMS_TEST_PG_URL (skips in the normal
// job); run against a throwaway pg (e.g. infra/foundation-dev). Uses the
// faithful fake KMS so ScheduleKeyDeletion calls are deterministically
// inspectable.

import (
	"context"
	"os"
	"testing"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

func kekPGPool(t *testing.T) *pgxpool.Pool {
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
		"../../../migrations/meta/028_pii_kek_single_active.up.sql",
	} {
		sql, err := os.ReadFile(f)
		if err != nil {
			t.Fatalf("read %s: %v", f, err)
		}
		if _, err := pool.Exec(ctx, string(sql)); err != nil {
			t.Fatalf("apply %s: %v", f, err)
		}
	}
	return pool
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
	pool := kekPGPool(t)
	fk := newFakeKMS()
	m := NewPgKEKManager(pool, fk, 30)
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
}

func TestDestroyKEK_Idempotent_NoActiveKEK(t *testing.T) {
	pool := kekPGPool(t)
	fk := newFakeKMS()
	m := NewPgKEKManager(pool, fk, 30)

	// Unknown user → no active KEK → nil, no KMS call.
	if err := m.DestroyKEK(context.Background(), uuid.New(), "INC-1", "x"); err != nil {
		t.Fatalf("DestroyKEK (no kek): %v", err)
	}
	if len(fk.scheduled) != 0 {
		t.Errorf("no-active-KEK must not schedule deletion; got %d", len(fk.scheduled))
	}
}

// TestDestroyKEK_ShredsAllActive_DefenseInDepth verifies the set-based shred is
// TOTAL (code-r1 BLOCK fix) + the cross-CMK fan-out. The UNIQUE index normally
// forbids ≥2 active KEKs per user, so we DROP it to fabricate the multi-active
// state the set-based UPDATE defends against, then assert ALL are shredded and
// each distinct CMK is scheduled.
func TestDestroyKEK_ShredsAllActive_DefenseInDepth(t *testing.T) {
	pool := kekPGPool(t)
	ctx := context.Background()
	// Remove the structural singleton so we can create the pathological state.
	if _, err := pool.Exec(ctx, `DROP INDEX IF EXISTS uq_pii_kek_user_active`); err != nil {
		t.Fatalf("drop unique idx: %v", err)
	}
	fk := newFakeKMS()
	m := NewPgKEKManager(pool, fk, 30)

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
}

func TestDestroyKEK_SuppressedWhenCMKShared(t *testing.T) {
	pool := kekPGPool(t)
	fk := newFakeKMS()
	m := NewPgKEKManager(pool, fk, 30)

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
