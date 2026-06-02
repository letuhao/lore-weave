package ws

import (
	"context"
	"encoding/base64"
	"encoding/json"
	"errors"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
)

func goodTicket(now time.Time) Ticket {
	return Ticket{
		TicketID:              "wst_" + uuid.New().String(),
		UserRefID:             uuid.New(),
		AllowedRealities:      []uuid.UUID{uuid.New()},
		AllowedScopes:         []string{"chat", "presence"},
		OriginHash:            Hash32{1, 2, 3, 4},
		ClientFingerprintHash: Hash32{5, 6, 7, 8},
		IssuedAt:              now,
		ExpiresAt:             now.Add(TicketTTL),
	}
}

func TestTicket_Validate_Happy(t *testing.T) {
	now := time.Now()
	tk := goodTicket(now)
	if err := tk.Validate(now); err != nil {
		t.Fatalf("Validate err = %v; want nil", err)
	}
}

func TestTicket_Validate_Required(t *testing.T) {
	now := time.Now()
	cases := []struct {
		name   string
		mutate func(*Ticket)
	}{
		{"id", func(t *Ticket) { t.TicketID = "" }},
		{"user", func(t *Ticket) { t.UserRefID = uuid.Nil }},
		{"origin", func(t *Ticket) { t.OriginHash = Hash32{} }},
		{"fingerprint", func(t *Ticket) { t.ClientFingerprintHash = Hash32{} }},
		{"iat", func(t *Ticket) { t.IssuedAt = time.Time{} }},
		{"exp", func(t *Ticket) { t.ExpiresAt = time.Time{} }},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			tk := goodTicket(now)
			c.mutate(&tk)
			if err := tk.Validate(now); err == nil {
				t.Fatalf("Validate = nil; want missing-%s error", c.name)
			}
		})
	}
}

func TestTicket_Validate_Expired(t *testing.T) {
	now := time.Now()
	tk := goodTicket(now)
	if err := tk.Validate(now.Add(2 * TicketTTL)); err == nil {
		t.Fatalf("Validate = nil; want expired error")
	}
}

func TestTicket_Validate_TTLWindowSanity(t *testing.T) {
	now := time.Now()
	tk := goodTicket(now)
	tk.ExpiresAt = now.Add(10 * TicketTTL) // way too wide
	if err := tk.Validate(now); err == nil {
		t.Fatalf("Validate = nil; want TTL window sanity error")
	}
}

func TestTicket_BindsToOriginAndFingerprint(t *testing.T) {
	tk := goodTicket(time.Now())
	if !tk.BindsToOrigin(tk.OriginHash) {
		t.Errorf("BindsToOrigin self-match = false; want true")
	}
	if tk.BindsToOrigin(Hash32{99}) {
		t.Errorf("BindsToOrigin foreign = true; want false")
	}
	if !tk.BindsToFingerprint(tk.ClientFingerprintHash) {
		t.Errorf("BindsToFingerprint self-match = false; want true")
	}
}

func TestInMemoryTicketStore_IssueRedeem(t *testing.T) {
	st := &InMemoryTicketStore{}
	now := time.Now()
	tk := goodTicket(now)
	if err := st.Issue(context.Background(), tk); err != nil {
		t.Fatalf("Issue err = %v", err)
	}
	got, err := st.Redeem(context.Background(), tk.TicketID, now)
	if err != nil {
		t.Fatalf("Redeem err = %v", err)
	}
	if got.UserRefID != tk.UserRefID {
		t.Errorf("Redeem user = %v; want %v", got.UserRefID, tk.UserRefID)
	}
	// Second redeem must fail (one-shot).
	if _, err := st.Redeem(context.Background(), tk.TicketID, now); !errors.Is(err, ErrTicketNotFound) {
		t.Errorf("second Redeem err = %v; want ErrTicketNotFound", err)
	}
}

func TestInMemoryTicketStore_Collision(t *testing.T) {
	st := &InMemoryTicketStore{}
	tk := goodTicket(time.Now())
	if err := st.Issue(context.Background(), tk); err != nil {
		t.Fatalf("first Issue err = %v", err)
	}
	if err := st.Issue(context.Background(), tk); !errors.Is(err, ErrTicketAlreadyExists) {
		t.Errorf("second Issue err = %v; want ErrTicketAlreadyExists", err)
	}
}

