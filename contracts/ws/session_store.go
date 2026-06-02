package ws

import (
	"context"
	"errors"
	"fmt"
	"sync"
	"time"

	"github.com/google/uuid"
)

// SessionTTL is the canonical V1 window per S12 §12AB.3. WSSession
// independent of user JWT expiry. Clients refresh via ws.refresh
// ~2 min before expiry (S12 client UX note).
const SessionTTL = 15 * time.Minute

// WSSession is the per-connection state the gateway holds for the
// life of the WS connection. Mirrors S12 §12AB.3 Go shape.
//
// **Server-side only.** This struct is NEVER serialized to the client;
// clients see only the side-effects (subscription confirmations,
// rate-limit frames, close codes).
type WSSession struct {
	// ConnectionID — unique per accepted connection (UUIDv4). Used as
	// the join key for the per-connection Redis token bucket
	// (lw:rl:ws:<connection_id>) and the connection_events audit
	// rows (§12AB.9).
	ConnectionID uuid.UUID

	// UserRefID — bearer's user ref ID (carried over from ticket).
	UserRefID uuid.UUID

	// AllowedRealities + AllowedScopes — scope set captured at handshake.
	// Refresh does NOT widen these (defense: a compromised refresh
	// ticket cannot grant new scopes).
	AllowedRealities []uuid.UUID
	AllowedScopes    []string

	// OriginHash + ClientFingerprint — pinned at handshake; mid-connection
	// checks re-compute and compare (L4 + L6 defenses). Hash32 for type-parity
	// with Ticket (this struct is server-side only / never serialized, so the
	// base64 marshaling is irrelevant here — the type just keeps == comparisons
	// and the NewSession assignment from the ticket clean).
	OriginHash        Hash32
	ClientFingerprint Hash32

	// SubscribedTopics — current subscription set (server tracks for
	// fanout). Foundation does NOT constrain TopicRef shape — strings.
	SubscribedTopics []string

	// ExpiresAt — session-level expiry (15m from open / last refresh).
	// Distinct from per-Subscription expiry (none) and from the
	// per-connection token bucket (Redis TTL).
	ExpiresAt time.Time

	// LastRefreshAt — wall clock of the last successful ws.refresh
	// (zero if never refreshed).
	LastRefreshAt time.Time

	// SeqCounter — per-Type monotonic counter. Inbound seq must equal
	// expected (within tolerance per S12 §12AB.7); outbound is
	// monotonically incremented by the sender.
	//
	// Protected by Mu — direct field access is forbidden outside this
	// package's helper methods. Tests may use the helper.
	SeqCounter map[string]uint64

	// SeenNonces — TTL set of nonces seen in the last 60s. Map for
	// O(1) lookups; bounded by S12 §12AB.6 rate limits + the 60s
	// nonce window. Use [WSSession.SeenNonce] to check + record.
	SeenNonces map[string]time.Time

	// Mu protects SeqCounter + SeenNonces + SubscribedTopics +
	// ExpiresAt + LastRefreshAt. The session is touched concurrently
	// by the inbound reader goroutine + outbound writer goroutine +
	// admin control-channel handler.
	Mu sync.Mutex
}

// NewSession constructs a session from a redeemed ticket + new
// connection ID + wall-clock now. Caller must hold the ticket.Validate
// result before calling this.
func NewSession(t Ticket, connID uuid.UUID, now time.Time) *WSSession {
	return &WSSession{
		ConnectionID:      connID,
		UserRefID:         t.UserRefID,
		AllowedRealities:  append([]uuid.UUID(nil), t.AllowedRealities...),
		AllowedScopes:     append([]string(nil), t.AllowedScopes...),
		OriginHash:        t.OriginHash,
		ClientFingerprint: t.ClientFingerprintHash,
		SubscribedTopics:  nil,
		ExpiresAt:         now.Add(SessionTTL),
		SeqCounter:        make(map[string]uint64),
		SeenNonces:        make(map[string]time.Time),
	}
}

// IsExpired returns true if now is at or past ExpiresAt. Caller MUST
// take Mu before calling — this is a leaf helper that does NOT lock.
func (s *WSSession) IsExpired(now time.Time) bool {
	return !now.Before(s.ExpiresAt)
}

// Refresh extends the session to now + SessionTTL using a fresh ticket.
// Returns ErrTicketFingerprintMismatch if the refresh ticket's
// fingerprint doesn't match the session's pinned fingerprint (defense
// against ticket theft across devices).
//
// Per S12 §12AB.3 + L4 (Q-L6-3): refresh MUST NOT widen scopes; this
// helper takes the SCOPE INTERSECTION of the session's current
// AllowedScopes and the refresh ticket's AllowedScopes (similar for
// realities). A refresh that would shrink to zero is rejected
// (signals a server-side state-revoke; the gateway should close 4002).
func (s *WSSession) Refresh(refreshTicket Ticket, now time.Time) error {
	if err := refreshTicket.Validate(now); err != nil {
		return err
	}
	if refreshTicket.ClientFingerprintHash != s.ClientFingerprint {
		return ErrTicketFingerprintMismatch
	}
	if refreshTicket.OriginHash != s.OriginHash {
		return ErrTicketOriginMismatch
	}
	if refreshTicket.UserRefID != s.UserRefID {
		return fmt.Errorf("ws: refresh ticket user_ref_id mismatch")
	}

	s.Mu.Lock()
	defer s.Mu.Unlock()

	// Intersect scopes (refresh cannot widen).
	newScopes := intersectStrings(s.AllowedScopes, refreshTicket.AllowedScopes)
	newRealities := intersectUUIDs(s.AllowedRealities, refreshTicket.AllowedRealities)
	if len(newScopes) == 0 || len(newRealities) == 0 {
		return errors.New("ws: refresh would empty scopes/realities (likely server-side revoke)")
	}
	s.AllowedScopes = newScopes
	s.AllowedRealities = newRealities
	s.ExpiresAt = now.Add(SessionTTL)
	s.LastRefreshAt = now
	return nil
}

