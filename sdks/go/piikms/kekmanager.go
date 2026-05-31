package piikms

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"time"

	awskms "github.com/aws/aws-sdk-go-v2/service/kms"
	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
)

// PgKEKManager implements contracts/pii.KEKManager.DestroyKEK against the meta
// DB (pii_kek) + AWS KMS. The authoritative crypto-shred is the per-row
// destroyed_at marker (OpenPII refuses to decrypt once set); ScheduleKeyDeletion
// is defense-in-depth and is SUPPRESSED unless the CMK is the user's alone.
//
// P2/113: the shred runs THROUGH contracts/meta MetaWriteBatch (not a direct
// UPDATE) so each pii_kek destroy is audited (same-TX meta_write_audit) AND
// emits the allowlisted `user.erased` event — with a DOMAIN OutboxPayload
// (XRealityUserErasedV1 {user_id, erased_at}) so the meta-outbox relay's
// xreality bridge feeds the 071 per-reality cascade. MetaWriteBatch keeps the
// total-shred atomic (all active KEKs in one tx); the KMS step is unchanged.
type PgKEKManager struct {
	db  *pgxpool.Pool
	kms kmsAPI
	// cfg is the MetaWrite Config (DB=metapg(pool), allowlist incl. pii_kek,
	// Outbox appender). The shred's destroy + audit + user.erased emit run via it.
	cfg *meta.Config
	// actorID is the admin subject recorded in meta_write_audit.actor_id for the
	// shred (the erasure is an admin action — ActorAdmin).
	actorID string
	// pendingWindowDays is the KMS ScheduleKeyDeletion window (KMS min 7, max 30).
	pendingWindowDays int32
}

// NewPgKEKManager binds the meta pool + KMS API + the MetaWrite Config + the
// admin actor. window<=0 defaults to 30d. cfg MUST have a non-nil Outbox for
// user.erased to actually emit (the erasure handler wires it; probeMetaOutbox
// guards the table's existence).
func NewPgKEKManager(db *pgxpool.Pool, api kmsAPI, windowDays int32, cfg *meta.Config, actorID string) *PgKEKManager {
	if windowDays <= 0 {
		windowDays = 30
	}
	return &PgKEKManager{db: db, kms: api, cfg: cfg, actorID: actorID, pendingWindowDays: windowDays}
}

// DestroyKEK crypto-shreds the user's active KEK(s) via MetaWriteBatch: each
// pii_kek row gets destroyed_at + ticket + reason (the authoritative erasure) +
// a same-TX audit row + a `user.erased` outbox event carrying the DOMAIN
// payload {user_id, erased_at}; then best-effort ScheduleKeyDeletion on the
// per-user CMK. IDEMPOTENT — no active KEK → nil; a concurrent erasure that
// wins the CAS → nil (we treat it as already-done).
func (m *PgKEKManager) DestroyKEK(ctx context.Context, userRefID uuid.UUID, ticket, reason string) error {
	if ticket == "" || reason == "" {
		return fmt.Errorf("piikms: DestroyKEK requires ticket+reason (pii_kek CHECK)")
	}
	if m.cfg == nil {
		return fmt.Errorf("piikms: DestroyKEK requires a MetaWrite Config (P2/113)")
	}

	// 1. Enumerate the active KEK set (≤1 by migration 028's UNIQUE partial
	// index; the SELECT is the defense-in-depth enumeration so the shred is
	// TOTAL — leaving any active KEK would let OpenPII still decrypt the blob).
	rows, err := m.db.Query(ctx,
		`SELECT kek_id, kms_key_ref FROM pii_kek WHERE user_ref_id=$1 AND destroyed_at IS NULL`,
		userRefID)
	if err != nil {
		return fmt.Errorf("piikms: enumerate active KEKs for user %s: %w", userRefID, err)
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
			return fmt.Errorf("piikms: scan active KEK: %w", err)
		}
		destroyed = append(destroyed, s)
	}
	rows.Close()
	if err := rows.Err(); err != nil {
		return fmt.Errorf("piikms: iterate active KEKs: %w", err)
	}
	if len(destroyed) == 0 {
		return nil // already destroyed / none — idempotent
	}

	// 2. Shred ALL active KEKs in ONE MetaWriteBatch tx (atomic total shred):
	// each intent destroys one row (CAS on destroyed_at IS NULL), writes its
	// meta_write_audit row, and emits user.erased with the DOMAIN payload. If a
	// concurrent erasure already won the CAS, the batch returns
	// ErrConcurrentStateTransition and NOTHING in this call shredded → treat as
	// already-done (idempotent) and skip KMS (the winner handles it). Any other
	// error fails CLOSED — the shred rolled back, nothing destroyed, admin retries.
	erasedAt := time.Now().UTC()
	domainPayload := map[string]any{
		"user_id":   userRefID.String(),
		"erased_at": erasedAt.Format(time.RFC3339Nano),
	}
	intents := make([]meta.MetaWriteIntent, 0, len(destroyed))
	for _, s := range destroyed {
		intents = append(intents, meta.MetaWriteIntent{
			Table:     "pii_kek",
			Operation: meta.OpUpdate,
			PK:        map[string]any{"kek_id": s.kekID},
			NewValues: map[string]any{
				"destroyed_at":        erasedAt,
				"destroyed_by_ticket": ticket,
				"destroyed_reason":    reason,
			},
			ExpectedBefore: map[string]any{"destroyed_at": nil},
			Actor:          meta.Actor{Type: meta.ActorAdmin, ID: m.actorID},
			Reason:         reason,
			OutboxPayload:  domainPayload, // P2/113 — canonical XRealityUserErasedV1 shape
		})
	}
	if _, err := meta.MetaWriteBatch(ctx, m.cfg, intents); err != nil {
		if errors.Is(err, meta.ErrConcurrentStateTransition) {
			return nil // a concurrent erasure won the CAS — already shredded
		}
		return fmt.Errorf("piikms: shred KEKs for user %s: %w", userRefID, err)
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
