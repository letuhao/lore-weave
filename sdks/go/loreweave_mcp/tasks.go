// ext-tasks durable-gate CORE — Go mirror of sdks/python/loreweave_mcp/tasks.py (T3).
//
// The transport-free heart of the MCP-Tasks durable human gate for the Go domain
// services (glossary, book), so they gate high-impact writes the SAME way the Python
// domains do (spec docs/specs/2026-07-19-mcp-tasks-durable-gate.md). A confirm gate
// starts at input_required; ProvideInput(accept) runs the bound executor (the real
// domain write) → completed with its result; decline → cancelled; executor error →
// failed; TTL lapse → failed (token_expired analogue) surfaced on the next Get.
//
// In-memory reference store (single-process; a persistent store bound to the domain's
// confirm/consumed-token layer implements the same TaskStore for multi-replica — the
// T3 hardening). Concurrency: a per-task resolving flag makes ProvideInput single-
// winner, so two concurrent accepts can't both run the executor (the double-commit
// race chat_suspended_runs guards); the executor runs OUTSIDE the lock.
package loreweave_mcp

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
)

// TaskStatus wire values (ext-tasks).
type TaskStatus = string

const (
	TaskWorking       TaskStatus = "working"
	TaskInputRequired TaskStatus = "input_required"
	TaskCompleted     TaskStatus = "completed"
	TaskFailed        TaskStatus = "failed"
	TaskCancelled     TaskStatus = "cancelled"
)

// IsTaskTerminal reports whether a status is terminal (never changes after).
func IsTaskTerminal(s TaskStatus) bool {
	return s == TaskCompleted || s == TaskFailed || s == TaskCancelled
}

const (
	DefaultPollIntervalMs = 1000
	DefaultTaskTTLMs      = 600000 // 10 min — mirrors the confirm-token default TTL.
)

var (
	// ErrTaskNotFound — no task with that id (never minted, or swept after terminal TTL).
	ErrTaskNotFound = errors.New("task not found")
	// ErrTaskNotWaiting — ProvideInput/Cancel on a task already terminal or resolving
	// (idempotency + double-confirm guard: a second accept must not re-run the executor).
	ErrTaskNotWaiting = errors.New("task is not awaiting input")
)

// TaskExecutor runs the real domain write on accept; its return becomes the task
// Result (what the original tools/call would have returned). inputs carries the
// human's response payload.
type TaskExecutor func(ctx context.Context, inputs map[string]any) (any, error)

// Task is one durable gate task.
type Task struct {
	TaskID         string
	Status         TaskStatus
	Descriptor     string // the action descriptor, e.g. "composition.derive"
	InputRequests  any    // the rich card payload (title/preview) the client renders
	Result         any    // set on completed
	ErrorMsg       string // set on failed
	CreatedAt      time.Time
	UpdatedAt      time.Time
	TTLMs          int
	PollIntervalMs int
	executor       TaskExecutor // never serialized to the client
}

// Expired reports whether the task is past its TTL as of now.
func (t *Task) Expired(now time.Time) bool {
	return now.Sub(t.CreatedAt).Milliseconds() >= int64(t.TTLMs)
}

// TaskStore is the durable task-store surface (in-memory reference below; a
// persistent impl bound to confirm/consumed-token storage implements the same API).
type TaskStore interface {
	Create(descriptor string, executor TaskExecutor, inputRequests any, ttlMs int) (*Task, error)
	Get(taskID string, now time.Time) (*Task, error)
	ProvideInput(ctx context.Context, taskID string, inputs map[string]any) (*Task, error)
	Cancel(taskID string) (*Task, error)
}

// InMemoryTaskStore is the reference + test-double store.
type InMemoryTaskStore struct {
	mu        sync.Mutex
	tasks     map[string]*Task
	resolving map[string]bool
}

// NewInMemoryTaskStore constructs an empty in-memory store.
func NewInMemoryTaskStore() *InMemoryTaskStore {
	return &InMemoryTaskStore{tasks: map[string]*Task{}, resolving: map[string]bool{}}
}

