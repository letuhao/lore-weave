// services/retention-worker/cmd/retention-worker — entry point for L2.K.
//
// V1 ships as a SKELETON: validate defaults, print banner, exit 0.
// Production wiring (pgx + DSN lookup against reality_registry +
// scripts/event-audit-retention-cron.sh exec + ticker + /healthz +
// /readyz + /metrics) lands alongside D-PUBLISHER-LIVE-WIRING.

package main

import (
	"fmt"
	"os"

	"github.com/loreweave/foundation/services/retention-worker/pkg/types"
)

const banner = `
[retention-worker] L2.K retention worker — V1 skeleton
[retention-worker] SEPARATE binary from archive-worker (Q-L2K-1)
[retention-worker] addresses D-OUTBOX-PRUNE (deferred row 055)
[retention-worker] wraps existing scripts/event-audit-retention-cron.sh (cycle 9 L2.B.3)
[retention-worker] NEVER touches the events table (archive-worker's surface)
[retention-worker] heartbeat namespace: retention-worker-<replica> (reuses publisher_heartbeats)
[retention-worker] production wiring lands cycle 11/L4 (pgx + DSN lookup + ticker)
`

func main() {
	fmt.Print(banner)

	cfg := types.DefaultConfig()
	if cfg.OutboxPublishedGrace == 0 || cfg.OutboxBatchSize == 0 ||
		cfg.AuditNonFlaggedDays == 0 || cfg.AuditFlaggedDays == 0 {
		fmt.Fprintln(os.Stderr, "[retention-worker] FATAL: DefaultConfig() returned zero-value field — invariant broken")
		os.Exit(2)
	}
	fmt.Printf("[retention-worker] config: outbox_grace=%v batch_size=%d audit_non_flagged_days=%d audit_flagged_days=%d\n",
		cfg.OutboxPublishedGrace, cfg.OutboxBatchSize, cfg.AuditNonFlaggedDays, cfg.AuditFlaggedDays)

	fmt.Println("[retention-worker] skeleton OK — exit 0 (live wiring deferred to cycle 11/L4)")
}
