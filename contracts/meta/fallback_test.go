package meta

import (
	"context"
	"errors"
	"sync"
	"testing"
)

func TestFallbackBuffer_Append_Bounded(t *testing.T) {
	b := NewFallbackBuffer(3)
	for i := 0; i < 3; i++ {
		err := b.Append(int64(i), Actor{ID: "u", Type: "system"}, MetaWriteIntent{Table: "x"})
		if err != nil {
			t.Fatalf("Append[%d] err=%v", i, err)
		}
	}
	// 4th must fail with ErrBufferFull, and the dropped counter must tick.
	err := b.Append(99, Actor{ID: "u", Type: "system"}, MetaWriteIntent{Table: "x"})
	if !errors.Is(err, ErrBufferFull) {
		t.Errorf("over-cap Append err = %v, want ErrBufferFull", err)
	}
	if got := b.DroppedOnFull(); got != 1 {
		t.Errorf("DroppedOnFull = %d, want 1", got)
	}
	if got := b.Len(); got != 3 {
		t.Errorf("Len = %d, want 3 (cap honored)", got)
	}
}

func TestFallbackBuffer_DisabledByZeroCap(t *testing.T) {
	b := NewFallbackBuffer(0)
	err := b.Append(1, Actor{ID: "u", Type: "system"}, MetaWriteIntent{Table: "x"})
	if !errors.Is(err, ErrBufferDisabled) {
		t.Errorf("disabled Append err = %v, want ErrBufferDisabled", err)
	}
}

func TestFallbackBuffer_Flush_FIFO_Success(t *testing.T) {
	b := NewFallbackBuffer(10)
	for i := 0; i < 5; i++ {
		_ = b.Append(int64(i), Actor{ID: "u", Type: "system"}, MetaWriteIntent{
			Table: "reality_registry", Operation: OpUpdate,
			PK:        map[string]any{"reality_id": i},
			NewValues: map[string]any{"status": "active"},
		})
	}
	seen := make([]int, 0, 5)
	exec := FlushExecutorFunc(func(ctx context.Context, intent MetaWriteIntent) error {
		seen = append(seen, intent.PK["reality_id"].(int))
		return nil
	})
	res := b.Flush(context.Background(), exec)
	if res.Attempted != 5 || res.Succeeded != 5 {
		t.Errorf("Flush result = %+v, want attempted=5 succeeded=5", res)
	}
	for i, n := range seen {
		if n != i {
			t.Errorf("FIFO violation: seen[%d] = %d", i, n)
		}
	}
	if got := b.Len(); got != 0 {
		t.Errorf("Len after flush = %d, want 0", got)
	}
}

func TestFallbackBuffer_Flush_CASConflict_NotRequeued(t *testing.T) {
	b := NewFallbackBuffer(10)
	_ = b.Append(1, Actor{ID: "u", Type: "system"}, MetaWriteIntent{Table: "x"})
	_ = b.Append(2, Actor{ID: "u", Type: "system"}, MetaWriteIntent{Table: "x"})
	exec := FlushExecutorFunc(func(ctx context.Context, intent MetaWriteIntent) error {
		return ErrConcurrentStateTransition
	})
	res := b.Flush(context.Background(), exec)
	if res.Conflicts != 2 || res.Errors != 0 {
		t.Errorf("Flush result = %+v, want conflicts=2 errors=0", res)
	}
	if got := b.Len(); got != 0 {
		t.Errorf("CAS conflicts should NOT requeue; Len = %d, want 0", got)
	}
}

func TestFallbackBuffer_Flush_HardError_PartialRequeue(t *testing.T) {
	b := NewFallbackBuffer(10)
	for i := 0; i < 5; i++ {
		_ = b.Append(int64(i), Actor{ID: "u", Type: "system"}, MetaWriteIntent{
			Table: "x", PK: map[string]any{"id": i},
		})
	}
	hardErr := errors.New("rpc broken pipe")
	calls := 0
	exec := FlushExecutorFunc(func(ctx context.Context, intent MetaWriteIntent) error {
		calls++
		if calls == 3 { // 3rd intent fails hard
			return hardErr
		}
		return nil
	})
	res := b.Flush(context.Background(), exec)
	if res.Succeeded != 2 || res.Errors != 1 {
		t.Errorf("Flush result = %+v, want succeeded=2 errors=1", res)
	}
	// 3 unprocessed (intent 3,4,5) must remain in the buffer for retry.
	if got := b.Len(); got != 3 {
		t.Errorf("Len after partial = %d, want 3 (unprocessed tail requeued)", got)
	}
	// FIFO order preserved on the requeued tail.
	snap := b.Snapshot()
	if snap[0].Intent.PK["id"].(int) != 2 {
		t.Errorf("requeue order broken; snap[0].id = %v, want 2", snap[0].Intent.PK["id"])
	}
}

func TestFallbackBuffer_ConcurrentAppendAndFlush(t *testing.T) {
	b := NewFallbackBuffer(1000)
	var wg sync.WaitGroup
	// 10 writers append 100 each
	for w := 0; w < 10; w++ {
		wg.Add(1)
		go func() {
			defer wg.Done()
			for i := 0; i < 100; i++ {
				_ = b.Append(int64(i), Actor{ID: "u", Type: "system"}, MetaWriteIntent{Table: "x"})
			}
		}()
	}
	wg.Wait()
	if got := b.Len(); got != 1000 {
		t.Errorf("Len after 10×100 appends = %d, want 1000", got)
	}
	exec := FlushExecutorFunc(func(ctx context.Context, intent MetaWriteIntent) error { return nil })
	res := b.Flush(context.Background(), exec)
	if res.Succeeded != 1000 {
		t.Errorf("Flush result = %+v, want succeeded=1000", res)
	}
}

func TestFallbackBuffer_DefaultBufferCap_10K(t *testing.T) {
	// L1.J §8 acceptance: "bounded at 10K".
	if DefaultBufferCap != 10000 {
		t.Errorf("DefaultBufferCap drifted: got %d, want 10000 per L1.J §8", DefaultBufferCap)
	}
}
