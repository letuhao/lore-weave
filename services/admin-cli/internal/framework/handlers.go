// handlers.go — registry of NO-OP handlers used by the framework when a real
// implementation has not yet wired in.
//
// Cycle 36 ships every command in registry/*.yaml with a SKELETON handler so
// the framework can dispatch + the audit row gets written. Real per-command
// I/O wires in subsequent cycles (the carry_forward_cycle field in the YAML
// names the cycle that owns the real implementation; e.g. cycle 14 for
// rebuild-projection, cycle 37 for incident-bot integration).
//
// CONSOLIDATION pattern (Q-L7A-2): the existing per-command implementations
// in services/admin-cli/commands/{capacity_override.go, rebuild_projection.go,
// catastrophic_rebuild.go} are NOT duplicated here. The CLI wires them up
// through commands.Register() in cmd/admin/main.go. This package holds only
// the registry-default no-op so an un-wired command produces a structured
// "not-yet-wired" outcome instead of a panic.
package framework

import (
	"context"
	"fmt"
	"sync"
)

// HandlerRegistry maps a command Name → Handler.
type HandlerRegistry struct {
	mu sync.RWMutex
	m  map[string]Handler
}

// NewHandlerRegistry returns an empty registry.
func NewHandlerRegistry() *HandlerRegistry {
	return &HandlerRegistry{m: make(map[string]Handler)}
}

// Register associates name → h. Re-registration overwrites (test fixtures).
func (h *HandlerRegistry) Register(name string, fn Handler) {
	h.mu.Lock()
	defer h.mu.Unlock()
	h.m[name] = fn
}

// Get returns the registered handler or a tier-less NotWired fallback.
// Prefer Resolve(c) in production code so the fail-closed tier policy applies.
func (h *HandlerRegistry) Get(name string) Handler {
	h.mu.RLock()
	defer h.mu.RUnlock()
	if fn, ok := h.m[name]; ok {
		return fn
	}
	return NotWiredHandler(name, "")
}

// Resolve returns the registered handler for c.Name, or a fail-closed
// NotWiredHandler carrying c's impact class. This is the production entry point:
// it guarantees an un-wired DESTRUCTIVE/GRIEFING command errors instead of
// reporting success (PRR-05).
func (h *HandlerRegistry) Resolve(c *Command) Handler {
	if c == nil {
		return NotWiredHandler("", "")
	}
	h.mu.RLock()
	defer h.mu.RUnlock()
	if fn, ok := h.m[c.Name]; ok {
		return fn
	}
	return NotWiredHandler(c.Name, string(c.ImpactClass))
}

// NotWiredHandler is the default for commands whose carry_forward_cycle has not
// yet shipped. Run() audits the invocation regardless. FAIL-CLOSED (PRR-05): a
// tier-1-destructive or tier-2-griefing command that is not wired returns an
// ERROR so it can never exit 0 "success" while doing nothing (e.g. a GDPR
// erasure must not silently no-op). Tier-3-informational (and the tier-less
// Get fallback) surface the recognised-but-not-wired message.
func NotWiredHandler(name, impactClass string) Handler {
	return func(ctx context.Context, inv Invocation) (string, error) {
		switch impactClass {
		case string(Tier1Destructive), string(Tier2Griefing):
			return "", fmt.Errorf(
				"admin-cli: %q (%s) is NOT wired — refusing to report success for a destructive/griefing command. Real body pending live-wiring (contracts/admin/registry/* carry_forward_cycle + DEFERRED.md D-ADMIN-CLI-LIVE-WIRING / D-ADMIN-CLI-METAWRITE)",
				name, impactClass,
			)
		default:
			return fmt.Sprintf(
				"admin-cli: %q recognised + audited but not yet wired. See contracts/admin/registry/* for carry_forward_cycle.",
				name,
			), nil
		}
	}
}
