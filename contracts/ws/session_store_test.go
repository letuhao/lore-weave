package ws

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/google/uuid"
)

func newSession(t *testing.T, now time.Time) *WSSession {
	t.Helper()
	tk := goodTicket(now)
	return NewSession(tk, uuid.New(), now)
}

func TestNewSession_TTL(t *testing.T) {
	now := time.Now()
	s := newSession(t, now)
	if !s.ExpiresAt.Equal(now.Add(SessionTTL)) {
		t.Errorf("ExpiresAt = %v; want %v", s.ExpiresAt, now.Add(SessionTTL))
	}
	if s.IsExpired(now) {
		t.Errorf("IsExpired(now) = true; want false (fresh session)")
	}
	if !s.IsExpired(now.Add(SessionTTL)) {
		t.Errorf("IsExpired(at-expiry) = false; want true")
	}
}

func TestSession_AcceptSeq_StrictMonotonic(t *testing.T) {
	s := newSession(t, time.Now())
	if err := s.AcceptSeq("chat.message", 1); err != nil {
		t.Fatalf("first seq err = %v", err)
	}
	if err := s.AcceptSeq("chat.message", 2); err != nil {
		t.Fatalf("seq=2 err = %v", err)
	}
	if err := s.AcceptSeq("chat.message", 2); err == nil {
		t.Errorf("replay seq=2 = nil; want err")
	}
	if err := s.AcceptSeq("chat.message", 1); err == nil {
		t.Errorf("out-of-order seq=1 = nil; want err")
	}
	// Different type tracks its own counter.
	if err := s.AcceptSeq("presence.update", 7); err != nil {
		t.Errorf("first seq on new type err = %v", err)
	}
}

func TestSession_AcceptSeq_ZeroReserved(t *testing.T) {
	s := newSession(t, time.Now())
	if err := s.AcceptSeq("chat.message", 0); err == nil {
		t.Errorf("seq=0 = nil; want err (reserved for control)")
	}
}

func TestSession_SeenNonce(t *testing.T) {
	s := newSession(t, time.Now())
	now := time.Now()
	if err := s.SeenNonce("n1", now); err != nil {
		t.Fatalf("first SeenNonce err = %v", err)
	}
	if err := s.SeenNonce("n1", now.Add(5*time.Second)); !errors.Is(err, ErrNonceReplay) {
		t.Errorf("replay err = %v; want ErrNonceReplay", err)
	}
	// After 60s + epsilon, sweep evicts; same nonce should be accepted.
	if err := s.SeenNonce("n1", now.Add(120*time.Second)); err != nil {
		t.Errorf("post-expiry SeenNonce err = %v; want nil", err)
	}
}

func TestSession_SeenNonce_EmptyRejected(t *testing.T) {
	s := newSession(t, time.Now())
	if err := s.SeenNonce("", time.Now()); err == nil {
		t.Errorf("empty nonce = nil err; want validation err")
	}
}

func TestSession_Subscribe_LimitFive(t *testing.T) {
	s := newSession(t, time.Now())
	for i := 0; i < 5; i++ {
		topic := uuid.New().String()
		if err := s.Subscribe(topic); err != nil {
			t.Fatalf("Subscribe %d err = %v", i, err)
		}
	}
	if err := s.Subscribe(uuid.New().String()); !errors.Is(err, ErrSubscriptionLimitExceeded) {
		t.Errorf("6th Subscribe err = %v; want ErrSubscriptionLimitExceeded", err)
	}
}

func TestSession_Subscribe_Idempotent(t *testing.T) {
	s := newSession(t, time.Now())
	if err := s.Subscribe("topic.a"); err != nil {
		t.Fatalf("Subscribe err = %v", err)
	}
	if err := s.Subscribe("topic.a"); err != nil {
		t.Errorf("re-Subscribe err = %v; want nil (idempotent)", err)
	}
	if len(s.SubscribedTopics) != 1 {
		t.Errorf("SubscribedTopics len = %d; want 1 (no dup)", len(s.SubscribedTopics))
	}
}

