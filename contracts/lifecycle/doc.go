// Package lifecycle holds the system-wide service-mode enum + Redis-control-
// channel envelope shared by every service. Owned by the platform team.
//
// Cycle 7 (L1.J) ships:
//   - service_mode.go — ServiceMode enum (Full|Limited|Essentials|ReadOnly|Offline)
//   - mode_propagation.go — envelope + serde for the shared Redis pubsub channel
//     `lw:dependency:control` (Q-L1J-1 LOCKED: shared cache Redis, not separate)
//
// The actual Redis client binding (subscribe loop, downgrade-on-disconnect,
// publish-on-modeshift) lives in each service's internal/buffer_flush/. This
// package only owns the wire format + decoding helpers so all services agree.
package lifecycle
