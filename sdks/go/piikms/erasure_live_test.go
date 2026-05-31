package piikms

// PG + LocalStack-KMS live-smoke for 076 Slice C: the full pii.SDK.ErasePII
// path through the production drivers (PgKEKManager + PgPIIReader +
// PgReadAuditWriter). Gated on BOTH PIIKMS_TEST_PG_URL and
// PIIKMS_TEST_KMS_ENDPOINT (skips in the normal job).
//
// WHY a live-smoke (not just mocks): the adversary BLOCK#1 — ErasePII writes a
// meta_read_audit row whose query_type ("pii_user_erase") + actor_type
// ("admin") are gated by DB CHECK constraints (migration 014 + 029). Mock-only
// coverage hides a CHECK violation, which would surface only AFTER the KEK is
// irreversibly shredded. This test proves the real row LANDS.

import (
	"context"
	"os"
	"testing"

	"github.com/aws/aws-sdk-go-v2/aws"
	awsconfig "github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/credentials"
	awskms "github.com/aws/aws-sdk-go-v2/service/kms"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/pii"
)

// applyReadAuditMigrations layers the meta_read_audit table (014) + the Slice-C
// query_type widening (029) on top of the pii tables kekPGPool already applied.
func applyReadAuditMigrations(t *testing.T, pool *pgxpool.Pool) {
	t.Helper()
	ctx := context.Background()
	for _, f := range []string{
		"../../../migrations/meta/014_meta_read_audit.up.sql",
		"../../../migrations/meta/029_meta_read_audit_pii_query_types.up.sql",
	} {
		sql, err := os.ReadFile(f)
		if err != nil {
			t.Fatalf("read %s: %v", f, err)
		}
		if _, err := pool.Exec(ctx, string(sql)); err != nil {
			t.Fatalf("apply %s: %v", f, err)
		}
	}
}

func realKMSClient(t *testing.T, endpoint string) *awskms.Client {
	t.Helper()
	cfg, err := awsconfig.LoadDefaultConfig(context.Background(),
		awsconfig.WithRegion("us-east-1"),
		awsconfig.WithCredentialsProvider(credentials.NewStaticCredentialsProvider("test", "test", "")),
	)
	if err != nil {
		t.Fatalf("aws config: %v", err)
	}
	return awskms.NewFromConfig(cfg, func(o *awskms.Options) { o.BaseEndpoint = aws.String(endpoint) })
}

func TestLive_ErasePII_WritesRealAuditRow(t *testing.T) {
	pool, cfg := kekPGEnv(t) // skips if PIIKMS_TEST_PG_URL unset; applies pii + meta_write_audit + meta_outbox
	applyReadAuditMigrations(t, pool)
	ep := os.Getenv("PIIKMS_TEST_KMS_ENDPOINT")
	if ep == "" {
		t.Skip("PIIKMS_TEST_KMS_ENDPOINT not set; skipping ErasePII live-smoke")
	}
	ctx := context.Background()
	cl := realKMSClient(t, ep)

	// A real LocalStack CMK so ScheduleKeyDeletion (step 3 defense-in-depth) works.
	ck, err := cl.CreateKey(ctx, &awskms.CreateKeyInput{})
	if err != nil {
		t.Fatalf("CreateKey: %v", err)
	}
	keyRef := "aws-kms:" + *ck.KeyMetadata.KeyId
	user, kek := seedKEK(t, pool, keyRef)

	const actorID = "op-admin-live"
	sdk, err := pii.NewSDK(pii.Config{
		KMS:         NewAWSKMSClient(cl),
		DB:          NewPgPIIReader(pool),
		KEKManager:  NewPgKEKManager(pool, cl, 7, cfg, actorID),
		AuditWriter: NewPgReadAuditWriter(pool),
		ActorID:     actorID,
		ActorType:   "admin", // BLOCK#1: enum-valid; "admin-cli" would fail the CHECK
	})
	if err != nil {
		t.Fatalf("NewSDK: %v", err)
	}

	if err := sdk.ErasePII(ctx, user, "INC-LIVE-1", "gdpr erasure live-smoke"); err != nil {
		t.Fatalf("ErasePII: %v", err) // BLOCK#1 regression would surface here ("audit failed")
	}
	if !destroyedAt(t, pool, kek) {
		t.Error("pii_kek.destroyed_at not set after ErasePII")
	}

	// The forensic invariant: a real meta_read_audit row landed with the
	// enum-valid query_type + actor_type (proves migration 029 + actor_type pin).
	var qt, at string
	if err := pool.QueryRow(ctx,
		`SELECT query_type, actor_type FROM meta_read_audit
		  WHERE actor_id=$1 ORDER BY created_at_nanos DESC LIMIT 1`, actorID).Scan(&qt, &at); err != nil {
		t.Fatalf("expected a meta_read_audit row for the erasure: %v", err)
	}
	if qt != "pii_user_erase" {
		t.Errorf("query_type = %q, want pii_user_erase", qt)
	}
	if at != "admin" {
		t.Errorf("actor_type = %q, want admin", at)
	}
}

func TestLive_PgPIIReader_RoundTrip(t *testing.T) {
	pool, _ := kekPGEnv(t)
	ctx := context.Background()
	user, kek := seedKEK(t, pool, "aws-kms:cmk-"+uuid.NewString())

	r := NewPgPIIReader(pool)
	row, err := r.ReadPIIRow(ctx, user)
	if err != nil {
		t.Fatalf("ReadPIIRow: %v", err)
	}
	if row.UserRefID != user || row.KEKID != kek {
		t.Fatalf("round-trip mismatch: got user=%s kek=%s", row.UserRefID, row.KEKID)
	}
	if row.ErasedAt != nil {
		t.Errorf("fresh row should not be erased; ErasedAt=%v", row.ErasedAt)
	}
	krow, err := r.ReadKEKRow(ctx, kek)
	if err != nil {
		t.Fatalf("ReadKEKRow: %v", err)
	}
	if krow.KEKID != kek || krow.DestroyedAt != nil {
		t.Fatalf("kek round-trip mismatch: %+v", krow)
	}

	// Not-found path.
	if _, err := r.ReadPIIRow(ctx, uuid.New()); err == nil {
		t.Error("ReadPIIRow on unknown user should return an error (ErrPIINotFound)")
	}
}