func TestSession_Refresh_HappyPath(t *testing.T) {
	now := time.Now()
	tk := goodTicket(now)
	s := NewSession(tk, uuid.New(), now)
	later := now.Add(10 * time.Minute)
	refresh := goodTicket(later)
	refresh.UserRefID = s.UserRefID
	refresh.OriginHash = s.OriginHash
	refresh.ClientFingerprintHash = s.ClientFingerprint
	refresh.AllowedScopes = s.AllowedScopes // same set
	refresh.AllowedRealities = s.AllowedRealities
	if err := s.Refresh(refresh, later); err != nil {
		t.Fatalf("Refresh err = %v; want nil", err)
	}
	if !s.ExpiresAt.Equal(later.Add(SessionTTL)) {
		t.Errorf("ExpiresAt = %v; want refreshed window", s.ExpiresAt)
	}
}

func TestSession_Refresh_FingerprintMismatch(t *testing.T) {
	now := time.Now()
	s := newSession(t, now)
	refresh := goodTicket(now)
	refresh.UserRefID = s.UserRefID
	refresh.OriginHash = s.OriginHash
	refresh.ClientFingerprintHash = Hash32{99} // mismatch
	refresh.AllowedScopes = s.AllowedScopes
	refresh.AllowedRealities = s.AllowedRealities
	if err := s.Refresh(refresh, now); !errors.Is(err, ErrTicketFingerprintMismatch) {
		t.Errorf("Refresh err = %v; want ErrTicketFingerprintMismatch", err)
	}
}

func TestSession_Refresh_DoesNotWidenScopes(t *testing.T) {
	now := time.Now()
	tk := goodTicket(now)
	tk.AllowedScopes = []string{"chat"}
	tk.AllowedRealities = []uuid.UUID{uuid.New()}
	s := NewSession(tk, uuid.New(), now)

	refresh := goodTicket(now)
	refresh.UserRefID = s.UserRefID
	refresh.OriginHash = s.OriginHash
	refresh.ClientFingerprintHash = s.ClientFingerprint
	refresh.AllowedScopes = []string{"chat", "events"} // try to add scope
	refresh.AllowedRealities = append([]uuid.UUID(nil), s.AllowedRealities...)
	if err := s.Refresh(refresh, now); err != nil {
		t.Fatalf("Refresh err = %v", err)
	}
	if len(s.AllowedScopes) != 1 || s.AllowedScopes[0] != "chat" {
		t.Errorf("AllowedScopes = %v; want [chat] (intersection only)", s.AllowedScopes)
	}
}

func TestSession_Refresh_RejectsRevoke(t *testing.T) {
	now := time.Now()
	s := newSession(t, now)
	refresh := goodTicket(now)
	refresh.UserRefID = s.UserRefID
	refresh.OriginHash = s.OriginHash
	refresh.ClientFingerprintHash = s.ClientFingerprint
	refresh.AllowedScopes = []string{"nonexistent"} // intersection is empty
	refresh.AllowedRealities = s.AllowedRealities
	if err := s.Refresh(refresh, now); err == nil {
		t.Errorf("Refresh = nil; want revoke-detection error")
	}
}

func TestInMemorySessionStore(t *testing.T) {
	st := &InMemorySessionStore{}
	s := newSession(t, time.Now())
	if err := st.Put(context.Background(), s); err != nil {
		t.Fatalf("Put err = %v", err)
	}
	got, err := st.Get(context.Background(), s.ConnectionID)
	if err != nil {
		t.Fatalf("Get err = %v", err)
	}
	if got.ConnectionID != s.ConnectionID {
		t.Errorf("Get returned wrong session")
	}
	if err := st.Delete(context.Background(), s.ConnectionID); err != nil {
		t.Fatalf("Delete err = %v", err)
	}
	if _, err := st.Get(context.Background(), s.ConnectionID); !errors.Is(err, ErrSessionNotFound) {
		t.Errorf("post-delete Get err = %v; want ErrSessionNotFound", err)
	}
}