func TestInMemoryTicketStore_Expired(t *testing.T) {
	st := &InMemoryTicketStore{}
	now := time.Now()
	tk := goodTicket(now)
	_ = st.Issue(context.Background(), tk)
	_, err := st.Redeem(context.Background(), tk.TicketID, now.Add(2*TicketTTL))
	if !errors.Is(err, ErrTicketExpired) {
		t.Errorf("Redeem expired err = %v; want ErrTicketExpired", err)
	}
}

// TestTicket_HashWireFormat_Base64 pins the D-WS-TICKET-WIRE (068) fix: the
// ticket hashes MUST marshal as base64 STRINGS (ws/v1.yaml format: byte), not
// the Go-default [N]byte int-array, and MUST round-trip back byte-for-byte.
func TestTicket_HashWireFormat_Base64(t *testing.T) {
	tk := goodTicket(time.Now())
	raw, err := json.Marshal(tk)
	if err != nil {
		t.Fatalf("marshal err = %v", err)
	}
	js := string(raw)
	wantOrigin := base64.StdEncoding.EncodeToString(tk.OriginHash[:])
	if !strings.Contains(js, `"origin_hash":"`+wantOrigin+`"`) {
		t.Fatalf("origin_hash not a base64 string in JSON:\n%s", js)
	}
	if strings.Contains(js, `"origin_hash":[`) {
		t.Fatalf("origin_hash marshaled as int-array (068 regression):\n%s", js)
	}
	var got Ticket
	if err := json.Unmarshal(raw, &got); err != nil {
		t.Fatalf("unmarshal err = %v", err)
	}
	if got.OriginHash != tk.OriginHash || got.ClientFingerprintHash != tk.ClientFingerprintHash {
		t.Fatalf("hash round-trip mismatch: origin %x→%x fp %x→%x",
			tk.OriginHash, got.OriginHash, tk.ClientFingerprintHash, got.ClientFingerprintHash)
	}
}

// TestHash32_UnmarshalEnforces32Bytes proves UnmarshalJSON rejects a
// wrong-length or non-base64 digest rather than silently zero-padding.
func TestHash32_UnmarshalEnforces32Bytes(t *testing.T) {
	var h Hash32
	for _, n := range []int{0, 31, 33, 64} {
		s := base64.StdEncoding.EncodeToString(make([]byte, n))
		if err := h.UnmarshalJSON([]byte(`"` + s + `"`)); err == nil {
			t.Errorf("UnmarshalJSON accepted %d-byte hash; want error", n)
		}
	}
	if err := h.UnmarshalJSON([]byte(`"!!! not base64 !!!"`)); err == nil {
		t.Error("UnmarshalJSON accepted non-base64; want error")
	}
	valid := base64.StdEncoding.EncodeToString(make([]byte, 32))
	if err := h.UnmarshalJSON([]byte(`"` + valid + `"`)); err != nil {
		t.Errorf("UnmarshalJSON rejected valid 32-byte hash: %v", err)
	}
}

// TestHash32_GoldenLiteralCrossImpl pins the 132 cross-impl golden fixture in
// Go: base64(StdEncoding) of bytes 0..31 → the EXACT literal also asserted by
// the gateway redis-ticket-store.spec.ts + the game-server ticket-store.test.ts.
// Makes the golden fixture genuinely tri-impl (Go / gateway / game-server), so
// a silent StdEncoding-vs-URLEncoding drift in ANY impl is caught (077 LOW-1).
func TestHash32_GoldenLiteralCrossImpl(t *testing.T) {
	const golden = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
	var h Hash32
	for i := range h {
		h[i] = byte(i)
	}
	b, err := json.Marshal(h)
	if err != nil {
		t.Fatal(err)
	}
	if string(b) != `"`+golden+`"` {
		t.Fatalf("Hash32 golden literal mismatch: got %s want %q", b, golden)
	}
}