func (s *InMemoryTaskStore) Create(descriptor string, executor TaskExecutor, inputRequests any, ttlMs int) (*Task, error) {
	if strings.TrimSpace(descriptor) == "" {
		return nil, fmt.Errorf("task descriptor is required")
	}
	if ttlMs <= 0 {
		ttlMs = DefaultTaskTTLMs
	}
	now := time.Now()
	t := &Task{
		TaskID:         "task_" + strings.ReplaceAll(uuid.NewString(), "-", ""),
		Status:         TaskInputRequired, // a confirm gate needs the human immediately
		Descriptor:     descriptor,
		InputRequests:  inputRequests,
		CreatedAt:      now,
		UpdatedAt:      now,
		TTLMs:          ttlMs,
		PollIntervalMs: DefaultPollIntervalMs,
		executor:       executor,
	}
	s.mu.Lock()
	s.tasks[t.TaskID] = t
	snap := snapshot(t)
	s.mu.Unlock()
	return snap, nil
}

// snapshot returns a copy of the task safe to hand to a caller: the store keeps the
// live pointer and mutates it under the lock, so returning the live pointer would let
// a caller read fields lock-free while another goroutine writes them (a data race Go —
// unlike the GIL/asyncio Python mirror — does not paper over). The executor field is
// intentionally NOT copied out (never exposed to a client). Caller holds the lock.
func snapshot(t *Task) *Task {
	c := *t
	c.executor = nil
	return &c
}

// lapseIfExpired flips a non-terminal, past-TTL task to failed. Caller holds the lock.
func lapseIfExpired(t *Task, now time.Time) {
	if !IsTaskTerminal(t.Status) && t.Expired(now) {
		t.Status = TaskFailed
		t.ErrorMsg = "task_expired"
		t.UpdatedAt = now
	}
}

func (s *InMemoryTaskStore) Get(taskID string, now time.Time) (*Task, error) {
	if now.IsZero() {
		now = time.Now()
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	t, ok := s.tasks[taskID]
	if !ok {
		return nil, ErrTaskNotFound
	}
	lapseIfExpired(t, now)
	return snapshot(t), nil
}

func (s *InMemoryTaskStore) ProvideInput(ctx context.Context, taskID string, inputs map[string]any) (*Task, error) {
	s.mu.Lock()
	t, ok := s.tasks[taskID]
	if !ok {
		s.mu.Unlock()
		return nil, ErrTaskNotFound
	}
	lapseIfExpired(t, time.Now())
	if IsTaskTerminal(t.Status) {
		s.mu.Unlock()
		return nil, ErrTaskNotWaiting
	}
	if s.resolving[taskID] {
		s.mu.Unlock()
		return nil, ErrTaskNotWaiting
	}
	// A decline short-circuits to cancelled without running the executor.
	if inputs != nil {
		if act, _ := inputs["action"].(string); act == "decline" {
			t.Status = TaskCancelled
			t.UpdatedAt = time.Now()
			snap := snapshot(t)
			s.mu.Unlock()
			return snap, nil
		}
		if acc, present := inputs["accepted"].(bool); present && !acc {
			t.Status = TaskCancelled
			t.UpdatedAt = time.Now()
			snap := snapshot(t)
			s.mu.Unlock()
			return snap, nil
		}
	}
	s.resolving[taskID] = true
	t.Status = TaskWorking
	t.UpdatedAt = time.Now()
	exec := t.executor
	s.mu.Unlock()

	// Run the executor OUTSIDE the lock (a real write may be slow / block).
	var result any
	var err error
	if exec != nil {
		result, err = exec(ctx, inputs)
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	delete(s.resolving, taskID)
	if err != nil {
		t.Status = TaskFailed
		t.ErrorMsg = err.Error()
	} else {
		t.Result = result
		t.Status = TaskCompleted
	}
	t.UpdatedAt = time.Now()
	return snapshot(t), nil
}

func (s *InMemoryTaskStore) Cancel(taskID string) (*Task, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	t, ok := s.tasks[taskID]
	if !ok {
		return nil, ErrTaskNotFound
	}
	if IsTaskTerminal(t.Status) {
		return snapshot(t), nil // idempotent on a terminal task (cooperative)
	}
	t.Status = TaskCancelled
	t.UpdatedAt = time.Now()
	return snapshot(t), nil
}
