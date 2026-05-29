// services/archive-worker/cmd/archive-worker — entry point for L2.J archive
// worker.
//
// V1 ships as a SKELETON: main() validates a minimal config, prints a banner,
// and exits 0. Real production wiring (pgx for partition catalog + ATTACH/DROP,
// minio-go for object_store, ticker loop with per-reality scheduling,
// graceful shutdown, /healthz + /readyz + /metrics) lands in cycle 11/L4 —
// see deferred row D-PUBLISHER-LIVE-WIRING (the publisher needs the same
// shape; the archive-worker shares the wiring patterns).
//
// Why ship the entry point now? Three reasons (mirror cycle-10 publisher):
//  1. The binary is referenced by infra/k8s/archive-worker-deployment.yaml
//     and budgets.yaml — without main.go, the manifests dangle.
//  2. CI smoke (`go build ./...` per verify-cycle-11.sh) catches wiring
//     drift early.
//  3. The archive_loop package's tests drive Run() directly via in-mem
//     fakes; they don't need main to be a long-running daemon.

package main

import (
	"fmt"
	"os"

	"github.com/loreweave/foundation/services/archive-worker/pkg/parquet_writer"
)

const banner = `
[archive-worker] L2.J event archive worker — V1 skeleton
[archive-worker] placement: dedicated service (Q-L2J-1)
[archive-worker] separate from retention-worker (Q-L2K-1)
[archive-worker] bucket: lw-event-archive (separate from lw-db-backups)
[archive-worker] heartbeat namespace: archive-worker-<replica> (reuses publisher_heartbeats)
[archive-worker] production wiring lands cycle 11/L4 (pgx + minio-go + ticker)
`

func main() {
	fmt.Print(banner)

	// Sanity check: the parquet_writer ABI constants haven't drifted.
	// Downstream cmd/archive-restore + L3 integrity-checker rely on these.
	if parquet_writer.SchemaVersion != 1 {
		fmt.Fprintf(os.Stderr, "[archive-worker] FATAL: parquet_writer.SchemaVersion drifted: got %d, want 1\n",
			parquet_writer.SchemaVersion)
		os.Exit(2)
	}
	if string(parquet_writer.Magic[:]) != "LWP1" {
		fmt.Fprintf(os.Stderr, "[archive-worker] FATAL: parquet_writer.Magic drifted: got %q, want LWP1\n",
			parquet_writer.Magic[:])
		os.Exit(2)
	}
	fmt.Printf("[archive-worker] parquet ABI: magic=%q schema_version=%d\n",
		parquet_writer.Magic[:], parquet_writer.SchemaVersion)

	fmt.Println("[archive-worker] skeleton OK — exit 0 (live wiring deferred to cycle 11/L4)")
}
