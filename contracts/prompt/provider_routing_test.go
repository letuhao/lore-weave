package prompt

import (
	"context"
	"encoding/json"
	"errors"
	"testing"
	"time"
)

func TestProviderConfig_Validate(t *testing.T) {
	cases := []struct {
		name    string
		cfg     ProviderConfig
		wantErr bool
	}{
		{"empty provider", ProviderConfig{ModelRef: "m", EndpointURL: "https://x"}, true},
		{"empty model", ProviderConfig{ProviderName: "p", EndpointURL: "https://x"}, true},
		{"empty endpoint", ProviderConfig{ProviderName: "p", ModelRef: "m"}, true},
		{"valid", ProviderConfig{ProviderName: "p", ModelRef: "m", EndpointURL: "https://x"}, false},
	}
	for _, c := range cases {
		err := c.cfg.Validate()
		if (err != nil) != c.wantErr {
			t.Fatalf("%s: wantErr=%v got %v", c.name, c.wantErr, err)
		}
	}
}

func TestMockProviderResolver_NotFound(t *testing.T) {
	m := &MockProviderResolver{Entries: map[string]ProviderConfig{}}
	_, err := m.Resolve(context.Background(), "unknown", "reality-1")
	if !errors.Is(err, ErrProviderNotFound) {
		t.Fatalf("expected ErrProviderNotFound, got %v", err)
	}
}

func TestMockProviderResolver_Found(t *testing.T) {
	m := &MockProviderResolver{Entries: map[string]ProviderConfig{
		"m1": {ProviderName: "anthropic", ModelRef: "claude-3-5-sonnet", EndpointURL: "https://api.anthropic.com"},
	}}
	cfg, err := m.Resolve(context.Background(), "m1", "reality-1")
	if err != nil {
		t.Fatalf("unexpected error: %v", err)
	}
	if cfg.ProviderName != "anthropic" {
		t.Fatalf("wrong provider: %q", cfg.ProviderName)
	}
}

func TestCachedProviderResolver_CachesWithinTTL(t *testing.T) {
	calls := 0
	inner := &MockProviderResolver{Entries: map[string]ProviderConfig{
		"m1": {ProviderName: "anthropic", ModelRef: "claude", EndpointURL: "https://x"},
	}}
	// Wrap inner to count calls.
	counter := &countingResolver{inner: inner, calls: &calls}

	cache := NewCachedProviderResolver(counter, 1*time.Minute)
	now := time.Unix(1_700_000_000, 0)
	cache.Now = func() time.Time { return now }

	for i := 0; i < 5; i++ {
		_, err := cache.Resolve(context.Background(), "m1", "r1")
		if err != nil {
			t.Fatalf("resolve err: %v", err)
		}
	}
	if calls != 1 {
		t.Fatalf("expected 1 inner call (cached), got %d", calls)
	}
}

func TestCachedProviderResolver_RefreshesAfterTTL(t *testing.T) {
	calls := 0
	inner := &MockProviderResolver{Entries: map[string]ProviderConfig{
		"m1": {ProviderName: "anthropic", ModelRef: "claude", EndpointURL: "https://x"},
	}}
	counter := &countingResolver{inner: inner, calls: &calls}

	cache := NewCachedProviderResolver(counter, 1*time.Minute)
	t0 := time.Unix(1_700_000_000, 0)
	cache.Now = func() time.Time { return t0 }
	if _, err := cache.Resolve(context.Background(), "m1", "r1"); err != nil {
		t.Fatalf("first resolve: %v", err)
	}
	// Advance past TTL.
	cache.Now = func() time.Time { return t0.Add(2 * time.Minute) }
	if _, err := cache.Resolve(context.Background(), "m1", "r1"); err != nil {
		t.Fatalf("post-TTL resolve: %v", err)
	}
	if calls != 2 {
		t.Fatalf("expected 2 inner calls (cache expired), got %d", calls)
	}
}

func TestCachedProviderResolver_DefaultTTLIs5Min(t *testing.T) {
	// Acceptance: cache TTL matches cycle 1 L1.B consent.go 5min.
	if DefaultProviderTTL != 5*time.Minute {
		t.Fatalf("expected DefaultProviderTTL = 5min, got %v", DefaultProviderTTL)
	}
	c := NewCachedProviderResolver(&MockProviderResolver{}, 0)
	if c.TTL != 5*time.Minute {
		t.Fatalf("expected 5min default when ttl=0, got %v", c.TTL)
	}
}

type countingResolver struct {
	inner ProviderResolver
	calls *int
}

func (c *countingResolver) Resolve(ctx context.Context, modelID, realityID string) (ProviderConfig, error) {
	*c.calls++
	return c.inner.Resolve(ctx, modelID, realityID)
}

func TestDefaultProviderRouter_RoutesToCorrectAdapter(t *testing.T) {
	r := NewDefaultProviderRouter()
	a := &MockProviderAdapter{Name: "anthropic"}
	b := &MockProviderAdapter{Name: "openai"}
	r.Register(a)
	r.Register(b)

	bundle := PromptBundle{
		ProviderPayload: json.RawMessage(`{"x":1}`),
		ProviderName:    "openai",
		ModelRef:        "gpt-4",
		ContextHash:     [32]byte{1},
		TemplateID:      "t",
		TemplateVersion: 1,
	}
	cfg := ProviderConfig{ProviderName: "openai", ModelRef: "gpt-4", EndpointURL: "https://x"}

	_, err := r.Route(context.Background(), bundle, cfg)
	if err != nil {
		t.Fatalf("route err: %v", err)
	}
	if a.CallCount != 0 || b.CallCount != 1 {
		t.Fatalf("dispatch wrong: anthropic=%d openai=%d", a.CallCount, b.CallCount)
	}
}

func TestDefaultProviderRouter_UnregisteredFails(t *testing.T) {
	r := NewDefaultProviderRouter()
	bundle := PromptBundle{ProviderName: "missing"}
	_, err := r.Route(context.Background(), bundle, ProviderConfig{})
	if !errors.Is(err, ErrProviderRouteUnregistered) {
		t.Fatalf("expected ErrProviderRouteUnregistered, got %v", err)
	}
}

func TestDefaultProviderRouter_BundleConfigMismatchFails(t *testing.T) {
	r := NewDefaultProviderRouter()
	a := &MockProviderAdapter{Name: "anthropic"}
	r.Register(a)
	bundle := PromptBundle{ProviderName: "anthropic"}
	cfg := ProviderConfig{ProviderName: "openai", ModelRef: "x", EndpointURL: "https://x"}
	_, err := r.Route(context.Background(), bundle, cfg)
	if err == nil {
		t.Fatal("expected error on provider mismatch")
	}
}

func TestNotConfiguredAdapter_FailsClosed(t *testing.T) {
	n := &NotConfiguredAdapter{Name: "byok_local"}
	_, err := n.SendPrompt(context.Background(), PromptBundle{}, ProviderConfig{})
	if err == nil {
		t.Fatal("expected NotConfiguredAdapter to FAIL closed")
	}
}

func TestProviderRouter_NoDirectSDKImports(t *testing.T) {
	// Static contract: foundation must NOT import provider SDKs.
	// This is a documentation test — the CI lint
	// scripts/prompt-assembly-discipline-lint.sh enforces at PR time.
	// We assert here as a behavioral test that the foundation router
	// works without any vendor SDK.
	_ = NewDefaultProviderRouter() // compiles without anthropic-sdk-go etc.
}
