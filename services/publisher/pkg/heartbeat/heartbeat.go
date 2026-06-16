// Package heartbeat writes the publisher's liveness row to
// `publisher_heartbeats` (meta DB) every 10s.
//
// Per L2.D.5 + L1.A-1 §1.3:
//   - The publisher upserts (publisher_id, shard_host, status='active',
//     last_heartbeat_at=NOW()) on every tick.
//   - meta-worker (L2.L.3) is the SOLE reader; if it sees a stale heartbeat
//     (older than 30s) it flips status='dead' so the L2.D failover path
//     (V2+ multi-replica) can pick up.
//   - Heartbeat write failure is the L1.J degraded-mode trigger: 3
//     consecutive write failures → publisher sets its local ServiceMode to
//     ModeLimited (cycle 7 enum from contracts/lifecycle).
package heartbeat

import (
	"context"
	"errors"
	"time"

	"github.com/loreweave/foundation/contracts/lifecycle"
)

// Writer is the meta-DB write sink. Concrete impl in cycle 11+ binds to
// the contracts/meta MetaWrite() library; tests inject a fake.
type Writer interface {
	// WriteHeartbeat upserts the publisher's row. publisherID is the
	// SPIFFE-id-derived unique replica id; shardHost groups the publisher
	// by physical host for meta-worker dashboarding. Returns the underlying
	// driver error on failure — the loop interprets via DegradedClassifier.
	WriteHeartbeat(ctx context.Context, publisherID, shardHost string, now time.Time) error
}

// Clock is the time source. Production binds `time.Now`; tests inject a
// frozen clock to make tick assertions deterministic.
type Clock interface {
	Now() time.Time
}

// RealClock binds the system time.
type RealClock struct{}

// Now returns the current system time.
func (RealClock) Now() time.Time { return time.Now() }

// Loop is the heartbeat ticker. Owns its own ServiceMode pointer so the
// degraded-mode wire-in is local (the publisher's main.go reads
// loop.Mode() to gate background work — L1.J integration).
//
// The loop is NOT a goroutine on its own; the caller invokes Tick on a
// time.Ticker (publisher's main loop fans heartbeat + poll on the same
// scheduler). Keeping it pull-style lets tests step time deterministically.
type Loop struct {
	publisherID  string
	shardHost    string
	writer       Writer
	clock        Clock
	failureCount int
	// degradedThreshold is the consecutive-fail count that flips Mode
	// to ModeLimited. Default 3.
	degradedThreshold int
	mode              lifecycle.ServiceMode
}

// New constructs a heartbeat loop. publisherID and shardHost MUST be
// non-empty; writer + clock MUST be non-nil.
func New(publisherID, shardHost string, writer Writer, clock Clock) (*Loop, error) {
	if publisherID == "" {
		return nil, errors.New("heartbeat: publisherID empty")
	}
	if shardHost == "" {
		return nil, errors.New("heartbeat: shardHost empty")
	}
	if writer == nil {
		return nil, errors.New("heartbeat: writer nil")
	}
	if clock == nil {
		return nil, errors.New("heartbeat: clock nil")
	}
	return &Loop{
		publisherID:       publisherID,
		shardHost:         shardHost,
		writer:            writer,
		clock:             clock,
		degradedThreshold: 3,
		mode:              lifecycle.ModeFull,
	}, nil
}

// Tick performs one heartbeat write. On success: failureCount = 0, mode →
// ModeFull. On failure: failureCount++, and once it reaches
// degradedThreshold mode flips to ModeLimited (L1.J integration). Returns
// the underlying writer error so the caller can log + alert.
func (l *Loop) Tick(ctx context.Context) error {
	err := l.writer.WriteHeartbeat(ctx, l.publisherID, l.shardHost, l.clock.Now())
	if err != nil {
		l.failureCount++
		if l.failureCount >= l.degradedThreshold {
			// Latch into Limited; recovers on first successful Tick.
			l.mode = lifecycle.ModeLimited
		}
		return err
	}
	l.failureCount = 0
	l.mode = lifecycle.ModeFull
	return nil
}

// Mode returns the publisher's CURRENT operational mode. The caller (main
// loop) checks this on every poll-loop iteration and DEFERS background
// fanout work when mode >= ModeEssentials (per L1.J degraded-mode rules).
func (l *Loop) Mode() lifecycle.ServiceMode { return l.mode }

// FailureCount exposes the consecutive-fail count for tests + metrics.
func (l *Loop) FailureCount() int { return l.failureCount }

// SetDegradedThreshold overrides the default (3) — used by tests to flip
// the latch in a single tick.
func (l *Loop) SetDegradedThreshold(n int) {
	if n < 1 {
		n = 1
	}
	l.degradedThreshold = n
}
