package commands

import (
	"context"
	"errors"
	"fmt"
	"time"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5/pgxpool"

	"github.com/loreweave/foundation/contracts/meta"
)

// ── Production pgx/MetaWrite implementations of the orchestrator interfaces. ──

// PgConsentRevoker revokes consent rows via contracts/meta MetaWrite (so each
// revoke is audited in meta_write_audit) and lists active scopes via a direct
// SELECT. The CAS (revoked_at IS NULL) makes a double-revoke an idempotent
// no-op rather than an error.
//
// NOTE on the user.consent.revoked event: the user_consent_ledger UPDATE is
// allowlisted to emit user.consent.revoked, but MetaWrite only emits when
// cfg.Outbox is set, and NO caller wires a production OutboxAppender platform-
// wide yet (the outbox-emit layer is universally unwired today). So the
// revoked_at DB state is the authoritative record and the event is currently
// DROPPED — consistent with the deferred steps 4/5. When the platform wires an
// OutboxAppender, the erasure handler's cfg.Outbox must be set too, or
// consent.revoked stays dropped. Tracked: D-METAWRITE-OUTBOX-UNWIRED.
type PgConsentRevoker struct {
	pool    *pgxpool.Pool
	cfg     *meta.Config
	actorID string
	clock   func() time.Time
}

// NewPgConsentRevoker binds the meta pool + MetaWrite Config. actorID is the
// admin subject (TEXT actor_id in meta_write_audit). The pool is caller-owned.
func NewPgConsentRevoker(pool *pgxpool.Pool, cfg *meta.Config, actorID string, clock func() time.Time) *PgConsentRevoker {
	if clock == nil {
		clock = time.Now
	}
	return &PgConsentRevoker{pool: pool, cfg: cfg, actorID: actorID, clock: clock}
}

var _ ConsentRevoker = (*PgConsentRevoker)(nil)

// ActiveScopes lists scopes still granted (revoked_at IS NULL). READ-ONLY.
func (r *PgConsentRevoker) ActiveScopes(ctx context.Context, userRefID uuid.UUID) ([]ConsentScope, error) {
	rows, err := r.pool.Query(ctx,
		`SELECT consent_scope, scope_version
		   FROM user_consent_ledger
		  WHERE user_ref_id = $1 AND revoked_at IS NULL`,
		userRefID)
	if err != nil {
		return nil, fmt.Errorf("query active consent scopes: %w", err)
	}
	defer rows.Close()
	var out []ConsentScope
	for rows.Next() {
		var sc ConsentScope
		if err := rows.Scan(&sc.Scope, &sc.Version); err != nil {
			return nil, fmt.Errorf("scan consent scope: %w", err)
		}
		out = append(out, sc)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate consent scopes: %w", err)
	}
	return out, nil
}

// RevokeScope sets revoked_at on one row, guarded by ExpectedBefore
// (revoked_at IS NULL). A 0-row CAS surfaces as ErrConcurrentStateTransition,
// which we translate to alreadyRevoked=true.
//
// This mapping is sound (not a wrong-PK false-success): the (scope, version)
// always come from ActiveScopes for THIS user_ref_id, so the PK matches an
// existing row; and consent rows are never DELETEd (migration 011 — append-only,
// revoked-once). So the ONLY way the row fails the revoked_at IS NULL predicate
// is that it was concurrently/previously revoked — a genuine idempotent no-op.
func (r *PgConsentRevoker) RevokeScope(ctx context.Context, userRefID uuid.UUID, scope ConsentScope, reason string) (bool, error) {
	intent := meta.MetaWriteIntent{
		Table:     "user_consent_ledger",
		Operation: meta.OpUpdate,
		PK: map[string]any{
			"user_ref_id":   userRefID,
			"consent_scope": scope.Scope,
			"scope_version": scope.Version,
		},
		NewValues: map[string]any{
			"revoked_at":    r.clock().UTC(),
			"revoke_reason": reason,
		},
		ExpectedBefore: map[string]any{"revoked_at": nil}, // CAS → revoked_at IS NULL
		Actor:          meta.Actor{Type: meta.ActorAdmin, ID: r.actorID},
		Reason:         reason,
	}
	if _, err := meta.MetaWrite(ctx, r.cfg, intent); err != nil {
		if errors.Is(err, meta.ErrConcurrentStateTransition) {
			return true, nil // already revoked — idempotent
		}
		return false, err
	}
	return false, nil
}

// PgBalanceReader is the best-effort cost-ledger proxy for the step-2 pre-check.
// It is NOT an authoritative account balance (that lives in usage-billing-
// service). net = sum(cost), with refunds subtracted.
type PgBalanceReader struct {
	pool *pgxpool.Pool
}

// NewPgBalanceReader binds the meta pool (caller-owned).
func NewPgBalanceReader(pool *pgxpool.Pool) *PgBalanceReader { return &PgBalanceReader{pool: pool} }

var _ BalanceReader = (*PgBalanceReader)(nil)

// CostLedgerSummary returns the row count + net micro-USD for a user.
func (b *PgBalanceReader) CostLedgerSummary(ctx context.Context, userRefID uuid.UUID) (int, int64, error) {
	var (
		rows int
		net  int64
	)
	err := b.pool.QueryRow(ctx,
		`SELECT COUNT(*),
		        COALESCE(SUM(CASE WHEN reason = 'refund' THEN -cost_micro_usd ELSE cost_micro_usd END), 0)
		   FROM user_cost_ledger
		  WHERE user_ref_id = $1`,
		userRefID).Scan(&rows, &net)
	if err != nil {
		return 0, 0, fmt.Errorf("cost-ledger summary: %w", err)
	}
	return rows, net, nil
}
