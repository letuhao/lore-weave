package ws

import (
	"errors"
	"fmt"
)

// ServiceMode mirrors cycle 7's contracts/lifecycle.ServiceMode integer
// values WITHOUT importing the lifecycle package (avoid a build-time
// dep on contracts/lifecycle from contracts/ws). Cross-language wire
// values match cycle 18 Rust mirror. Adding a variant is a Go-AND-Rust
// change in the same PR.
//
// **Why duplicate the enum here?** The ws package is consumed by the
// L6 ws-gateway (cycle 27+) and by Rust services that may not link
// contracts/lifecycle. Foundation invariant: cross-package contract
// deps stay one-way (lifecycle → ws is fine; ws → lifecycle would
// pull cycle-18 dependency-matrix loading into every WS-aware crate).
// Cycle 18's lifecycle SSOT enforces the integer values; this
// package's ParseServiceMode + tests guarantee parity.
type ServiceMode int

const (
	// ModeFull — normal operation. WS writes accepted.
	ModeFull ServiceMode = 0

	// ModeLimited — non-critical dep degraded. WS writes accepted.
	ModeLimited ServiceMode = 1

	// ModeEssentials — critical dep degraded. WS writes for feature
	// scopes REJECTED; control + session-essential scopes accepted.
	ModeEssentials ServiceMode = 2

	// ModeReadOnly — no writes. WS writes REJECTED across all scopes.
	ModeReadOnly ServiceMode = 3

	// ModeOffline — no traffic. The gateway SHOULD have closed
	// connections; if any survive, WS writes REJECTED.
	ModeOffline ServiceMode = 4
)

// AcceptsWrites returns true iff the mode allows new WS data messages
// (KindData). Control messages (ws.ping, ws.pong, ws.refresh) bypass
// this gate — they're always allowed so the gateway can keep
// connections alive long enough to send a clean close.
func (m ServiceMode) AcceptsWrites() bool {
	return m == ModeFull || m == ModeLimited
}

// AcceptsEssentialWrites returns true iff the mode allows essential
// write paths (auth, session heartbeat). Used by L6 routers to
// distinguish "auth POST that MUST proceed" from "chat message that
// can wait".
func (m ServiceMode) AcceptsEssentialWrites() bool {
	return m == ModeFull || m == ModeLimited || m == ModeEssentials
}

// IsValid returns true iff m is one of the 5 enumerated modes.
func (m ServiceMode) IsValid() bool {
	switch m {
	case ModeFull, ModeLimited, ModeEssentials, ModeReadOnly, ModeOffline:
		return true
	}
	return false
}

// String returns the canonical lowercase wire string. Matches cycle
// 7's contracts/lifecycle.ServiceMode.String byte-for-byte (this is
// the parity contract).
func (m ServiceMode) String() string {
	switch m {
	case ModeFull:
		return "full"
	case ModeLimited:
		return "limited"
	case ModeEssentials:
		return "essentials"
	case ModeReadOnly:
		return "read_only"
	case ModeOffline:
		return "offline"
	}
	return fmt.Sprintf("invalid_service_mode(%d)", int(m))
}

// ServiceModeProvider supplies the current ServiceMode to the gate.
// Production wires cycle 18's lifecycle mode-propagation Redis channel
// (lw:dependency:control); tests use a fixed value.
type ServiceModeProvider interface {
	CurrentMode() ServiceMode
}

// StaticMode is the zero-config provider — returns the same mode
// always. Useful for tests and for the gateway's startup phase
// (before mode-propagation hooks land).
type StaticMode ServiceMode

// CurrentMode satisfies ServiceModeProvider.
func (s StaticMode) CurrentMode() ServiceMode { return ServiceMode(s) }

// Sentinel errors. Both wrap ErrModeRejected so a caller can do
// `errors.Is(err, ErrModeRejected)` to coalesce them at the
// per-connection metric layer.
var (
	// ErrModeRejected is the parent class. ServiceModeGate wraps either
	// specific error with this.
	ErrModeRejected = errors.New("ws: mode rejected message")

	// ErrModeRejectsWrites means the current mode is ReadOnly /
	// Offline (or otherwise refusing data messages).
	ErrModeRejectsWrites = errors.New("ws: mode rejects writes")

	// ErrModeRejectsScope means the mode accepts SOME writes but not
	// the scope the inbound message is using (e.g., Essentials mode
	// rejecting feature scopes).
	ErrModeRejectsScope = errors.New("ws: mode rejects scope")
)

// ServiceModeGate is the helper L6 ws-gateway calls before processing
// an inbound data envelope. Returns nil = accept; error (wrapping
// ErrModeRejected) = reject.
//
// V1 policy:
//   - Control envelopes (KindControl) always accepted.
//   - Data envelopes rejected if mode is ReadOnly or Offline.
//   - Data envelopes in Essentials mode accepted ONLY when isEssential
//     (caller passes per-message based on Type / scope; default false).
type ServiceModeGate struct {
	Provider ServiceModeProvider
}

// Check returns nil if the envelope is allowed to proceed; otherwise
// returns a wrapped ErrModeRejected. Caller closes with
// CloseRateLimitExceeded if appropriate.
func (g ServiceModeGate) Check(env Envelope, isEssential bool) error {
	if g.Provider == nil {
		// Defensive: missing provider = treat as Full (don't break the
		// world if the gateway forgets to wire a provider; SRE will
		// see the lw_ws_mode_provider_missing_total metric).
		return nil
	}
	mode := g.Provider.CurrentMode()
	if !mode.IsValid() {
		return fmt.Errorf("%w: invalid mode %d", ErrModeRejected, int(mode))
	}
	// Control messages always allowed.
	if env.Kind == KindControl {
		return nil
	}
	// Data messages.
	if mode.AcceptsWrites() {
		return nil
	}
	if mode.AcceptsEssentialWrites() && isEssential {
		return nil
	}
	// Reject with the most specific reason.
	if mode == ModeEssentials {
		return fmt.Errorf("%w: %w: scope=%s mode=%s", ErrModeRejected, ErrModeRejectsScope, env.Type, mode)
	}
	return fmt.Errorf("%w: %w: mode=%s", ErrModeRejected, ErrModeRejectsWrites, mode)
}
