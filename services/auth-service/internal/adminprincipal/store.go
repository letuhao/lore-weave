// Package adminprincipal owns the admin RBAC source of truth (admin_principals)
// and the append-only token-issuance audit (admin_token_issuance_audit), both in
// auth-service's own DB. It backs the 074/075 admin-JWT issuance endpoints.
package adminprincipal

import (
	"context"
	"errors"
	"fmt"

	"github.com/google/uuid"
	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Principal is an admin RBAC row: who may be issued an admin token and with what
// authority.
type Principal struct {
	UserID uuid.UUID
	Handle string // human-readable (email) for audit legibility; denormalized into audit rows
	Role   string
	Scopes []string
	Active bool
}

// IssuanceAuditRow is one append-only row recording a token-issuance ATTEMPT
// (success, deny, or error). Free-text reason is never stored — only ReasonLen
// and a keyed HMAC (see the audit writer in the api package).
type IssuanceAuditRow struct {
	AuditID           uuid.UUID
	ActorID           uuid.UUID
	ActorHandle       string
	SecondActorID     *uuid.UUID
	SecondActorHandle *string
	TokenKind         string // "admin" | "break_glass"
	Outcome           string // "success" | "deny" | "error"
	DenyReason        *string
	Role              *string
	Scopes            []string
	BreakGlass        bool
	IncidentTicket    *string
	ReasonLen         *int
	ReasonHMAC        []byte
	JTI               *uuid.UUID
	IssuedAtNanos     *int64
	ExpiresAtNanos    *int64
	CreatedAtNanos    int64
}

// Store is the pgx-backed implementation.
type Store struct {
	pool *pgxpool.Pool
}

// New returns a Store over the given pool.
func New(pool *pgxpool.Pool) *Store { return &Store{pool: pool} }

// Lookup returns the admin principal for userID. The bool is false (with a nil
// error) when no row exists — the caller treats "not a principal" as a deny, not
// an error.
func (s *Store) Lookup(ctx context.Context, userID uuid.UUID) (Principal, bool, error) {
	var p Principal
	p.UserID = userID
	// The JOIN requires the user row to be 'active' — a soft-deleted account
	// (DELETE /account sets account_status='deleted') therefore stops being a
	// valid admin principal, so no admin token can be minted for it even though
	// its admin_principals row still exists.
	err := s.pool.QueryRow(ctx, `
		SELECT ap.role, ap.scopes, ap.active, COALESCE(u.email, '')
		FROM admin_principals ap
		JOIN users u ON u.id = ap.user_id
		WHERE ap.user_id = $1 AND u.account_status = 'active'`, userID).Scan(&p.Role, &p.Scopes, &p.Active, &p.Handle)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return Principal{}, false, nil
		}
		return Principal{}, false, fmt.Errorf("adminprincipal: lookup: %w", err)
	}
	return p, true, nil
}

// InsertAudit appends one issuance-attempt row. It is called on success AND on
// deny/error (after issuer auth) so every attempt is recorded.
func (s *Store) InsertAudit(ctx context.Context, r IssuanceAuditRow) error {
	_, err := s.pool.Exec(ctx, `
		INSERT INTO admin_token_issuance_audit (
			audit_id, actor_id, actor_handle, second_actor_id, second_actor_handle,
			token_kind, outcome, deny_reason, role, scopes, break_glass,
			incident_ticket, reason_len, reason_hmac, jti,
			issued_at_nanos, expires_at_nanos, created_at_nanos
		) VALUES (
			$1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18
		)`,
		r.AuditID, r.ActorID, r.ActorHandle, r.SecondActorID, r.SecondActorHandle,
		r.TokenKind, r.Outcome, r.DenyReason, r.Role, r.Scopes, r.BreakGlass,
		r.IncidentTicket, r.ReasonLen, r.ReasonHMAC, r.JTI,
		r.IssuedAtNanos, r.ExpiresAtNanos, r.CreatedAtNanos,
	)
	if err != nil {
		return fmt.Errorf("adminprincipal: insert audit: %w", err)
	}
	return nil
}
