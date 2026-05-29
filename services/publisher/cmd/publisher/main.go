// services/publisher/cmd/publisher — entry point for L2.D publisher.
//
// V1 ships as a SKELETON: the main() function wires the no-op leader,
// validates the policy + config, prints a banner, and exits. The real
// production wiring (pgx + redis bindings, ticker loop, graceful shutdown)
// lands in cycle 11/L4 when the live cross-service smoke flows can
// actually exercise the publisher end-to-end (Q-L1B-5 docker-compose
// meta-ha + Q-L1F-1 Redis Sentinel come online).
//
// Why ship the entry point now? Three reasons:
//  1. The Go binary is referenced by infra/k8s/publisher-deployment.yaml
//     and budgets.yaml — without main.go, the manifests dangle.
//  2. CI smoke (`go build ./...` per the cycle-10 verify script) catches
//     wiring drift early.
//  3. The "live" tests in tests/integration/publisher_lag_test.go drive
//     the loop directly via the pkg/poll_loop API; they don't need main
//     to be a long-running daemon.

package main

import (
	"fmt"
	"os"

	"github.com/loreweave/foundation/services/publisher/pkg/leader_election"
	"github.com/loreweave/foundation/services/publisher/pkg/retry"
)

const banner = `
[publisher] L2.D outbox publisher — V1 skeleton
[publisher] leader_election: V1 single-replica no-op (Q-L2-5)
[publisher] V2+ multi-replica trigger: 1000 active realities (Q-L2D-1)
[publisher] Production wiring lands cycle 11/L4 (pgx + redis + ticker)
`

func main() {
	fmt.Print(banner)

	// Sanity check: the default retry policy must validate. If a future
	// change breaks this (e.g. someone sets MaxBackoff < BaseBackoff in
	// retry.DefaultPolicy), the binary refuses to start.
	policy := retry.DefaultPolicy()
	if err := policy.Validate(); err != nil {
		fmt.Fprintf(os.Stderr, "[publisher] FATAL: default retry policy invalid: %v\n", err)
		os.Exit(2)
	}
	fmt.Printf("[publisher] retry policy: max_attempts=%d base_backoff=%v max_backoff=%v\n",
		policy.MaxAttempts, policy.BaseBackoff, policy.MaxBackoff)

	// Confirm the no-op leader compiles + returns true.
	leader := leader_election.NewNoOp()
	if !leader.IsLeader() {
		fmt.Fprintln(os.Stderr, "[publisher] FATAL: V1 no-op leader returned false; invariant broken")
		os.Exit(2)
	}
	fmt.Println("[publisher] leader: V1 no-op returns IsLeader()=true")

	// V1 skeleton: exit cleanly. Cycle 11/L4 wires the real ticker.
	fmt.Println("[publisher] skeleton OK — exit 0 (wire-in deferred to cycle 11/L4)")
}
