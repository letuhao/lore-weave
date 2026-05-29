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

// Get returns the registered handler or the default NotWired handler.
func (h *HandlerRegistry) Get(name string) Handler {
	h.mu.RLock()
	defer h.mu.RUnlock()
	if fn, ok := h.m[name]; ok {
		return fn
	}
	return NotWiredHandler(name)
}

// NotWiredHandler is the default for commands whose carry_forward_cycle has
// not yet shipped. It RECORDS the invocation via audit (because Run() audits
// regardless) and returns a structured "wires-in-later" message so operators
// know the command exists but the body hasn't shipped.
func NotWiredHandler(name string) Handler {
	return func(ctx context.Context, inv Invocation) (string, error) {
		return fmt.Sprintf(
			"admin-cli: %q recognised + audited but not yet wired. See contracts/admin/registry/* for carry_forward_cycle.",
			name,
		), nil
	}
}
