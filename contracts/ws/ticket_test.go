package ws

import (
	"context"
	"errors"
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
		OriginHash:            [32]byte{1, 2, 3, 4},
		ClientFingerprintHash: [32]byte{5, 6, 7, 8},
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
		{"origin", func(t *Ticket) { t.OriginHash = [32]byte{} }},
		{"fingerprint", func(t *Ticket) { t.ClientFingerprintHash = [32]byte{} }},
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
	if tk.BindsToOrigin([32]byte{99}) {
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
