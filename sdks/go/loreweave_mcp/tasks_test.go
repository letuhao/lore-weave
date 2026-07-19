package loreweave_mcp

import (
	"context"
	"errors"
	"testing"
	"time"
)

func noopExec(ctx context.Context, inputs map[string]any) (any, error) {
	return map[string]any{"ok": true}, nil
}

func TestTaskCreateStartsInputRequired(t *testing.T) {
	s := NewInMemoryTaskStore()
	task, err := s.Create("composition.derive", noopExec, map[string]any{"title": "Spawn?"}, 0)
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	if task.Status != TaskInputRequired {
		t.Fatalf("status = %q, want input_required", task.Status)
	}
	if len(task.TaskID) < 5 || task.TaskID[:5] != "task_" {
		t.Fatalf("taskID = %q, want task_ prefix", task.TaskID)
	}
	got, err := s.Get(task.TaskID, time.Time{})
	if err != nil || got.Status != TaskInputRequired {
		t.Fatalf("Get after create: %v status=%q", err, got.Status)
	}
}

// A returned task is a SNAPSHOT: mutating the store afterwards must not change a
// value the caller already holds (guards the data-race fix — Get/Create/ProvideInput
// must not hand out the live, store-mutated pointer).
func TestTaskReturnIsSnapshotNotLiveAlias(t *testing.T) {
	s := NewInMemoryTaskStore()
	created, _ := s.Create("d", noopExec, nil, 0)
	if created.Status != TaskInputRequired {
		t.Fatalf("created status = %q", created.Status)
	}
	// Resolve the task in the store; the earlier `created` handle must stay put.
	if _, err := s.ProvideInput(context.Background(), created.TaskID, map[string]any{"accepted": true}); err != nil {
		t.Fatalf("ProvideInput: %v", err)
	}
	if created.Status != TaskInputRequired {
		t.Fatalf("earlier snapshot mutated by later store write: status = %q, want input_required", created.Status)
	}
	// A fresh Get reflects the new terminal state (proving it wasn't just a stale read).
	got, _ := s.Get(created.TaskID, time.Time{})
	if got.Status != TaskCompleted {
		t.Fatalf("fresh Get status = %q, want completed", got.Status)
	}
	// And the executor is never leaked out to a caller.
	if got.executor != nil {
		t.Fatal("returned snapshot leaks the bound executor")
	}
}

func TestTaskCreateRequiresDescriptor(t *testing.T) {
	s := NewInMemoryTaskStore()
	if _, err := s.Create("  ", noopExec, nil, 0); err == nil {
		t.Fatal("expected error for empty descriptor")
	}
}

func TestTaskGetUnknown(t *testing.T) {
	s := NewInMemoryTaskStore()
	if _, err := s.Get("task_nope", time.Time{}); !errors.Is(err, ErrTaskNotFound) {
		t.Fatalf("err = %v, want ErrTaskNotFound", err)
	}
}

func TestTaskAcceptRunsExecutorAndCompletes(t *testing.T) {
	s := NewInMemoryTaskStore()
	var ran map[string]any
	exec := func(ctx context.Context, inputs map[string]any) (any, error) {
		ran = inputs
		return map[string]any{"deleted": true}, nil
	}
	task, _ := s.Create("d", exec, nil, 0)
	done, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": true, "note": "go"})
	if err != nil {
		t.Fatalf("ProvideInput: %v", err)
	}
	if done.Status != TaskCompleted {
		t.Fatalf("status = %q, want completed", done.Status)
	}
	res, _ := done.Result.(map[string]any)
	if res["deleted"] != true {
		t.Fatalf("result = %v", done.Result)
	}
	if ran["note"] != "go" {
		t.Fatalf("inputs not threaded: %v", ran)
	}
}

func TestTaskDeclineCancelsWithoutExecutor(t *testing.T) {
	s := NewInMemoryTaskStore()
	ranCount := 0
	exec := func(ctx context.Context, inputs map[string]any) (any, error) { ranCount++; return nil, nil }
	task, _ := s.Create("d", exec, nil, 0)
	res, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": false})
	if err != nil || res.Status != TaskCancelled {
		t.Fatalf("decline: err=%v status=%q", err, res.Status)
	}
	if ranCount != 0 {
		t.Fatalf("executor ran %d times on decline, want 0", ranCount)
	}
}

func TestTaskExecutorErrorMarksFailed(t *testing.T) {
	s := NewInMemoryTaskStore()
	exec := func(ctx context.Context, inputs map[string]any) (any, error) {
		return nil, errors.New("write conflict 409")
	}
	task, _ := s.Create("d", exec, nil, 0)
	res, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": true})
	if err != nil {
		t.Fatalf("ProvideInput returned err: %v", err)
	}
	if res.Status != TaskFailed || res.ErrorMsg == "" {
		t.Fatalf("status=%q err=%q, want failed with message", res.Status, res.ErrorMsg)
	}
}

func TestTaskDoubleConfirmBlocked(t *testing.T) {
	s := NewInMemoryTaskStore()
	calls := 0
	exec := func(ctx context.Context, inputs map[string]any) (any, error) { calls++; return calls, nil }
	task, _ := s.Create("d", exec, nil, 0)
	if _, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": true}); err != nil {
		t.Fatalf("first accept: %v", err)
	}
	if _, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": true}); !errors.Is(err, ErrTaskNotWaiting) {
		t.Fatalf("second accept err = %v, want ErrTaskNotWaiting", err)
	}
	if calls != 1 {
		t.Fatalf("executor ran %d times, want exactly 1", calls)
	}
}

func TestTaskCancelIdempotentThenReject(t *testing.T) {
	s := NewInMemoryTaskStore()
	task, _ := s.Create("d", noopExec, nil, 0)
	c, _ := s.Cancel(task.TaskID)
	if c.Status != TaskCancelled {
		t.Fatalf("cancel status = %q", c.Status)
	}
	c2, err := s.Cancel(task.TaskID)
	if err != nil || c2.Status != TaskCancelled {
		t.Fatalf("second cancel: %v status=%q", err, c2.Status)
	}
	if _, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": true}); !errors.Is(err, ErrTaskNotWaiting) {
		t.Fatalf("accept after cancel err = %v, want ErrTaskNotWaiting", err)
	}
}

func TestTaskTTLExpiryLapsesToFailed(t *testing.T) {
	s := NewInMemoryTaskStore()
	task, _ := s.Create("d", noopExec, nil, 10) // 10ms TTL
	future := task.CreatedAt.Add(100 * time.Second)
	got, _ := s.Get(task.TaskID, future)
	if got.Status != TaskFailed || got.ErrorMsg != "task_expired" {
		t.Fatalf("status=%q err=%q, want failed/task_expired", got.Status, got.ErrorMsg)
	}
	if _, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": true}); !errors.Is(err, ErrTaskNotWaiting) {
		t.Fatalf("accept after expiry err = %v, want ErrTaskNotWaiting", err)
	}
}

func TestTaskCompletedNotExpiredByTTL(t *testing.T) {
	s := NewInMemoryTaskStore()
	task, _ := s.Create("d", noopExec, nil, 10)
	if _, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": true}); err != nil {
		t.Fatalf("accept: %v", err)
	}
	got, _ := s.Get(task.TaskID, task.CreatedAt.Add(100*time.Second))
	if got.Status != TaskCompleted {
		t.Fatalf("terminal task re-lapsed: status = %q", got.Status)
	}
}
