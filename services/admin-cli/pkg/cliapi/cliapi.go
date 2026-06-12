// Package cliapi is a NON-internal re-export of the framework + audit_emitter
// API surface so cross-module consumers (tests/integration, future BFF
// wrappers) can exercise admin-cli without importing the internal/ tree.
//
// This package is intentionally thin: type aliases + small wrapper funcs only.
// Do NOT add behaviour here — keep all logic in internal/.
package cliapi

import (
	"context"
	"time"

	"github.com/loreweave/foundation/services/admin-cli/internal/audit_emitter"
	"github.com/loreweave/foundation/services/admin-cli/internal/framework"
)

// ─── Type aliases ────────────────────────────────────────────────────────────

type (
	Registry        = framework.Registry
	Command         = framework.Command
	Param           = framework.Param
	ImpactClass     = framework.ImpactClass
	Handler         = framework.Handler
	Invocation      = framework.Invocation
	HandlerRegistry = framework.HandlerRegistry
	Action          = audit_emitter.Action
	Emitter         = audit_emitter.Emitter
	MemorySink      = audit_emitter.MemorySink
	Sink            = audit_emitter.Sink
)

// ─── Constants re-export ────────────────────────────────────────────────────

const (
	Tier1Destructive   = framework.Tier1Destructive
	Tier2Griefing      = framework.Tier2Griefing
	Tier3Informational = framework.Tier3Informational
)

// ─── Function re-exports ─────────────────────────────────────────────────────

// LoadRegistry calls framework.LoadRegistry.
func LoadRegistry(dir string) (*Registry, error) { return framework.LoadRegistry(dir) }

// NewHandlerRegistry calls framework.NewHandlerRegistry.
func NewHandlerRegistry() *HandlerRegistry { return framework.NewHandlerRegistry() }

// Run calls framework.Run.
func Run(
	ctx context.Context,
	c *Command,
	inv Invocation,
	token string,
	handler Handler,
	emitter *Emitter,
) (string, error) {
	return framework.Run(ctx, c, inv, token, handler, emitter)
}

// NewMemorySink calls audit_emitter.NewMemorySink.
func NewMemorySink() *MemorySink { return audit_emitter.NewMemorySink() }

// NewEmitter calls audit_emitter.New.
func NewEmitter(sink Sink, now func() time.Time) *Emitter { return audit_emitter.New(sink, now) }
