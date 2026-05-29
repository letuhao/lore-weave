package ws

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/google/uuid"
)

// TicketTTL is the canonical V1 window per S12 §12AB.2. Tickets are
// strictly one-shot; redemption DELETEs them.
const TicketTTL = 60 * time.Second

// Ticket is the one-shot handshake credential issued by auth-service
// (POST /v1/ws/ticket) and redeemed by the WS gateway at the HTTP 101
// upgrade. Per S12 §12AB:
//
//   - Never appears in URL (always in Sec-WebSocket-Protocol header)
//   - 60s TTL; one-shot DELETE on redemption
//   - Stored in Redis (caller-supplied TicketStore)
//   - origin_hash binds the ticket to a specific browser origin
//   - fingerprint_hash binds to (UA, IP /24, TLS session prefix)
//
// **Type-level discipline:** the ticket carries hashes, NOT raw origin
// strings or raw fingerprint bytes — the auth-service hashes both
// before issuing the ticket and the gateway re-hashes on redemption.
// This makes the ticket safe to log at INFO level.
type Ticket struct {
	// TicketID — opaque random ID (e.g., "wst_01h..."). Foundation does
	// not constrain the format beyond "non-empty string"; the issuer
	// owns the canonical shape.
	TicketID string `json:"ticket_id"`

	// UserRefID — the bearer's user ref ID (from the auth JWT).
	UserRefID uuid.UUID `json:"user_ref_id"`

	// AllowedRealities — every reality the bearer may subscribe to
	// during the resulting WS session. Empty = no realities allowed
	// (effectively a protocol-only session for ws.ping / ws.pong).
	AllowedRealities []uuid.UUID `json:"allowed_realities"`

	// AllowedScopes — operation scopes the session may exercise.
	// Foundation does NOT constrain the namespace; see S12 §12AB.2
	// for the V1 list ("chat", "presence", "events").
	AllowedScopes []string `json:"allowed_scopes"`

	// OriginHash — SHA-256 of the issuer-canonicalized origin string
	// (e.g., "https://app.loreweave.dev"). Wire format = 32 raw bytes
	// (NOT hex) to match the ticket store wire shape.
	OriginHash [32]byte `json:"origin_hash"`

	// ClientFingerprintHash — SHA-256 over (user_agent || ip_/24 ||
	// tls_session_id_first_16b). 32 raw bytes.
	ClientFingerprintHash [32]byte `json:"client_fingerprint_hash"`

	// ExpiresAt — wall clock time after which the ticket is invalid
	// even if not yet redeemed. ~60s past IssuedAt.
	ExpiresAt time.Time `json:"exp"`

	// IssuedAt — when auth-service produced the ticket. Useful for
	// forensics (auth-side TTL math + clock skew detection).
	IssuedAt time.Time `json:"iat"`
}

// Validate enforces shape invariants the gateway MUST check before
// trusting the ticket bytes. The gateway calls Validate AFTER
// successful Redis redemption (so an invalid ticket does NOT consume
// the one-shot DELETE; the redeemer typically reads → validates →
// deletes).
func (t Ticket) Validate(now time.Time) error {
	if t.TicketID == "" {
		return errors.New("ws: ticket_id empty")
	}
	if t.UserRefID == uuid.Nil {
		return errors.New("ws: user_ref_id zero")
	}
	if t.OriginHash == ([32]byte{}) {
		return errors.New("ws: origin_hash zero (auth-service must hash before issuing)")
	}
	if t.ClientFingerprintHash == ([32]byte{}) {
		return errors.New("ws: client_fingerprint_hash zero")
	}
	if t.IssuedAt.IsZero() {
		return errors.New("ws: iat zero")
	}
	if t.ExpiresAt.IsZero() {
		return errors.New("ws: exp zero")
	}
	if !now.Before(t.ExpiresAt) {
		return fmt.Errorf("ws: ticket expired at %s (now %s)", t.ExpiresAt, now)
	}
	// Sanity: TTL window <= 2*TicketTTL (clock skew tolerance).
	if t.ExpiresAt.Sub(t.IssuedAt) > 2*TicketTTL {
		return fmt.Errorf("ws: ticket TTL window too wide: %s > %s",
			t.ExpiresAt.Sub(t.IssuedAt), 2*TicketTTL)
	}
	return nil
}

