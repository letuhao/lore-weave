package prompt

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
)

// ProviderResponse is the shape returned by an adapter call. Cycle 31
// L6.J.2 keeps it minimal — opaque JSON body + provider-side metadata.
// V1 does NOT parse the body shape (CLAUDE.md provider gateway
// invariant — the gateway is the only code that may inspect provider
// wire formats).
type ProviderResponse struct {
	// Body — provider-shaped response bytes (e.g., Anthropic Messages
	// completion JSON). Opaque to foundation; callers route to a
	// provider-specific parser in the LLM-gateway sub-program.
	Body json.RawMessage

	// ProviderName + ModelRef — echo from request for audit trail.
	ProviderName string
	ModelRef     string

	// EstimatedTokensIn / EstimatedTokensOut — optional metadata
	// (the adapter MAY supply if known; foundation does not validate).
	EstimatedTokensIn  int
	EstimatedTokensOut int
}

// ProviderAdapter is the per-provider boundary. Cycle 31 L6.J.2 ships
// the trait + a mock impl + a NotConfigured impl that fails closed.
// Concrete adapters (Anthropic, OpenAI, BYOK-local) live in the
// llm-gateway sub-program (NOT in foundation per CLAUDE.md).
//
// **Q-L4D-1 (LOCKED):** ProviderPayload remains OPAQUE. The router
// dispatches on bundle.ProviderName + hands the opaque bytes to the
// registered adapter; foundation NEVER inspects payload shape.
//
// **Provider gateway invariant:** implementations MUST go through
// provider-registry-service for credentials. Direct SDK imports (e.g.,
// importing `github.com/anthropics/anthropic-sdk-go`) in foundation
// code are a code-review reject. The CI lint
// `scripts/prompt-assembly-discipline-lint.sh` (shipped earlier per
// layer plan) enforces this at PR time.
type ProviderAdapter interface {
	// SendPrompt forwards a PromptBundle to the registered provider.
	// Returns the provider response or an error (caller's retry logic
	// is provider-aware; foundation does not retry).
	SendPrompt(ctx context.Context, bundle PromptBundle, cfg ProviderConfig) (ProviderResponse, error)

	// ProviderName returns the canonical name this adapter handles.
	// The ProviderRouter dispatches on this string.
	ProviderName() string
}

// ProviderRouter dispatches a PromptBundle to the matching
// ProviderAdapter based on PromptBundle.ProviderName. Cycle 31 L6.J.2
// ships the trait + a default map-backed impl.
//
// **Why a router instead of a single adapter:** services may register
// multiple providers (BYOK Anthropic + house OpenAI fallback per
// S6-D5 fallback chain). Router dispatch keeps the call-site simple.
type ProviderRouter interface {
	// Route picks an adapter for the bundle's ProviderName and forwards.
	// Returns ErrProviderRouteUnregistered if no adapter is registered.
	Route(ctx context.Context, bundle PromptBundle, cfg ProviderConfig) (ProviderResponse, error)

	// Register adds an adapter to the dispatch map. Subsequent
	// Route calls for the adapter's ProviderName() dispatch to it.
	// Re-registering a name OVERWRITES (last writer wins — services
	// reload config + re-register on hot-reload).
	Register(a ProviderAdapter)
}

// ErrProviderRouteUnregistered is returned when no adapter handles
// the bundle's provider name.
var ErrProviderRouteUnregistered = errors.New("provider_router: no adapter registered")

// DefaultProviderRouter is a map-backed dispatcher. Safe for
// concurrent Route calls after Register settles (typical service
// startup wires all adapters synchronously).
type DefaultProviderRouter struct {
	adapters map[string]ProviderAdapter
}

// NewDefaultProviderRouter constructs an empty router. Services call
// Register for each adapter at startup.
func NewDefaultProviderRouter() *DefaultProviderRouter {
	return &DefaultProviderRouter{adapters: make(map[string]ProviderAdapter)}
}

// Register — see ProviderRouter.
func (r *DefaultProviderRouter) Register(a ProviderAdapter) {
	if r == nil || a == nil {
		return
	}
	if r.adapters == nil {
		r.adapters = make(map[string]ProviderAdapter)
	}
	r.adapters[a.ProviderName()] = a
}

// Route — see ProviderRouter.
func (r *DefaultProviderRouter) Route(ctx context.Context, bundle PromptBundle, cfg ProviderConfig) (ProviderResponse, error) {
	if r == nil || r.adapters == nil {
		return ProviderResponse{}, ErrProviderRouteUnregistered
	}
	if bundle.ProviderName == "" {
		return ProviderResponse{}, errors.New("provider_router: bundle has empty ProviderName")
	}
	a, ok := r.adapters[bundle.ProviderName]
	if !ok {
		return ProviderResponse{}, fmt.Errorf("%w: provider=%q", ErrProviderRouteUnregistered, bundle.ProviderName)
	}
	// Defense in depth — confirm bundle and config agree on provider.
	// A mismatch usually means the resolver returned the wrong config
	// (typically a caller wiring bug). Q-L6H-1: FAIL.
	if cfg.ProviderName != "" && cfg.ProviderName != bundle.ProviderName {
		return ProviderResponse{}, fmt.Errorf("provider_router: bundle=%q config=%q mismatch (caller wiring bug)", bundle.ProviderName, cfg.ProviderName)
	}
	return a.SendPrompt(ctx, bundle, cfg)
}

// MockProviderAdapter is a test impl that echoes a canned response.
// Useful for foundation tests + integration tests that don't need
// real provider behavior.
type MockProviderAdapter struct {
	Name      string
	OnSend    func(ctx context.Context, bundle PromptBundle, cfg ProviderConfig) (ProviderResponse, error)
	CallCount int
}

// SendPrompt — see ProviderAdapter. Increments CallCount + calls
// OnSend (defaults to a canned echo if OnSend is nil).
func (m *MockProviderAdapter) SendPrompt(ctx context.Context, bundle PromptBundle, cfg ProviderConfig) (ProviderResponse, error) {
	m.CallCount++
	if m.OnSend != nil {
		return m.OnSend(ctx, bundle, cfg)
	}
	return ProviderResponse{
		Body:         json.RawMessage(`{"mock":true}`),
		ProviderName: m.Name,
		ModelRef:     cfg.ModelRef,
	}, nil
}

// ProviderName — see ProviderAdapter.
func (m *MockProviderAdapter) ProviderName() string {
	return m.Name
}

// NotConfiguredAdapter is the fail-closed default for providers not
// yet wired by the LLM-gateway sub-program. Every SendPrompt returns
// an error. Services register this for known-but-not-wired providers
// so route attempts FAIL fast instead of nil-derefing.
type NotConfiguredAdapter struct {
	Name string
}

// SendPrompt — fails closed.
func (n *NotConfiguredAdapter) SendPrompt(_ context.Context, _ PromptBundle, _ ProviderConfig) (ProviderResponse, error) {
	return ProviderResponse{}, fmt.Errorf("provider_router: adapter %q not configured (LLM-gateway sub-program owns wiring)", n.Name)
}

// ProviderName — see ProviderAdapter.
func (n *NotConfiguredAdapter) ProviderName() string {
	return n.Name
}
