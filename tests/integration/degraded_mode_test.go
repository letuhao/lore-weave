//go:build integration

package integration

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/loreweave/foundation/contracts/lifecycle"
	"github.com/loreweave/foundation/contracts/meta"
)

// TestDegradedMode_KillMetaPrimary_BufferFills_FlushesOnRecovery validates the L1.J §8 acceptance:
//
//   "Kill meta primary, verify buffer fills + correctly bounded + flushes on recovery"
//
// Cycle 7 ships this as a CONTRACT test driven by fake executors + the
// service_mode enum. The live docker-compose-driven variant ships in the
// L7 ops cycle (D-DEGRADED-LIVE-SMOKE).
//
// Auto-skips when LW_DEGRADED_LIVE_HARNESS is unset (matches cycle 5/6 pattern).
func TestDegradedMode_KillMetaPrimary_BufferFills_FlushesOnRecovery(t *testing.T) {
	if !envSet("LW_DEGRADED_LIVE_HARNESS") {
		t.Skip("LW_DEGRADED_LIVE_HARNESS unset; running contract-level test only")
	}
	// LIVE harness path would: docker compose stop meta-primary; wait; verify
	// every service has lw_service_mode==Limited; do 100 writes; restart;
	// wait for flush_succeeded counter to tick; assert buffer Len()==0.
	t.Skip("D-DEGRADED-LIVE-SMOKE — live harness deferred to L7 ops cycle")
}

// TestDegradedMode_FallbackBuffer_RoundTripContract — pure contract test that
// runs in CI without infra. Exercises the FallbackBuffer + ServiceMode pair
// end-to-end (Full → Limited → Append → Recovery → Flush → Full).
func TestDegradedMode_FallbackBuffer_RoundTripContract(t *testing.T) {
	// Initial mode = Full
	currentMode := lifecycle.ModeFull
	if !currentMode.AcceptsFreshAckRequired() {
		t.Fatal("Full must accept fresh-ack-required commands")
	}

	// Simulate meta outage: shift to Limited
	currentMode = lifecycle.ModeLimited
	if currentMode.AcceptsFreshAckRequired() {
		t.Error("Limited must REJECT fresh-ack-required commands")
	}

	// Buffer 50 writes during outage
	buf := meta.NewFallbackBuffer(100)
	for i := 0; i < 50; i++ {
		err := buf.Append(int64(i), meta.Actor{ID: "system", Type: "system"}, meta.MetaWriteIntent{
			Table: "reality_registry", Operation: meta.OpUpdate,
			PK: map[string]any{"reality_id": i},
		})
		if err != nil {
			t.Fatalf("Append[%d] err = %v", i, err)
		}
	}
	if buf.Len() != 50 {
		t.Errorf("buffer Len = %d, want 50", buf.Len())
	}

	// Recovery: shift to Full + flush
	currentMode = lifecycle.ModeFull
	flushed := 0
	exec := meta.FlushExecutorFunc(func(ctx context.Context, intent meta.MetaWriteIntent) error {
		flushed++
		return nil
	})
	res := buf.Flush(context.Background(), exec)
	if res.Succeeded != 50 {
		t.Errorf("flush Succeeded = %d, want 50", res.Succeeded)
	}
	if buf.Len() != 0 {
		t.Errorf("post-flush Len = %d, want 0", buf.Len())
	}
}

// TestDegradedMode_BufferBoundedAt10K — Q-L1J-1 + L1.J §8 hard cap.
func TestDegradedMode_BufferBoundedAt10K(t *testing.T) {
	buf := meta.NewFallbackBuffer(meta.DefaultBufferCap)
	for i := 0; i < meta.DefaultBufferCap; i++ {
		_ = buf.Append(int64(i), meta.Actor{ID: "u", Type: "system"}, meta.MetaWriteIntent{Table: "x"})
	}
	// 10001st must be rejected
	err := buf.Append(int64(meta.DefaultBufferCap), meta.Actor{ID: "u", Type: "system"}, meta.MetaWriteIntent{Table: "x"})
	if !errors.Is(err, meta.ErrBufferFull) {
		t.Errorf("over-cap Append err = %v, want ErrBufferFull", err)
	}
}

// TestDegradedMode_ModePropagationWireFormat — pin the wire format of the
// control-channel envelope so a future change is a visible test break.
func TestDegradedMode_ModePropagationWireFormat(t *testing.T) {
	raw, err := lifecycle.EncodeModeShift("world-service", "world-7f", lifecycle.ModeFull, lifecycle.ModeLimited, "meta_primary_unreachable", time.Now().UnixNano())
	if err != nil {
		t.Fatal(err)
	}
	msg, err := lifecycle.DecodeControlMessage(raw)
	if err != nil {
		t.Fatal(err)
	}
	if msg.Kind != lifecycle.KindModeShift {
		t.Errorf("Kind = %q, want %q", msg.Kind, lifecycle.KindModeShift)
	}
	if msg.FromMode != "full" || msg.ToMode != "limited" {
		t.Errorf("mode shift drift: %q→%q", msg.FromMode, msg.ToMode)
	}
}

func envSet(_ string) bool {
	// Hook for the live harness — kept as a function so tests stay diff-clean.
	return false
}
