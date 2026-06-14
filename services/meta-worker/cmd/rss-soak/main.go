// services/meta-worker/cmd/rss-soak — S14 (D2) in-process RSS / heap-leak soak.
//
// docker --memory OOM-kill is not reliably observable under WSL2 (plan R5), so the
// leak check is in-process: run the REAL meta write-path allocation loop (build a
// LifecycleTransitionAuditRow → QueryBuilder.BuildLifecycleAuditInsert → discard) for
// a window and assert the LIVE heap (HeapAlloc sampled right after a forced GC)
// PLATEAUS — transient garbage is collected, steady-state heap is flat.
//
//	-mode soak   discard each built object → heap must plateau (no leak)
//	-mode bite   RETAIN every built object in a package slice → heap grows
//	             monotonically → proves the plateau check can actually fail
//
// Lives in the meta-worker module to reuse the resolved contracts/meta dep.
package main

import (
	"flag"
	"fmt"
	"os"
	"runtime"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/meta"
)

// retained holds references in bite mode so the GC cannot reclaim them — a synthetic
// leak that the plateau check MUST catch.
var retained []any

func main() {
	secs := flag.Int("secs", 6, "soak window seconds")
	mode := flag.String("mode", "soak", "soak | bite")
	flag.Parse()
	os.Exit(run(*secs, *mode))
}

func run(secs int, mode string) int {
	qb := meta.PostgresQueryBuilder{}
	deadline := time.Now().Add(time.Duration(secs) * time.Second)
	sampleEvery := max(time.Duration(secs)*time.Second/6, 200*time.Millisecond) // ~6 samples
	nextSample := time.Now().Add(sampleEvery)

	var samples []uint64
	i := 0
	for time.Now().Before(deadline) {
		// REAL meta write-path allocation: build an audit row + its INSERT SQL+args.
		row := meta.LifecycleTransitionAuditRow{
			AuditID:          uuid.New(),
			ResourceID:       "11111111-1111-1111-1111-111111111111",
			FromStatus:       "active",
			ToStatus:         "migrating",
			ActorID:          "00000000-0000-0000-0000-0000000000aa",
			ActorType:        meta.ActorSystem,
			Succeeded:        true,
			FailureReason:    "",
			Payload:          map[string]any{"i": i, "k": "v", "n": "s14-rss-soak"},
			AttemptedAtNanos: time.Now().UnixNano(),
		}
		q, args, err := qb.BuildLifecycleAuditInsert(row)
		if err != nil {
			fmt.Fprintf(os.Stderr, "rss-soak: BuildLifecycleAuditInsert: %v\n", err)
			return 2
		}
		if mode == "bite" {
			retained = append(retained, q, args) // synthetic leak
		} else {
			_ = q
			_ = args
		}
		i++

		if time.Now().After(nextSample) {
			samples = append(samples, liveHeap())
			nextSample = nextSample.Add(sampleEvery)
		}
	}
	samples = append(samples, liveHeap())

	if len(samples) < 3 {
		fmt.Fprintf(os.Stderr, "NOTRUN: only %d heap samples (window too short) — re-run with larger -secs\n", len(samples))
		return 2
	}
	// Drop the first sample (warm-up: pools/buffers still filling).
	base := samples[1]
	end := samples[len(samples)-1]
	growth := float64(end) / float64(base)

	fmt.Printf(`{"mode":%q,"iterations":%d,"heap_base_bytes":%d,"heap_end_bytes":%d,"growth_x":%.2f,"samples":%d}`+"\n",
		mode, i, base, end, growth, len(samples))

	switch mode {
	case "soak":
		// Plateau: live heap must NOT grow materially over the window (allow 1.5× for
		// GC pacing / sample noise). A real leak would compound well past this.
		if growth > 1.5 {
			fmt.Fprintf(os.Stderr, "FAIL: live heap grew %.2f× over the soak (base=%d end=%d) — possible leak in the meta write path\n", growth, base, end)
			return 1
		}
		fmt.Fprintf(os.Stderr, "PASS(soak): live heap plateaued (%.2f× over %d iterations) — no leak in the meta write-path allocation loop\n", growth, i)
		return 0
	case "bite":
		// The synthetic leak MUST be visible — else the plateau check is blind.
		if growth < 2.0 {
			fmt.Fprintf(os.Stderr, "FAIL(bite vacuous): retaining every object grew the heap only %.2f× — the leak detector cannot see growth (retain GC'd? window too short?)\n", growth)
			return 1
		}
		fmt.Fprintf(os.Stderr, "PASS(bite): retaining every object grew the live heap %.2f× — the plateau check has teeth (a real leak would be caught)\n", growth)
		return 0
	default:
		fmt.Fprintf(os.Stderr, "rss-soak: unknown mode %q\n", mode)
		return 2
	}
}

// liveHeap returns HeapAlloc right after a forced GC — i.e. memory still REACHABLE
// (a leak), not transient garbage.
func liveHeap() uint64 {
	runtime.GC()
	var m runtime.MemStats
	runtime.ReadMemStats(&m)
	return m.HeapAlloc
}
