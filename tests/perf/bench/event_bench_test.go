// Package bench holds S7 deliverable F2 — per-layer micro-benchmarks over the
// REAL, importable spine event wire path (`contracts/events`), the same
// Envelope/OutboxWrite code the emit path (L2) and replay/projection read path
// (L3) run. They need no DB, so the benchstat regression gate (scripts/perf/
// bench-gate.sh) runs them per-PR in-toolchain.
//
// Scope honesty: the FULL DB projection-apply + rebuild is Rust (world-service)
// and DB-bound — it is measured end-to-end by the F3 hyperfine harness over the
// `replay-aggregate` binary, NOT here. These Go micro-benches cover the
// importable encode / decode / validate inner loops:
//   - BenchmarkEventMarshal   → L2 event-write serialize (emit path)
//   - BenchmarkEventUnmarshal → L3 replay/projection decode inner loop
//   - BenchmarkEnvelopeValidate → per-event structural gate run on every append
package bench

import (
	"encoding/json"
	"os"
	"testing"
	"time"

	"github.com/google/uuid"

	"github.com/loreweave/foundation/contracts/events"
)

// sampleEnvelope builds a representative npc.said event (the kind the workload
// generator emits) with a non-trivial payload so marshal/unmarshal do real work.
func sampleEnvelope() events.Envelope {
	now := time.Unix(1_700_000_000, 0).UTC()
	return events.Envelope{
		EventID:          uuid.MustParse("11111111-1111-4111-8111-111111111111"),
		EventType:        "npc.said",
		EventVersion:     1,
		AggregateID:      "npc-00000000-0000-4000-8000-000000000abc",
		AggregateType:    "npc",
		AggregateVersion: 42,
		RealityID:        uuid.MustParse("22222222-2222-4222-8222-222222222222"),
		OccurredAt:       now,
		RecordedAt:       now.Add(5 * time.Millisecond),
		Payload: map[string]any{
			"speaker_id":  "npc-00000000-0000-4000-8000-000000000abc",
			"text":        "The river forks east of the old mill; the bridge is out.",
			"locale":      "en",
			"in_world_ts": "1456-03-12T08:30:00Z",
			"listeners":   []any{"pc-1", "pc-2", "npc-7"},
		},
		Metadata: map[string]any{
			"request_id": "req-abc123",
			"actor_id":   "system",
			"trace_id":   "trace-deadbeef",
		},
	}
}

func BenchmarkEventMarshal(b *testing.B) {
	env := sampleEnvelope()
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		out, err := json.Marshal(&env)
		if err != nil {
			b.Fatal(err)
		}
		if len(out) == 0 {
			b.Fatal("empty marshal")
		}
	}
}

func BenchmarkEventUnmarshal(b *testing.B) {
	raw, err := json.Marshal(sampleEnvelope())
	if err != nil {
		b.Fatal(err)
	}
	b.ReportAllocs()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		var env events.Envelope
		if err := json.Unmarshal(raw, &env); err != nil {
			b.Fatal(err)
		}
	}
}

func BenchmarkEnvelopeValidate(b *testing.B) {
	env := sampleEnvelope()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		if err := env.Validate(); err != nil {
			b.Fatal(err)
		}
	}
}

// BenchmarkPerfGateBite is the NON-VACUITY proof for the benchstat gate (S7
// review HIGH-2 / §4). It does a fixed baseline amount of work; when
// LW_PERF_BITE=1 it injects an artificial regression (extra allocation + spin).
// bench-gate.sh --bite runs old=clean / new=bite on the SAME process and
// asserts benchstat FLAGS the regression — if it doesn't, the gate is vacuous
// and the script exits 1. Same-machine, so the bite validates the real gate
// path (not a cross-machine proxy).
func BenchmarkPerfGateBite(b *testing.B) {
	bite := os.Getenv("LW_PERF_BITE") == "1"
	env := sampleEnvelope()
	b.ResetTimer()
	for i := 0; i < b.N; i++ {
		out, _ := json.Marshal(&env) // baseline work
		_ = out
		if bite {
			// Injected regression: a heap allocation the clean path never does,
			// plus a short CPU spin — large enough that benchstat sees it across
			// -count runs, small enough the bench still completes quickly.
			sink := make([]byte, 8192)
			for j := range sink {
				sink[j] = byte(j)
			}
			var acc int
			for j := 0; j < 5000; j++ {
				acc += j * j
			}
			if acc < 0 {
				b.Fatal("unreachable")
			}
		}
	}
}
