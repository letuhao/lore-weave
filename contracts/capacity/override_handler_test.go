package capacity

import (
	"context"
	"errors"
	"strings"
	"testing"
	"time"
)

func mustGrantOverride(t *testing.T, s *InMemOverrideStore, o Override) {
	t.Helper()
	if err := s.Grant(o); err != nil {
		t.Fatalf("Grant: %v", err)
	}
}

func validOverride(now time.Time) Override {
	return Override{
		ServiceName: "publisher",
		GrantedBy:   "alice@loreweave.dev",
		GrantedAt:   now,
		ExpiresAt:   now.Add(24 * time.Hour),
		Reason:      "incident-1234 fanout investigation requires extra replicas",
		Action:      OverrideAllow,
	}
}

func TestOverride_Validate_HappyPath(t *testing.T) {
	o := validOverride(time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC))
	if err := o.Validate(); err != nil {
		t.Fatalf("Validate: %v", err)
	}
}

func TestOverride_Validate_Rejections(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	cases := []struct {
		name string
		mut  func(*Override)
	}{
		{"empty service", func(o *Override) { o.ServiceName = "" }},
		{"empty granter", func(o *Override) { o.GrantedBy = "" }},
		{"short reason", func(o *Override) { o.Reason = "too short" }},
		{"bad action", func(o *Override) { o.Action = "deny" }},
		{"zero expires", func(o *Override) { o.ExpiresAt = time.Time{} }},
		{"expires before granted", func(o *Override) { o.ExpiresAt = now.Add(-time.Hour) }},
		{"ttl > 24h", func(o *Override) { o.ExpiresAt = now.Add(25 * time.Hour) }},
	}
	for _, c := range cases {
		t.Run(c.name, func(t *testing.T) {
			o := validOverride(now)
			c.mut(&o)
			if err := o.Validate(); !errors.Is(err, ErrInvalidOverride) {
				t.Fatalf("expected ErrInvalidOverride; got %v", err)
			}
		})
	}
}

func TestOverride_IsActive_WithinWindow(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	o := validOverride(now)
	if !o.IsActive(now) {
		t.Fatalf("override should be active at GrantedAt")
	}
	if !o.IsActive(now.Add(23*time.Hour + 59*time.Minute)) {
		t.Fatalf("override should be active just inside expiration")
	}
}

func TestOverride_IsActive_AutoExpire24h(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	o := validOverride(now)
	if o.IsActive(now.Add(24 * time.Hour)) {
		t.Fatalf("override should NOT be active AT expiration")
	}
	if o.IsActive(now.Add(48 * time.Hour)) {
		t.Fatalf("override should NOT be active well past expiration")
	}
}

func TestOverrideHandler_IsAllowed_CachesAndExpires(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	clock := now
	store := NewInMemOverrideStore()
	mustGrantOverride(t, store, validOverride(now))

	h := NewOverrideHandler(store,
		WithClock(func() time.Time { return clock }),
		WithCacheTTL(60*time.Second),
	)

	ok, _ := h.IsAllowed(context.Background(), "publisher")
	if !ok {
		t.Fatalf("publisher should be allowed at grant time")
	}
	if hits, _, _ := h.Stats(); hits != 1 {
		t.Fatalf("expected cache hit=1; got %d", hits)
	}

	// Tick 30s — still within cache TTL, no store re-query.
	clock = clock.Add(30 * time.Second)
	if ok, _ := h.IsAllowed(context.Background(), "publisher"); !ok {
		t.Fatalf("publisher should still be allowed within cache TTL")
	}

	// Tick to 25h — cache stale + override expired → not allowed.
	clock = clock.Add(25 * time.Hour)
	if ok, _ := h.IsAllowed(context.Background(), "publisher"); ok {
		t.Fatalf("publisher should NOT be allowed 25h after grant (Q-L6G-1 24h cap)")
	}
}

func TestOverrideHandler_StoreError_FailsClosed(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	clock := now
	h := NewOverrideHandler(failingStore{},
		WithClock(func() time.Time { return clock }),
	)
	ok, _ := h.IsAllowed(context.Background(), "publisher")
	if ok {
		t.Fatalf("flaky store must fail-closed (no allowed=true on error)")
	}
	if _, _, storeErr := h.Stats(); storeErr != 1 {
		t.Fatalf("storeErr counter not incremented")
	}
}

func TestInMemStore_GrantThenListFiltersExpired(t *testing.T) {
	now := time.Date(2026, 5, 29, 12, 0, 0, 0, time.UTC)
	s := NewInMemOverrideStore()

	// Grant active.
	active := validOverride(now)
	mustGrantOverride(t, s, active)

	// Grant expired.
	expired := validOverride(now.Add(-48 * time.Hour))
	expired.ServiceName = "world-service"
	mustGrantOverride(t, s, expired)

	got, err := s.List(context.Background(), now)
	if err != nil {
		t.Fatalf("List: %v", err)
	}
	if len(got) != 1 || got[0].ServiceName != "publisher" {
		t.Fatalf("expected 1 active row for publisher; got %v", got)
	}
	if total := len(s.All()); total != 2 {
		t.Fatalf("All() should preserve audit history; got %d", total)
	}
}

func TestInMemStore_GrantRejectsInvalid(t *testing.T) {
	s := NewInMemOverrideStore()
	bad := Override{ServiceName: ""}
	err := s.Grant(bad)
	if !errors.Is(err, ErrInvalidOverride) {
		t.Fatalf("expected ErrInvalidOverride; got %v", err)
	}
	if !strings.Contains(err.Error(), "service_name") {
		t.Fatalf("expected service_name in error; got %v", err)
	}
}

// failingStore always returns an error — used for fail-closed test.
type failingStore struct{}

func (failingStore) List(_ context.Context, _ time.Time) ([]Override, error) {
	return nil, errors.New("simulated meta-db unavailable")
}
