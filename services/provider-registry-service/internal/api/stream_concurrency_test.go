package api

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/google/uuid"
	"github.com/loreweave/provider-registry-service/internal/billing"
	"github.com/loreweave/provider-registry-service/internal/provider"
	"github.com/loreweave/provider-registry-service/internal/ratelimit"
)

type alwaysBusyGovernor struct{}

func (alwaysBusyGovernor) Acquire(context.Context, context.Context, string, int) (ratelimit.ProviderPermit, error) {
	return nil, ratelimit.ErrGovernorTimeout
}

type countingPermit struct {
	ctx      context.Context
	released *int
}

func (p countingPermit) Context() context.Context { return p.ctx }
func (p countingPermit) Release()                 { *p.released++ }

type countingGovernor struct{ acquired, released int }

func (g *countingGovernor) Acquire(_ context.Context, callCtx context.Context, _ string, _ int) (ratelimit.ProviderPermit, error) {
	g.acquired++
	return countingPermit{ctx: callCtx, released: &g.released}, nil
}

func TestStreamChatEmitsCanonicalRateLimitCode(t *testing.T) {
	rr := httptest.NewRecorder()
	guard := &streamGuard{op: "chat", pricing: testPricing(), startedAt: time.Now()}
	retryAfter := 3.5
	adapter := &failingStreamAdapter{err: &provider.ErrUpstreamRateLimited{StatusCode: 429, Body: "temporary limit", RetryAfterS: &retryAfter}}
	req := httptest.NewRequest(http.MethodPost, "/v1/llm/stream", nil)

	(&Server{}).streamChat(req, rr, rr, adapter, "", "", "model-ref", streamRequest{
		Messages: []any{map[string]any{"role": "user", "content": "safe test"}},
	}, guard)

	body := rr.Body.String()
	if !strings.Contains(body, `"code":"LLM_RATE_LIMITED"`) || !strings.Contains(body, `"retry_after_s":3.5`) {
		t.Fatalf("expected typed rate-limit SSE with Retry-After, got %q", body)
	}
	if guard.requestStatus != "provider_error" {
		t.Fatalf("requestStatus = %q, want provider_error", guard.requestStatus)
	}
}

func TestStreamAdmissionPermitReleasedAfterAllowedCall(t *testing.T) {
	gov := &countingGovernor{}
	srv := &Server{
		providerGovernor:       gov,
		providerDefaultMax:     8,
		providerAcquireTimeout: time.Second,
	}
	callCtx, cancel := context.WithCancel(context.Background())
	defer cancel()
	permit, err := srv.acquireProviderSlot(context.Background(), callCtx, "credential", 2)
	if err != nil {
		t.Fatalf("acquire: %v", err)
	}
	if gov.acquired != 1 || gov.released != 0 {
		t.Fatalf("before release acquired/released=%d/%d", gov.acquired, gov.released)
	}
	permit.Release()
	if gov.released != 1 {
		t.Fatalf("release count=%d want 1", gov.released)
	}
}

func TestAcquireProviderSlotReturnsBusyWhenCapIsReached(t *testing.T) {
	srv := &Server{
		providerGovernor:       alwaysBusyGovernor{},
		providerDefaultMax:     8,
		providerAcquireTimeout: time.Millisecond,
	}
	if _, err := srv.acquireProviderSlot(context.Background(), context.Background(), uuid.NewString(), 1); !errors.Is(err, ratelimit.ErrGovernorTimeout) {
		t.Fatalf("Acquire error = %v, want governor timeout", err)
	}
}

type failingStreamAdapter struct {
	provider.Adapter
	err error
}

func (f *failingStreamAdapter) Stream(context.Context, string, string, string, map[string]any, provider.EmitFn) error {
	return f.err
}

func testPricing() billing.Pricing {
	return billing.Pricing{InputPerMTok: ptr(1), OutputPerMTok: ptr(1)}
}