// AcceptSeq atomically validates + records an inbound seq for the
// given message Type. Returns an error if the seq is out-of-order
// or duplicate (within tolerance 5 per S12 §12AB.7).
//
// V1 implementation: strictly monotonic (no out-of-order window —
// keep it simple; the §12AB.7 tolerance window adds complexity that
// only matters under reorder-friendly transports we don't ship V1).
func (s *WSSession) AcceptSeq(msgType string, incoming uint64) error {
	s.Mu.Lock()
	defer s.Mu.Unlock()
	last := s.SeqCounter[msgType]
	// First message on this type: any non-zero seq accepted; subsequent
	// must strictly increase.
	if last == 0 {
		if incoming == 0 {
			return fmt.Errorf("ws: seq=0 reserved for control messages; type=%q", msgType)
		}
		s.SeqCounter[msgType] = incoming
		return nil
	}
	if incoming <= last {
		return fmt.Errorf("ws: seq replay or out-of-order: type=%q last=%d incoming=%d",
			msgType, last, incoming)
	}
	s.SeqCounter[msgType] = incoming
	return nil
}

// SeenNonce atomically checks and records a nonce. Returns
// ErrNonceReplay when the nonce was seen within the last 60s.
// Caller supplies `now` so tests can deterministically expire entries.
func (s *WSSession) SeenNonce(nonce string, now time.Time) error {
	if nonce == "" {
		return errors.New("ws: empty nonce")
	}
	s.Mu.Lock()
	defer s.Mu.Unlock()
	// Sweep expired entries each call — O(N) over the active set;
	// bounded by S6 rate limits.
	cutoff := now.Add(-60 * time.Second)
	for k, t := range s.SeenNonces {
		if t.Before(cutoff) {
			delete(s.SeenNonces, k)
		}
	}
	if _, dup := s.SeenNonces[nonce]; dup {
		return fmt.Errorf("%w: %s", ErrNonceReplay, nonce)
	}
	s.SeenNonces[nonce] = now
	return nil
}

// Subscribe atomically records a subscription. Returns
// ErrSubscriptionLimitExceeded if the per-connection cap (S12 §12AB.6
// — 5 topics) would be exceeded. Idempotent for already-subscribed
// topics.
func (s *WSSession) Subscribe(topic string) error {
	if topic == "" {
		return errors.New("ws: empty topic")
	}
	s.Mu.Lock()
	defer s.Mu.Unlock()
	for _, t := range s.SubscribedTopics {
		if t == topic {
			return nil // already subscribed
		}
	}
	if len(s.SubscribedTopics) >= 5 {
		return fmt.Errorf("%w: max 5 topics per connection", ErrSubscriptionLimitExceeded)
	}
	s.SubscribedTopics = append(s.SubscribedTopics, topic)
	return nil
}

// Sentinel errors for session-state operations.
var (
	ErrNonceReplay               = errors.New("ws: nonce replay")
	ErrSubscriptionLimitExceeded = errors.New("ws: subscription limit exceeded")
)

// SessionStore is the per-connection state cache. Production wires a
// per-gateway in-memory map (sessions live on the gateway replica that
// owns the connection); tests use the InMemorySessionStore.
type SessionStore interface {
	Put(ctx context.Context, s *WSSession) error
	Get(ctx context.Context, connectionID uuid.UUID) (*WSSession, error)
	Delete(ctx context.Context, connectionID uuid.UUID) error
}

// InMemorySessionStore is the reference impl + foundation test double.
type InMemorySessionStore struct {
	m sync.Map // key = connection_id (uuid.UUID), val = *WSSession
}

// Put records a session.
func (st *InMemorySessionStore) Put(_ context.Context, s *WSSession) error {
	if s == nil {
		return errors.New("ws: nil session")
	}
	st.m.Store(s.ConnectionID, s)
	return nil
}

// Get returns the session or ErrSessionNotFound.
func (st *InMemorySessionStore) Get(_ context.Context, id uuid.UUID) (*WSSession, error) {
	v, ok := st.m.Load(id)
	if !ok {
		return nil, fmt.Errorf("%w: %s", ErrSessionNotFound, id)
	}
	return v.(*WSSession), nil
}

// Delete removes the session (idempotent — missing IDs return nil).
func (st *InMemorySessionStore) Delete(_ context.Context, id uuid.UUID) error {
	st.m.Delete(id)
	return nil
}

// ErrSessionNotFound is the canonical missing-session error.
var ErrSessionNotFound = errors.New("ws: session not found")

// ── small set helpers ──────────────────────────────────────────────────

func intersectStrings(a, b []string) []string {
	set := make(map[string]struct{}, len(b))
	for _, x := range b {
		set[x] = struct{}{}
	}
	out := make([]string, 0, len(a))
	for _, x := range a {
		if _, ok := set[x]; ok {
			out = append(out, x)
		}
	}
	return out
}

func intersectUUIDs(a, b []uuid.UUID) []uuid.UUID {
	set := make(map[uuid.UUID]struct{}, len(b))
	for _, x := range b {
		set[x] = struct{}{}
	}
	out := make([]uuid.UUID, 0, len(a))
	for _, x := range a {
		if _, ok := set[x]; ok {
			out = append(out, x)
		}
	}
	return out
}
