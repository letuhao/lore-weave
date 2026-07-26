package loreweave_mcp

import (
	"context"
	"errors"
	"testing"
	"time"
)

// noopResolver is the default test resolver (registered per-descriptor via storeWith).
func noopResolver(ctx context.Context, ownerUserID string, payload, inputs map[string]any) (any, error) {
	return map[string]any{"ok": true}, nil
}

// storeWith builds an in-memory store whose registry runs `fn` for the descriptors the
// tests use ("d" and "composition.derive"). The resolver-registry replaces the old
// per-Create closure: the store persists only {descriptor, owner, payload}, and looks
// the write up by descriptor on accept.
func storeWith(fn TaskResolver) *InMemoryTaskStore {
	return NewInMemoryTaskStore(TaskResolverRegistry{"d": fn, "composition.derive": fn})
}

func TestTaskCreateStartsInputRequired(t *testing.T) {
	s := storeWith(noopResolver)
	task, err := s.Create("composition.derive", "u1", map[string]any{"name": "dị bản"}, map[string]any{"title": "Spawn?"}, 0)
	if err != nil {
		t.Fatalf("Create: %v", err)
	}
	if task.Status != TaskInputRequired {
		t.Fatalf("status = %q, want input_required", task.Status)
	}
	if len(task.TaskID) < 5 || task.TaskID[:5] != "task_" {
		t.Fatalf("taskID = %q, want task_ prefix", task.TaskID)
	}
	if task.OwnerUserID != "u1" || task.Payload["name"] != "dị bản" {
		t.Fatalf("owner/payload not stored: owner=%q payload=%v", task.OwnerUserID, task.Payload)
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
	s := storeWith(noopResolver)
	created, _ := s.Create("d", "u1", nil, nil, 0)
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
}

func TestTaskCreateRequiresDescriptor(t *testing.T) {
	s := storeWith(noopResolver)
	if _, err := s.Create("  ", "u1", nil, nil, 0); err == nil {
		t.Fatal("expected error for empty descriptor")
	}
}

func TestTaskGetUnknown(t *testing.T) {
	s := storeWith(noopResolver)
	if _, err := s.Get("task_nope", time.Time{}); !errors.Is(err, ErrTaskNotFound) {
		t.Fatalf("err = %v, want ErrTaskNotFound", err)
	}
}

func TestTaskAcceptRunsResolverAndCompletes(t *testing.T) {
	var gotOwner string
	var gotPayload, gotInputs map[string]any
	resolver := func(ctx context.Context, ownerUserID string, payload, inputs map[string]any) (any, error) {
		gotOwner, gotPayload, gotInputs = ownerUserID, payload, inputs
		return map[string]any{"deleted": true}, nil
	}
	s := storeWith(resolver)
	task, _ := s.Create("d", "u9", map[string]any{"chapter_id": "ch1"}, nil, 0)
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
	// The resolver received the durable {owner, payload} + the human's inputs — not a closure.
	if gotOwner != "u9" || gotPayload["chapter_id"] != "ch1" || gotInputs["note"] != "go" {
		t.Fatalf("resolver args wrong: owner=%q payload=%v inputs=%v", gotOwner, gotPayload, gotInputs)
	}
}

// A descriptor with NO registered resolver is a wiring bug → the accept fails the task
// with a clear error (never a silent no-op).
func TestTaskAcceptWithNoResolverFails(t *testing.T) {
	s := NewInMemoryTaskStore(nil) // empty registry
	task, _ := s.Create("d", "u1", nil, nil, 0)
	done, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": true})
	if err != nil {
		t.Fatalf("ProvideInput returned err: %v", err)
	}
	if done.Status != TaskFailed || done.ErrorMsg == "" {
		t.Fatalf("status=%q err=%q, want failed with a 'no resolver' message", done.Status, done.ErrorMsg)
	}
}

func TestTaskDeclineCancelsWithoutResolver(t *testing.T) {
	ranCount := 0
	resolver := func(ctx context.Context, ownerUserID string, payload, inputs map[string]any) (any, error) { ranCount++; return nil, nil }
	s := storeWith(resolver)
	task, _ := s.Create("d", "u1", nil, nil, 0)
	res, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": false})
	if err != nil || res.Status != TaskCancelled {
		t.Fatalf("decline: err=%v status=%q", err, res.Status)
	}
	if ranCount != 0 {
		t.Fatalf("resolver ran %d times on decline, want 0", ranCount)
	}
}

func TestTaskResolverErrorMarksFailed(t *testing.T) {
	resolver := func(ctx context.Context, ownerUserID string, payload, inputs map[string]any) (any, error) {
		return nil, errors.New("write conflict 409")
	}
	s := storeWith(resolver)
	task, _ := s.Create("d", "u1", nil, nil, 0)
	res, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": true})
	if err != nil {
		t.Fatalf("ProvideInput returned err: %v", err)
	}
	if res.Status != TaskFailed || res.ErrorMsg == "" {
		t.Fatalf("status=%q err=%q, want failed with message", res.Status, res.ErrorMsg)
	}
}

func TestTaskDoubleConfirmBlocked(t *testing.T) {
	calls := 0
	resolver := func(ctx context.Context, ownerUserID string, payload, inputs map[string]any) (any, error) { calls++; return calls, nil }
	s := storeWith(resolver)
	task, _ := s.Create("d", "u1", nil, nil, 0)
	if _, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": true}); err != nil {
		t.Fatalf("first accept: %v", err)
	}
	if _, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": true}); !errors.Is(err, ErrTaskNotWaiting) {
		t.Fatalf("second accept err = %v, want ErrTaskNotWaiting", err)
	}
	if calls != 1 {
		t.Fatalf("resolver ran %d times, want exactly 1", calls)
	}
}

func TestTaskCancelIdempotentThenReject(t *testing.T) {
	s := storeWith(noopResolver)
	task, _ := s.Create("d", "u1", nil, nil, 0)
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
	s := storeWith(noopResolver)
	task, _ := s.Create("d", "u1", nil, nil, 10) // 10ms TTL
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
	s := storeWith(noopResolver)
	task, _ := s.Create("d", "u1", nil, nil, 10)
	if _, err := s.ProvideInput(context.Background(), task.TaskID, map[string]any{"accepted": true}); err != nil {
		t.Fatalf("accept: %v", err)
	}
	got, _ := s.Get(task.TaskID, task.CreatedAt.Add(100*time.Second))
	if got.Status != TaskCompleted {
		t.Fatalf("terminal task re-lapsed: status = %q", got.Status)
	}
}