// BindsToOrigin returns true iff the supplied originHash (gateway-recomputed
// over the Origin header) matches the ticket's bound origin.
func (t Ticket) BindsToOrigin(originHash [32]byte) bool {
	return t.OriginHash == originHash
}

// BindsToFingerprint returns true iff the supplied fingerprint matches
// the ticket's bound fingerprint exactly. See S12 §12AB.7 for the
// soft-mismatch (mobile handoff) policy — that policy lives in the
// gateway, not the foundation contract.
func (t Ticket) BindsToFingerprint(fp [32]byte) bool {
	return t.ClientFingerprintHash == fp
}

// TicketStore is the persistence boundary. Production wires Redis
// (key = "ticket:<ticket_id>", TTL = TicketTTL, one-shot via DEL on
// Redeem). Tests use an in-memory implementation.
//
// **Redeem MUST be atomic + one-shot.** The contract: a successful
// Redeem call returns the ticket bytes AND removes the ticket from
// the store; a second Redeem for the same TicketID returns
// ErrTicketNotFound.
type TicketStore interface {
	// Issue persists a fresh ticket. Returns ErrTicketAlreadyExists
	// on collision (TicketID conflict). The caller owns ID generation
	// + TTL math; this method just persists.
	Issue(ctx context.Context, t Ticket) error

	// Redeem atomically reads-and-deletes the ticket. ErrTicketNotFound
	// when missing OR already redeemed. ErrTicketExpired when the
	// stored ExpiresAt has passed (store MAY also lazy-delete on
	// expiry, but Redeem must double-check via wall clock).
	Redeem(ctx context.Context, ticketID string, now time.Time) (Ticket, error)
}

// Sentinel errors. Callers MUST use errors.Is to classify.
var (
	ErrTicketNotFound       = errors.New("ws: ticket not found or already redeemed")
	ErrTicketExpired        = errors.New("ws: ticket expired")
	ErrTicketAlreadyExists  = errors.New("ws: ticket id collision")
	ErrTicketOriginMismatch = errors.New("ws: ticket origin mismatch")
	ErrTicketFingerprintMismatch = errors.New("ws: ticket fingerprint mismatch")
)

// InMemoryTicketStore is the foundation reference impl + test double.
// Thread-safe via the embedded sync.Map. **Not** production-ready —
// no TTL eviction, no replica fanout — but matches the TicketStore
// contract byte-for-byte so wire tests can run without a Redis dep.
type InMemoryTicketStore struct {
	store sync.Map // key = ticket_id (string), val = Ticket
}

// Issue persists if no collision.
func (s *InMemoryTicketStore) Issue(_ context.Context, t Ticket) error {
	if _, loaded := s.store.LoadOrStore(t.TicketID, t); loaded {
		return fmt.Errorf("%w: %s", ErrTicketAlreadyExists, t.TicketID)
	}
	return nil
}

// Redeem atomically reads-and-deletes.
func (s *InMemoryTicketStore) Redeem(_ context.Context, ticketID string, now time.Time) (Ticket, error) {
	v, ok := s.store.LoadAndDelete(ticketID)
	if !ok {
		return Ticket{}, fmt.Errorf("%w: %s", ErrTicketNotFound, ticketID)
	}
	t := v.(Ticket)
	if !now.Before(t.ExpiresAt) {
		return Ticket{}, fmt.Errorf("%w: %s", ErrTicketExpired, ticketID)
	}
	return t, nil
}
