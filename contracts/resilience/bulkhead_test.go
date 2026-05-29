package resilience

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"
)

func TestNewBulkhead_RejectsInvalidConfig(t *testing.T) {
	cases := []BulkheadConfig{
		{DepName: "d", MaxConcurrent: 0, QueueDepth: 1, QueueTimeout: time.Millisecond},
		{DepName: "d", MaxConcurrent: -1, QueueDepth: 1, QueueTimeout: time.Millisecond},
		{DepName: "d", MaxConcurrent: 1, QueueDepth: -1, QueueTimeout: time.Millisecond},
		{DepName: "d", MaxConcurrent: 1, QueueDepth: 1, QueueTimeout: -time.Millisecond},
	}
	for _, c := range cases {
		_, err := NewBulkhead(c)
		if !errors.Is(err, ErrInvalidBulkheadConfig) {
			t.Errorf("cfg=%+v err = %v, want ErrInvalidBulkheadConfig", c, err)
		}
	}
}

func TestBulkhead_FastPathBelowConcurrency(t *testing.T) {
	bh, err := NewBulkhead(BulkheadConfig{DepName: "d", MaxConcurrent: 3, QueueDepth: 0, QueueTimeout: time.Millisecond})
	if err != nil {
		t.Fatal(err)
	}
	for i := 0; i < 3; i++ {
		if err := bh.Call(context.Background(), func(ctx context.Context) error { return nil }); err != nil {
			t.Errorf("call %d: err = %v", i, err)
		}
	}
	if bh.Rejected() != 0 {
		t.Errorf("Rejected = %d, want 0", bh.Rejected())
	}
}

func TestBulkhead_RejectsWhenSlotsAndQueueFull(t *testing.T) {
	bh, err := NewBulkhead(BulkheadConfig{DepName: "d", MaxConcurrent: 1, QueueDepth: 0, QueueTimeout: time.Millisecond})
	if err != nil {
		t.Fatal(err)
	}
	// Hold the single slot.
	hold := make(chan struct{})
	go func() {
		_ = bh.Call(context.Background(), func(ctx context.Context) error {
			<-hold
			return nil
		})
	}()
	// Wait until the goroutine actually holds the slot.
	deadline := time.Now().Add(time.Second)
	for bh.Active() < 1 && time.Now().Before(deadline) {
		time.Sleep(time.Millisecond)
	}
	if bh.Active() != 1 {
		t.Fatalf("Active = %d, want 1 (precondition)", bh.Active())
	}
	// Second call should hit ErrBulkheadFull immediately (QueueDepth=0).
	start := time.Now()
	err = bh.Call(context.Background(), func(ctx context.Context) error {
		t.Error("fn should NOT be invoked when bulkhead is full")
		return nil
	})
	elapsed := time.Since(start)
	if !errors.Is(err, ErrBulkheadFull) {
		t.Errorf("err = %v, want ErrBulkheadFull", err)
	}
	if elapsed > 50*time.Millisecond {
		t.Errorf("rejection took %v, expected immediate (QueueDepth=0)", elapsed)
	}
	if bh.Rejected() != 1 {
		t.Errorf("Rejected = %d, want 1", bh.Rejected())
	}
	close(hold)
}

func TestBulkhead_QueueWaitsThenRunsWhenSlotFrees(t *testing.T) {
	bh, err := NewBulkhead(BulkheadConfig{DepName: "d", MaxConcurrent: 1, QueueDepth: 1, QueueTimeout: 200 * time.Millisecond})
	if err != nil {
		t.Fatal(err)
	}
	hold := make(chan struct{})
	go func() {
		_ = bh.Call(context.Background(), func(ctx context.Context) error {
			<-hold
			return nil
		})
	}()
	// Wait until slot taken.
	for bh.Active() < 1 {
		time.Sleep(time.Millisecond)
	}
	// Release slot after a short delay; queued caller should then proceed.
	go func() {
		time.Sleep(20 * time.Millisecond)
		close(hold)
	}()
	ran := false
	err = bh.Call(context.Background(), func(ctx context.Context) error {
		ran = true
		return nil
	})
	if err != nil {
		t.Errorf("queued call err = %v, want nil", err)
	}
	if !ran {
		t.Errorf("queued fn should have run after slot freed")
	}
}

func TestBulkhead_QueueTimeoutRejects(t *testing.T) {
	bh, err := NewBulkhead(BulkheadConfig{DepName: "d", MaxConcurrent: 1, QueueDepth: 1, QueueTimeout: 10 * time.Millisecond})
	if err != nil {
		t.Fatal(err)
	}
	hold := make(chan struct{})
	defer close(hold)
	go func() {
		_ = bh.Call(context.Background(), func(ctx context.Context) error {
			<-hold
			return nil
		})
	}()
	for bh.Active() < 1 {
		time.Sleep(time.Millisecond)
	}
	start := time.Now()
	err = bh.Call(context.Background(), func(ctx context.Context) error {
		t.Error("fn should NOT execute (queue timeout)")
		return nil
	})
	elapsed := time.Since(start)
	if !errors.Is(err, ErrBulkheadFull) {
		t.Errorf("err = %v, want ErrBulkheadFull on queue timeout", err)
	}
	if elapsed < 5*time.Millisecond {
		t.Errorf("rejection returned in %v, expected ≥ QueueTimeout", elapsed)
	}
}

func TestBulkhead_ContextCancelDuringQueue(t *testing.T) {
	bh, err := NewBulkhead(BulkheadConfig{DepName: "d", MaxConcurrent: 1, QueueDepth: 1, QueueTimeout: 5 * time.Second})
	if err != nil {
		t.Fatal(err)
	}
	hold := make(chan struct{})
	defer close(hold)
	go func() {
		_ = bh.Call(context.Background(), func(ctx context.Context) error {
			<-hold
			return nil
		})
	}()
	for bh.Active() < 1 {
		time.Sleep(time.Millisecond)
	}
	ctx, cancel := context.WithCancel(context.Background())
	var wg sync.WaitGroup
	wg.Add(1)
	var gotErr error
	go func() {
		defer wg.Done()
		gotErr = bh.Call(ctx, func(ctx context.Context) error { return nil })
	}()
	time.Sleep(5 * time.Millisecond)
	cancel()
	wg.Wait()
	if !errors.Is(gotErr, context.Canceled) {
		t.Errorf("queued err = %v, want context.Canceled", gotErr)
	}
}
