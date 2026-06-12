package lifecycle

import (
	"errors"
	"fmt"
	"strings"
)

// ServiceMode is the system-wide operational mode every service tracks per
// the SR06-D5 service-mode enum.
//
// Mode semantics (SR06-D5 + L1.J §8 acceptance):
//
//   - Full:       normal operation. Reads + writes online; cache fresh.
//   - Limited:    a non-critical dep is degraded. Writes buffered if meta
//                 down (FallbackBuffer); reads serve stale cache for
//                 sensitive paths. Admin commands gated on fresh ack are
//                 BLOCKED (e.g., R9 close confirmations).
//   - Essentials: critical dep degraded — accept only essential write paths
//                 (auth, session heartbeats); reject feature writes.
//                 Background jobs (rollup workers, archive workers) paused.
//   - ReadOnly:   no writes accepted; reads from cache + replicas only.
//                 Frontend renders a banner; user input disabled.
//   - Offline:    no traffic accepted; gateway returns 503. Used during
//                 planned maintenance windows.
//
// The enum is intentionally a linear severity ladder: Full(0) → Offline(4).
// `ge(a, b)` answers "is `a` at LEAST as degraded as `b`?", which is the
// common admission check ("if currentMode.GreaterOrEqual(Essentials) { ... }").
type ServiceMode int

const (
	ModeFull       ServiceMode = 0
	ModeLimited    ServiceMode = 1
	ModeEssentials ServiceMode = 2
	ModeReadOnly   ServiceMode = 3
	ModeOffline    ServiceMode = 4
)

// String returns the canonical lowercase wire representation.
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

// ErrInvalidServiceMode is returned by ParseServiceMode on unknown wire values.
var ErrInvalidServiceMode = errors.New("lifecycle: invalid service mode")

// ParseServiceMode decodes the lowercase wire representation produced by
// ServiceMode.String. Returns ErrInvalidServiceMode on unknown values so
// callers can drop the message + alert rather than silently default to Full.
func ParseServiceMode(s string) (ServiceMode, error) {
	switch strings.ToLower(strings.TrimSpace(s)) {
	case "full":
		return ModeFull, nil
	case "limited":
		return ModeLimited, nil
	case "essentials":
		return ModeEssentials, nil
	case "read_only", "readonly":
		return ModeReadOnly, nil
	case "offline":
		return ModeOffline, nil
	}
	return ModeFull, fmt.Errorf("%w: %q", ErrInvalidServiceMode, s)
}

// GreaterOrEqual answers "is m at LEAST as degraded as other?". This is the
// admission-check primitive — handlers should branch on
// `if currentMode.GreaterOrEqual(lifecycle.ModeEssentials) { reject }`.
func (m ServiceMode) GreaterOrEqual(other ServiceMode) bool {
	return int(m) >= int(other)
}

// AcceptsWrites returns true for modes that accept new write traffic.
// ReadOnly + Offline reject; everything else accepts (with buffering at
// Limited if meta is unreachable, and essential-only at Essentials).
func (m ServiceMode) AcceptsWrites() bool {
	return m < ModeReadOnly
}

// AcceptsBackgroundJobs returns true for modes that allow background workers
// (rollup workers, archive workers, retention sweepers). At Essentials and
// worse, background jobs MUST pause to keep critical path latency budget.
func (m ServiceMode) AcceptsBackgroundJobs() bool {
	return m <= ModeLimited
}

// AcceptsFreshAckRequired returns true for modes that allow admin commands
// requiring a fresh ack (R9 close confirmations, retire-shard ops). At
// Limited and worse, these MUST be deferred until mode returns to Full.
func (m ServiceMode) AcceptsFreshAckRequired() bool {
	return m == ModeFull
}

// AllModes returns the canonical ordered slice — exposed so tests and lint
// can assert exhaustiveness (no "Maintenance" or other drift).
func AllModes() []ServiceMode {
	return []ServiceMode{
		ModeFull,
		ModeLimited,
		ModeEssentials,
		ModeReadOnly,
		ModeOffline,
	}
}
