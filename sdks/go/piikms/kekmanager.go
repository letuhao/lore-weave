package piikms

import (
	"context"
	"fmt"
	"log/slog"

	awskms "github.com/aws/aws-sdk-go-v2/service/kms"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"
)

// PgKEKManager implements contracts/pii.KEKManager.DestroyKEK against the meta
// DB (pii_kek) + AWS KMS. The authoritative crypto-shred is the per-row
// destroyed_at marker (OpenPII refuses to decrypt once set); ScheduleKeyDeletion
// is defense-in-depth and is SUPPRESSED unless the CMK is the user's alone.
type PgKEKManager struct {
	db  *pgxpool.Pool
	kms kmsAPI
	// pendingWindowDays is the KMS ScheduleKeyDeletion window (KMS min 7, max 30).
	pendingWindowDays int32
}

// NewPgKEKManager binds the meta pool + KMS API. window<=0 defaults to 30d.
func NewPgKEKManager(db *pgxpool.Pool, api kmsAPI, windowDays int32) *PgKEKManager {
	if windowDays <= 0 {
		windowDays = 30
	}
	return &PgKEKManager{db: db, kms: api, pendingWindowDays: windowDays}
}

// DestroyKEK crypto-shreds the user's active KEK: set destroyed_at + ticket +
// reason (the authoritative erasure), then best-effort ScheduleKeyDeletion on
// the per-user CMK. IDEMPOTENT — no active KEK → nil.
func (m *PgKEKManager) DestroyKEK(ctx context.Context, userRefID uuid.UUID, ticket, reason string) error {
	if ticket == "" || reason == "" {
		return fmt.Errorf("piikms: DestroyKEK requires ticket+reason (pii_kek CHECK)")
	}

	// 1+2. SET-BASED shred: mark EVERY active KEK row for the user destroyed in
	// one statement (not just one row). Migration 028's UNIQUE partial index
	// makes ≥2-active structurally impossible, but the set-based UPDATE is
	// defense-in-depth so erasure is TOTAL regardless — leaving any active KEK
	// would let OpenPII still decrypt the user's blob (a silently-incomplete
	// GDPR erasure). RETURNING gives the distinct CMKs we just shredded.
	rows, err := m.db.Query(ctx,
		`UPDATE pii_kek SET destroyed_at=now(), destroyed_by_ticket=$2, destroyed_reason=$3
		 WHERE user_ref_id=$1 AND destroyed_at IS NULL
		 RETURNING kek_id, kms_key_ref`,
		userRefID, ticket, reason)
	if err != nil {
		return fmt.Errorf("piikms: shred KEKs for user %s: %w", userRefID, err)
	}
	type shredded struct {
		kekID  uuid.UUID
		keyRef string
	}
	var destroyed []shredded
	for rows.Next() {
		var s shredded
		if err := rows.Scan(&s.kekID, &s.keyRef); err != nil {
			rows.Close()
			return fmt.Errorf("piikms: scan shredded KEK: %w", err)
		}
		destroyed = append(destroyed, s)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return fmt.Errorf("piikms: iterate shredded KEKs: %w", err)
	}
	if len(destroyed) == 0 {
		return nil // already destroyed / none — idempotent
	}

	// 3. Defense-in-depth: per distinct CMK, schedule deletion ONLY if no OTHER
	// live KEK references it (WARN-1 co-tenant + WARN-2 rotation-chain safety).
	// NOTE (tracked, D-PIIKMS-DESTROY-TOCTOU): the count is not in the same tx
	// as the UPDATE, so two concurrent erasures of co-tenants on a shared CMK
	// could both observe 0 and both schedule deletion — recoverable via the
	// 7-30d pending window + CancelKeyDeletion, and the per-user-CMK precondition
	// makes co-tenancy a misconfiguration. Authoritative erasure (destroyed_at)
	// is unaffected.
	seen := make(map[string]bool, len(destroyed))
	for _, s := range destroyed {
		if seen[s.keyRef] {
			continue
		}
		seen[s.keyRef] = true
		m.maybeScheduleDeletion(ctx, s.kekID, s.keyRef)
	}
	return nil
}

// maybeScheduleDeletion schedules CMK deletion only if no other live KEK uses
// it. All failures are non-fatal (the destroyed_at marker is the authoritative
// erasure) and logged for SRE follow-up.
func (m *PgKEKManager) maybeScheduleDeletion(ctx context.Context, kekID uuid.UUID, kmsKeyRef string) {
	var liveOnSameCMK int
	if err := m.db.QueryRow(ctx,
		`SELECT count(*) FROM pii_kek WHERE kms_key_ref=$1 AND destroyed_at IS NULL`,
		kmsKeyRef).Scan(&liveOnSameCMK); err != nil {
		slog.Error("piikms: CMK liveness check failed; suppressing ScheduleKeyDeletion (erasure satisfied by destroyed_at)",
			"kek_id", kekID, "error", err)
		return
	}
	if liveOnSameCMK > 0 {
		slog.Warn("piikms: kms_key_ref shared by other live KEK rows; SUPPRESSING ScheduleKeyDeletion (per-user-CMK precondition violated) — erasure satisfied by destroyed_at",
			"kek_id", kekID, "kms_key_ref", kmsKeyRef, "live_on_same_cmk", liveOnSameCMK)
		return
	}
	keyID, err := arn(kmsKeyRef)
	if err != nil {
		slog.Error("piikms: bad kms_key_ref; skipping ScheduleKeyDeletion (erasure satisfied by destroyed_at)",
			"kek_id", kekID, "error", err)
		return
	}
	if _, err := m.kms.ScheduleKeyDeletion(ctx, &awskms.ScheduleKeyDeletionInput{
		KeyId:               &keyID,
		PendingWindowInDays: &m.pendingWindowDays,
	}); err != nil {
		slog.Error("piikms: ScheduleKeyDeletion failed (non-fatal; erasure satisfied by destroyed_at marker)",
			"kek_id", kekID, "kms_key_ref", kmsKeyRef, "error", err)
	}
}
