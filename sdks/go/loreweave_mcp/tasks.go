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

// TaskResolver runs the real domain write on accept, RECONSTRUCTED on any replica
// from persisted data (NOT a closure over per-request state). It is registered once
// per descriptor at startup and receives the durable inputs: the proposing user
// (ownerUserID — for the caller re-bind / grant re-check), the serializable payload
// captured at propose-time, and the human's response (inputs). Its return becomes the
// task Result. This shape is what makes a DB-backed store possible — the persistent
// store stores {descriptor, ownerUserID, payload} and looks the resolver up by
// descriptor, so the same store interface serves single-process and multi-replica.
type TaskResolver func(ctx context.Context, ownerUserID string, payload map[string]any, inputs map[string]any) (any, error)

// TaskResolverRegistry maps an action descriptor → its resolver. A domain builds one
// at startup and hands it to the store constructor; the store never holds a closure.
type TaskResolverRegistry map[string]TaskResolver

// Task is one durable gate task. Every field is serializable (no bound function) so a
// persistent store can round-trip it and any replica can resolve it.
type Task struct {
	TaskID         string
	Status         TaskStatus
	Descriptor     string         // the action descriptor, e.g. "composition.derive" — also the resolver key
	OwnerUserID    string         // the proposing user (tenancy scope key; passed to the resolver)
	Payload        map[string]any // the serializable action data captured at propose-time
	InputRequests  any            // the rich card payload (title/preview) the client renders
	Result         any            // set on completed
	ErrorMsg       string         // set on failed
	CreatedAt      time.Time
	UpdatedAt      time.Time
	TTLMs          int
	PollIntervalMs int
}

// Expired reports whether the task is past its TTL as of now.
func (t *Task) Expired(now time.Time) bool {
	return now.Sub(t.CreatedAt).Milliseconds() >= int64(t.TTLMs)
}

// TaskStore is the durable task-store surface (in-memory reference below; a
// persistent impl bound to confirm/consumed-token storage implements the same API).
// Both are constructed with a TaskResolverRegistry — the store never holds a closure,
// so the SAME interface serves single-process and multi-replica.
type TaskStore interface {
	Create(descriptor, ownerUserID string, payload map[string]any, inputRequests any, ttlMs int) (*Task, error)
	Get(taskID string, now time.Time) (*Task, error)
	ProvideInput(ctx context.Context, taskID string, inputs map[string]any) (*Task, error)
	Cancel(taskID string) (*Task, error)
}

// InMemoryTaskStore is the reference + test-double store.
type InMemoryTaskStore struct {
	mu        sync.Mutex
	tasks     map[string]*Task
	resolving map[string]bool
	resolvers TaskResolverRegistry
}

// NewInMemoryTaskStore constructs an empty in-memory store bound to the given resolver
// registry (descriptor → the write to run on accept). A nil registry is allowed (a
// task whose descriptor has no resolver fails on accept with a clear error).
func NewInMemoryTaskStore(resolvers TaskResolverRegistry) *InMemoryTaskStore {
	if resolvers == nil {
		resolvers = TaskResolverRegistry{}
	}
	return &InMemoryTaskStore{tasks: map[string]*Task{}, resolving: map[string]bool{}, resolvers: resolvers}
}

func (s *InMemoryTaskStore) Create(descriptor, ownerUserID string, payload map[string]any, inputRequests any, ttlMs int) (*Task, error) {
	if strings.TrimSpace(descriptor) == "" {
		return nil, fmt.Errorf("task descriptor is required")
	}
	if ttlMs <= 0 {
		ttlMs = DefaultTaskTTLMs
	}
	now := time.Now()
	// Defensively copy the payload (parity with the Python store's dict(payload)) so a
	// caller mutating its map after Create can't alter the durable task.
	pcopy := make(map[string]any, len(payload))
	for k, v := range payload {
		pcopy[k] = v
	}
	t := &Task{
		TaskID:         "task_" + strings.ReplaceAll(uuid.NewString(), "-", ""),
		Status:         TaskInputRequired, // a confirm gate needs the human immediately
		Descriptor:     descriptor,
		OwnerUserID:    ownerUserID,
		Payload:        pcopy,
		InputRequests:  inputRequests,
		CreatedAt:      now,
		UpdatedAt:      now,
		TTLMs:          ttlMs,
		PollIntervalMs: DefaultPollIntervalMs,
	}
	s.mu.Lock()
	s.tasks[t.TaskID] = t
	snap := snapshot(t)
	s.mu.Unlock()
	return snap, nil
}

// snapshot returns a copy of the task safe to hand to a caller: the store keeps the
// live pointer and mutates it under the lock, so returning the live pointer would let
// a caller read the scalar status fields lock-free while another goroutine writes them
// (a data race Go — unlike the GIL/asyncio Python mirror — does not paper over). Payload
// is write-once at Create (never mutated after), so sharing its map reference is safe.
// Caller holds the lock.
func snapshot(t *Task) *Task {
	c := *t
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
	descriptor := t.Descriptor
	ownerUserID := t.OwnerUserID
	payload := t.Payload
	resolver := s.resolvers[descriptor]
	s.mu.Unlock()

	// Run the resolver OUTSIDE the lock (a real write may be slow / block). The
	// resolver is looked up by descriptor from the startup registry — reconstructed
	// on any replica from the persisted {descriptor, ownerUserID, payload}, not a
	// closure. A missing resolver is a wiring bug → fail the task with a clear error.
	var result any
	var err error
	if resolver == nil {
		err = fmt.Errorf("no resolver registered for descriptor %q", descriptor)
	} else {
		result, err = resolver(ctx, ownerUserID, payload, inputs)
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
