// Package leader_election implements the publisher's leader-election layer.
//
// V1 ships a NO-OP impl (Q-L2-5): with a SINGLE replica per shard host
// (Q-L2D-1) every publisher is trivially leader. We expose the same
// interface as the planned V2+ Redis SETNX implementation so the rest of
// the publisher (poll loop, heartbeat, fanout) is replica-count agnostic
// — when V2 lands we swap the constructor without touching callers.
//
// ## V2+ activation plan (deferred)
//
//	type RedisLeader struct {
//	    client    redis.Cmdable
//	    key       string      // "lw:publisher:leader:<shard>"
//	    lease     time.Duration
//	    publisher string      // unique pod id
//	}
//	IsLeader() — SETNX (key, publisher) PX (lease.ms)
//	             on success → true; refresh lease on every heartbeat
//	             on failure → check existing holder; false
//	Stop() — DEL key only if held (compare-and-swap via Lua)
//
// Q-L2D-1 trigger: 1000 active realities. Tracked as deferred row.
package leader_election

// Leader is the abstraction every publisher consults before pulling a
// batch from the outbox. V1 NoOp returns true; V2+ RedisLeader respects
// the SETNX lease.
type Leader interface {
	// IsLeader returns true iff THIS replica may currently drain the
	// outbox. V1 always returns true.
	IsLeader() bool
	// Step is invoked on every heartbeat tick — V2+ uses it to refresh
	// the lease; V1 is a no-op.
	Step()
	// Stop is invoked at graceful shutdown — V2+ releases the lease;
	// V1 is a no-op.
	Stop()
}

// NoOp is the V1 leader — trivially leader because we deploy 1 replica
// per shard host. Q-L2-5 explicitly LOCKS this V1 shape: ship the
// skeleton at zero cost so V2+ scale-up doesn't require a publisher
// rewrite, only a constructor swap.
type NoOp struct{}

// NewNoOp returns the V1 no-op leader. Logged via the caller (cmd/publisher
// emits "leader_election: V1 single-replica no-op (Q-L2-5)" at startup).
func NewNoOp() *NoOp { return &NoOp{} }

// IsLeader — single replica is trivially leader.
func (*NoOp) IsLeader() bool { return true }

// Step — V2+ refreshes the Redis SETNX lease here. V1 no-op.
func (*NoOp) Step() {}

// Stop — V2+ releases the lease here. V1 no-op.
func (*NoOp) Stop() {}
